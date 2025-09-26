"""
Tests for IP filtering with CIDR support
"""

import pytest
from app.ipfilter import (
    parse_cidr, check_ip_allowed, IpFilter, 
    is_private_ip, is_loopback_ip, normalize_ip
)


class TestCidrParsing:
    """Test CIDR notation parsing"""
    
    def test_parse_ipv4_cidr(self):
        """Test parsing IPv4 CIDR notation"""
        
        # Standard CIDR
        network = parse_cidr("192.168.1.0/24")
        assert network is not None
        assert str(network) == "192.168.1.0/24"
        
        # Single host
        network = parse_cidr("192.168.1.100/32")
        assert network is not None
        assert str(network) == "192.168.1.100/32"
        
        # Large network
        network = parse_cidr("10.0.0.0/8")
        assert network is not None
        assert str(network) == "10.0.0.0/8"
        
        # Small network
        network = parse_cidr("192.168.1.0/30")
        assert network is not None
        assert str(network) == "192.168.1.0/30"
    
    def test_parse_ipv6_cidr(self):
        """Test parsing IPv6 CIDR notation"""
        
        # Standard IPv6
        network = parse_cidr("2001:db8::/32")
        assert network is not None
        assert "2001:db8::" in str(network)
        
        # Loopback
        network = parse_cidr("::1/128")
        assert network is not None
        assert "::1" in str(network)
        
        # Full IPv6
        network = parse_cidr("2001:0db8:85a3:0000:0000:8a2e:0370:7334/128")
        assert network is not None
    
    def test_parse_single_ip(self):
        """Test parsing single IP addresses without CIDR"""
        
        # IPv4 single IP
        network = parse_cidr("192.168.1.100")
        assert network is not None
        assert str(network) == "192.168.1.100/32"
        
        # IPv6 single IP
        network = parse_cidr("::1")
        assert network is not None
        assert "/128" in str(network)
        
        # Localhost
        network = parse_cidr("127.0.0.1")
        assert network is not None
        assert str(network) == "127.0.0.1/32"
    
    def test_parse_wildcard(self):
        """Test parsing wildcard notation"""
        
        network = parse_cidr("*")
        assert network is not None
        assert str(network) == "0.0.0.0/0"
    
    def test_parse_invalid_cidr(self):
        """Test parsing invalid CIDR notation"""
        
        # Invalid IP
        assert parse_cidr("999.999.999.999/24") is None
        
        # Invalid subnet mask
        assert parse_cidr("192.168.1.0/99") is None
        
        # Invalid format
        assert parse_cidr("192.168.1.0/24/extra") is None
        assert parse_cidr("not-an-ip") is None
        assert parse_cidr("") is None
        
        # Missing parts
        assert parse_cidr("192.168./24") is None


