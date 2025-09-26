"""
WebDAV support for chfs-py using WsgiDAV
"""

import logging
import os
from pathlib import Path
from typing import Optional, Dict, Any

try:
    from wsgidav.wsgidav_app import WsgiDAVApp
    from wsgidav.fs_dav_provider import FilesystemProvider
    try:
        from wsgidav.domain_controller import BaseDomainController
    except ImportError:
        # Fallback for older wsgidav versions
        from wsgidav.dc.base_dc import BaseDomainController
    try:
        from wsgidav.lock_manager import LockManager
        from wsgidav.property_manager import PropertyManager
    except ImportError:
        # Fallback for older wsgidav versions
        LockManager = None
        PropertyManager = None
    WEBDAV_AVAILABLE = True
except ImportError as e:
    logger.error(f"WebDAV dependencies not available: {e}")
    WEBDAV_AVAILABLE = False
    WsgiDAVApp = None
    FilesystemProvider = None
    BaseDomainController = None
    LockManager = None
    PropertyManager = None

from .config import get_config, get_share_by_name
from .auth import authenticate_user
from .rules import evaluate_access
from .models import Permission, UserInfo
from .fs import get_absolute_path, FileSystemError
from .metrics import metrics_manager

logger = logging.getLogger(__name__)


class ChfsPropertyManager:
    """Custom property manager for chfs WebDAV"""
    
    def __init__(self):
        if PropertyManager:
            self._manager = PropertyManager()
        else:
            self._manager = None


class ChfsLockManager:
    """Custom lock manager for chfs WebDAV"""
    
    def __init__(self):
        if LockManager:
            self._manager = LockManager()
        else:
            self._manager = None


class ChfsDomainController(BaseDomainController if 'BaseDomainController' in globals() and BaseDomainController else object):
    """Domain controller for chfs WebDAV authentication"""
    
    # WsgiDAV may instantiate with (wsgidav_app) or (wsgidav_app, config) or no args
    def __init__(self, *args, **kwargs):
        try:
            super().__init__()  # type: ignore[misc]
        except Exception:
            pass
        self.config = get_config()
    
    def get_domain_realm(self, path_info: str, environ: Dict[str, Any]) -> str:
        """Return the realm for a given path"""
        return self.config.ui.brand
    
    def require_authentication(self, realm: str, environ: Dict[str, Any]) -> bool:
        """Return True if authentication is required for this request"""
        return True
    
    def basic_auth_user(self, realm: str, username: str, password: str, environ: Dict[str, Any]) -> bool:
        """Authenticate user with basic auth"""
        try:
            user = authenticate_user(username, password)
            if user:
                # Store user info in environ for later use
                environ['chfs.user'] = user
                return True
            return False
        except Exception as e:
            logger.error(f"WebDAV authentication error: {e}")
            return False
    
    def supports_http_digest_auth(self) -> bool:
        """We don't support digest auth"""
        return False


