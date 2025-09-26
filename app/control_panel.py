"""Utilities for assembling the server-side control panel payload."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import platform
import shutil
import socket
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Union

from .config import get_config
from .ipfilter import parse_cidr
from .metrics import metrics_manager
from .quota import quota_manager
from .user_store import list_registered_usernames
from .utils import format_file_size
from .server_store import get_custom_urls

logger = logging.getLogger(__name__)

# Common private network ranges that should stay reachable inside a LAN
Network = Union[ipaddress.IPv4Network, ipaddress.IPv6Network]
_PRIVATE_NETWORKS: Tuple[Network, ...] = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local
    ipaddress.ip_network("fc00::/7"),  # unique local IPv6 addresses
)


def _format_host(address: str) -> str:
    """Return host formatted for URLs, wrapping IPv6 in brackets."""

    if ":" in address and not address.startswith("["):
        return f"[{address}]"
    return address


def _safe_disk_usage(path: Path) -> Optional[Dict[str, int]]:
    """Return disk usage statistics for the given path if available."""

    try:
        target = path if path.exists() else path.parent
        if not target.exists():
            return None
        usage = shutil.disk_usage(target)
        return {
            "total": usage.total,
            "used": usage.total - usage.free,
            "free": usage.free,
        }
    except OSError as exc:
        logger.debug("Failed to read disk usage for \%s: %s", path, exc)
        return None


async def _share_status(share) -> Dict[str, Any]:
    """Build share status payload."""

    path = Path(share.path)
    exists = path.exists()
    status = {
        "name": share.name,
        "path": str(path),
        "exists": exists,
        "readable": os.access(path, os.R_OK) if exists else False,
        "writable": os.access(path, os.W_OK) if exists else False,
    }

    disk = _safe_disk_usage(path)
    if disk:
        status["disk"] = disk

    usage = await quota_manager.get_usage(share, force=not exists)
    status["usage"] = {
        "bytes": usage,
        "display": format_file_size(usage),
    }

    quota_info = quota_manager.describe_quota(share, usage)
    status["quota"] = quota_info
    status["quota_enabled"] = quota_info is not None

    return status


def _discover_local_addresses() -> List[str]:
    """Try to discover non-loopback addresses for quick LAN access."""

    addresses: Set[str] = set()

    # Resolve hostname interfaces
    hostname = socket.gethostname()
    for family in (socket.AF_INET, socket.AF_INET6):
        try:
            infos = socket.getaddrinfo(hostname, None, family, socket.SOCK_STREAM)
        except socket.gaierror:
            continue

        for info in infos:
            addr = info[4][0]
            if not addr:
                continue

            if family == socket.AF_INET:
                if addr.startswith("127."):
                    continue
                addresses.add(addr)
            else:
                if addr.startswith("::1"):
                    continue
                addr = addr.split("%", 1)[0]  # strip scope
                addresses.add(addr)

    # UDP connect trick to learn outbound interface
    for target in (("8.8.8.8", 80), ("1.1.1.1", 80)):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(target)
                addr = sock.getsockname()[0]
                if not addr.startswith("127."):
                    addresses.add(addr)
        except OSError:
            continue

    if not addresses:
        addresses.add("127.0.0.1")

    return sorted(addresses)


def _overlaps_private(network: Network) -> bool:
    for private in _PRIVATE_NETWORKS:
        if network.version != private.version:
            continue
        if network.overlaps(private):
            return True
    return False


def _summarize_ip_filter(allow_list: Iterable[str], deny_list: Iterable[str]) -> Dict[str, Any]:
    allow_networks = [parse_cidr(entry) for entry in allow_list or []]
    allow_networks = [net for net in allow_networks if net is not None]

    deny_networks = [parse_cidr(entry) for entry in deny_list or []]
    deny_networks = [net for net in deny_networks if net is not None]

    has_allow_rules = bool(allow_networks)
    lan_allowing = [str(net) for net in allow_networks if _overlaps_private(net)]
    lan_blocking = [str(net) for net in deny_networks if _overlaps_private(net)]

    lan_access = (not has_allow_rules or bool(lan_allowing)) and not lan_blocking

    return {
        "allow": list(allow_list or []),
        "deny": list(deny_list or []),
        "allow_count": len(allow_networks),
        "deny_count": len(deny_networks),
        "mode": "allowlist" if has_allow_rules else "deny-only",
        "lan_allowed": lan_access,
        "lan_allowing_rules": lan_allowing,
        "lan_blocking_rules": lan_blocking,
    }


def _summarize_users(config) -> List[Dict[str, Any]]:
    dynamic = set(list_registered_usernames())
    users: List[Dict[str, Any]] = []
    for entry in config.users:
        users.append(
            {
                "name": entry.name,
                "dynamic": entry.name in dynamic,
                "is_bcrypt": entry.is_bcrypt,
            }
        )
    users.sort(key=lambda item: item["name"].lower())
    return users


async def build_control_panel_state(current_user: str) -> Dict[str, Any]:
    """Return the payload consumed by the front-end control panel."""

    config = get_config()
    metrics = metrics_manager.get_metrics()

    scheme = "https" if config.server.tls.enabled else "http"
    lan_addresses = _discover_local_addresses()

    lan_urls: List[str] = [
        f"{scheme}://{_format_host(address)}:{config.server.port}" for address in lan_addresses
    ]

    bind_all = config.server.addr in {"0.0.0.0", "::"}
    if not bind_all:
        lan_urls.insert(0, f"{scheme}://{_format_host(config.server.addr)}:{config.server.port}")

    shares = await asyncio.gather(*(_share_status(share) for share in config.shares))

    return {
        "user": {"name": current_user},
        "server": {
            "host": config.server.addr,
            "port": config.server.port,
            "scheme": scheme,
            "bind_all_interfaces": bind_all,
            "lan_urls": lan_urls,
            "custom_urls": get_custom_urls(),
        },
        "shares": shares,
        "metrics": metrics,
        "ip_filter": _summarize_ip_filter(config.ipFilter.allow, config.ipFilter.deny),
        "environment": {
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "working_directory": str(Path.cwd()),
        },
        "users": _summarize_users(config),
    }
