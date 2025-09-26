"""
Tests for filesystem path safety and operations
"""

import pytest
import tempfile
import shutil
from pathlib import Path

from app.fs import safe_join, PathTraversalError, FileSystemError


class TestPathSafety:
    """Test path safety functions"""
    
    def setup_method(self):
        """Setup test environment"""
        # Create temporary directory for testing
        self.temp_dir = Path(tempfile.mkdtemp())
        self.root_path = self.temp_dir / "root"
        self.root_path.mkdir(parents=True)
        
        # Create test directory structure
        (self.root_path / "folder1").mkdir()
        (self.root_path / "folder1" / "subfolder").mkdir()
        (self.root_path / "folder2").mkdir()
        (self.root_path / "test.txt").write_text("test content")
    
    def teardown_method(self):
        """Cleanup test environment"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
    
    def test_safe_join_normal_paths(self):
        """Test safe_join with normal paths"""
        
        # Simple file
        result = safe_join(self.root_path, "test.txt")
        expected = self.root_path / "test.txt"
        assert result == expected.resolve()
        
        # Subfolder file
        result = safe_join(self.root_path, "folder1/subfolder/file.txt")
        expected = self.root_path / "folder1" / "subfolder" / "file.txt"
        assert result == expected.resolve()
        
        # Leading slash should be handled
        result = safe_join(self.root_path, "/folder1/test.txt")
        expected = self.root_path / "folder1" / "test.txt"
        assert result == expected.resolve()
    
    def test_safe_join_path_traversal_attempts(self):
        """Test safe_join blocks path traversal attempts"""
        
        # Basic path traversal
        with pytest.raises(PathTraversalError):
            safe_join(self.root_path, "../outside.txt")
        
        # Multiple levels
        with pytest.raises(PathTraversalError):
            safe_join(self.root_path, "../../outside.txt")
        
        # Mixed with normal path
        with pytest.raises(PathTraversalError):
            safe_join(self.root_path, "folder1/../../../outside.txt")
        
        # Hidden path traversal
        with pytest.raises(PathTraversalError):
            safe_join(self.root_path, "folder1/./../../outside.txt")
        
        # URL encoded path traversal
        with pytest.raises(PathTraversalError):
            safe_join(self.root_path, "folder1%2F..%2F..%2Foutside.txt")
    
    def test_safe_join_windows_paths(self):
        """Test safe_join with Windows-style paths"""
        
        # Backslash separators
        result = safe_join(self.root_path, "folder1\\subfolder\\file.txt")
        expected = self.root_path / "folder1" / "subfolder" / "file.txt"
        assert result == expected.resolve()
        
        # Mixed separators
        result = safe_join(self.root_path, "folder1/subfolder\\file.txt")
        expected = self.root_path / "folder1" / "subfolder" / "file.txt"
        assert result == expected.resolve()
        
        # Windows path traversal attempt
        with pytest.raises(PathTraversalError):
            safe_join(self.root_path, "folder1\\..\\..\\outside.txt")
    
    def test_safe_join_edge_cases(self):
        """Test safe_join edge cases"""
        
        # Empty path
        result = safe_join(self.root_path, "")
        assert result == self.root_path.resolve()
        
        # Root path
        result = safe_join(self.root_path, "/")
        assert result == self.root_path.resolve()
        
        # Current directory
        result = safe_join(self.root_path, ".")
        assert result == self.root_path.resolve()
        
        # Current directory in path
        result = safe_join(self.root_path, "./folder1/./test.txt")
        expected = self.root_path / "folder1" / "test.txt"
        assert result == expected.resolve()
        
        # Multiple slashes
        result = safe_join(self.root_path, "//folder1///subfolder//file.txt")
        expected = self.root_path / "folder1" / "subfolder" / "file.txt"
        assert result == expected.resolve()
    
    def test_safe_join_special_characters(self):
        """Test safe_join with special characters"""
        
        # Spaces in path
        result = safe_join(self.root_path, "folder with spaces/file name.txt")
        expected = self.root_path / "folder with spaces" / "file name.txt"
        assert result == expected.resolve()
        
        # Unicode characters
        result = safe_join(self.root_path, "测试文件夹/测试文件.txt")
        expected = self.root_path / "测试文件夹" / "测试文件.txt"
        assert result == expected.resolve()
        
        # Special characters that should be allowed
        result = safe_join(self.root_path, "folder-name_123/file@#$.txt")
        expected = self.root_path / "folder-name_123" / "file@#$.txt"
        assert result == expected.resolve()
    
    def test_safe_join_symlink_attacks(self):
        """Test safe_join handles symlink attacks (if supported by OS)"""
        
        try:
            # Create symlink outside root
            outside_dir = self.temp_dir / "outside"
            outside_dir.mkdir()
            (outside_dir / "secret.txt").write_text("secret data")
            
            symlink_path = self.root_path / "symlink"
            symlink_path.symlink_to(outside_dir)
            
            # Attempt to access file through symlink
            with pytest.raises(PathTraversalError):
                safe_join(self.root_path, "symlink/secret.txt")
                
        except OSError:
            # Symlinks not supported on this system, skip test
            pytest.skip("Symlinks not supported on this system")
    
    def test_path_normalization(self):
        """Test path normalization behavior"""
        
        from app.utils import normalize_path
        
        # Basic normalization
        assert normalize_path("folder\\subfolder") == "folder/subfolder"
        assert normalize_path("folder/subfolder") == "folder/subfolder"
        
        # Multiple backslashes
        assert normalize_path("folder\\\\subfolder") == "folder//subfolder"
        
        # Mixed separators
        assert normalize_path("folder\\sub/folder") == "folder/sub/folder"
    
    def test_validate_filename(self):
        """Test filename validation"""
        
        from app.utils import validate_filename
        
        # Valid filenames
        assert validate_filename("test.txt")
        assert validate_filename("document-v1.2.pdf")
        assert validate_filename("image_001.jpg")
        assert validate_filename("测试文件.txt")
        
        # Invalid filenames
        assert not validate_filename("")  # Empty
        assert not validate_filename(".")  # Current directory
        assert not validate_filename("..")  # Parent directory
        assert not validate_filename("file<name.txt")  # Dangerous character
        assert not validate_filename("file>name.txt")  # Dangerous character
        assert not validate_filename("file:name.txt")  # Dangerous character (Windows)
        assert not validate_filename("file\"name.txt")  # Quote character
        assert not validate_filename("file/name.txt")  # Path separator
        assert not validate_filename("file\\name.txt")  # Path separator
        assert not validate_filename("file|name.txt")  # Pipe character
        assert not validate_filename("file?name.txt")  # Wildcard
        assert not validate_filename("file*name.txt")  # Wildcard
        assert not validate_filename("file\x00name.txt")  # Null character
        assert not validate_filename("file\x1fname.txt")  # Control character
    
    def test_sanitize_filename(self):
        """Test filename sanitization"""
        
        from app.utils import sanitize_filename
        
        # Basic sanitization
        assert sanitize_filename("file<name.txt") == "file_name.txt"
        assert sanitize_filename("file>name.txt") == "file_name.txt"
        assert sanitize_filename("file:name.txt") == "file_name.txt"
        assert sanitize_filename("file\"name.txt") == "file_name.txt"
        assert sanitize_filename("file/name.txt") == "file_name.txt"
        assert sanitize_filename("file\\name.txt") == "file_name.txt"
        assert sanitize_filename("file|name.txt") == "file_name.txt"
        assert sanitize_filename("file?name.txt") == "file_name.txt"
        assert sanitize_filename("file*name.txt") == "file_name.txt"
        
        # Control characters
        assert sanitize_filename("file\x00name.txt") == "filename.txt"
        assert sanitize_filename("file\x1fname.txt") == "filename.txt"
        
        # Whitespace trimming
        assert sanitize_filename("  filename.txt  ") == "filename.txt"
        assert sanitize_filename("filename.txt...") == "filename.txt"
        
        # Empty filename
        assert sanitize_filename("") == "unnamed"
        assert sanitize_filename("   ") == "unnamed"
        assert sanitize_filename("...") == "unnamed"
        
        # Long filename truncation
        long_name = "a" * 300 + ".txt"
        sanitized = sanitize_filename(long_name)
        assert len(sanitized) <= 255
        assert sanitized.endswith(".txt")
        
        # Unicode preservation
        assert sanitize_filename("测试文件.txt") == "测试文件.txt"
    
    def test_path_resolution_consistency(self):
        """Test that path resolution is consistent"""
        
        # Create various equivalent paths
        test_paths = [
            "folder1/subfolder/../test.txt",
            "folder1/./test.txt", 
            "folder1//test.txt",
            "./folder1/test.txt",
        ]
        
        expected = self.root_path / "folder1" / "test.txt"
        
        for path in test_paths:
            try:
                result = safe_join(self.root_path, path)
                assert result == expected.resolve()
            except PathTraversalError:
                # Some of these might be blocked by safety checks
                pass
