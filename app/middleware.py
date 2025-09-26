"""
Middleware for chfs-py
"""

import asyncio
import logging
import time
from typing import Callable, Optional
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .models import ApiResponse, ResponseCode, TokenBucket
from .config import get_config
from .ipfilter import get_client_ip, check_ip_allowed
from .auth import get_current_user_optional, get_auth_context
from .metrics import metrics_manager
from .utils import format_duration

logger = logging.getLogger(__name__)


class AccessLogMiddleware(BaseHTTPMiddleware):
    """Access logging middleware"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()
        
        # Get client info
        client_ip = get_client_ip(request)
        auth_context = get_auth_context(request)
        
        try:
            response = await call_next(request)
            
            # Log access
            duration = time.time() - start_time
            self._log_access(
                request=request,
                response=response,
                duration=duration,
                client_ip=client_ip,
                user=auth_context.get("user")
            )
            
            # Record metrics
            metrics_manager.record_response(response.status_code, duration)
            
            return response
            
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Request failed: {request.method} {request.url.path} - {e}")
            
            # Log failed request
            self._log_access(
                request=request,
                response=None,
                duration=duration,
                client_ip=client_ip,
                user=auth_context.get("user"),
                error=str(e)
            )
            
            metrics_manager.increment_errors()
            raise
    
    def _log_access(
        self,
        request: Request,
        response: Optional[Response],
        duration: float,
        client_ip: str,
        user: Optional[str],
        error: Optional[str] = None
    ):
        """Log access information"""
        
        status_code = response.status_code if response else 500
        content_length = response.headers.get("content-length", "-") if response else "-"
        user_agent = request.headers.get("user-agent", "-")
        
        # JSON format log
        log_data = {
            "method": request.method,
            "path": str(request.url.path),
            "query": str(request.url.query) if request.url.query else "",
            "status": status_code,
            "size": content_length,
            "duration": round(duration * 1000, 2),  # milliseconds
            "ip": client_ip,
            "user": user or "-",
            "user_agent": user_agent,
        }
        
        if error:
            log_data["error"] = error
        
        # Log level based on status code
        if status_code >= 500:
            logger.error(f"ACCESS {log_data}")
        elif status_code >= 400:
            logger.warning(f"ACCESS {log_data}")
        else:
            logger.info(f"ACCESS {log_data}")


class ExceptionHandlerMiddleware(BaseHTTPMiddleware):
    """Global exception handler middleware"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        try:
            return await call_next(request)
            
        except HTTPException:
            # Let FastAPI handle HTTP exceptions
            raise
            
        except Exception as e:
            logger.exception(f"Unhandled exception: {e}")
            metrics_manager.increment_errors()
            
            # Return standardized error response
            error_response = ApiResponse(
                code=ResponseCode.INTERNAL_ERROR.value,
                msg=f"Internal server error: {str(e)}",
                data=None
            )
            
            return JSONResponse(
                status_code=500,
                content=error_response.to_dict()
            )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware using token bucket algorithm"""
    
    def __init__(self, app: FastAPI, rps: int = 50, burst: int = 100):
        super().__init__(app)
        self.token_bucket = TokenBucket(
            capacity=burst,
            tokens=float(burst),
            last_refill=time.time(),
            refill_rate=float(rps)
        )
        self.rps = rps
        self.burst = burst
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Check if request is rate limited
        if not self.token_bucket.consume(1):
            metrics_manager.increment_rate_limit_hits()
            
            error_response = ApiResponse(
                code=ResponseCode.RATE_LIMITED.value,
                msg="Rate limit exceeded",
                data={
                    "limit": self.rps,
                    "burst": self.burst,
                    "retry_after": 1
                }
            )
            
            return JSONResponse(
                status_code=429,
                content=error_response.to_dict(),
                headers={"Retry-After": "1"}
            )
        
        return await call_next(request)
    
    def update_limits(self, rps: int, burst: int):
        """Update rate limits"""
        self.rps = rps
        self.burst = burst
        self.token_bucket.capacity = burst
        self.token_bucket.refill_rate = float(rps)


class ConcurrencyLimitMiddleware(BaseHTTPMiddleware):
    """Concurrency limiting middleware"""
    
    def __init__(self, app: FastAPI, max_concurrent: int = 32):
        super().__init__(app)
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.max_concurrent = max_concurrent
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        try:
            # Try short wait for an available slot to reduce false 429s
            try:
                await asyncio.wait_for(self.semaphore.acquire(), timeout=0.1)
                acquired = True
            except asyncio.TimeoutError:
                acquired = False

            if not acquired:
                error_response = ApiResponse(
                    code=ResponseCode.RATE_LIMITED.value,
                    msg="Too many concurrent requests",
                    data={"max_concurrent": self.max_concurrent}
                )
                return JSONResponse(
                    status_code=429,
                    content=error_response.to_dict(),
                    headers={"Retry-After": "1"}
                )
            
            # Track active requests
            metrics_manager.increment_active_requests()
            
            try:
                return await call_next(request)
            finally:
                metrics_manager.decrement_active_requests()
                # Release only if held
                if getattr(self, "semaphore", None):
                    self.semaphore.release()
                
        except Exception:
            metrics_manager.decrement_active_requests()
            if getattr(self, "semaphore", None):
                # Best-effort release in case of error
                try:
                    self.semaphore.release()
                except Exception:
                    pass
            raise
    
    def update_limit(self, max_concurrent: int):
        """Update concurrency limit"""
        self.max_concurrent = max_concurrent
        # Create new semaphore (can't resize existing one)
        self.semaphore = asyncio.Semaphore(max_concurrent)


class IpFilterMiddleware(BaseHTTPMiddleware):
    """IP filtering middleware"""
    
    def __init__(self, app: FastAPI, allow_list: list = None, deny_list: list = None):
        super().__init__(app)
        self.allow_list = allow_list or []
        self.deny_list = deny_list or []
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        client_ip = get_client_ip(request)
        
        # Check IP whitelist for certain endpoints
        if self._is_whitelisted_endpoint(request):
            return await call_next(request)
        
        # Check IP filter
        if not check_ip_allowed(client_ip, self.allow_list, self.deny_list):
            logger.warning(f"IP blocked: {client_ip} -> {request.url.path}")
            
            error_response = ApiResponse(
                code=ResponseCode.FORBIDDEN.value,
                msg="Access denied from your IP address",
                data=None
            )
            
            return JSONResponse(
                status_code=403,
                content=error_response.to_dict()
            )
        
        return await call_next(request)
    
    def _is_whitelisted_endpoint(self, request: Request) -> bool:
        """Check if endpoint is whitelisted (bypass IP filter)"""
        path = request.url.path
        method = request.method
        
        # Whitelist certain endpoints
        whitelist = [
            ("GET", "/healthz"),
            ("GET", "/metrics"),
            ("GET", "/"),
            ("GET", "/t/"),  # Text sharing (prefix)
        ]
        
        for wl_method, wl_path in whitelist:
            if method == wl_method:
                if wl_path.endswith("/") and path.startswith(wl_path):
                    return True
                elif path == wl_path:
                    return True
        
        return False
    
    def update_rules(self, allow_list: list = None, deny_list: list = None):
        """Update IP filter rules"""
        if allow_list is not None:
            self.allow_list = allow_list
        if deny_list is not None:
            self.deny_list = deny_list


class RequestMetricsMiddleware(BaseHTTPMiddleware):
    """Request metrics collection middleware"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Record request
        metrics_manager.increment_requests(request.method)
        
        with metrics_manager.request_context(request.method):
            return await call_next(request)