class ChfsFilesystemProvider(FilesystemProvider):
    """Custom filesystem provider with access control"""
    
    def __init__(self, root_path: str, share_name: str):
        if FilesystemProvider:
            try:
                super().__init__(root_path, readonly=False)
            except:
                pass
        self.share_name = share_name
        self.root_path = Path(root_path).resolve()
    
    def _get_user_from_environ(self, environ: Dict[str, Any]) -> Optional[UserInfo]:
        """Get authenticated user from WSGI environ"""
        return environ.get('chfs.user')
    
    def _get_client_ip(self, environ: Dict[str, Any]) -> str:
        """Get client IP from WSGI environ"""
        # Check various headers for client IP
        for header in ['HTTP_X_FORWARDED_FOR', 'HTTP_X_REAL_IP', 'HTTP_CF_CONNECTING_IP']:
            if header in environ:
                return environ[header].split(',')[0].strip()
        
        return environ.get('REMOTE_ADDR', 'unknown')
    
    def _check_access(self, environ: Dict[str, Any], operation: Permission, rel_path: str) -> bool:
        """Check if user has access to perform operation on path"""
        user = self._get_user_from_environ(environ)
        if not user:
            return False
        
        client_ip = self._get_client_ip(environ)
        
        try:
            allowed, reason = evaluate_access(user, operation, self.share_name, rel_path, client_ip)
            if not allowed:
                logger.warning(f"WebDAV access denied: {user.name} -> {operation.value} {self.share_name}{rel_path} - {reason}")
            return allowed
        except Exception as e:
            logger.error(f"WebDAV access check error: {e}")
            return False
    
    def _get_rel_path(self, path: str) -> str:
        """Convert DAV path to relative path"""
        # Remove leading slash and normalize
        rel_path = path.lstrip('/').replace('\\', '/')
        return rel_path
    
    def exists(self, path: str, environ: Dict[str, Any]) -> bool:
        """Check if resource exists"""
        rel_path = self._get_rel_path(path)
        
        # Check read access
        if not self._check_access(environ, Permission.READ, rel_path):
            return False
        
        return super().exists(path, environ)
    
    def is_collection(self, path: str, environ: Dict[str, Any]) -> bool:
        """Check if resource is a collection (directory)"""
        rel_path = self._get_rel_path(path)
        
        # Check read access
        if not self._check_access(environ, Permission.READ, rel_path):
            return False
        
        return super().is_collection(path, environ)
    
    def get_content_length(self, path: str, environ: Dict[str, Any]) -> int:
        """Get content length"""
        rel_path = self._get_rel_path(path)
        
        # Check read access
        if not self._check_access(environ, Permission.READ, rel_path):
            raise Exception("Access denied")
        
        return super().get_content_length(path, environ)
    
    def get_content_type(self, path: str, environ: Dict[str, Any]) -> str:
        """Get content type"""
        rel_path = self._get_rel_path(path)
        
        # Check read access
        if not self._check_access(environ, Permission.READ, rel_path):
            raise Exception("Access denied")
        
        return super().get_content_type(path, environ)
    
    def get_creation_date(self, path: str, environ: Dict[str, Any]) -> float:
        """Get creation date"""
        rel_path = self._get_rel_path(path)
        
        # Check read access
        if not self._check_access(environ, Permission.READ, rel_path):
            raise Exception("Access denied")
        
        return super().get_creation_date(path, environ)
    
    def get_last_modified(self, path: str, environ: Dict[str, Any]) -> float:
        """Get last modified time"""
        rel_path = self._get_rel_path(path)
        
        # Check read access
        if not self._check_access(environ, Permission.READ, rel_path):
            raise Exception("Access denied")
        
        return super().get_last_modified(path, environ)
    
    def get_etag(self, path: str, environ: Dict[str, Any]) -> str:
        """Get ETag"""
        rel_path = self._get_rel_path(path)
        
        # Check read access
        if not self._check_access(environ, Permission.READ, rel_path):
            raise Exception("Access denied")
        
        return super().get_etag(path, environ)
    
    def get_directory_info(self, path: str, environ: Dict[str, Any]) -> list:
        """Get directory listing"""
        rel_path = self._get_rel_path(path)
        
        # Check read access
        if not self._check_access(environ, Permission.READ, rel_path):
            raise Exception("Access denied")
        
        # Get directory info and filter based on access
        try:
            info_list = super().get_directory_info(path, environ)
            filtered_list = []
            
            for info in info_list:
                child_rel_path = self._get_rel_path(info['href'])
                if self._check_access(environ, Permission.READ, child_rel_path):
                    filtered_list.append(info)
            
            return filtered_list
            
        except Exception as e:
            logger.error(f"WebDAV directory listing error: {e}")
            raise
    
    def get_content(self, path: str, environ: Dict[str, Any]):
        """Get file content"""
        rel_path = self._get_rel_path(path)
        
        # Check read access
        if not self._check_access(environ, Permission.READ, rel_path):
            raise Exception("Access denied")
        
        # Count download bytes
        metrics_manager.add_download_bytes(self.get_content_length(path, environ))
        
        return super().get_content(path, environ)
    
    def begin_write(self, path: str, environ: Dict[str, Any]):
        """Begin write operation"""
        rel_path = self._get_rel_path(path)
        
        # Check write access
        if not self._check_access(environ, Permission.WRITE, rel_path):
            raise Exception("Access denied")
        
        return super().begin_write(path, environ)
    
    def end_write(self, path: str, environ: Dict[str, Any], file_obj):
        """End write operation"""
        rel_path = self._get_rel_path(path)
        
        # Check write access
        if not self._check_access(environ, Permission.WRITE, rel_path):
            raise Exception("Access denied")
        
        # Get file size for metrics
        try:
            if hasattr(file_obj, 'tell'):
                file_size = file_obj.tell()
                metrics_manager.add_upload_bytes(file_size)
        except Exception:
            pass
        
        return super().end_write(path, environ, file_obj)
    
    def create_collection(self, path: str, environ: Dict[str, Any]):
        """Create directory"""
        rel_path = self._get_rel_path(path)
        
        # Check write access
        if not self._check_access(environ, Permission.WRITE, rel_path):
            raise Exception("Access denied")
        
        return super().create_collection(path, environ)
    
    def delete(self, path: str, environ: Dict[str, Any]):
        """Delete resource"""
        rel_path = self._get_rel_path(path)
        
        # Check delete access
        if not self._check_access(environ, Permission.DELETE, rel_path):
            raise Exception("Access denied")
        
        return super().delete(path, environ)
    
    def copy_move_single(self, path: str, dest_path: str, is_move: bool, environ: Dict[str, Any]):
        """Copy or move resource"""
        src_rel_path = self._get_rel_path(path)
        dest_rel_path = self._get_rel_path(dest_path)
        
        # Check source read access
        if not self._check_access(environ, Permission.READ, src_rel_path):
            raise Exception("Access denied to source")
        
        # Check destination write access
        if not self._check_access(environ, Permission.WRITE, dest_rel_path):
            raise Exception("Access denied to destination")
        
        # If move, also check delete access on source
        if is_move and not self._check_access(environ, Permission.DELETE, src_rel_path):
            raise Exception("Access denied to delete source")
        
        return super().copy_move_single(path, dest_path, is_move, environ)


