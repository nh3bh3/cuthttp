"""Server-side runtime helpers consolidating storage operations."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import AsyncGenerator, Callable, List, Optional, Tuple

from fastapi import UploadFile

from .auth import hash_password
from .config import get_config, get_user_by_name
from .fs import (
    FileSystemError,
    PathTraversalError,
    create_directory,
    delete_file_or_directory,
    list_directory,
    open_file_for_download,
    rename_file_or_directory,
    save_uploaded_file,
    write_text_file,
)
from .models import Config, FileInfo, HttpRange, UserInfo
from .user_store import add_registered_user

logger = logging.getLogger(__name__)


class FileServer:
    """High-level facade for server-side storage actions."""

    def __init__(self, config_provider: Callable[[], Config] = get_config):
        self._config_provider = config_provider

    @property
    def config(self) -> Config:
        """Return the latest loaded configuration."""
        return self._config_provider()

    def _default_roots(self) -> List[str]:
        return [share.name for share in self.config.shares]

    async def list_directory(self, root: str, path: str) -> List[FileInfo]:
        return await list_directory(root, path)

    async def upload_file(self, root: str, path: str, upload: UploadFile) -> int:
        filename = upload.filename or "unnamed"
        return await save_uploaded_file(
            root,
            path,
            filename,
            upload,
            max_size=self.config.ui.maxUploadSize,
        )

    async def create_directory(self, root: str, path: str) -> None:
        await create_directory(root, path)

    async def delete_path(self, root: str, path: str) -> None:
        await delete_file_or_directory(root, path)

    async def rename_path(self, root: str, path: str, new_name: str) -> None:
        await rename_file_or_directory(root, path, new_name)

    async def open_for_download(
        self,
        root: str,
        path: str,
        http_range: Optional[HttpRange],
    ) -> Tuple[AsyncGenerator[bytes, None], int, int, int]:
        return await open_file_for_download(root, path, http_range)

    async def write_text(self, root: str, rel_path: str, content: str) -> int:
        return await write_text_file(root, rel_path, content)

    async def save_text_share(self, share_id: str, text: str) -> Optional[str]:
        """Persist a text share to disk when configured."""
        config = self.config
        if not config.ui.textShareDir:
            return None

        text_dir_path = Path(config.ui.textShareDir).resolve()

        for share in config.shares:
            try:
                relative = text_dir_path.relative_to(share.path)
            except ValueError:
                continue

            target_rel = f"{relative}/{share_id}.txt".strip("/")
            await write_text_file(share.name, target_rel, text)
            logger.info("Saved text share %s to %s:%s", share_id, share.name, target_rel)
            return f"{share.name}:{target_rel}"

        logger.warning("Text share directory %s is not within any share", text_dir_path)
        return None

    def register_user(self, username: str, password: str) -> Tuple[UserInfo, List[str]]:
        """Register a new user and persist credentials."""
        if get_user_by_name(username):
            raise ValueError("Username already exists")

        default_roots = self._default_roots()
        hashed = hash_password(password)

        user, rules = add_registered_user(username, hashed, default_roots)

        config = self.config
        config.users.append(user)
        config.rules.extend(rules)

        logger.info("Registered new user %s with roots %s", username, default_roots)
        return user, default_roots


file_server = FileServer()

__all__ = [
    "FileServer",
    "file_server",
    "FileSystemError",
    "PathTraversalError",
]