class TestIpFiltering:
    """Test IP filtering logic"""
    
    def test_basic_allow_list(self):
        """Test basic allow list functionality"""
        
        allow_list = ["192.168.1.0/24", "10.0.0.0/8"]
        deny_list = []
        
        # Should allow IPs in range
        assert check_ip_allowed("192.168.1.100", allow_list, deny_list)
        assert check_ip_allowed("192.168.1.1", allow_list, deny_list)
        assert check_ip_allowed("10.0.0.1", allow_list, deny_list)
        assert check_ip_allowed("10.255.255.255", allow_list, deny_list)
        
        # Should deny IPs not in range
        assert not check_ip_allowed("192.168.2.100", allow_list, deny_list)
        assert not check_ip_allowed("172.16.0.1", allow_list, deny_list)
        assert not check_ip_allowed("8.8.8.8", allow_list, deny_list)
    
    def test_basic_deny_list(self):
        """Test basic deny list functionality"""
        
        allow_list = []  # Empty allow list means allow all
        deny_list = ["192.168.1.0/24", "10.0.0.0/8"]
        
        # Should deny IPs in deny list
        assert not check_ip_allowed("192.168.1.100", allow_list, deny_list)
        assert not check_ip_allowed("10.0.0.1", allow_list, deny_list)
        
        # Should allow IPs not in deny list
        assert check_ip_allowed("172.16.0.1", allow_list, deny_list)
        assert check_ip_allowed("8.8.8.8", allow_list, deny_list)
    
    def test_allow_and_deny_lists(self):
        """Test combination of allow and deny lists"""
        
        allow_list = ["192.168.0.0/16"]  # Allow all 192.168.x.x
        deny_list = ["192.168.1.0/24"]  # But deny 192.168.1.x
        
        # Should allow IPs in allow list but not in deny list
        assert check_ip_allowed("192.168.2.100", allow_list, deny_list)
        assert check_ip_allowed("192.168.100.1", allow_list, deny_list)
        
        # Should deny IPs in deny list (even if in allow list)
        assert not check_ip_allowed("192.168.1.100", allow_list, deny_list)
        assert not check_ip_allowed("192.168.1.1", allow_list, deny_list)
        
        # Should deny IPs not in allow list
        assert not check_ip_allowed("10.0.0.1", allow_list, deny_list)
    
    def test_wildcard_allow(self):
        """Test wildcard in allow list"""
        
        allow_list = ["*"]
        deny_list = ["192.168.1.0/24"]
        
        # Should allow most IPs
        assert check_ip_allowed("8.8.8.8", allow_list, deny_list)
        assert check_ip_allowed("1.1.1.1", allow_list, deny_list)
        
        # But still deny IPs in deny list
        assert not check_ip_allowed("192.168.1.100", allow_list, deny_list)
    
    def test_localhost_patterns(self):
        """Test common localhost patterns"""
        
        allow_list = ["127.0.0.1/32", "::1/128"]
        deny_list = []
        
        # Should allow localhost
        assert check_ip_allowed("127.0.0.1", allow_list, deny_list)
        assert check_ip_allowed("::1", allow_list, deny_list)
        
        # Should deny other IPs
        assert not check_ip_allowed("127.0.0.2", allow_list, deny_list)
        assert not check_ip_allowed("192.168.1.1", allow_list, deny_list)
    
    def test_private_network_patterns(self):
        """Test common private network patterns"""
        
        allow_list = [
            "127.0.0.1/32",      # Localhost
            "10.0.0.0/8",        # Private Class A
            "172.16.0.0/12",     # Private Class B
            "192.168.0.0/16",    # Private Class C
            "::1/128"            # IPv6 localhost
        ]
        deny_list = []
        
        # Should allow private IPs
        assert check_ip_allowed("127.0.0.1", allow_list, deny_list)
        assert check_ip_allowed("10.0.0.1", allow_list, deny_list)
        assert check_ip_allowed("172.16.0.1", allow_list, deny_list)
        assert check_ip_allowed("192.168.1.1", allow_list, deny_list)
        assert check_ip_allowed("::1", allow_list, deny_list)
        
        # Should deny public IPs
        assert not check_ip_allowed("8.8.8.8", allow_list, deny_list)
        assert not check_ip_allowed("1.1.1.1", allow_list, deny_list)
    
    def test_empty_lists(self):
        """Test behavior with empty allow/deny lists"""
        
        # Empty allow list means allow all (if no deny rules apply)
        assert check_ip_allowed("8.8.8.8", [], [])
        assert check_ip_allowed("192.168.1.1", [], [])
        
        # Empty allow list with deny rules
        assert not check_ip_allowed("192.168.1.1", [], ["192.168.1.0/24"])
        assert check_ip_allowed("8.8.8.8", [], ["192.168.1.0/24"])
    
    def test_invalid_ips(self):
        """Test handling of invalid IP addresses"""
        
        allow_list = ["192.168.1.0/24"]
        deny_list = []
        
        # Invalid IPs should be denied
        assert not check_ip_allowed("", allow_list, deny_list)
        assert not check_ip_allowed("invalid-ip", allow_list, deny_list)
        assert not check_ip_allowed("999.999.999.999", allow_list, deny_list)
        assert not check_ip_allowed(None, allow_list, deny_list)


