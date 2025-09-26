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


def check_ip_allowed(ip_str: str, allow_list: List[str], deny_list: List[str]) -> bool:
    """
    Check if IP is allowed based on allow/deny lists
    
    Logic:
    1. If allow_list is empty, allow all IPs by default
    2. If allow_list is not empty, IP must match at least one allow rule
    3. If IP matches any deny rule, it's denied (deny takes precedence)
    
    Args:
        ip_str: IP address to check
        allow_list: List of allowed CIDR patterns
        deny_list: List of denied CIDR patterns
        
    Returns:
        True if IP is allowed, False otherwise
    """
    
    if not ip_str:
        return False
    
    # Parse allow rules
    allow_networks = []
    for allow_rule in allow_list:
        network = parse_cidr(allow_rule)
        if network:
            allow_networks.append(network)
    
    # Parse deny rules
    deny_networks = []
    for deny_rule in deny_list:
        network = parse_cidr(deny_rule)
        if network:
            deny_networks.append(network)
    
    # Check deny rules first (deny takes precedence)
    for network in deny_networks:
        if ip_in_network(ip_str, network):
            logger.debug(f"IP {ip_str} denied by rule: {network}")
            return False
    
    # If no allow rules, allow by default (after checking deny rules)
    if not allow_networks:
        return True
    
    # Check allow rules
    for network in allow_networks:
        if ip_in_network(ip_str, network):
            logger.debug(f"IP {ip_str} allowed by rule: {network}")
            return True
    
    # IP not in any allow rule
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
