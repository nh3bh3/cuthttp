"""Persistent storage for server-related overrides."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable, List

logger = logging.getLogger(__name__)

STORE_PATH = Path("data/server.json")


def _load_store() -> dict:
    try:
        if not STORE_PATH.exists():
            return {"custom_urls": []}
        with STORE_PATH.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            logger.warning("Invalid server override store; resetting")
            return {"custom_urls": []}
        urls = data.get("custom_urls", [])
        if not isinstance(urls, list):
            logger.warning("Invalid custom_urls entry in server store; resetting")
            urls = []
        return {"custom_urls": [str(url) for url in urls]}
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse server override store: %s", exc)
        return {"custom_urls": []}
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Unexpected error loading server overrides: %s", exc)
        return {"custom_urls": []}


def _atomic_write(data: dict) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = STORE_PATH.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    tmp_path.replace(STORE_PATH)


def get_custom_urls() -> List[str]:
    """Return the persisted custom URLs, if any."""

    return _load_store().get("custom_urls", [])


def set_custom_urls(urls: Iterable[str]) -> List[str]:
    """Persist the provided list of custom URLs."""

    normalized = [str(url) for url in urls]
    store = {"custom_urls": normalized}
    _atomic_write(store)
    return normalized


__all__ = ["get_custom_urls", "set_custom_urls"]
