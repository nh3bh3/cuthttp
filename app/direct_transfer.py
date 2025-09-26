"""Direct transfer management between users."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import UploadFile

from .utils import generate_short_id

logger = logging.getLogger(__name__)


class DirectTransferError(Exception):
    """Base exception for direct transfer operations."""

    def __init__(self, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class DirectTransferEntry:
    """Represents a pending direct transfer entry."""

    id: str
    sender: str
    recipient: str
    filename: str
    stored_filename: str
    size: int
    content_type: str
    created_at: float
    expires_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialise entry for persistence."""

        return {
            "id": self.id,
            "sender": self.sender,
            "recipient": self.recipient,
            "filename": self.filename,
            "stored_filename": self.stored_filename,
            "size": self.size,
            "content_type": self.content_type,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }

    def to_public_dict(self) -> Dict[str, Any]:
        """Serialise entry for API responses."""

        return {
            "id": self.id,
            "sender": self.sender,
            "recipient": self.recipient,
            "filename": self.filename,
            "size": self.size,
            "contentType": self.content_type,
            "createdAt": self.created_at,
            "expiresAt": self.expires_at,
            "downloadUrl": f"/api/direct-transfer/download/{self.id}",
        }


class DirectTransferStore:
    """Persists pending direct transfer entries and payloads."""

    def __init__(self, base_dir: Path | None = None):
        self.base_dir = (base_dir or Path("data/direct_transfers")).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.meta_path = self.base_dir / "transfers.json"
        self._lock = asyncio.Lock()
        self._entries: Dict[str, DirectTransferEntry] = {}
        self._load()

    def _load(self) -> None:
        """Load existing metadata from disk."""

        if not self.meta_path.exists():
            return

        try:
            with self.meta_path.open("r", encoding="utf-8") as f:
                data = json.load(f) or {}
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse direct transfer metadata: %s", exc)
            return
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Unexpected error loading transfer metadata: %s", exc)
            return

        entries = data.get("transfers", [])
        if not isinstance(entries, list):
            logger.warning("Invalid transfers structure in metadata file")
            return

        loaded = 0
        for item in entries:
            if not isinstance(item, dict):
                continue
            try:
                entry = DirectTransferEntry(
                    id=item["id"],
                    sender=item["sender"],
                    recipient=item["recipient"],
                    filename=item["filename"],
                    stored_filename=item["stored_filename"],
                    size=int(item["size"]),
                    content_type=item.get("content_type", "application/octet-stream"),
                    created_at=float(item["created_at"]),
                    expires_at=(float(item["expires_at"]) if item.get("expires_at") else None),
                )
            except (KeyError, TypeError, ValueError):
                logger.warning("Skipping invalid transfer metadata entry: %s", item)
                continue

            payload_path = self.base_dir / entry.stored_filename
            if not payload_path.exists():
                logger.info("Removing metadata for missing transfer payload: %s", entry.id)
                continue

            self._entries[entry.id] = entry
            loaded += 1

        if loaded:
            logger.info("Loaded %d pending direct transfers", loaded)

    def _save_locked(self) -> None:
        """Persist current metadata to disk. Caller must hold the lock."""

        data = {"transfers": [entry.to_dict() for entry in self._entries.values()]}
        tmp_path = self.meta_path.with_suffix(".tmp")
        self.meta_path.parent.mkdir(parents=True, exist_ok=True)
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp_path.replace(self.meta_path)

    def _delete_file(self, path: Path) -> None:
        """Delete a payload file safely."""

        try:
            path.unlink(missing_ok=True)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to delete transfer payload %s: %s", path, exc)

    def _prune_locked(self) -> None:
        """Remove expired or missing entries. Caller must hold the lock."""

        now = time.time()
        removed = False
        for transfer_id, entry in list(self._entries.items()):
            should_remove = False
            if entry.expires_at is not None and entry.expires_at < now:
                should_remove = True
            else:
                payload_path = self.base_dir / entry.stored_filename
                if not payload_path.exists():
                    should_remove = True

            if should_remove:
                removed = True
                logger.info("Pruning expired or missing transfer %s", transfer_id)
                self._entries.pop(transfer_id, None)
                self._delete_file(self.base_dir / entry.stored_filename)

        if removed:
            self._save_locked()

    def _allocate_locked(self, original_filename: str) -> Tuple[str, str]:
        """Allocate a unique transfer identifier and stored filename."""

        suffix = Path(original_filename or "transfer").suffix
        if not suffix:
            suffix = ".bin"

        for _ in range(64):
            transfer_id = generate_short_id(12)
            stored_filename = f"{transfer_id}{suffix}"
            if transfer_id in self._entries:
                continue
            if (self.base_dir / stored_filename).exists():
                continue
            return transfer_id, stored_filename

        raise DirectTransferError("Unable to allocate a transfer identifier", status_code=500)

    async def _write_upload_to_path(
        self,
        upload_file: UploadFile,
        destination: Path,
        *,
        max_size: Optional[int] = None,
    ) -> int:
        """Write an upload file to the destination path and return bytes written."""

        destination.parent.mkdir(parents=True, exist_ok=True)
        await upload_file.seek(0)

        size = 0
        try:
            with destination.open("wb") as output:
                while True:
                    chunk = await upload_file.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if max_size is not None and size > max_size:
                        raise DirectTransferError(
                            f"File too large (max: {max_size} bytes)",
                            status_code=413,
                        )
                    output.write(chunk)
        finally:
            await upload_file.close()

        return size

    async def create_transfer(
        self,
        sender: str,
        recipient: str,
        upload_file: UploadFile,
        *,
        expires_in: Optional[int] = None,
        max_size: Optional[int] = None,
    ) -> DirectTransferEntry:
        """Create a direct transfer entry and persist payload."""

        if not upload_file:
            raise DirectTransferError("No file uploaded for transfer")

        tmp_name = f"tmp-{generate_short_id(10)}"
        tmp_path = self.base_dir / tmp_name

        try:
            size = await self._write_upload_to_path(
                upload_file,
                tmp_path,
                max_size=max_size,
            )
        except DirectTransferError:
            self._delete_file(tmp_path)
            raise
        except Exception as exc:
            self._delete_file(tmp_path)
            logger.error("Failed to store direct transfer payload: %s", exc)
            raise DirectTransferError("Failed to store uploaded file", status_code=500) from exc

        created_at = time.time()
        expires_at = created_at + expires_in if expires_in and expires_in > 0 else None
        content_type = upload_file.content_type or "application/octet-stream"

        async with self._lock:
            self._prune_locked()
            transfer_id, stored_filename = self._allocate_locked(upload_file.filename or "transfer")
            final_path = self.base_dir / stored_filename
            tmp_path.replace(final_path)

            entry = DirectTransferEntry(
                id=transfer_id,
                sender=sender,
                recipient=recipient,
                filename=upload_file.filename or stored_filename,
                stored_filename=stored_filename,
                size=size,
                content_type=content_type,
                created_at=created_at,
                expires_at=expires_at,
            )

            self._entries[entry.id] = entry
            self._save_locked()

        logger.info("Created direct transfer %s from %s to %s", entry.id, sender, recipient)
        return entry

    async def list_transfers(self, username: str, direction: str) -> List[Dict[str, Any]]:
        """List pending transfers for a user in the given direction."""

        direction = direction.lower()
        if direction not in {"incoming", "outgoing"}:
            raise DirectTransferError("Invalid transfer direction", status_code=400)

        async with self._lock:
            self._prune_locked()
            if direction == "incoming":
                entries = [entry.to_public_dict() for entry in self._entries.values() if entry.recipient == username]
            else:
                entries = [entry.to_public_dict() for entry in self._entries.values() if entry.sender == username]

        entries.sort(key=lambda item: item.get("createdAt", 0), reverse=True)
        return entries

    async def prepare_download(self, transfer_id: str, username: str) -> Tuple[Path, DirectTransferEntry]:
        """Prepare a transfer for download and remove it from the queue."""

        async with self._lock:
            self._prune_locked()
            entry = self._entries.get(transfer_id)
            if not entry:
                raise DirectTransferError("Transfer not found", status_code=404)

            if entry.recipient != username:
                raise DirectTransferError("You do not have access to this transfer", status_code=403)

            payload_path = self.base_dir / entry.stored_filename
            if not payload_path.exists():
                self._entries.pop(transfer_id, None)
                self._save_locked()
                raise DirectTransferError("Transfer payload is no longer available", status_code=404)

            self._entries.pop(transfer_id, None)
            self._save_locked()

        return payload_path, entry

    def cleanup_after_download(self, entry: DirectTransferEntry) -> None:
        """Cleanup payload after a download completes."""

        self._delete_file(self.base_dir / entry.stored_filename)
        logger.info(
            "Direct transfer %s delivered to %s", entry.id, entry.recipient
        )

    async def delete_transfer(self, transfer_id: str, username: str) -> DirectTransferEntry:
        """Remove a transfer without downloading it."""

        async with self._lock:
            self._prune_locked()
            entry = self._entries.get(transfer_id)
            if not entry:
                raise DirectTransferError("Transfer not found", status_code=404)

            if username not in {entry.sender, entry.recipient}:
                raise DirectTransferError("You do not have access to this transfer", status_code=403)

            self._entries.pop(transfer_id, None)
            self._save_locked()

        self._delete_file(self.base_dir / entry.stored_filename)
        logger.info("Direct transfer %s removed by %s", transfer_id, username)
        return entry


direct_transfer_store = DirectTransferStore()

__all__ = ["direct_transfer_store", "DirectTransferStore", "DirectTransferError"]