class TestIpFilterClass:
    """Test IpFilter class"""
    
    def test_ip_filter_creation(self):
        """Test creating IpFilter instances"""
        
        # Default filter (allow all)
        filter1 = IpFilter()
        assert filter1.is_allowed("8.8.8.8")
        assert filter1.is_allowed("192.168.1.1")
        
        # Filter with allow list
        filter2 = IpFilter(allow_list=["192.168.1.0/24"])
        assert filter2.is_allowed("192.168.1.100")
        assert not filter2.is_allowed("8.8.8.8")
        
        # Filter with deny list
        filter3 = IpFilter(deny_list=["192.168.1.0/24"])
        assert not filter3.is_allowed("192.168.1.100")
        assert filter3.is_allowed("8.8.8.8")
    
    def test_ip_filter_update_rules(self):
        """Test updating filter rules"""
        
        ip_filter = IpFilter()
        
        # Initially allows all
        assert ip_filter.is_allowed("8.8.8.8")
        
        # Update to restrict
        ip_filter.update_rules(allow_list=["192.168.1.0/24"])
        assert ip_filter.is_allowed("192.168.1.100")
        assert not ip_filter.is_allowed("8.8.8.8")
        
        # Update deny list
        ip_filter.update_rules(deny_list=["192.168.1.100/32"])
        assert not ip_filter.is_allowed("192.168.1.100")  # Now denied
        assert ip_filter.is_allowed("192.168.1.101")      # Still allowed
    
    def test_ip_filter_get_rules(self):
        """Test getting current rules"""
        
        allow_list = ["192.168.1.0/24", "10.0.0.0/8"]
        deny_list = ["192.168.1.100/32"]
        
        ip_filter = IpFilter(allow_list=allow_list, deny_list=deny_list)
        rules = ip_filter.get_rules()
        
        assert rules["allow"] == allow_list
        assert rules["deny"] == deny_list
        
        # Should return copies, not references
        rules["allow"].append("new-rule")
        assert len(ip_filter.get_rules()["allow"]) == 2  # Original unchanged


class TestIpUtilities:
    """Test IP utility functions"""
    
    def test_is_private_ip(self):
        """Test private IP detection"""
        
        # Private IPv4 ranges
        assert is_private_ip("10.0.0.1")
        assert is_private_ip("172.16.0.1")
        assert is_private_ip("192.168.1.1")
        
        # Public IPv4
        assert not is_private_ip("8.8.8.8")
        assert not is_private_ip("1.1.1.1")
        
        # Localhost is considered private
        assert is_private_ip("127.0.0.1")
        
        # Invalid IP
        assert not is_private_ip("invalid-ip")
    
    def test_is_loopback_ip(self):
        """Test loopback IP detection"""
        
        # IPv4 loopback
        assert is_loopback_ip("127.0.0.1")
        assert is_loopback_ip("127.0.0.2")
        assert is_loopback_ip("127.255.255.255")
        
        # IPv6 loopback
        assert is_loopback_ip("::1")
        
        # Not loopback
        assert not is_loopback_ip("192.168.1.1")
        assert not is_loopback_ip("8.8.8.8")
        
        # Invalid IP
        assert not is_loopback_ip("invalid-ip")
    
    def test_normalize_ip(self):
        """Test IP address normalization"""
        
        # IPv4 addresses (should remain unchanged)
        assert normalize_ip("192.168.1.1") == "192.168.1.1"
        assert normalize_ip("127.0.0.1") == "127.0.0.1"
        
        # IPv6 addresses (may be normalized)
        assert normalize_ip("::1") == "::1"
        
        # Invalid IP (should return as-is)
        assert normalize_ip("invalid-ip") == "invalid-ip"
        assert normalize_ip("") == ""
    
    def test_predefined_filters(self):
        """Test predefined filter configurations"""
        
        from app.ipfilter import LOCALHOST_ONLY, PRIVATE_NETWORKS, ALLOW_ALL, DENY_ALL
        
        # Localhost only
        assert LOCALHOST_ONLY.is_allowed("127.0.0.1")
        assert LOCALHOST_ONLY.is_allowed("::1")
        assert not LOCALHOST_ONLY.is_allowed("192.168.1.1")
        
        # Private networks
        assert PRIVATE_NETWORKS.is_allowed("127.0.0.1")
        assert PRIVATE_NETWORKS.is_allowed("192.168.1.1")
        assert PRIVATE_NETWORKS.is_allowed("10.0.0.1")
        assert not PRIVATE_NETWORKS.is_allowed("8.8.8.8")
        
        # Allow all
        assert ALLOW_ALL.is_allowed("8.8.8.8")
        assert ALLOW_ALL.is_allowed("192.168.1.1")
        
        # Deny all
        assert not DENY_ALL.is_allowed("8.8.8.8")
        assert not DENY_ALL.is_allowed("192.168.1.1")
        assert not DENY_ALL.is_allowed("127.0.0.1")
