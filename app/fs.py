"""
Safe filesystem operations for chfs-py
"""

import os
import shutil
import logging
from pathlib import Path
from typing import List, Optional, Tuple, AsyncGenerator, BinaryIO
import aiofiles
import aiofiles.os
from fastapi import UploadFile

from .models import FileInfo, HttpRange
from .utils import get_mime_type, normalize_path, sanitize_filename, validate_filename
from .config import get_share_by_name

logger = logging.getLogger(__name__)


class PathTraversalError(Exception):
    """Raised when path traversal attack is detected"""
    pass


class FileSystemError(Exception):
    """Generic filesystem error"""
    pass


def safe_join(root_path: Path, rel_path: str) -> Path:
    """
    Safely join root path with relative path, preventing directory traversal
    
    Args:
        root_path: Root directory path (must be resolved)
        rel_path: Relative path to join
        
    Returns:
        Resolved absolute path within root
        
    Raises:
        PathTraversalError: If path would escape root directory
    """
    
    # Normalize the relative path
    from urllib.parse import unquote

    rel_path = normalize_path(unquote(rel_path.strip()))

    # Special cases that should map to the root itself
    if rel_path in {"", ".", "./"}:
        return root_path.resolve()

    # Remove all leading separators to avoid absolute paths overriding the root
    rel_path = rel_path.lstrip('/')

    # Split the path into components and validate each part
    parts = []
    for part in rel_path.split('/'):
        if not part or part == '.':
            # Skip empty or current-directory segments caused by // or ./
            continue
        if part == '..':
            raise PathTraversalError(f"Path traversal detected: {rel_path}")
        parts.append(part)

    # Join the validated parts with the resolved root
    base_path = root_path.resolve()
    full_path = base_path.joinpath(*parts) if parts else base_path

    # Resolve symlinks without requiring the target to exist
    try:
        resolved_path = full_path.resolve(strict=False)
    except OSError as e:
        raise FileSystemError(f"Failed to resolve path: {e}")

    # Ensure resolved path is within root
    try:
        resolved_path.relative_to(base_path)
    except ValueError:
        raise PathTraversalError(f"Path traversal detected: {rel_path}")

    return resolved_path


async def list_directory(root_name: str, rel_path: str) -> List[FileInfo]:
    """
    List directory contents safely
    
    Args:
        root_name: Share root name
        rel_path: Relative path within share
        
    Returns:
        List of FileInfo objects
        
    Raises:
        FileSystemError: If operation fails
    """
    
    # Get share configuration
    share = get_share_by_name(root_name)
    if not share:
        raise FileSystemError(f"Share not found: {root_name}")
    
    # Get safe path
    try:
        dir_path = safe_join(share.path, rel_path)
    except PathTraversalError as e:
        raise FileSystemError(str(e))
    
    # Check if directory exists
    if not await aiofiles.os.path.exists(dir_path):
        raise FileSystemError(f"Directory not found: {rel_path}")
    
    if not await aiofiles.os.path.isdir(dir_path):
        raise FileSystemError(f"Not a directory: {rel_path}")
    
    # List directory contents
    try:
        entries = []
        for entry in await aiofiles.os.listdir(dir_path):
            entry_path = dir_path / entry
            
            try:
                stat = await aiofiles.os.stat(entry_path)
                is_dir = await aiofiles.os.path.isdir(entry_path)
                
                file_info = FileInfo(
                    name=entry,
                    path=normalize_path(f"{rel_path.rstrip('/')}/{entry}"),
                    size=0 if is_dir else stat.st_size,
                    is_dir=is_dir,
                    modified=stat.st_mtime,
                    mime_type="" if is_dir else get_mime_type(entry_path)
                )
                entries.append(file_info)
                
            except OSError as e:
                logger.warning(f"Failed to stat {entry_path}: {e}")
                continue
        
        # Sort: directories first, then files, both alphabetically
        entries.sort(key=lambda x: (not x.is_dir, x.name.lower()))
        return entries
        
    except OSError as e:
        raise FileSystemError(f"Failed to list directory: {e}")


