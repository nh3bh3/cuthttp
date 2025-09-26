"""
Metrics collection and reporting for chfs-py
"""

import time
import threading
from typing import Dict, Any
from contextlib import contextmanager
from dataclasses import dataclass, field


@dataclass
class Metrics:
    """Application metrics container"""
    
    # Request metrics
    total_requests: int = 0
    active_requests: int = 0
    requests_by_method: Dict[str, int] = field(default_factory=dict)
    requests_by_status: Dict[int, int] = field(default_factory=dict)
    
    # Transfer metrics
    total_upload_bytes: int = 0
    total_download_bytes: int = 0
    
    # Error metrics
    total_errors: int = 0
    auth_failures: int = 0
    rate_limit_hits: int = 0
    
    # Performance metrics
    avg_response_time: float = 0.0
    total_response_time: float = 0.0
    
    # WebDAV metrics
    webdav_requests: int = 0
    webdav_errors: int = 0
    
    # Startup time
    startup_time: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary"""
        uptime = time.time() - self.startup_time
        
        return {
            "uptime_seconds": uptime,
            "requests": {
                "total": self.total_requests,
                "active": self.active_requests,
                "by_method": self.requests_by_method.copy(),
                "by_status": self.requests_by_status.copy(),
                "avg_response_time": self.avg_response_time,
            },
            "transfer": {
                "upload_bytes": self.total_upload_bytes,
                "download_bytes": self.total_download_bytes,
            },
            "errors": {
                "total": self.total_errors,
                "auth_failures": self.auth_failures,
                "rate_limit_hits": self.rate_limit_hits,
            },
            "webdav": {
                "requests": self.webdav_requests,
                "errors": self.webdav_errors,
            }
        }


class MetricsManager:
    """Thread-safe metrics manager"""
    
    def __init__(self):
        self.metrics = Metrics()
        self._lock = threading.Lock()
    
    def increment_requests(self, method: str = "GET"):
        """Increment request counter"""
        with self._lock:
            self.metrics.total_requests += 1
            self.metrics.requests_by_method[method] = self.metrics.requests_by_method.get(method, 0) + 1
    
    def increment_active_requests(self):
        """Increment active request counter"""
        with self._lock:
            self.metrics.active_requests += 1
    
    def decrement_active_requests(self):
        """Decrement active request counter"""
        with self._lock:
            self.metrics.active_requests = max(0, self.metrics.active_requests - 1)
    
    def record_response(self, status_code: int, response_time: float):
        """Record response metrics"""
        with self._lock:
            self.metrics.requests_by_status[status_code] = self.metrics.requests_by_status.get(status_code, 0) + 1
            
            # Update average response time
            total_requests = self.metrics.total_requests
            if total_requests > 0:
                self.metrics.total_response_time += response_time
                self.metrics.avg_response_time = self.metrics.total_response_time / total_requests
    
    def add_upload_bytes(self, bytes_count: int):
        """Add to upload byte counter"""
        with self._lock:
            self.metrics.total_upload_bytes += bytes_count
    
    def add_download_bytes(self, bytes_count: int):
        """Add to download byte counter"""
        with self._lock:
            self.metrics.total_download_bytes += bytes_count
    
    def increment_errors(self):
        """Increment error counter"""
        with self._lock:
            self.metrics.total_errors += 1
    
    def increment_auth_failures(self):
        """Increment auth failure counter"""
        with self._lock:
            self.metrics.auth_failures += 1
    
    def increment_rate_limit_hits(self):
        """Increment rate limit counter"""
        with self._lock:
            self.metrics.rate_limit_hits += 1
    
    def increment_webdav_requests(self):
        """Increment WebDAV request counter"""
        with self._lock:
            self.metrics.webdav_requests += 1
    
    def increment_webdav_errors(self):
        """Increment WebDAV error counter"""
        with self._lock:
            self.metrics.webdav_errors += 1
    
    @contextmanager
    def request_context(self, method: str = "GET"):
        """Context manager for request metrics"""
        start_time = time.time()
        
        self.increment_requests(method)
        self.increment_active_requests()
        
        try:
            yield
        finally:
            self.decrement_active_requests()
            response_time = time.time() - start_time
            # Status code will be recorded separately
    
    @contextmanager
    def upload_context(self):
        """Context manager for upload metrics"""
        class UploadCounter:
            def __init__(self, manager):
                self.manager = manager
                self.bytes_count = 0
            
            def add_bytes(self, count: int):
                self.bytes_count += count
                self.manager.add_upload_bytes(count)
        
        counter = UploadCounter(self)
        try:
            yield counter
        finally:
            pass  # Bytes already counted in add_bytes
    
    @contextmanager
    def download_context(self):
        """Context manager for download metrics"""
        class DownloadCounter:
            def __init__(self, manager):
                self.manager = manager
                self.bytes_count = 0
            
            def add_bytes(self, count: int):
                self.bytes_count += count
                self.manager.add_download_bytes(count)
        
        counter = DownloadCounter(self)
        try:
            yield counter
        finally:
            pass  # Bytes already counted in add_bytes
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics snapshot"""
        with self._lock:
            return self.metrics.to_dict()
    
    def reset_metrics(self):
        """Reset all metrics (for testing)"""
        with self._lock:
            self.metrics = Metrics()


# Global metrics manager instance
metrics_manager = MetricsManager()


def get_metrics() -> Dict[str, Any]:
    """Get current metrics (global function)"""
    return metrics_manager.get_metrics()


def increment_requests(method: str = "GET"):
    """Increment request counter (global function)"""
    metrics_manager.increment_requests(method)


def record_response(status_code: int, response_time: float):
    """Record response metrics (global function)"""
    metrics_manager.record_response(status_code, response_time)


def add_upload_bytes(bytes_count: int):
    """Add upload bytes (global function)"""
    metrics_manager.add_upload_bytes(bytes_count)


def add_download_bytes(bytes_count: int):
    """Add download bytes (global function)"""
    metrics_manager.add_download_bytes(bytes_count)


def increment_errors():
    """Increment error counter (global function)"""
    metrics_manager.increment_errors()


def increment_auth_failures():
    """Increment auth failure counter (global function)"""
    metrics_manager.increment_auth_failures()


def increment_rate_limit_hits():
    """Increment rate limit hits (global function)"""
    metrics_manager.increment_rate_limit_hits()


@contextmanager
def request_context(method: str = "GET"):
    """Request context manager (global function)"""
    with metrics_manager.request_context(method):
        yield


@contextmanager
def upload_context():
    """Upload context manager (global function)"""
    with metrics_manager.upload_context() as counter:
        yield counter


@contextmanager
def download_context():
    """Download context manager (global function)"""
    with metrics_manager.download_context() as counter:
        yield counter
