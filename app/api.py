"""
API routes for chfs-py
"""

import logging
import time
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

from .models import ApiResponse, ResponseCode, FileInfo, TextShare
from .auth import get_current_user, UserInfo, hash_password
from .rules import check_api_access, get_accessible_roots
from .fs import (
    list_directory, create_directory, delete_file_or_directory,
    rename_file_or_directory, save_uploaded_file, open_file_for_download,
    write_text_file, FileSystemError, PathTraversalError
)
from .utils import parse_http_range, generate_short_id, create_response_headers
from .metrics import upload_context, download_context
from .config import get_config, get_user_by_name
from .ipfilter import get_client_ip
from .user_store import add_registered_user

logger = logging.getLogger(__name__)

# API router
api_router = APIRouter(prefix="/api", tags=["api"])

# Text shares storage (in-memory for simplicity)
text_shares = {}


class RegisterRequest(BaseModel):
    username: str
    password: str
    confirmPassword: str


# Session endpoints
@api_router.get("/session")
async def get_session(request: Request, user: UserInfo = Depends(get_current_user)):
    """Return current session information"""

    client_ip = get_client_ip(request)
    roots = get_accessible_roots(user, client_ip)

    return ApiResponse(
        code=ResponseCode.SUCCESS.value,
        msg="success",
        data={
            "user": {"name": user.name},
            "roots": roots,
        }
    ).to_dict()


@api_router.post("/register")
async def register_user(register_req: RegisterRequest):
    """Register a new user account."""

    username = register_req.username.strip()
    password = register_req.password
    confirm = register_req.confirmPassword

    if not username:
        raise HTTPException(
            status_code=400,
            detail=ApiResponse(
                code=ResponseCode.ERROR.value,
                msg="Username is required",
                data=None,
            ).to_dict(),
        )

    if len(username) < 3:
        raise HTTPException(
            status_code=400,
            detail=ApiResponse(
                code=ResponseCode.ERROR.value,
                msg="Username must be at least 3 characters",
                data=None,
            ).to_dict(),
        )

    if not password or len(password) < 6:
        raise HTTPException(
            status_code=400,
            detail=ApiResponse(
                code=ResponseCode.ERROR.value,
                msg="Password must be at least 6 characters",
                data=None,
            ).to_dict(),
        )

    if password != confirm:
        raise HTTPException(
            status_code=400,
            detail=ApiResponse(
                code=ResponseCode.ERROR.value,
                msg="Passwords do not match",
                data=None,
            ).to_dict(),
        )

    if get_user_by_name(username):
        raise HTTPException(
            status_code=409,
            detail=ApiResponse(
                code=ResponseCode.CONFLICT.value,
                msg="Username already exists",
                data=None,
            ).to_dict(),
        )

    config = get_config()
    default_roots = [share.name for share in config.shares] or []

    try:
        hashed = hash_password(password)
        new_user, new_rules = add_registered_user(username, hashed, default_roots)
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=ApiResponse(
                code=ResponseCode.CONFLICT.value,
                msg=str(exc),
                data=None,
            ).to_dict(),
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Failed to register user: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=ApiResponse(
                code=ResponseCode.INTERNAL_ERROR.value,
                msg="Failed to register user",
                data=None,
            ).to_dict(),
        ) from exc

    # Update in-memory config so the new user can log in immediately
    config.users.append(new_user)
    config.rules.extend(new_rules)

    return ApiResponse(
        code=ResponseCode.SUCCESS.value,
        msg="Registration successful",
        data={
            "user": {"name": username},
            "roots": default_roots,
        },
    ).to_dict()


# Request models
class MkdirRequest(BaseModel):
    root: str
    path: str


class RenameRequest(BaseModel):
    root: str
    path: str
    newName: str


class DeleteRequest(BaseModel):
    root: str
    paths: List[str]


class TextShareRequest(BaseModel):
    text: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    confirmPassword: str


@api_router.get("/list")
async def list_files(
    request: Request,
    root: str,
    path: str = "",
    user: UserInfo = Depends(get_current_user)
):
    """List directory contents"""
    
    client_ip = get_client_ip(request)
    
    # Check permissions
    allowed, reason = check_api_access(user, "list", root, path, client_ip)
    if not allowed:
        raise HTTPException(
            status_code=403,
            detail=ApiResponse(
                code=ResponseCode.FORBIDDEN.value,
                msg=reason,
                data=None
            ).to_dict()
        )
    
    try:
        files = await list_directory(root, path)
        
        return ApiResponse(
            code=ResponseCode.SUCCESS.value,
            msg="success",
            data={
                "root": root,
                "path": path,
                "files": [f.to_dict() for f in files]
            }
        ).to_dict()
        
    except FileSystemError as e:
        raise HTTPException(
            status_code=404,
            detail=ApiResponse(
                code=ResponseCode.NOT_FOUND.value,
                msg=str(e),
                data=None
            ).to_dict()
        )


