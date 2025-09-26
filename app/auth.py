"""
Authentication and authorization for chfs-py
"""

import base64
import logging
from typing import Optional, Tuple
from fastapi import HTTPException, Request, Depends
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from passlib.context import CryptContext

from .config import get_config, get_user_by_name
from .models import UserInfo, ResponseCode

logger = logging.getLogger(__name__)

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# HTTP Basic Auth
security = HTTPBasic(auto_error=False)


def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str, is_bcrypt: bool = True) -> bool:
    """Verify a password against its hash"""
    if is_bcrypt:
        return pwd_context.verify(plain_password, hashed_password)
    else:
        # Plain text comparison (not recommended for production)
        return plain_password == hashed_password


def authenticate_user(username: str, password: str) -> Optional[UserInfo]:
    """Authenticate user by username and password"""
    user = get_user_by_name(username)
    if not user:
        logger.warning(f"Authentication failed: user not found: {username}")
        return None
    
    if not verify_password(password, user.pass_hash, user.is_bcrypt):
        logger.warning(f"Authentication failed: invalid password for user: {username}")
        return None
    
    logger.info(f"User authenticated successfully: {username}")
    return user


def parse_basic_auth(authorization: str) -> Optional[Tuple[str, str]]:
    """Parse Basic Auth header"""
    try:
        if not authorization.startswith("Basic "):
            return None
        
        encoded = authorization[6:]  # Remove "Basic " prefix
        decoded = base64.b64decode(encoded).decode('utf-8')
        
        if ':' not in decoded:
            return None
        
        username, password = decoded.split(':', 1)
        return username, password
        
    except Exception as e:
        logger.warning(f"Failed to parse Basic Auth header: {e}")
        return None


def get_current_user_optional(request: Request) -> Optional[UserInfo]:
    """Get current authenticated user (optional)"""
    try:
        # Check Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return None
        
        credentials = parse_basic_auth(auth_header)
        if not credentials:
            return None
        
        username, password = credentials
        return authenticate_user(username, password)
        
    except Exception as e:
        logger.warning(f"Failed to get current user: {e}")
        return None


def get_current_user(request: Request) -> UserInfo:
    """Get current authenticated user (required)"""
    user = get_current_user_optional(request)
    if not user:
        raise HTTPException(
            status_code=401,
            detail={
                "code": ResponseCode.UNAUTHORIZED.value,
                "msg": "Authentication required",
                "data": None
            },
            headers={"WWW-Authenticate": "Basic"},
        )
    return user


def require_auth(request: Request) -> UserInfo:
    """Dependency to require authentication"""
    return get_current_user(request)


def optional_auth(request: Request) -> Optional[UserInfo]:
    """Dependency for optional authentication"""
    return get_current_user_optional(request)


class AuthChecker:
    """Authentication checker for different contexts"""
    
    def __init__(self, required: bool = True):
        self.required = required
    
    def __call__(self, request: Request) -> Optional[UserInfo]:
        if self.required:
            return get_current_user(request)
        else:
            return get_current_user_optional(request)


# Common auth dependencies
auth_required = AuthChecker(required=True)
auth_optional = AuthChecker(required=False)


def create_basic_auth_header(username: str, password: str) -> str:
    """Create Basic Auth header value"""
    credentials = f"{username}:{password}"
    encoded = base64.b64encode(credentials.encode('utf-8')).decode('ascii')
    return f"Basic {encoded}"


def validate_user_credentials(username: str, password: str) -> bool:
    """Validate user credentials (for external use)"""
    user = authenticate_user(username, password)
    return user is not None


def get_user_from_request(request: Request) -> Optional[str]:
    """Extract username from request without full authentication"""
    try:
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return None
        
        credentials = parse_basic_auth(auth_header)
        if not credentials:
            return None
        
        return credentials[0]  # Return username
        
    except Exception:
        return None


def is_authenticated(request: Request) -> bool:
    """Check if request is authenticated"""
    return get_current_user_optional(request) is not None


def get_auth_context(request: Request) -> dict:
    """Get authentication context for logging"""
    user = get_current_user_optional(request)
    return {
        "user": user.name if user else None,
        "authenticated": user is not None,
        "ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("User-Agent"),
    }
