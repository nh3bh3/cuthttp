"""
Tests for access control rules evaluation
"""

import pytest
from app.models import Permission, RuleInfo, UserInfo
from app.rules import RuleEvaluator


class TestRuleEvaluator:
    """Test access control rule evaluation"""
    
    def setup_method(self):
        """Setup test data"""
        self.evaluator = RuleEvaluator()
        
        # Test users
        self.alice = UserInfo(name="alice", pass_hash="alice123", is_bcrypt=False)
        self.bob = UserInfo(name="bob", pass_hash="bob123", is_bcrypt=False)
        
        # Test rules
        self.rules = [
            # Alice has full access to public and home
            RuleInfo(
                who="alice",
                allow=[Permission.READ, Permission.WRITE, Permission.DELETE],
                roots=["public", "home"],
                paths=["/"],
                ip_allow=["*"],
                ip_deny=[]
            ),
            # Bob has read-only access to public
            RuleInfo(
                who="bob",
                allow=[Permission.READ],
                roots=["public"],
                paths=["/"],
                ip_allow=["192.168.1.0/24", "127.0.0.1/32"],
                ip_deny=[]
            ),
            # Wildcard user with limited access
            RuleInfo(
                who="*",
                allow=[Permission.READ],
                roots=["public"],
                paths=["/readonly"],
                ip_allow=["127.0.0.1/32"],
                ip_deny=[]
            )
        ]
        
        # Mock config
        from unittest.mock import Mock
        mock_config = Mock()
        mock_config.rules = self.rules
        
        # Patch get_config
        import app.rules
        app.rules.get_config = lambda: mock_config
    
    def test_alice_full_access(self):
        """Test Alice's full access permissions"""
        
        # Alice can read from public
        allowed, reason = self.evaluator.evaluate(
            self.alice, Permission.READ, "public", "/test.txt", "127.0.0.1"
        )
        assert allowed
        assert "granted" in reason.lower()
        
        # Alice can write to public
        allowed, reason = self.evaluator.evaluate(
            self.alice, Permission.WRITE, "public", "/test.txt", "127.0.0.1"
        )
        assert allowed
        
        # Alice can delete from public
        allowed, reason = self.evaluator.evaluate(
            self.alice, Permission.DELETE, "public", "/test.txt", "127.0.0.1"
        )
        assert allowed
        
        # Alice can access home share
        allowed, reason = self.evaluator.evaluate(
            self.alice, Permission.READ, "home", "/documents/file.pdf", "127.0.0.1"
        )
        assert allowed
    
    def test_bob_read_only_access(self):
        """Test Bob's read-only access permissions"""
        
        # Bob can read from public
        allowed, reason = self.evaluator.evaluate(
            self.bob, Permission.READ, "public", "/test.txt", "192.168.1.100"
        )
        assert allowed
        
        # Bob cannot write to public
        allowed, reason = self.evaluator.evaluate(
            self.bob, Permission.WRITE, "public", "/test.txt", "192.168.1.100"
        )
        assert not allowed
        assert "not allowed" in reason.lower()
        
        # Bob cannot delete from public
        allowed, reason = self.evaluator.evaluate(
            self.bob, Permission.DELETE, "public", "/test.txt", "192.168.1.100"
        )
        assert not allowed
        
        # Bob cannot access home share
        allowed, reason = self.evaluator.evaluate(
            self.bob, Permission.READ, "home", "/documents/file.pdf", "192.168.1.100"
        )
        assert not allowed
        assert "not allowed" in reason.lower()
    
    def test_ip_filtering(self):
        """Test IP address filtering"""
        
        # Bob from allowed IP range
        allowed, reason = self.evaluator.evaluate(
            self.bob, Permission.READ, "public", "/test.txt", "192.168.1.50"
        )
        assert allowed
        
        # Bob from localhost
        allowed, reason = self.evaluator.evaluate(
            self.bob, Permission.READ, "public", "/test.txt", "127.0.0.1"
        )
        assert allowed
        
        # Bob from disallowed IP
        allowed, reason = self.evaluator.evaluate(
            self.bob, Permission.READ, "public", "/test.txt", "10.0.0.1"
        )
        assert not allowed
        assert "not allowed" in reason.lower()
    
    def test_path_restrictions(self):
        """Test path-based access restrictions"""
        
        # Test wildcard user with path restrictions
        guest_user = UserInfo(name="guest", pass_hash="guest", is_bcrypt=False)
        
        # Guest can access /readonly path
        allowed, reason = self.evaluator.evaluate(
            guest_user, Permission.READ, "public", "/readonly/file.txt", "127.0.0.1"
        )
        assert allowed
        
        # Guest cannot access root path
        allowed, reason = self.evaluator.evaluate(
            guest_user, Permission.READ, "public", "/secret.txt", "127.0.0.1"
        )
        assert not allowed
    
    def test_anonymous_access(self):
        """Test anonymous access (should be denied)"""
        
        allowed, reason = self.evaluator.evaluate(
            None, Permission.READ, "public", "/test.txt", "127.0.0.1"
        )
        assert not allowed
        assert "authentication required" in reason.lower()
    
    def test_nonexistent_user(self):
        """Test access for user with no rules"""
        
        unknown_user = UserInfo(name="unknown", pass_hash="unknown", is_bcrypt=False)
        
        allowed, reason = self.evaluator.evaluate(
            unknown_user, Permission.READ, "public", "/test.txt", "127.0.0.1"
        )
        assert not allowed
        assert "no access rules found" in reason.lower()
    
    def test_path_normalization(self):
        """Test path normalization in rule evaluation"""
        
        # Test various path formats
        test_paths = [
            "/test.txt",
            "test.txt",
            "/folder/test.txt",
            "folder/test.txt",
            "/folder/../test.txt"
        ]
        
        for path in test_paths:
            allowed, reason = self.evaluator.evaluate(
                self.alice, Permission.READ, "public", path, "127.0.0.1"
            )
            assert allowed, f"Failed for path: {path}"
    
    def test_check_path_allowed_method(self):
        """Test the _check_path_allowed method directly"""
        
        # Test exact match
        assert self.evaluator._check_path_allowed("/test.txt", ["/test.txt"])
        
        # Test prefix match
        assert self.evaluator._check_path_allowed("/folder/file.txt", ["/folder/"])
        
        # Test wildcard
        assert self.evaluator._check_path_allowed("/anything/file.txt", ["*"])
        assert self.evaluator._check_path_allowed("/anything/file.txt", ["/*"])
        
        # Test no match
        assert not self.evaluator._check_path_allowed("/secret.txt", ["/public/"])
        
        # Test directory access
        assert self.evaluator._check_path_allowed("/docs/readme.txt", ["/docs"])
        assert self.evaluator._check_path_allowed("/docs/sub/file.txt", ["/docs"])
    
    def test_helper_methods(self):
        """Test helper methods"""
        
        # Test can_read
        assert self.evaluator.can_read(self.alice, "public", "/test.txt", "127.0.0.1")
        assert not self.evaluator.can_read(self.bob, "home", "/test.txt", "127.0.0.1")
        
        # Test can_write
        assert self.evaluator.can_write(self.alice, "public", "/test.txt", "127.0.0.1")
        assert not self.evaluator.can_write(self.bob, "public", "/test.txt", "192.168.1.100")
        
        # Test can_delete
        assert self.evaluator.can_delete(self.alice, "public", "/test.txt", "127.0.0.1")
        assert not self.evaluator.can_delete(self.bob, "public", "/test.txt", "192.168.1.100")
    
    def test_get_accessible_roots(self):
        """Test getting accessible roots for user"""
        
        # Mock shares in config
        from unittest.mock import Mock
        mock_share1 = Mock()
        mock_share1.name = "public"
        mock_share2 = Mock()
        mock_share2.name = "home"
        mock_share3 = Mock()
        mock_share3.name = "private"
        
        import app.rules
        mock_config = app.rules.get_config()
        mock_config.shares = [mock_share1, mock_share2, mock_share3]
        
        # Alice should have access to public and home
        roots = self.evaluator.get_accessible_roots(self.alice, "127.0.0.1")
        assert "public" in roots
        assert "home" in roots
        assert "private" not in roots
        
        # Bob should only have access to public
        roots = self.evaluator.get_accessible_roots(self.bob, "192.168.1.100")
        assert "public" in roots
        assert "home" not in roots
        assert "private" not in roots
        
        # Anonymous user should have no access
        roots = self.evaluator.get_accessible_roots(None, "127.0.0.1")
        assert len(roots) == 0
