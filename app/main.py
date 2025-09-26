"""
Main application factory for chfs-py
"""

import logging
import logging.handlers
import os
import sys
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from asgiref.wsgi import WsgiToAsgi

from .config import load_config, config_manager
from .models import Config
from .middleware import setup_middleware
from .ui import setup_ui_routes
from .api import setup_api_routes
from .webdav import create_webdav_app
from .metrics import metrics_manager


logger = logging.getLogger(__name__)


def setup_logging(config: Config):
    """Setup logging configuration"""
    log_config = config.logging
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_config.level.upper(), logging.INFO))
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Create formatter
    if log_config.json:
        formatter = logging.Formatter(
            '{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}'
        )
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # File handler if configured
    if log_config.file:
        log_file = Path(log_config.file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=log_config.max_size_mb * 1024 * 1024,
            backupCount=log_config.backup_count,
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)


def create_directories(config: Config):
    """Create necessary directories"""
    try:
        # Create share directories
        for share in config.shares:
            share.path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Ensured share directory exists: {share.path}")
        
        # Create text share directory
        if config.ui.textShareDir:
            text_dir = Path(config.ui.textShareDir)
            text_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Ensured text share directory exists: {text_dir}")
        
        # Create log directory
        if config.logging.file:
            log_dir = Path(config.logging.file).parent
            log_dir.mkdir(parents=True, exist_ok=True)
            
    except Exception as e:
        logger.error(f"Failed to create directories: {e}")
        raise


def create_app(config_path: str = None) -> FastAPI:
    """Create FastAPI application"""
    
    # Load configuration
    # If not provided explicitly, fall back to env or default
    if not config_path:
        config_path = os.getenv("CHFS_CONFIG", "chfs.yaml")
    config = load_config(config_path)
    
    # Setup logging
    setup_logging(config)
    
    # Create directories
    create_directories(config)
    
    # Create FastAPI app
    app = FastAPI(
        title=config.ui.title,
        description="Lightweight file server with WebDAV support",
        version="1.0.0",
        docs_url="/docs" if os.getenv("CHFS_DEBUG") else None,
        redoc_url="/redoc" if os.getenv("CHFS_DEBUG") else None,
    )
    
    # Store config in app state
    app.state.config = config
    app.state.config_manager = config_manager
    app.state.metrics = metrics_manager
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Setup custom middleware
    setup_middleware(app)
    
    # Setup routes
    setup_ui_routes(app)
    setup_api_routes(app)
    
    # Mount WebDAV if enabled
    if config.dav.enabled:
        try:
            webdav_app = create_webdav_app(config)
            if webdav_app:
                webdav_asgi = WsgiToAsgi(webdav_app)
                app.mount(config.dav.mountPath, webdav_asgi)
                logger.info(f"WebDAV mounted at {config.dav.mountPath}")
            else:
                logger.warning("WebDAV app creation failed, WebDAV disabled")
        except Exception as e:
            logger.error(f"Failed to setup WebDAV: {e}")
            logger.warning("WebDAV functionality will be disabled")
    
    # Mount static files if directory exists
    static_dir = Path("static")
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory="static"), name="static")
    
    # Start configuration watcher (ensure manager points to same path)
    try:
        app.state.config_manager = config_manager
        config_manager.start_watching()
    except Exception:
        logger.warning("Failed to start config watcher; continuing without hot reload")
    
    # Health check endpoint
    @app.get("/healthz")
    async def health_check():
        return {"ok": True, "version": "1.0.0"}
    
    # Metrics endpoint
    @app.get("/metrics")
    async def get_metrics():
        return metrics_manager.get_metrics()
    
    # Startup event
    @app.on_event("startup")
    async def startup_event():
        logger.info(f"chfs-py starting on {config.server.addr}:{config.server.port}")
        logger.info(f"Shares: {[s.name for s in config.shares]}")
        logger.info(f"WebDAV: {'enabled' if config.dav.enabled else 'disabled'}")
        logger.info(f"TLS: {'enabled' if config.server.tls.enabled else 'disabled'}")
    
    # Shutdown event
    @app.on_event("shutdown")
    async def shutdown_event():
        config_manager.stop_watching()
        logger.info("chfs-py shutdown complete")
    
    return app


def main():
    """Main entry point for running the server"""
    import argparse
    
    parser = argparse.ArgumentParser(description="chfs-py file server")
    parser.add_argument("--config", "-c", default="chfs.yaml", help="Configuration file path")
    parser.add_argument("--host", default=None, help="Host to bind to")
    parser.add_argument("--port", type=int, default=None, help="Port to bind to")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    
    args = parser.parse_args()
    
    # Set debug environment
    if args.debug:
        os.environ["CHFS_DEBUG"] = "1"
    
    # Load config to get server settings
    config = load_config(args.config)
    
    # Override with command line args
    host = args.host or config.server.addr
    port = args.port or config.server.port
    
    # SSL context
    ssl_keyfile = None
    ssl_certfile = None
    if config.server.tls.enabled:
        ssl_keyfile = config.server.tls.keyfile
        ssl_certfile = config.server.tls.certfile
    
    # Run server
    uvicorn.run(
        "app.main:create_app",
        factory=True,
        host=host,
        port=port,
        reload=args.reload,
        ssl_keyfile=ssl_keyfile,
        ssl_certfile=ssl_certfile,
        access_log=False,  # We handle access logging ourselves
        server_header=False,
        date_header=False,
    )


if __name__ == "__main__":
    main()