async def get_file_info(root_name: str, rel_path: str) -> FileInfo:
    """
    Get file information
    
    Args:
        root_name: Share root name
        rel_path: Relative path within share
        
    Returns:
        FileInfo object
        
    Raises:
        FileSystemError: If file not found or operation fails
    """
    
    # Get share configuration
    share = get_share_by_name(root_name)
    if not share:
        raise FileSystemError(f"Share not found: {root_name}")
    
    # Get safe path
    try:
        file_path = safe_join(share.path, rel_path)
    except PathTraversalError as e:
        raise FileSystemError(str(e))
    
    # Check if file exists
    if not await aiofiles.os.path.exists(file_path):
        raise FileSystemError(f"File not found: {rel_path}")
    
    try:
        stat = await aiofiles.os.stat(file_path)
        is_dir = await aiofiles.os.path.isdir(file_path)
        
        return FileInfo(
            name=file_path.name,
            path=rel_path,
            size=0 if is_dir else stat.st_size,
            is_dir=is_dir,
            modified=stat.st_mtime,
            mime_type="" if is_dir else get_mime_type(file_path)
        )
        
    except OSError as e:
        raise FileSystemError(f"Failed to get file info: {e}")


async def create_directory(root_name: str, rel_path: str) -> None:
    """
    Create directory safely
    
    Args:
        root_name: Share root name
        rel_path: Relative path of directory to create
        
    Raises:
        FileSystemError: If operation fails
    """
    
    # Get share configuration
    share = get_share_by_name(root_name)
    if not share:
        raise FileSystemError(f"Share not found: {root_name}")
    
    # Get safe path
    try:
        dir_path = safe_join(share.path, rel_path)
    except PathTraversalError as e:
        raise FileSystemError(str(e))
    
    # Check if already exists
    if await aiofiles.os.path.exists(dir_path):
        raise FileSystemError(f"Directory already exists: {rel_path}")
    
    try:
        await aiofiles.os.makedirs(dir_path, exist_ok=False)
        logger.info(f"Created directory: {dir_path}")
        
    except OSError as e:
        raise FileSystemError(f"Failed to create directory: {e}")


async def delete_file_or_directory(root_name: str, rel_path: str) -> None:
    """
    Delete file or directory safely
    
    Args:
        root_name: Share root name
        rel_path: Relative path to delete
        
    Raises:
        FileSystemError: If operation fails
    """
    
    # Get share configuration
    share = get_share_by_name(root_name)
    if not share:
        raise FileSystemError(f"Share not found: {root_name}")
    
    # Get safe path
    try:
        target_path = safe_join(share.path, rel_path)
    except PathTraversalError as e:
        raise FileSystemError(str(e))
    
    # Check if exists
    if not await aiofiles.os.path.exists(target_path):
        raise FileSystemError(f"Path not found: {rel_path}")
    
    try:
        if await aiofiles.os.path.isdir(target_path):
            # Remove directory recursively
            await aiofiles.os.rmdir(target_path) if not os.listdir(target_path) else None
            if await aiofiles.os.path.exists(target_path):
                # Directory not empty, use shutil.rmtree (sync)
                shutil.rmtree(target_path)
        else:
            # Remove file
            await aiofiles.os.remove(target_path)
        
        logger.info(f"Deleted: {target_path}")
        
    except OSError as e:
        raise FileSystemError(f"Failed to delete: {e}")