@api_router.post("/upload")
async def upload_file(
    request: Request,
    root: str = Form(...),
    path: str = Form(""),
    file: UploadFile = File(...),
    user: UserInfo = Depends(get_current_user)
):
    """Upload file"""
    
    client_ip = get_client_ip(request)
    
    # Check permissions
    allowed, reason = check_api_access(user, "upload", root, path, client_ip)
    if not allowed:
        raise HTTPException(
            status_code=403,
            detail=ApiResponse(
                code=ResponseCode.FORBIDDEN.value,
                msg=reason,
                data=None
            ).to_dict()
        )
    
    # Check file size
    config = get_config()
    max_size = config.ui.maxUploadSize
    
    if file.size and file.size > max_size:
        raise HTTPException(
            status_code=413,
            detail=ApiResponse(
                code=ResponseCode.PAYLOAD_TOO_LARGE.value,
                msg=f"File too large (max: {max_size} bytes)",
                data=None
            ).to_dict()
        )
    
    try:
        with upload_context() as counter:
            bytes_written = await save_uploaded_file(
                root, path, file.filename or "unnamed", file, max_size
            )
            counter.add_bytes(bytes_written)
        
        return ApiResponse(
            code=ResponseCode.SUCCESS.value,
            msg="File uploaded successfully",
            data={
                "filename": file.filename,
                "size": bytes_written,
                "path": path
            }
        ).to_dict()
        
    except FileSystemError as e:
        raise HTTPException(
            status_code=400,
            detail=ApiResponse(
                code=ResponseCode.ERROR.value,
                msg=str(e),
                data=None
            ).to_dict()
        )


@api_router.post("/mkdir")
async def make_directory(
    request: Request,
    mkdir_req: MkdirRequest,
    user: UserInfo = Depends(get_current_user)
):
    """Create directory"""
    
    client_ip = get_client_ip(request)
    
    # Check permissions
    allowed, reason = check_api_access(user, "mkdir", mkdir_req.root, mkdir_req.path, client_ip)
    if not allowed:
        raise HTTPException(
            status_code=403,
            detail=ApiResponse(
                code=ResponseCode.FORBIDDEN.value,
                msg=reason,
                data=None
            ).to_dict()
        )
    
    try:
        await create_directory(mkdir_req.root, mkdir_req.path)
        
        return ApiResponse(
            code=ResponseCode.SUCCESS.value,
            msg="Directory created successfully",
            data={
                "root": mkdir_req.root,
                "path": mkdir_req.path
            }
        ).to_dict()
        
    except FileSystemError as e:
        raise HTTPException(
            status_code=400,
            detail=ApiResponse(
                code=ResponseCode.ERROR.value,
                msg=str(e),
                data=None
            ).to_dict()
        )


@api_router.post("/rename")
async def rename_item(
    request: Request,
    rename_req: RenameRequest,
    user: UserInfo = Depends(get_current_user)
):
    """Rename file or directory"""
    
    client_ip = get_client_ip(request)
    
    # Check permissions
    allowed, reason = check_api_access(user, "rename", rename_req.root, rename_req.path, client_ip)
    if not allowed:
        raise HTTPException(
            status_code=403,
            detail=ApiResponse(
                code=ResponseCode.FORBIDDEN.value,
                msg=reason,
                data=None
            ).to_dict()
        )
    
    try:
        await rename_file_or_directory(rename_req.root, rename_req.path, rename_req.newName)
        
        return ApiResponse(
            code=ResponseCode.SUCCESS.value,
            msg="Renamed successfully",
            data={
                "root": rename_req.root,
                "oldPath": rename_req.path,
                "newName": rename_req.newName
            }
        ).to_dict()
        
    except FileSystemError as e:
        raise HTTPException(
            status_code=400,
            detail=ApiResponse(
                code=ResponseCode.ERROR.value,
                msg=str(e),
                data=None
            ).to_dict()
        )


