"""
Utility functions for chfs-py
"""

import hashlib
import mimetypes
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, List
import logging

from .models import HttpRange, MIME_TYPES, DEFAULT_MIME_TYPE

logger = logging.getLogger(__name__)


def get_mime_type(file_path: Path) -> str:
    """Get MIME type for file"""
    suffix = file_path.suffix.lower()
    
    # Check our custom MIME types first
    if suffix in MIME_TYPES:
        return MIME_TYPES[suffix]
    
    # Fall back to system mimetypes
    mime_type, _ = mimetypes.guess_type(str(file_path))
    return mime_type or DEFAULT_MIME_TYPE


def format_file_size(size_bytes: int) -> str:
    """Format file size in human readable format"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    size = float(size_bytes)
    
    while size >= 1024.0 and i < len(size_names) - 1:
        size /= 1024.0
        i += 1
    
    if i == 0:
        return f"{int(size)} {size_names[i]}"
    else:
        return f"{size:.1f} {size_names[i]}"


def format_timestamp(timestamp: float, format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Format timestamp to readable string"""
    try:
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime(format_str)
    except (ValueError, OSError):
        return "Unknown"


def parse_http_range(range_header: str) -> Optional[HttpRange]:
    """
    Parse HTTP Range header
    
    Supports:
    - bytes=start-end
    - bytes=start-
    - bytes=-suffix
    
    Args:
        range_header: Range header value (e.g., "bytes=0-1023")
        
    Returns:
        HttpRange object or None if invalid
    """
    if not range_header:
        return None
    
    # Must start with "bytes="
    if not range_header.startswith("bytes="):
        return None
    
    range_spec = range_header[6:]  # Remove "bytes=" prefix
    
    # Handle multiple ranges (not supported, take first one)
    if ',' in range_spec:
        range_spec = range_spec.split(',')[0].strip()
    
    # Parse range specification
    if range_spec.startswith('-'):
        # Suffix range: bytes=-500
        try:
            suffix_length = int(range_spec[1:])
            return HttpRange(suffix_length=suffix_length)
        except ValueError:
            return None
    
    elif range_spec.endswith('-'):
        # Start range: bytes=500-
        try:
            start = int(range_spec[:-1])
            return HttpRange(start=start)
        except ValueError:
            return None
    
    elif '-' in range_spec:
        # Full range: bytes=0-1023
        try:
            start_str, end_str = range_spec.split('-', 1)
            start = int(start_str)
            end = int(end_str)
            return HttpRange(start=start, end=end)
        except ValueError:
            return None
    
    else:
        # Invalid format
        return None


def generate_etag(file_path: Path) -> str:
    """Generate ETag for file based on path and mtime"""
    try:
        stat = file_path.stat()
        data = f"{file_path}:{stat.st_mtime}:{stat.st_size}"
        return hashlib.md5(data.encode()).hexdigest()
    except OSError:
        return hashlib.md5(str(file_path).encode()).hexdigest()


def generate_short_id(length: int = 8) -> str:
    """Generate short random ID"""
    return str(uuid.uuid4()).replace('-', '')[:length]


def sanitize_filename(filename: str) -> str:
    """Sanitize filename for safe filesystem storage"""
    # Remove or replace dangerous characters
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    
    # Remove control characters
    filename = re.sub(r'[\x00-\x1f\x7f]', '', filename)
    
    # Trim whitespace and dots
    filename = filename.strip(' .')
    
    # Ensure not empty
    if not filename:
        filename = "unnamed"
    
    # Limit length
    if len(filename) > 255:
        name, ext = Path(filename).stem, Path(filename).suffix
        max_name_len = 255 - len(ext)
        filename = name[:max_name_len] + ext
    
    return filename


def is_text_file(file_path: Path) -> bool:
    """Check if file is likely a text file"""
    text_extensions = {
        '.txt', '.md', '.rst', '.log', '.cfg', '.conf', '.ini',
        '.json', '.xml', '.yaml', '.yml', '.toml',
        '.py', '.js', '.ts', '.html', '.htm', '.css', '.scss', '.sass',
        '.c', '.cpp', '.h', '.hpp', '.java', '.cs', '.php', '.rb',
        '.go', '.rs', '.sh', '.bat', '.ps1', '.sql'
    }
    
    return file_path.suffix.lower() in text_extensions


def calculate_file_hash(file_path: Path, algorithm: str = "md5") -> str:
    """Calculate file hash"""
    hash_func = hashlib.new(algorithm)
    
    try:
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_func.update(chunk)
        return hash_func.hexdigest()
    except OSError as e:
        logger.error(f"Failed to calculate hash for {file_path}: {e}")
        return ""


