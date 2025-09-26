"""
Configuration loading and management for chfs-py
"""

import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import asyncio
import time

from .models import (
    Config, ServerConfig, ShareInfo, UserInfo, RuleInfo, Permission,
    TlsConfig, LoggingConfig, RateLimitConfig, IpFilterConfig,
    UiConfig, DavConfig, HotReloadConfig
)

logger = logging.getLogger(__name__)


class ConfigFileHandler(FileSystemEventHandler):
    """File system event handler for config file changes"""
    
    def __init__(self, config_path: Path, callback):
        self.config_path = config_path.resolve()
        self.callback = callback
        self.last_modified = 0
        self.debounce_ms = 1000
    
    def on_modified(self, event):
        if event.is_directory:
            return
        
        file_path = Path(event.src_path).resolve()
        if file_path == self.config_path:
            # Debounce multiple events
            now = time.time() * 1000
            if now - self.last_modified < self.debounce_ms:
                return
            self.last_modified = now
            
            logger.info(f"Configuration file changed: {file_path}")
            try:
                self.callback()
            except Exception as e:
                logger.error(f"Failed to reload configuration: {e}")


class ConfigManager:
    """Configuration manager with hot reload support"""
    
    def __init__(self, config_path: str = "chfs.yaml"):
        self.config_path = Path(config_path).resolve()
        self.config: Optional[Config] = None
        self.observer: Optional[Observer] = None
        self.reload_callbacks = []
    
    def load_config(self) -> Config:
        """Load configuration from YAML file"""
        try:
            if not self.config_path.exists():
                logger.warning(f"Configuration file not found: {self.config_path}")
                return Config()
            
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
            
            config = self._parse_config(data)
            self.config = config
            logger.info(f"Configuration loaded from {self.config_path}")
            return config
            
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            return Config()
    
    def _parse_config(self, data: Dict[str, Any]) -> Config:
        """Parse configuration data into Config object"""
        
        # Server configuration
        server_data = data.get('server', {})
        tls_data = server_data.get('tls', {})
        server = ServerConfig(
            addr=server_data.get('addr', '0.0.0.0'),
            port=server_data.get('port', 8080),
            tls=TlsConfig(
                enabled=tls_data.get('enabled', False),
                certfile=tls_data.get('certfile', ''),
                keyfile=tls_data.get('keyfile', '')
            )
        )
        
        # Shares
        shares = []
        for share_data in data.get('shares', []):
            share = ShareInfo(
                name=share_data['name'],
                path=Path(share_data['path']).resolve()
            )
            shares.append(share)
        
        # Users
        users = []
        for user_data in data.get('users', []):
            user = UserInfo(
                name=user_data['name'],
                pass_hash=user_data['pass'],
                is_bcrypt=user_data.get('pass_bcrypt', False)
            )
            users.append(user)
        
        # Rules
        rules = []
        for rule_data in data.get('rules', []):
            rule = RuleInfo(
                who=rule_data['who'],
                allow=[Permission(p) for p in rule_data.get('allow', [])],
                roots=rule_data.get('roots', []),
                paths=rule_data.get('paths', ['/']),
                ip_allow=rule_data.get('ip_allow', ['*']),
                ip_deny=rule_data.get('ip_deny', [])
            )
            rules.append(rule)
        
        # Logging
        logging_data = data.get('logging', {})
        logging_config = LoggingConfig(
            json=logging_data.get('json', True),
            file=logging_data.get('file', ''),
            level=logging_data.get('level', 'INFO'),
            max_size_mb=logging_data.get('max_size_mb', 100),
            backup_count=logging_data.get('backup_count', 5)
        )
        
        # Rate limiting
        rate_data = data.get('rateLimit', {})
        rate_limit = RateLimitConfig(
            rps=rate_data.get('rps', 50),
            burst=rate_data.get('burst', 100),
            maxConcurrent=rate_data.get('maxConcurrent', 32)
        )
        
        # IP filtering
        ip_data = data.get('ipFilter', {})
        ip_filter = IpFilterConfig(
            allow=ip_data.get('allow', []),
            deny=ip_data.get('deny', [])
        )
        
        # UI
        ui_data = data.get('ui', {})
        ui = UiConfig(
            brand=ui_data.get('brand', 'chfs-py'),
            title=ui_data.get('title', 'chfs-py File Server'),
            textShareDir=ui_data.get('textShareDir', ''),
            maxUploadSize=ui_data.get('maxUploadSize', 104857600),
            language=ui_data.get('language', 'en')
        )
        
        # WebDAV
        dav_data = data.get('dav', {})
        dav = DavConfig(
            enabled=dav_data.get('enabled', True),
            mountPath=dav_data.get('mountPath', '/webdav'),
            lockManager=dav_data.get('lockManager', True),
            propertyManager=dav_data.get('propertyManager', True)
        )
        
        # Hot reload
        reload_data = data.get('hotReload', {})
        hot_reload = HotReloadConfig(
            enabled=reload_data.get('enabled', True),
            watchConfig=reload_data.get('watchConfig', True),
            debounceMs=reload_data.get('debounceMs', 1000)
        )
        
        return Config(
            server=server,
            shares=shares,
            users=users,
            rules=rules,
            logging=logging_config,
            rateLimit=rate_limit,
            ipFilter=ip_filter,
            ui=ui,
            dav=dav,
            hotReload=hot_reload
        )
    
    def start_watching(self):
        """Start watching configuration file for changes"""
        if not self.config or not self.config.hotReload.enabled or not self.config.hotReload.watchConfig:
            return
        
        if self.observer:
            return  # Already watching
        
        try:
            self.observer = Observer()
            handler = ConfigFileHandler(
                self.config_path,
                self._on_config_changed
            )
            handler.debounce_ms = self.config.hotReload.debounceMs
            
            watch_dir = self.config_path.parent
            self.observer.schedule(handler, str(watch_dir), recursive=False)
            self.observer.start()
            
            logger.info(f"Started watching configuration file: {self.config_path}")
            
        except Exception as e:
            logger.error(f"Failed to start configuration file watcher: {e}")
    
    def stop_watching(self):
        """Stop watching configuration file"""
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.observer = None
            logger.info("Stopped watching configuration file")
    
    def _on_config_changed(self):
        """Handle configuration file changes"""
        try:
            old_config = self.config
            new_config = self.load_config()
            
            # Notify callbacks
            for callback in self.reload_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        # Schedule async callback
                        loop = asyncio.get_event_loop()
                        loop.create_task(callback(old_config, new_config))
                    else:
                        callback(old_config, new_config)
                except Exception as e:
                    logger.error(f"Configuration reload callback failed: {e}")
            
            logger.info("Configuration reloaded successfully")
            
        except Exception as e:
            logger.error(f"Failed to reload configuration: {e}")
    
    def add_reload_callback(self, callback):
        """Add callback to be called when configuration is reloaded"""
        self.reload_callbacks.append(callback)
    
    def remove_reload_callback(self, callback):
        """Remove reload callback"""
        if callback in self.reload_callbacks:
            self.reload_callbacks.remove(callback)
    
    def get_config(self) -> Config:
        """Get current configuration"""
        if self.config is None:
            self.config = self.load_config()
        return self.config
    
    def get_share_by_name(self, name: str) -> Optional[ShareInfo]:
        """Get share by name"""
        config = self.get_config()
        for share in config.shares:
            if share.name == name:
                return share
        return None
    
    def get_user_by_name(self, name: str) -> Optional[UserInfo]:
        """Get user by name"""
        config = self.get_config()
        for user in config.users:
            if user.name == name:
                return user
        return None


# Global configuration manager instance
config_manager = ConfigManager()


def load_config(config_path: str = "chfs.yaml") -> Config:
    """Load configuration from file"""
    global config_manager
    config_manager = ConfigManager(config_path)
    return config_manager.load_config()


def get_config() -> Config:
    """Get current configuration"""
    return config_manager.get_config()


def get_share_by_name(name: str) -> Optional[ShareInfo]:
    """Get share by name"""
    return config_manager.get_share_by_name(name)


def get_user_by_name(name: str) -> Optional[UserInfo]:
    """Get user by name"""
    return config_manager.get_user_by_name(name)
