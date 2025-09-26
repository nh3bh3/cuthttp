"""Share quota management utilities."""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from .models import ShareInfo
from .utils import format_file_size


@dataclass
class ShareQuotaExceededError(Exception):
    """Raised when a share exceeds its configured quota."""

    share: str
    quota_bytes: int
    usage_bytes: int

    def __post_init__(self):
        limit = format_file_size(self.quota_bytes)
        used = format_file_size(self.usage_bytes)
        super().__init__(
            f"Share '{self.share}' quota exceeded: {used} used / {limit} limit"
        )


class ShareQuotaManager:
    """Helper that keeps track of share usage for quota enforcement."""

    def __init__(self):
        self._cache: Dict[str, tuple[float, int]] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._locks_guard = asyncio.Lock()

    async def _get_lock(self, share_name: str) -> asyncio.Lock:
        async with self._locks_guard:
            lock = self._locks.get(share_name)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[share_name] = lock
            return lock

    async def _calculate_usage(self, share: ShareInfo) -> int:
        path = Path(share.path)

        def _walk(target: Path) -> int:
            if not target.exists():
                return 0

            total = 0
            for root, _, files in os.walk(target):
                for filename in files:
                    file_path = Path(root) / filename
                    try:
                        total += file_path.stat().st_size
                    except OSError:
                        continue
            return total

        return await asyncio.to_thread(_walk, path)

    async def get_usage(self, share: ShareInfo, *, force: bool = False) -> int:
        """Return current share usage in bytes."""

        lock = await self._get_lock(share.name)
        async with lock:
            if not force and share.name in self._cache:
                return self._cache[share.name][1]

            usage = await self._calculate_usage(share)
            self._cache[share.name] = (time.time(), usage)
            return usage

    async def refresh_usage(self, share: ShareInfo) -> int:
        """Force-refresh usage for a share and return the new value."""

        return await self.get_usage(share, force=True)

    def invalidate(self, share_name: str) -> None:
        """Invalidate cached usage for a share."""

        self._cache.pop(share_name, None)

    def ensure_within_quota(self, share: ShareInfo, usage: int) -> None:
        """Raise if usage exceeds the configured quota."""

        if share.quota_bytes is None:
            return

        if usage > share.quota_bytes:
            raise ShareQuotaExceededError(share=share.name, quota_bytes=share.quota_bytes, usage_bytes=usage)

    def describe_quota(self, share: ShareInfo, usage: int) -> Optional[Dict[str, Any]]:
        """Return helper values describing quota state for UI payloads."""

        if share.quota_bytes is None:
            return None

        limit = share.quota_bytes
        remaining = max(limit - usage, 0)
        percent = 100.0 if limit == 0 else min((usage / limit) * 100.0, 100.0)
        return {
            "limit": limit,
            "limit_display": format_file_size(limit),
            "used": usage,
            "used_display": format_file_size(usage),
            "remaining": remaining,
            "remaining_display": format_file_size(remaining),
            "percent_used": percent,
            "over": usage > limit,
        }


quota_manager = ShareQuotaManager()

__all__ = [
    "ShareQuotaManager",
    "ShareQuotaExceededError",
    "quota_manager",
]
