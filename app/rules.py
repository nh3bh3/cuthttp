"""
Access control rules evaluation for chfs-py
"""

import logging
from typing import Optional, Tuple, List
from pathlib import Path

from .models import Permission, RuleInfo, UserInfo
from .config import get_config
from .ipfilter import check_ip_allowed

logger = logging.getLogger(__name__)


class RuleEvaluator:
    """Access control rule evaluator"""
    
    def __init__(self):
        self.config = get_config()
    
    def evaluate(
        self,
        user: Optional[UserInfo],
        operation: Permission,
        root_name: str,
        rel_path: str,
        client_ip: str
    ) -> Tuple[bool, str]:
        """
        Evaluate access control rules
        
        Args:
            user: Authenticated user (None for anonymous)
            operation: Requested operation (READ/WRITE/DELETE)
            root_name: Share root name
            rel_path: Relative path within share
            client_ip: Client IP address
            
        Returns:
            (allowed, reason) tuple
        """
        
        # Anonymous access not allowed for now
        if not user:
            return False, "Authentication required"
        
        # Get fresh config for hot reload support
        config = get_config()
        
        # Find matching rules for user
        matching_rules = []
        for rule in config.rules:
            if rule.who == user.name or rule.who == "*":
                matching_rules.append(rule)
        
        if not matching_rules:
            return False, f"No access rules found for user: {user.name}"
        
        # Evaluate each matching rule
        for rule in matching_rules:
            allowed, reason = self._evaluate_rule(rule, operation, root_name, rel_path, client_ip)
            if allowed:
                logger.debug(f"Access granted: {user.name} -> {operation.value} {root_name}{rel_path}")
                return True, reason
        
        # No rule allowed access
        logger.warning(f"Access denied: {user.name} -> {operation.value} {root_name}{rel_path}")
        return False, f"Access denied for {operation.value} operation"
    
    def _evaluate_rule(
        self,
        rule: RuleInfo,
        operation: Permission,
        root_name: str,
        rel_path: str,
        client_ip: str
    ) -> Tuple[bool, str]:
        """Evaluate a single rule"""
        
        # Check operation permission
        if operation not in rule.allow:
            return False, f"Operation {operation.value} not allowed by rule"
        
        # Check root access
        if root_name not in rule.roots and "*" not in rule.roots:
            return False, f"Root '{root_name}' not allowed by rule"
        
        # Check path access
        if not self._check_path_allowed(rel_path, rule.paths):
            return False, f"Path '{rel_path}' not allowed by rule"
        
        # Check IP access
        if not check_ip_allowed(client_ip, rule.ip_allow, rule.ip_deny):
            return False, f"IP '{client_ip}' not allowed by rule"
        
        return True, "Access granted by rule"
    
    def _check_path_allowed(self, rel_path: str, allowed_paths: List[str]) -> bool:
        """Check if relative path is allowed by rule paths"""
        
        # Normalize path
        rel_path = rel_path.replace('\\', '/')
        if not rel_path.startswith('/'):
            rel_path = '/' + rel_path
        
        # Check against allowed paths
        for allowed_path in allowed_paths:
            allowed_path = allowed_path.replace('\\', '/')
            if not allowed_path.startswith('/'):
                allowed_path = '/' + allowed_path
            
            # Wildcard match
            if allowed_path == "*" or allowed_path == "/*":
                return True
            
            # Exact match
            if rel_path == allowed_path:
                return True
            
            # Prefix match (directory access)
            if allowed_path.endswith('/'):
                if rel_path.startswith(allowed_path):
                    return True
            else:
                # Check if rel_path is under allowed_path directory
                if rel_path.startswith(allowed_path + '/'):
                    return True
        
        return False
    
    def can_read(self, user: Optional[UserInfo], root_name: str, rel_path: str, client_ip: str) -> bool:
        """Check if user can read from path"""
        allowed, _ = self.evaluate(user, Permission.READ, root_name, rel_path, client_ip)
        return allowed
    
    def can_write(self, user: Optional[UserInfo], root_name: str, rel_path: str, client_ip: str) -> bool:
        """Check if user can write to path"""
        allowed, _ = self.evaluate(user, Permission.WRITE, root_name, rel_path, client_ip)
        return allowed
    
    def can_delete(self, user: Optional[UserInfo], root_name: str, rel_path: str, client_ip: str) -> bool:
        """Check if user can delete from path"""
        allowed, _ = self.evaluate(user, Permission.DELETE, root_name, rel_path, client_ip)
        return allowed
    
    def get_accessible_roots(self, user: Optional[UserInfo], client_ip: str) -> List[str]:
        """Get list of root shares accessible to user"""
        if not user:
            return []
        
        config = get_config()
        accessible_roots = set()
        
        for rule in config.rules:
            if rule.who == user.name or rule.who == "*":
                if check_ip_allowed(client_ip, rule.ip_allow, rule.ip_deny):
                    if "*" in rule.roots:
                        # User has access to all roots
                        return [share.name for share in config.shares]
                    accessible_roots.update(rule.roots)
        
        # Filter by actual configured shares
        configured_roots = {share.name for share in config.shares}
        return list(accessible_roots.intersection(configured_roots))


# Global rule evaluator instance
rule_evaluator = RuleEvaluator()


def evaluate_access(
    user: Optional[UserInfo],
    operation: Permission,
    root_name: str,
    rel_path: str,
    client_ip: str
) -> Tuple[bool, str]:
    """Evaluate access control (global function)"""
    return rule_evaluator.evaluate(user, operation, root_name, rel_path, client_ip)


def can_read(user: Optional[UserInfo], root_name: str, rel_path: str, client_ip: str) -> bool:
    """Check read access (global function)"""
    return rule_evaluator.can_read(user, root_name, rel_path, client_ip)


def can_write(user: Optional[UserInfo], root_name: str, rel_path: str, client_ip: str) -> bool:
    """Check write access (global function)"""
    return rule_evaluator.can_write(user, root_name, rel_path, client_ip)


def can_delete(user: Optional[UserInfo], root_name: str, rel_path: str, client_ip: str) -> bool:
    """Check delete access (global function)"""
    return rule_evaluator.can_delete(user, root_name, rel_path, client_ip)


def get_accessible_roots(user: Optional[UserInfo], client_ip: str) -> List[str]:
    """Get accessible roots (global function)"""
    return rule_evaluator.get_accessible_roots(user, client_ip)


def check_api_access(
    user: Optional[UserInfo],
    operation: str,
    root_name: str,
    rel_path: str,
    client_ip: str
) -> Tuple[bool, str]:
    """
    Check API access with operation string mapping
    
    Args:
        user: Authenticated user
        operation: Operation string (list, upload, download, mkdir, rename, delete)
        root_name: Share root name
        rel_path: Relative path
        client_ip: Client IP
        
    Returns:
        (allowed, reason) tuple
    """
    
    # Map operation strings to permissions
    operation_map = {
        'list': Permission.READ,
        'download': Permission.READ,
        'upload': Permission.WRITE,
        'mkdir': Permission.WRITE,
        'rename': Permission.WRITE,
        'delete': Permission.DELETE,
    }
    
    permission = operation_map.get(operation)
    if not permission:
        return False, f"Unknown operation: {operation}"
    
    return evaluate_access(user, permission, root_name, rel_path, client_ip)


def refresh_rules():
    """Refresh rules from configuration (for hot reload)"""
    global rule_evaluator
    rule_evaluator = RuleEvaluator()
    logger.info("Access control rules refreshed")
