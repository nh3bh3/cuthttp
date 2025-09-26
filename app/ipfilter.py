"""
IP filtering with CIDR support for chfs-py
"""

import ipaddress
import logging
from typing import List, Union

logger = logging.getLogger(__name__)


def parse_cidr(cidr_str: str) -> Union[ipaddress.IPv4Network, ipaddress.IPv6Network, None]:
    """Parse CIDR notation string to IP network object"""
    try:
        # Handle wildcard
        if cidr_str == "*":
            return ipaddress.IPv4Network("0.0.0.0/0")
        
        # Handle single IP without subnet mask
        if '/' not in cidr_str:
            # Try to determine if it's IPv4 or IPv6
            try:
                ip = ipaddress.ip_address(cidr_str)
                if isinstance(ip, ipaddress.IPv4Address):
                    return ipaddress.IPv4Network(f"{cidr_str}/32")
                else:
                    return ipaddress.IPv6Network(f"{cidr_str}/128")
            except ValueError:
                return None
        
        # Parse as network
        return ipaddress.ip_network(cidr_str, strict=False)
        
    except ValueError as e:
        logger.warning(f"Invalid CIDR notation: {cidr_str} - {e}")
        return None


def ip_in_network(ip_str: str, network: Union[ipaddress.IPv4Network, ipaddress.IPv6Network]) -> bool:
    """Check if IP address is in network"""
    try:
        ip = ipaddress.ip_address(ip_str)
        return ip in network
    except ValueError:
        return False


def _parse_networks(cidr_list: List[str]):
    """Parse CIDR list into network objects while preserving order."""

    networks = []
    for cidr in cidr_list:
        network = parse_cidr(cidr)
        if network:
            networks.append(network)
    return networks


def _get_most_specific(networks, ip_obj):
    """Return the most specific network from list that matches the IP."""

    matching = [net for net in networks if ip_obj in net and net.version == ip_obj.version]
    if not matching:
        return None

    # Larger prefix length means more specific network
    return max(matching, key=lambda net: net.prefixlen)


def check_ip_allowed(ip_str: str, allow_list: List[str], deny_list: List[str]) -> bool:
    """Return True if the client IP should be allowed access.

    The evaluation honours both allow and deny lists with deterministic behaviour:

    * If the IP matches an entry in the allow list, it is permitted unless a more
      specific deny rule also matches.
    * If the IP does not match any allow rule but matches a deny rule, it is
      rejected.
    * When no allow list is defined the filter works as a classic deny-list, i.e.
      every IP is allowed unless it matches a deny rule.
    """

    if not ip_str:
        return False

    try:
        ip_obj = ipaddress.ip_address(ip_str)
    except ValueError:
        return False

    allow_networks = _parse_networks(allow_list)
    deny_networks = _parse_networks(deny_list)

    most_specific_allow = _get_most_specific(allow_networks, ip_obj)
    most_specific_deny = _get_most_specific(deny_networks, ip_obj)

    if most_specific_allow:
        if not most_specific_deny:
            logger.debug(f"IP {ip_str} allowed by rule: {most_specific_allow}")
            return True

        # If both lists match we favour the most specific rule.
        if most_specific_allow.prefixlen >= most_specific_deny.prefixlen:
            logger.debug(
                "IP %s allowed by more specific rule: allow %s overrides deny %s",
                ip_str,
                most_specific_allow,
                most_specific_deny,
            )
            return True

        logger.debug(
            "IP %s denied by more specific rule: deny %s overrides allow %s",
            ip_str,
            most_specific_deny,
            most_specific_allow,
        )
        return False

    if most_specific_deny:
        logger.debug(f"IP {ip_str} denied by rule: {most_specific_deny}")
        return False

    # No allow rule matched. If allow list is empty treat as deny-based filter.
    if not allow_networks:
        return True

    logger.debug(f"IP {ip_str} not in any allow rule")
    return False


def validate_cidr_list(cidr_list: List[str]) -> List[str]:
    """Validate and filter CIDR list, return valid ones"""
    valid_cidrs = []
    for cidr in cidr_list:
        if parse_cidr(cidr) is not None:
            valid_cidrs.append(cidr)
        else:
            logger.warning(f"Invalid CIDR pattern ignored: {cidr}")
    return valid_cidrs


class IpFilter:
    """IP filter with configurable allow/deny lists"""
    
    def __init__(self, allow_list: List[str] = None, deny_list: List[str] = None):
        self.allow_list = validate_cidr_list(allow_list or [])
        self.deny_list = validate_cidr_list(deny_list or [])
    
    def is_allowed(self, ip_str: str) -> bool:
        """Check if IP is allowed"""
        return check_ip_allowed(ip_str, self.allow_list, self.deny_list)
    
    def update_rules(self, allow_list: List[str] = None, deny_list: List[str] = None):
        """Update filter rules"""
        if allow_list is not None:
            self.allow_list = validate_cidr_list(allow_list)
        if deny_list is not None:
            self.deny_list = validate_cidr_list(deny_list)
    
    def get_rules(self) -> dict:
        """Get current rules"""
        return {
            "allow": self.allow_list.copy(),
            "deny": self.deny_list.copy()
        }


def get_client_ip(request) -> str:
    """Extract client IP from request, considering proxies"""
    
    # Check X-Forwarded-For header (proxy)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take the first IP (original client)
        return forwarded_for.split(",")[0].strip()
    
    # Check X-Real-IP header (nginx)
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    
    # Check CF-Connecting-IP header (Cloudflare)
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip.strip()
    
    # Fall back to direct connection IP
    if request.client:
        return request.client.host
    
    return "unknown"


def is_private_ip(ip_str: str) -> bool:
    """Check if IP is in private address space"""
    try:
        ip = ipaddress.ip_address(ip_str)
        return ip.is_private
    except ValueError:
        return False


def is_loopback_ip(ip_str: str) -> bool:
    """Check if IP is loopback address"""
    try:
        ip = ipaddress.ip_address(ip_str)
        return ip.is_loopback
    except ValueError:
        return False


def normalize_ip(ip_str: str) -> str:
    """Normalize IP address string"""
    try:
        ip = ipaddress.ip_address(ip_str)
        return str(ip)
    except ValueError:
        return ip_str


# Common IP filter presets
LOCALHOST_ONLY = IpFilter(allow_list=["127.0.0.1/32", "::1/128"])
PRIVATE_NETWORKS = IpFilter(allow_list=["127.0.0.1/32", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "::1/128"])
ALLOW_ALL = IpFilter(allow_list=["*"])
DENY_ALL = IpFilter(deny_list=["0.0.0.0/0", "::/0"])
