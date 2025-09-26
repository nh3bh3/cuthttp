"""Server-side storage orchestration layer."""

from __future__ import annotations

from typing import AsyncGenerator, List, Optional, Tuple
import logging

from fastapi import UploadFile

from .fs import (
    list_directory,
    create_directory,
    delete_file_or_directory,
    rename_file_or_directory,
    save_uploaded_file,
    open_file_for_download,
    write_text_file,
    FileSystemError,
)
from .models import FileInfo, HttpRange

logger = logging.getLogger(__name__)


class StorageServer:
    """Encapsulates all server-side storage operations."""

    async def list_files(self, root_name: str, rel_path: str) -> List[FileInfo]:
        logger.debug("Listing files", extra={"root": root_name, "path": rel_path})
        return await list_directory(root_name, rel_path)

    async def upload_file(
        self,
        root_name: str,
        rel_path: str,
        filename: str,
        upload_file_obj: UploadFile,
        *,
        max_size: Optional[int] = None,
    ) -> int:
        logger.debug(
            "Uploading file",
            extra={"root": root_name, "path": rel_path, "filename": filename},
        )
        return await save_uploaded_file(
            root_name,
            rel_path,
            filename,
            upload_file_obj,
            max_size=max_size,
        )

    async def make_directory(self, root_name: str, rel_path: str) -> None:
        logger.debug("Creating directory", extra={"root": root_name, "path": rel_path})
        await create_directory(root_name, rel_path)

    async def rename(self, root_name: str, rel_path: str, new_name: str) -> None:
        logger.debug(
            "Renaming entry",
            extra={"root": root_name, "path": rel_path, "new_name": new_name},
        )
        await rename_file_or_directory(root_name, rel_path, new_name)

    async def delete(self, root_name: str, rel_path: str) -> None:
        logger.debug("Deleting entry", extra={"root": root_name, "path": rel_path})
        await delete_file_or_directory(root_name, rel_path)

    async def open_for_download(
        self,
        root_name: str,
        rel_path: str,
        http_range: Optional[HttpRange] = None,
    ) -> Tuple[AsyncGenerator[bytes, None], int, int, int]:
        logger.debug(
            "Opening file for download",
            extra={"root": root_name, "path": rel_path},
        )
        return await open_file_for_download(root_name, rel_path, http_range)

    async def write_text(
        self,
        root_name: str,
        rel_path: str,
        content: str,
    ) -> int:
        logger.debug(
            "Writing text file",
            extra={"root": root_name, "path": rel_path},
        )
        return await write_text_file(root_name, rel_path, content)


storage_server = StorageServer()

__all__ = ["storage_server", "StorageServer", "FileSystemError"]
