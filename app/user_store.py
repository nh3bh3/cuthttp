"""Utility module for managing dynamically registered users."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Tuple

from .models import Permission, RuleInfo, UserInfo

logger = logging.getLogger(__name__)

STORE_PATH = Path("data/users.json")


def _default_store() -> Dict[str, List[Dict]]:
    """Return the default empty store structure."""
    return {"users": []}


def _load_store() -> Dict[str, List[Dict]]:
    """Load the dynamic user store from disk."""
    try:
        if not STORE_PATH.exists():
            return _default_store()

        with STORE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            logger.warning("Invalid user store structure; resetting store")
            return _default_store()

        data.setdefault("users", [])
        if not isinstance(data["users"], list):
            logger.warning("Invalid users list in store; resetting store")
            data["users"] = []
        return data
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse user store JSON: %s", exc)
        return _default_store()
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Unexpected error loading user store: %s", exc)
        return _default_store()


def _atomic_write(data: Dict[str, List[Dict]]):
    """Write store data atomically to disk."""
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = STORE_PATH.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp_path.replace(STORE_PATH)


def load_registered_entries() -> Tuple[List[UserInfo], List[RuleInfo]]:
    """Load registered users and their rules from the dynamic store."""
    store = _load_store()
    users: List[UserInfo] = []
    rules: List[RuleInfo] = []

    for entry in store.get("users", []):
        try:
            name = entry.get("name")
            pass_hash = entry.get("pass_hash")
            is_bcrypt = entry.get("is_bcrypt", True)
            if not name or not pass_hash:
                continue

            users.append(UserInfo(name=name, pass_hash=pass_hash, is_bcrypt=is_bcrypt))

            for rule_data in entry.get("rules", []):
                try:
                    allow_values = rule_data.get("allow", [Permission.READ.value])
                    allow = [Permission(value) for value in allow_values]
                except ValueError:
                    logger.warning("Invalid permission in rule for user %s", name)
                    allow = [Permission.READ]

                rule = RuleInfo(
                    who=name,
                    allow=allow,
                    roots=rule_data.get("roots", []),
                    paths=rule_data.get("paths", ["/"]),
                    ip_allow=rule_data.get("ip_allow", ["*"]),
                    ip_deny=rule_data.get("ip_deny", []),
                )
                rules.append(rule)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Failed to load user entry: %s", exc)
            continue

    return users, rules


def add_registered_user(
    username: str,
    pass_hash: str,
    roots: List[str],
    *,
    permissions: List[Permission] | None = None,
    paths: List[str] | None = None,
    ip_allow: List[str] | None = None,
    ip_deny: List[str] | None = None,
) -> Tuple[UserInfo, List[RuleInfo]]:
    """Add a new registered user to the dynamic store.

    Returns the created user info and associated rules.
    """

    store = _load_store()
    username_lower = username.lower()
    for entry in store.get("users", []):
        if str(entry.get("name", "")).lower() == username_lower:
            raise ValueError("User already exists")

    permissions = permissions or [Permission.READ, Permission.WRITE, Permission.DELETE]
    paths = paths or ["/"]
    ip_allow = ip_allow or ["*"]
    ip_deny = ip_deny or []

    user_entry = {
        "name": username,
        "pass_hash": pass_hash,
        "is_bcrypt": True,
        "rules": [
            {
                "allow": [perm.value for perm in permissions],
                "roots": roots,
                "paths": paths,
                "ip_allow": ip_allow,
                "ip_deny": ip_deny,
            }
        ],
    }

    store.setdefault("users", []).append(user_entry)
    _atomic_write(store)

    user = UserInfo(name=username, pass_hash=pass_hash, is_bcrypt=True)
    rule = RuleInfo(
        who=username,
        allow=list(permissions),
        roots=roots,
        paths=paths,
        ip_allow=ip_allow,
        ip_deny=ip_deny,
    )

    return user, [rule]