async def rename_file_or_directory(root_name: str, old_rel_path: str, new_name: str) -> None:
    """
    Rename file or directory safely
    
    Args:
        root_name: Share root name
        old_rel_path: Current relative path
        new_name: New name (filename only, not path)
        
    Raises:
        FileSystemError: If operation fails
    """
    
    # Validate new name
    if not validate_filename(new_name):
        raise FileSystemError(f"Invalid filename: {new_name}")
    
    # Sanitize new name
    new_name = sanitize_filename(new_name)
    
    # Get share configuration
    share = get_share_by_name(root_name)
    if not share:
        raise FileSystemError(f"Share not found: {root_name}")
    
    # Get safe paths
    try:
        old_path = safe_join(share.path, old_rel_path)
        
        # New path is in same directory as old path
        parent_rel_path = str(Path(old_rel_path).parent)
        if parent_rel_path == ".":
            parent_rel_path = ""
        new_rel_path = f"{parent_rel_path}/{new_name}".strip('/')
        new_path = safe_join(share.path, new_rel_path)
        
    except PathTraversalError as e:
        raise FileSystemError(str(e))
    
    # Check if old path exists
    if not await aiofiles.os.path.exists(old_path):
        raise FileSystemError(f"Source path not found: {old_rel_path}")
    
    # Check if new path already exists
    if await aiofiles.os.path.exists(new_path):
        raise FileSystemError(f"Destination already exists: {new_name}")
    
    try:
        await aiofiles.os.rename(old_path, new_path)
        logger.info(f"Renamed: {old_path} -> {new_path}")
        
    except OSError as e:
        raise FileSystemError(f"Failed to rename: {e}")


async def save_uploaded_file(
    root_name: str,
    rel_path: str,
    filename: str,
    upload_file: UploadFile,
    max_size: Optional[int] = None,
) -> int:
    """
    Save uploaded file safely
    
    Args:
        root_name: Share root name
        rel_path: Relative directory path
        filename: Target filename
        upload_file: FastAPI UploadFile object
        max_size: Optional maximum file size in bytes
        
    Returns:
        Number of bytes written
        
    Raises:
        FileSystemError: If operation fails
    """
    
    # Validate and sanitize filename
    if not validate_filename(filename):
        raise FileSystemError(f"Invalid filename: {filename}")
    
    filename = sanitize_filename(filename)
    
    # Get share configuration
    share = get_share_by_name(root_name)
    if not share:
        raise FileSystemError(f"Share not found: {root_name}")
    
    # Get safe path
    try:
        dir_path = safe_join(share.path, rel_path)
        file_path = safe_join(share.path, f"{rel_path.rstrip('/')}/{filename}")
    except PathTraversalError as e:
        raise FileSystemError(str(e))
    
    # Ensure directory exists
    if not await aiofiles.os.path.exists(dir_path):
        try:
            await aiofiles.os.makedirs(dir_path, exist_ok=True)
        except OSError as e:
            raise FileSystemError(f"Failed to create directory: {e}")
    
    # Check if file already exists
    if await aiofiles.os.path.exists(file_path):
        raise FileSystemError(f"File already exists: {filename}")
    
    try:
        bytes_written = 0
        async with aiofiles.open(file_path, 'wb') as f:
            while True:
                chunk = await upload_file.read(8192)  # 8KB chunks
                if not chunk:
                    break
                
                bytes_written += len(chunk)
                if max_size is not None and bytes_written > max_size:
                    # Clean up partial file
                    await aiofiles.os.remove(file_path)
                    raise FileSystemError(f"File too large (max: {max_size} bytes)")
                
                await f.write(chunk)
        
        logger.info(f"Uploaded file: {file_path} ({bytes_written} bytes)")
        return bytes_written
        
    except OSError as e:
        # Clean up partial file
        if await aiofiles.os.path.exists(file_path):
            await aiofiles.os.remove(file_path)
        raise FileSystemError(f"Failed to save file: {e}")