def setup_middleware(app: FastAPI):
    """Setup all middleware for the application"""
    
    config = get_config()
    
    # Request metrics (first)
    app.add_middleware(RequestMetricsMiddleware)
    
    # Access logging
    app.add_middleware(AccessLogMiddleware)
    
    # Exception handling
    app.add_middleware(ExceptionHandlerMiddleware)
    
    # IP filtering
    app.add_middleware(
        IpFilterMiddleware,
        allow_list=config.ipFilter.allow,
        deny_list=config.ipFilter.deny
    )
    
    # Rate limiting
    app.add_middleware(
        RateLimitMiddleware,
        rps=config.rateLimit.rps,
        burst=config.rateLimit.burst
    )
    
    # Concurrency limiting
    app.add_middleware(
        ConcurrencyLimitMiddleware,
        max_concurrent=config.rateLimit.maxConcurrent
    )
    
    logger.info("Middleware setup complete")


async def update_middleware_config(old_config, new_config):
    """Update middleware configuration on config reload"""
    
    # This is a simplified approach - in a real implementation,
    # you might need to store middleware references to update them
    logger.info("Middleware configuration updated (restart may be required for full effect)")
    
    # For now, just log the changes
    if old_config.rateLimit.rps != new_config.rateLimit.rps:
        logger.info(f"Rate limit changed: {old_config.rateLimit.rps} -> {new_config.rateLimit.rps} RPS")
    
    if old_config.rateLimit.maxConcurrent != new_config.rateLimit.maxConcurrent:
        logger.info(f"Concurrency limit changed: {old_config.rateLimit.maxConcurrent} -> {new_config.rateLimit.maxConcurrent}")
    
    if old_config.ipFilter.allow != new_config.ipFilter.allow:
        logger.info("IP allow list updated")
    
    if old_config.ipFilter.deny != new_config.ipFilter.deny:
        logger.info("IP deny list updated")