def normalize_path(path: str) -> str:
    """Normalize path separators for cross-platform compatibility"""
    return path.replace('\\', '/')


def safe_path_join(*parts: str) -> str:
    """Safely join path parts, normalizing separators"""
    path = '/'.join(str(part).strip('/') for part in parts if part)
    return normalize_path(path)


def get_file_extension(filename: str) -> str:
    """Get file extension in lowercase"""
    return Path(filename).suffix.lower()


def is_hidden_file(filename: str) -> bool:
    """Check if file is hidden (starts with dot)"""
    return filename.startswith('.')


def parse_content_range(content_range: str) -> Optional[Tuple[int, int, int]]:
    """
    Parse Content-Range header
    
    Format: bytes start-end/total
    
    Returns:
        (start, end, total) tuple or None
    """
    if not content_range:
        return None
    
    match = re.match(r'bytes (\d+)-(\d+)/(\d+|\*)', content_range)
    if not match:
        return None
    
    start = int(match.group(1))
    end = int(match.group(2))
    total_str = match.group(3)
    total = int(total_str) if total_str != '*' else -1
    
    return start, end, total


def create_content_range_header(start: int, end: int, total: int) -> str:
    """Create Content-Range header value"""
    return f"bytes {start}-{end}/{total}"


def validate_filename(filename: str) -> bool:
    """Validate filename for basic safety"""
    if not filename or filename in ('.', '..'):
        return False
    
    # Check for dangerous characters
    dangerous_chars = '<>:"/\\|?*'
    if any(char in filename for char in dangerous_chars):
        return False
    
    # Check for control characters
    if any(ord(char) < 32 for char in filename):
        return False
    
    return True


def get_relative_path(base_path: Path, target_path: Path) -> str:
    """Get relative path from base to target"""
    try:
        return str(target_path.relative_to(base_path))
    except ValueError:
        return str(target_path)


def ensure_directory(dir_path: Path) -> bool:
    """Ensure directory exists, create if necessary"""
    try:
        dir_path.mkdir(parents=True, exist_ok=True)
        return True
    except OSError as e:
        logger.error(f"Failed to create directory {dir_path}: {e}")
        return False


def get_disk_usage(path: Path) -> Tuple[int, int, int]:
    """Get disk usage statistics (total, used, free) in bytes"""
    try:
        import shutil
        total, used, free = shutil.disk_usage(path)
        return total, used, free
    except OSError:
        return 0, 0, 0


def format_duration(seconds: float) -> str:
    """Format duration in seconds to human readable string"""
    if seconds < 1:
        return f"{seconds*1000:.1f}ms"
    elif seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m{secs}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h{minutes}m"


def truncate_string(text: str, max_length: int, suffix: str = "...") -> str:
    """Truncate string to maximum length with suffix"""
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def parse_user_agent(user_agent: str) -> dict:
    """Parse User-Agent header for basic info"""
    ua = user_agent.lower() if user_agent else ""
    
    info = {
        "browser": "unknown",
        "os": "unknown",
        "mobile": False
    }
    
    # Detect mobile
    mobile_indicators = ["mobile", "android", "iphone", "ipad", "tablet"]
    info["mobile"] = any(indicator in ua for indicator in mobile_indicators)
    
    # Detect browser
    if "chrome" in ua:
        info["browser"] = "chrome"
    elif "firefox" in ua:
        info["browser"] = "firefox"
    elif "safari" in ua:
        info["browser"] = "safari"
    elif "edge" in ua:
        info["browser"] = "edge"
    
    # Detect OS
    if "windows" in ua:
        info["os"] = "windows"
    elif "mac" in ua:
        info["os"] = "macos"
    elif "linux" in ua:
        info["os"] = "linux"
    elif "android" in ua:
        info["os"] = "android"
    elif "ios" in ua:
        info["os"] = "ios"
    
    return info


def create_response_headers(
    content_length: Optional[int] = None,
    content_type: str = "application/octet-stream",
    etag: Optional[str] = None,
    last_modified: Optional[float] = None,
    cache_control: str = "no-cache"
) -> dict:
    """Create standard response headers"""
    headers = {
        "Content-Type": content_type,
        "Cache-Control": cache_control,
        "X-Content-Type-Options": "nosniff",
    }
    
    if content_length is not None:
        headers["Content-Length"] = str(content_length)
    
    if etag:
        headers["ETag"] = f'"{etag}"'
    
    if last_modified:
        headers["Last-Modified"] = time.strftime(
            "%a, %d %b %Y %H:%M:%S GMT",
            time.gmtime(last_modified)
        )
    
    return headers