@api_router.post("/delete")
async def delete_items(
    request: Request,
    delete_req: DeleteRequest,
    user: UserInfo = Depends(get_current_user)
):
    """Delete files or directories"""
    
    client_ip = get_client_ip(request)
    
    deleted_paths = []
    failed_paths = []
    
    for path in delete_req.paths:
        # Check permissions for each path
        allowed, reason = check_api_access(user, "delete", delete_req.root, path, client_ip)
        if not allowed:
            failed_paths.append({"path": path, "error": reason})
            continue
        
        try:
            await delete_file_or_directory(delete_req.root, path)
            deleted_paths.append(path)
            
        except FileSystemError as e:
            failed_paths.append({"path": path, "error": str(e)})
    
    return ApiResponse(
        code=ResponseCode.SUCCESS.value,
        msg=f"Deleted {len(deleted_paths)} items",
        data={
            "root": delete_req.root,
            "deleted": deleted_paths,
            "failed": failed_paths
        }
    ).to_dict()


@api_router.get("/download")
async def download_file(
    request: Request,
    root: str,
    path: str,
    user: UserInfo = Depends(get_current_user)
):
    """Download file with range support"""
    
    client_ip = get_client_ip(request)
    
    # Check permissions
    allowed, reason = check_api_access(user, "download", root, path, client_ip)
    if not allowed:
        raise HTTPException(
            status_code=403,
            detail=ApiResponse(
                code=ResponseCode.FORBIDDEN.value,
                msg=reason,
                data=None
            ).to_dict()
        )
    
    try:
        # Parse range header
        range_header = request.headers.get("Range")
        http_range = parse_http_range(range_header) if range_header else None
        
        # Open file for download
        file_generator, start, end, total_size = await open_file_for_download(
            root, path, http_range
        )
        
        # Create response headers
        filename = Path(path).name
        headers = create_response_headers(
            content_length=end - start + 1,
            content_type="application/octet-stream",
        )
        
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        
        # Add range headers if partial content
        if http_range:
            headers["Content-Range"] = f"bytes {start}-{end}/{total_size}"
            headers["Accept-Ranges"] = "bytes"
            status_code = 206
        else:
            headers["Accept-Ranges"] = "bytes"
            status_code = 200
        
        # Wrap generator to count bytes
        async def counted_generator():
            with download_context() as counter:
                async for chunk in file_generator:
                    counter.add_bytes(len(chunk))
                    yield chunk
        
        return StreamingResponse(
            counted_generator(),
            status_code=status_code,
            headers=headers,
            media_type="application/octet-stream"
        )
        
    except FileSystemError as e:
        raise HTTPException(
            status_code=404,
            detail=ApiResponse(
                code=ResponseCode.NOT_FOUND.value,
                msg=str(e),
                data=None
            ).to_dict()
        )


@api_router.post("/textshare")
async def create_text_share(
    request: Request,
    text_req: TextShareRequest,
    user: UserInfo = Depends(get_current_user)
):
    """Create text share"""
    
    if not text_req.text.strip():
        raise HTTPException(
            status_code=400,
            detail=ApiResponse(
                code=ResponseCode.ERROR.value,
                msg="Text content cannot be empty",
                data=None
            ).to_dict()
        )
    
    # Generate short ID
    share_id = generate_short_id(8)
    
    # Store text share
    text_share = TextShare(
        id=share_id,
        text=text_req.text,
        created=time.time()
    )
    text_shares[share_id] = text_share
    
    # Also save to file if configured
    config = get_config()
    if config.ui.textShareDir:
        try:
            # Find a share that contains the text share directory
            text_dir_path = Path(config.ui.textShareDir)
            root_name = None
            
            for share in config.shares:
                try:
                    text_dir_path.relative_to(share.path)
                    root_name = share.name
                    break
                except ValueError:
                    continue
            
            if root_name:
                rel_path = str(text_dir_path.relative_to(
                    next(s.path for s in config.shares if s.name == root_name)
                ))
                filename = f"{share_id}.txt"
                
                await write_text_file(root_name, f"{rel_path}/{filename}", text_req.text)
                
        except Exception as e:
            logger.warning(f"Failed to save text share to file: {e}")
    
    return ApiResponse(
        code=ResponseCode.SUCCESS.value,
        msg="Text share created",
        data={
            "id": share_id,
            "url": f"/t/{share_id}",
            "created": text_share.created
        }
    ).to_dict()


def setup_api_routes(app):
    """Setup API routes"""
    app.include_router(api_router)
    logger.info("API routes setup complete")
