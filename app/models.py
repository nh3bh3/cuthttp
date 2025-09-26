"""
Data models and constants for chfs-py
"""

from enum import Enum
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from pathlib import Path
import time


class Permission(Enum):
    """File operation permissions"""
    READ = "R"
    WRITE = "W"
    DELETE = "D"


class ResponseCode(Enum):
    """Standard response codes"""
    SUCCESS = 0
    ERROR = 1
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    METHOD_NOT_ALLOWED = 405
    CONFLICT = 409
    PAYLOAD_TOO_LARGE = 413
    RATE_LIMITED = 429
    INTERNAL_ERROR = 500


@dataclass
class ApiResponse:
    """Standard API response format"""
    code: int = ResponseCode.SUCCESS.value
    msg: str = "success"
    data: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "msg": self.msg,
            "data": self.data
        }


@dataclass
class FileInfo:
    """File information structure"""
    name: str
    path: str
    size: int
    is_dir: bool
    modified: float
    mime_type: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "size": self.size,
            "is_dir": self.is_dir,
            "modified": self.modified,
            "mime_type": self.mime_type
        }


@dataclass
class UserInfo:
    """User information"""
    name: str
    pass_hash: str
    is_bcrypt: bool = False


@dataclass
class ShareInfo:
    """Share configuration"""

    name: str
    path: Path
    quota_bytes: Optional[int] = None

    def __post_init__(self):
        if isinstance(self.path, str):
            self.path = Path(self.path).resolve()

        if self.quota_bytes is not None and self.quota_bytes <= 0:
            # Normalise non-positive values to unlimited
            self.quota_bytes = None


@dataclass
class RuleInfo:
    """Access control rule"""
    who: str
    allow: List[Permission]
    roots: List[str]
    paths: List[str]
    ip_allow: List[str] = field(default_factory=lambda: ["*"])
    ip_deny: List[str] = field(default_factory=list)


@dataclass
class TlsConfig:
    """TLS configuration"""
    enabled: bool = False
    certfile: str = ""
    keyfile: str = ""


@dataclass
class ServerConfig:
    """Server configuration"""
    addr: str = "0.0.0.0"
    port: int = 8080
    tls: TlsConfig = field(default_factory=TlsConfig)


@dataclass
class LoggingConfig:
    """Logging configuration"""
    json: bool = True
    file: str = ""
    level: str = "INFO"
    max_size_mb: int = 100
    backup_count: int = 5


@dataclass
class RateLimitConfig:
    """Rate limiting configuration"""
    rps: int = 50
    burst: int = 100
    maxConcurrent: int = 32


@dataclass
class IpFilterConfig:
    """IP filtering configuration"""
    allow: List[str] = field(default_factory=list)
    deny: List[str] = field(default_factory=list)


@dataclass
class UiConfig:
    """UI configuration"""
    brand: str = "chfs-py"
    title: str = "chfs-py File Server"
    textShareDir: str = ""
    maxUploadSize: Optional[int] = None
    language: str = "en"


@dataclass
class DavConfig:
    """WebDAV configuration"""
    enabled: bool = True
    mountPath: str = "/webdav"
    lockManager: bool = True
    propertyManager: bool = True


@dataclass
class HotReloadConfig:
    """Hot reload configuration"""
    enabled: bool = True
    watchConfig: bool = True
    debounceMs: int = 1000


@dataclass
class Config:
    """Main configuration container"""
    server: ServerConfig = field(default_factory=ServerConfig)
    shares: List[ShareInfo] = field(default_factory=list)
    users: List[UserInfo] = field(default_factory=list)
    rules: List[RuleInfo] = field(default_factory=list)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    rateLimit: RateLimitConfig = field(default_factory=RateLimitConfig)
    ipFilter: IpFilterConfig = field(default_factory=IpFilterConfig)
    ui: UiConfig = field(default_factory=UiConfig)
    dav: DavConfig = field(default_factory=DavConfig)
    hotReload: HotReloadConfig = field(default_factory=HotReloadConfig)


@dataclass
class TokenBucket:
    """Token bucket for rate limiting"""
    capacity: int
    tokens: float
    last_refill: float
    refill_rate: float  # tokens per second
    
    def __post_init__(self):
        self.tokens = float(self.capacity)
        self.last_refill = time.time()
    
    def consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens from bucket"""
        now = time.time()
        elapsed = now - self.last_refill
        
        # Refill tokens
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now
        
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False


@dataclass
class TextShare:
    """Text sharing entry"""
    id: str
    text: str
    created: float
    expires: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "created": self.created,
            "expires": self.expires
        }


# HTTP Range parsing result
@dataclass
class HttpRange:
    """HTTP Range header parsing result"""
    start: Optional[int] = None
    end: Optional[int] = None
    suffix_length: Optional[int] = None
    
    def resolve(self, content_length: int) -> tuple[int, int]:
        """Resolve range to actual start/end positions"""
        if self.suffix_length is not None:
            # bytes=-500 (last 500 bytes)
            start = max(0, content_length - self.suffix_length)
            end = content_length - 1
        else:
            start = self.start if self.start is not None else 0
            end = self.end if self.end is not None else content_length - 1

            # Clamp values within valid bounds
            if content_length <= 0:
                return 0, -1

            start = max(0, min(start, content_length))
            end = max(-1, min(end, content_length - 1))

            # If start moves beyond the last byte, produce an empty range at EOF
            if start > content_length - 1:
                start = content_length
                end = content_length - 1

            if end < start and end != content_length - 1:
                end = start

        return start, end


# Common MIME types
MIME_TYPES = {
    '.txt': 'text/plain',
    '.html': 'text/html',
    '.css': 'text/css',
    '.js': 'application/javascript',
    '.json': 'application/json',
    '.xml': 'application/xml',
    '.pdf': 'application/pdf',
    '.zip': 'application/zip',
    '.tar': 'application/x-tar',
    '.gz': 'application/gzip',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.gif': 'image/gif',
    '.bmp': 'image/bmp',
    '.ico': 'image/x-icon',
    '.svg': 'image/svg+xml',
    '.mp3': 'audio/mpeg',
    '.wav': 'audio/wav',
    '.mp4': 'video/mp4',
    '.avi': 'video/x-msvideo',
    '.mov': 'video/quicktime',
    '.doc': 'application/msword',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.xls': 'application/vnd.ms-excel',
    '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    '.ppt': 'application/vnd.ms-powerpoint',
    '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
}

# Default MIME type for unknown files
DEFAULT_MIME_TYPE = 'application/octet-stream'
