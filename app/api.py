"""
API routes for chfs-py
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form, Depends
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel
from urllib.parse import quote, urlparse

from .models import ApiResponse, ResponseCode, FileInfo
from .auth import get_current_user, UserInfo, hash_password
from .rules import check_api_access, get_accessible_roots
from .storage_server import storage_server, FileSystemError
from .utils import parse_http_range, create_response_headers
from .metrics import upload_context, download_context
from .config import get_config, get_user_by_name, get_share_by_name, set_share_quota, config_manager
from .ipfilter import get_client_ip
from .user_store import add_registered_user, remove_registered_user, list_registered_usernames
from .control_panel import build_control_panel_state
from .quota import quota_manager
from .utils import format_file_size, parse_size_to_bytes
from .direct_transfer import direct_transfer_store, DirectTransferError
from .server_store import set_custom_urls

logger = logging.getLogger(__name__)

# API router
api_router = APIRouter(prefix="/api", tags=["api"])

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


class RegisterRequest(BaseModel):
    username: str
    password: str
    confirmPassword: str


class ShareQuotaUpdate(BaseModel):
    quota: Optional[str] = None
    quotaBytes: Optional[int] = None


class ServerUrlUpdate(BaseModel):
    urls: List[str]


def _direct_transfer_http_exception(exc: DirectTransferError) -> HTTPException:
    """Convert a DirectTransferError into a HTTPException."""

    status_code = getattr(exc, "status_code", 400) or 400
    if status_code == 404:
        code = ResponseCode.NOT_FOUND.value
    elif status_code == 403:
        code = ResponseCode.FORBIDDEN.value
    elif status_code == 413:
        code = ResponseCode.PAYLOAD_TOO_LARGE.value
    elif status_code >= 500:
        code = ResponseCode.INTERNAL_ERROR.value
    else:
        code = ResponseCode.ERROR.value

    return HTTPException(
        status_code=status_code,
        detail=ApiResponse(
            code=code,
            msg=str(exc),
            data=None,
        ).to_dict(),
    )


def require_local_admin(request: Request, user: UserInfo = Depends(get_current_user)) -> UserInfo:
    """Ensure administrative actions originate from the local machine."""

    client_ip = get_client_ip(request)
    host = client_ip.split('%', 1)[0] if client_ip else ""
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        addr = None

    if addr is None or not addr.is_loopback:
        raise HTTPException(
            status_code=403,
            detail=ApiResponse(
                code=ResponseCode.FORBIDDEN.value,
                msg="Administrative APIs are only accessible from the server host.",
                data=None,
            ).to_dict(),
        )

    return user


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


@api_router.get("/admin/status")
async def get_admin_status(user: UserInfo = Depends(require_local_admin)):
    """Return consolidated information for the server control panel."""

    status = await build_control_panel_state(user.name)
    return ApiResponse(
        code=ResponseCode.SUCCESS.value,
        msg="success",
        data=status,
    ).to_dict()


@api_router.put("/admin/shares/{share_name}/quota")
async def update_share_quota(
    share_name: str,
    payload: ShareQuotaUpdate,
    user: UserInfo = Depends(require_local_admin),
):
    """Update or clear the quota for a share."""

    share = get_share_by_name(share_name)
    if not share:
        raise HTTPException(
            status_code=404,
            detail=ApiResponse(
                code=ResponseCode.NOT_FOUND.value,
                msg="Share not found",
                data=None,
            ).to_dict(),
        )

    if payload.quotaBytes is not None and payload.quotaBytes < 0:
        raise HTTPException(
            status_code=400,
            detail=ApiResponse(
                code=ResponseCode.ERROR.value,
                msg="Quota must be a positive value or omitted to remove the limit.",
                data=None,
            ).to_dict(),
        )

    quota_bytes: Optional[int] = None
    if payload.quotaBytes is not None:
        quota_bytes = payload.quotaBytes or None
    elif payload.quota is not None:
        try:
            quota_bytes = parse_size_to_bytes(payload.quota)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=ApiResponse(
                    code=ResponseCode.ERROR.value,
                    msg=str(exc),
                    data=None,
                ).to_dict(),
            )

    updated_share = set_share_quota(share_name, quota_bytes)
    quota_manager.invalidate(share_name)

    quota_display = (
        format_file_size(updated_share.quota_bytes)
        if updated_share.quota_bytes
        else "Unlimited"
    )

    return ApiResponse(
        code=ResponseCode.SUCCESS.value,
        msg="Share quota updated",
        data={
            "share": {
                "name": updated_share.name,
                "quotaBytes": updated_share.quota_bytes,
                "quotaDisplay": quota_display,
            }
        },
    ).to_dict()


@api_router.put("/admin/server/custom-urls")
async def update_server_custom_urls(
    payload: ServerUrlUpdate,
    user: UserInfo = Depends(require_local_admin),
):
    """Replace the list of custom URLs shown in the control panel."""

    sanitized: List[str] = []
    seen = set()

    for entry in payload.urls or []:
        trimmed = (entry or "").strip()
        if not trimmed:
            continue

        parsed = urlparse(trimmed)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise HTTPException(
                status_code=400,
                detail=ApiResponse(
                    code=ResponseCode.ERROR.value,
                    msg=f"Invalid URL: {trimmed}",
                    data=None,
                ).to_dict(),
            )

        if trimmed not in seen:
            sanitized.append(trimmed)
            seen.add(trimmed)

    stored = set_custom_urls(sanitized)

    return ApiResponse(
        code=ResponseCode.SUCCESS.value,
        msg="Server URLs updated",
        data={"custom_urls": stored},
    ).to_dict()


@api_router.get("/admin/users")
async def get_admin_users(user: UserInfo = Depends(require_local_admin)):
    """Return configured and dynamically registered users."""

    config = get_config()
    dynamic_users = set(list_registered_usernames())
    users = [
        {
            "name": entry.name,
            "dynamic": entry.name in dynamic_users,
            "is_bcrypt": entry.is_bcrypt,
        }
        for entry in config.users
    ]
    users.sort(key=lambda item: item["name"].lower())

    return ApiResponse(
        code=ResponseCode.SUCCESS.value,
        msg="success",
        data={"users": users},
    ).to_dict()


@api_router.delete("/admin/users/{username}")
async def delete_admin_user(
    username: str,
    user: UserInfo = Depends(require_local_admin),
):
    """Remove a dynamically registered user."""

    target = username.strip()
    if not target:
        raise HTTPException(
            status_code=400,
            detail=ApiResponse(
                code=ResponseCode.ERROR.value,
                msg="Username is required",
                data=None,
            ).to_dict(),
        )

    if target.lower() == user.name.lower():
        raise HTTPException(
            status_code=400,
            detail=ApiResponse(
                code=ResponseCode.ERROR.value,
                msg="You cannot remove the currently authenticated account.",
                data=None,
            ).to_dict(),
        )

    removed = remove_registered_user(target)
    if not removed:
        raise HTTPException(
            status_code=404,
            detail=ApiResponse(
                code=ResponseCode.NOT_FOUND.value,
                msg="User not found or not managed by the control panel.",
                data=None,
            ).to_dict(),
        )

    config_manager.load_config()

    return ApiResponse(
        code=ResponseCode.SUCCESS.value,
        msg="User removed",
        data={"username": target},
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
        files = await storage_server.list_files(root, path)
        
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

    if (
        max_size is not None
        and file.size is not None
        and file.size > max_size
    ):
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
            bytes_written = await storage_server.upload_file(
                root,
                path,
                file.filename or "unnamed",
                file,
                max_size=max_size,
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
        await storage_server.make_directory(mkdir_req.root, mkdir_req.path)
        
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
        await storage_server.rename(
            rename_req.root, rename_req.path, rename_req.newName
        )
        
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
            await storage_server.delete(delete_req.root, path)
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
        file_generator, start, end, total_size = await storage_server.open_for_download(
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


@api_router.get("/direct-transfer/recipients")
async def list_direct_transfer_recipients(
    user: UserInfo = Depends(get_current_user),
):
    """Return available recipients for direct transfers."""

    config = get_config()
    recipients = sorted({entry.name for entry in config.users if entry.name != user.name})

    return ApiResponse(
        code=ResponseCode.SUCCESS.value,
        msg="success",
        data={"recipients": recipients},
    ).to_dict()


@api_router.post("/direct-transfer/send")
async def create_direct_transfer(
    recipient: str = Form(...),
    file: UploadFile = File(...),
    expiresIn: Optional[int] = Form(None),
    user: UserInfo = Depends(get_current_user),
):
    """Create a direct file transfer between users."""

    config = get_config()
    available_users = {entry.name for entry in config.users}

    if recipient == user.name:
        raise HTTPException(
            status_code=400,
            detail=ApiResponse(
                code=ResponseCode.ERROR.value,
                msg="Cannot create a transfer to yourself",
                data=None,
            ).to_dict(),
        )

    if recipient not in available_users:
        raise HTTPException(
            status_code=404,
            detail=ApiResponse(
                code=ResponseCode.NOT_FOUND.value,
                msg="Recipient not found",
                data=None,
            ).to_dict(),
        )

    max_size = config.ui.maxUploadSize

    try:
        with upload_context() as counter:
            entry = await direct_transfer_store.create_transfer(
                user.name,
                recipient,
                file,
                expires_in=expiresIn,
                max_size=max_size,
            )
            counter.add_bytes(entry.size)
    except DirectTransferError as exc:
        raise _direct_transfer_http_exception(exc)

    return ApiResponse(
        code=ResponseCode.SUCCESS.value,
        msg="Direct transfer created",
        data={"transfer": entry.to_public_dict()},
    ).to_dict()


@api_router.get("/direct-transfer/list")
async def list_direct_transfers(
    direction: str = "incoming",
    user: UserInfo = Depends(get_current_user),
):
    """List pending direct transfers for the current user."""

    try:
        transfers = await direct_transfer_store.list_transfers(user.name, direction)
    except DirectTransferError as exc:
        raise _direct_transfer_http_exception(exc)

    return ApiResponse(
        code=ResponseCode.SUCCESS.value,
        msg="success",
        data={"direction": direction.lower(), "transfers": transfers},
    ).to_dict()


@api_router.delete("/direct-transfer/{transfer_id}")
async def delete_direct_transfer(
    transfer_id: str,
    user: UserInfo = Depends(get_current_user),
):
    """Delete or cancel a pending direct transfer."""

    try:
        entry = await direct_transfer_store.delete_transfer(transfer_id, user.name)
    except DirectTransferError as exc:
        raise _direct_transfer_http_exception(exc)

    action = "cancelled" if entry.sender == user.name else "dismissed"

    return ApiResponse(
        code=ResponseCode.SUCCESS.value,
        msg=f"Transfer {action}",
        data={"transfer": entry.to_public_dict(), "action": action},
    ).to_dict()


@api_router.get("/direct-transfer/download/{transfer_id}")
async def download_direct_transfer(
    transfer_id: str,
    user: UserInfo = Depends(get_current_user),
):
    """Download a direct transfer payload."""

    try:
        file_path, entry = await direct_transfer_store.prepare_download(transfer_id, user.name)
    except DirectTransferError as exc:
        raise _direct_transfer_http_exception(exc)

    try:
        file_obj = file_path.open("rb")
    except OSError as exc:
        direct_transfer_store.cleanup_after_download(entry)
        logger.error("Failed to open direct transfer payload %s: %s", transfer_id, exc)
        raise HTTPException(
            status_code=500,
            detail=ApiResponse(
                code=ResponseCode.INTERNAL_ERROR.value,
                msg="Failed to open transfer payload",
                data=None,
            ).to_dict(),
        ) from exc

    async def stream_file():
        try:
            with download_context() as counter:
                while True:
                    chunk = file_obj.read(64 * 1024)
                    if not chunk:
                        break
                    counter.add_bytes(len(chunk))
                    yield chunk
                    await asyncio.sleep(0)
        finally:
            file_obj.close()

    filename = entry.filename or transfer_id
    fallback_name = "".join(
        ch if 32 <= ord(ch) < 127 and ch not in {'"', '\\'} else "_"
        for ch in filename
    ) or "download"

    headers = create_response_headers(
        content_length=entry.size,
        content_type=entry.content_type or "application/octet-stream",
    )
    headers["Content-Disposition"] = (
        f"attachment; filename=\"{fallback_name}\"; filename*=UTF-8''{quote(filename, safe='')}"
    )

    background = BackgroundTask(direct_transfer_store.cleanup_after_download, entry)

    return StreamingResponse(
        stream_file(),
        headers=headers,
        media_type=entry.content_type or "application/octet-stream",
        background=background,
    )


def setup_api_routes(app):
    """Setup API routes"""
    app.include_router(api_router)
    logger.info("API routes setup complete")