async def open_file_for_download(
    root_name: str,
    rel_path: str,
    http_range: Optional[HttpRange] = None
) -> Tuple[AsyncGenerator[bytes, None], int, int, int]:
    """
    Open file for download with optional range support
    
    Args:
        root_name: Share root name
        rel_path: Relative file path
        http_range: Optional HTTP range specification
        
    Returns:
        (file_generator, start_pos, end_pos, total_size) tuple
        
    Raises:
        FileSystemError: If operation fails
    """
    
    # Get share configuration
    share = get_share_by_name(root_name)
    if not share:
        raise FileSystemError(f"Share not found: {root_name}")
    
    # Get safe path
    try:
        file_path = safe_join(share.path, rel_path)
    except PathTraversalError as e:
        raise FileSystemError(str(e))
    
    # Check if file exists and is readable
    if not await aiofiles.os.path.exists(file_path):
        raise FileSystemError(f"File not found: {rel_path}")
    
    if await aiofiles.os.path.isdir(file_path):
        raise FileSystemError(f"Path is a directory: {rel_path}")
    
    try:
        stat = await aiofiles.os.stat(file_path)
        total_size = stat.st_size
        
        # Calculate range
        if http_range:
            start, end = http_range.resolve(total_size)
        else:
            start, end = 0, total_size - 1
        
        # Validate range
        if start < 0 or end >= total_size or start > end:
            raise FileSystemError("Invalid range")
        
        async def file_generator():
            async with aiofiles.open(file_path, 'rb') as f:
                await f.seek(start)
                remaining = end - start + 1
                
                while remaining > 0:
                    chunk_size = min(8192, remaining)  # 8KB chunks
                    chunk = await f.read(chunk_size)
                    
                    if not chunk:
                        break
                    
                    remaining -= len(chunk)
                    yield chunk
        
        return file_generator(), start, end, total_size
        
    except OSError as e:
        raise FileSystemError(f"Failed to open file: {e}")


async def write_text_file(root_name: str, rel_path: str, content: str) -> int:
    """
    Write text content to file
    
    Args:
        root_name: Share root name
        rel_path: Relative file path
        content: Text content to write
        
    Returns:
        Number of bytes written
        
    Raises:
        FileSystemError: If operation fails
    """
    
    # Get share configuration
    share = get_share_by_name(root_name)
    if not share:
        raise FileSystemError(f"Share not found: {root_name}")
    
    # Get safe path
    try:
        file_path = safe_join(share.path, rel_path)
    except PathTraversalError as e:
        raise FileSystemError(str(e))
    
    # Ensure parent directory exists
    parent_dir = file_path.parent
    if not await aiofiles.os.path.exists(parent_dir):
        try:
            await aiofiles.os.makedirs(parent_dir, exist_ok=True)
        except OSError as e:
            raise FileSystemError(f"Failed to create directory: {e}")
    
    try:
        async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
            await f.write(content)
        
        stat = await aiofiles.os.stat(file_path)
        logger.info(f"Wrote text file: {file_path} ({stat.st_size} bytes)")
        return stat.st_size
        
    except OSError as e:
        raise FileSystemError(f"Failed to write file: {e}")


async def read_text_file(root_name: str, rel_path: str) -> str:
    """
    Read text content from file
    
    Args:
        root_name: Share root name
        rel_path: Relative file path
        
    Returns:
        File content as string
        
    Raises:
        FileSystemError: If operation fails
    """
    
    # Get share configuration
    share = get_share_by_name(root_name)
    if not share:
        raise FileSystemError(f"Share not found: {root_name}")
    
    # Get safe path
    try:
        file_path = safe_join(share.path, rel_path)
    except PathTraversalError as e:
        raise FileSystemError(str(e))
    
    # Check if file exists
    if not await aiofiles.os.path.exists(file_path):
        raise FileSystemError(f"File not found: {rel_path}")
    
    if await aiofiles.os.path.isdir(file_path):
        raise FileSystemError(f"Path is a directory: {rel_path}")
    
    try:
        async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
            return await f.read()
    except OSError as e:
        raise FileSystemError(f"Failed to read file: {e}")
    except UnicodeDecodeError as e:
        raise FileSystemError(f"File is not valid UTF-8 text: {e}")


def get_absolute_path(root_name: str, rel_path: str) -> Path:
    """
    Get absolute path for root and relative path (sync version for WebDAV)
    
    Args:
        root_name: Share root name
        rel_path: Relative path
        
    Returns:
        Absolute path
        
    Raises:
        FileSystemError: If operation fails
    """
    
    # Get share configuration
    share = get_share_by_name(root_name)
    if not share:
        raise FileSystemError(f"Share not found: {root_name}")
    
    # Get safe path
    try:
        return safe_join(share.path, rel_path)
    except PathTraversalError as e:
        raise FileSystemError(str(e))