class ChfsWebDAVProvider:
    """WebDAV provider manager for multiple shares"""
    
    def __init__(self, config):
        self.config = config
        self.providers = {}
        
        # Create providers for each share
        for share in config.shares:
            provider = ChfsFilesystemProvider(str(share.path), share.name)
            self.providers[f"/{share.name}"] = provider
    
    def get_provider_mapping(self) -> Dict[str, ChfsFilesystemProvider]:
        """Get provider mapping for WsgiDAV"""
        return self.providers


def create_webdav_app(config):
    """Create WebDAV WSGI application"""
    
    if not WEBDAV_AVAILABLE:
        logger.error("WebDAV dependencies not available")
        return None
    
    try:
        # Create provider mapping
        webdav_provider = ChfsWebDAVProvider(config)
        provider_mapping = webdav_provider.get_provider_mapping()
        
        # WebDAV configuration - using new configuration format
        # Note: Newer WsgiDAV versions deprecate "lock_manager" in favor of internal
        # "lock_storage" configuration. We omit custom lock manager to use defaults.
        webdav_config = {
            "provider_mapping": provider_mapping,
            "http_authenticator": {
                "domain_controller": "app.webdav.ChfsDomainController",
                "trusted_auth_header": None,
                "accept_basic": True,
                "accept_digest": False,
                "default_to_digest": False,
            },
            "verbose": 1 if os.getenv("CHFS_DEBUG") else 0,
            "logging": {
                "enable_loggers": ["wsgidav"],
            },
            # Use default property and lock storage behavior provided by WsgiDAV
            # "property_manager" and "lock_manager" keys are intentionally omitted
            "middleware_stack": [
                "wsgidav.debug_filter.WsgiDavDebugFilter",
                "wsgidav.error_printer.ErrorPrinter", 
                "wsgidav.http_authenticator.HTTPAuthenticator",
                "wsgidav.dir_browser.WsgiDavDirBrowser",
                "wsgidav.request_resolver.RequestResolver",
            ],
        }
        
        # Create WebDAV app
        app = WsgiDAVApp(webdav_config)
        
        # Wrap to count requests
        def webdav_wrapper(environ, start_response):
            metrics_manager.increment_webdav_requests()
            
            try:
                return app(environ, start_response)
            except Exception as e:
                metrics_manager.increment_webdav_errors()
                logger.error(f"WebDAV error: {e}")
                raise
        
        logger.info(f"WebDAV app created with {len(provider_mapping)} shares")
        return webdav_wrapper
        
    except Exception as e:
        logger.error(f"Failed to create WebDAV app: {e}")
        return None
