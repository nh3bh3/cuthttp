"""Persistent overrides for share settings such as quotas."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

STORE_PATH = Path("data/shares.json")


def _default_store() -> Dict[str, Dict[str, Dict]]:
    return {"shares": {}}


def _load_store() -> Dict[str, Dict[str, Dict]]:
    try:
        if not STORE_PATH.exists():
            return _default_store()

        with STORE_PATH.open("r", encoding="utf-8") as fh:
            data = json.load(fh)

        if not isinstance(data, dict):
            logger.warning("Invalid share store structure; resetting store")
            return _default_store()

        data.setdefault("shares", {})
        if not isinstance(data["shares"], dict):
            logger.warning("Invalid shares entry in store; resetting store")
            data["shares"] = {}

        return data
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse share store JSON: %s", exc)
        return _default_store()
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Unexpected error loading share store: %s", exc)
        return _default_store()


def _atomic_write(data: Dict[str, Dict[str, Dict]]):
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = STORE_PATH.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    tmp_path.replace(STORE_PATH)


def load_share_overrides() -> Dict[str, Dict[str, int]]:
    """Return all stored share overrides."""

    return _load_store().get("shares", {})


def set_share_quota_override(share_name: str, quota_bytes: Optional[int]) -> None:
    """Persist a quota override for the given share."""

    store = _load_store()
    shares = store.setdefault("shares", {})
    if quota_bytes is None:
        if share_name in shares:
            del shares[share_name]
    else:
        shares[share_name] = {"quota_bytes": int(quota_bytes)}
    _atomic_write(store)


__all__ = [
    "load_share_overrides",
    "set_share_quota_override",
]
