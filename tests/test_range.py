"""
Tests for HTTP Range header parsing and processing
"""

import pytest
from app.utils import parse_http_range
from app.models import HttpRange


class TestHttpRange:
    """Test HTTP Range header parsing"""
    
    def test_parse_full_range(self):
        """Test parsing full range specifications"""
        
        # Basic range
        result = parse_http_range("bytes=0-499")
        assert result is not None
        assert result.start == 0
        assert result.end == 499
        assert result.suffix_length is None
        
        # Larger range
        result = parse_http_range("bytes=1000-1999")
        assert result is not None
        assert result.start == 1000
        assert result.end == 1999
        
        # Single byte
        result = parse_http_range("bytes=100-100")
        assert result is not None
        assert result.start == 100
        assert result.end == 100
    
    def test_parse_start_range(self):
        """Test parsing start-only range specifications"""
        
        # Start from position
        result = parse_http_range("bytes=500-")
        assert result is not None
        assert result.start == 500
        assert result.end is None
        assert result.suffix_length is None
        
        # Start from beginning
        result = parse_http_range("bytes=0-")
        assert result is not None
        assert result.start == 0
        assert result.end is None
    
    def test_parse_suffix_range(self):
        """Test parsing suffix range specifications"""
        
        # Last 500 bytes
        result = parse_http_range("bytes=-500")
        assert result is not None
        assert result.start is None
        assert result.end is None
        assert result.suffix_length == 500
        
        # Last 1 byte
        result = parse_http_range("bytes=-1")
        assert result is not None
        assert result.suffix_length == 1
        
        # Last 1000 bytes
        result = parse_http_range("bytes=-1000")
        assert result is not None
        assert result.suffix_length == 1000
    
    def test_parse_invalid_ranges(self):
        """Test parsing invalid range specifications"""
        
        # Missing bytes= prefix
        assert parse_http_range("0-499") is None
        
        # Wrong prefix
        assert parse_http_range("items=0-499") is None
        
        # Empty range
        assert parse_http_range("bytes=") is None
        
        # Invalid format
        assert parse_http_range("bytes=abc-def") is None
        assert parse_http_range("bytes=100-abc") is None
        assert parse_http_range("bytes=abc-100") is None
        
        # Missing dash
        assert parse_http_range("bytes=100") is None
        
        # Multiple dashes
        assert parse_http_range("bytes=100-200-300") is None
        
        # Negative start (invalid format)
        assert parse_http_range("bytes=-100-200") is None
    
    def test_parse_multiple_ranges(self):
        """Test parsing multiple ranges (should take first one)"""
        
        # Multiple ranges - should take first
        result = parse_http_range("bytes=0-499, 1000-1499")
        assert result is not None
        assert result.start == 0
        assert result.end == 499
        
        # With whitespace
        result = parse_http_range("bytes=100-199, 300-399, 500-599")
        assert result is not None
        assert result.start == 100
        assert result.end == 199
    
    def test_parse_edge_cases(self):
        """Test edge cases in range parsing"""
        
        # Zero range
        result = parse_http_range("bytes=0-0")
        assert result is not None
        assert result.start == 0
        assert result.end == 0
        
        # Large numbers
        result = parse_http_range("bytes=1000000-2000000")
        assert result is not None
        assert result.start == 1000000
        assert result.end == 2000000
        
        # Whitespace handling
        result = parse_http_range("bytes= 0 - 499 ")
        assert result is not None
        assert result.start == 0
        assert result.end == 499
    
    def test_range_resolution(self):
        """Test HttpRange.resolve() method"""
        
        # Full range within content
        range_obj = HttpRange(start=0, end=499)
        start, end = range_obj.resolve(1000)
        assert start == 0
        assert end == 499
        
        # Full range beyond content (should be clamped)
        range_obj = HttpRange(start=0, end=1999)
        start, end = range_obj.resolve(1000)
        assert start == 0
        assert end == 999  # Clamped to content length - 1
        
        # Start range
        range_obj = HttpRange(start=500)
        start, end = range_obj.resolve(1000)
        assert start == 500
        assert end == 999
        
        # Start range beyond content
        range_obj = HttpRange(start=1500)
        start, end = range_obj.resolve(1000)
        assert start == 1000  # Clamped to max valid position
        assert end == 999
        
        # Suffix range
        range_obj = HttpRange(suffix_length=200)
        start, end = range_obj.resolve(1000)
        assert start == 800  # 1000 - 200
        assert end == 999
        
        # Suffix range larger than content
        range_obj = HttpRange(suffix_length=1500)
        start, end = range_obj.resolve(1000)
        assert start == 0  # Clamped to 0
        assert end == 999
        
        # Suffix range for small content
        range_obj = HttpRange(suffix_length=100)
        start, end = range_obj.resolve(50)
        assert start == 0  # Clamped to 0
        assert end == 49
    
    def test_range_validation(self):
        """Test range validation logic"""
        
        # Valid ranges
        range_obj = HttpRange(start=0, end=499)
        start, end = range_obj.resolve(1000)
        assert start <= end
        assert start >= 0
        assert end < 1000
        
        # Start equals end (single byte)
        range_obj = HttpRange(start=100, end=100)
        start, end = range_obj.resolve(1000)
        assert start == end
        assert start == 100
        
        # Empty content
        range_obj = HttpRange(start=0, end=0)
        start, end = range_obj.resolve(0)
        assert start == 0
        assert end == -1  # Invalid range for empty content
    
    def test_content_range_creation(self):
        """Test creating Content-Range headers"""
        
        from app.utils import create_content_range_header
        
        # Basic range
        header = create_content_range_header(0, 499, 1000)
        assert header == "bytes 0-499/1000"
        
        # Single byte
        header = create_content_range_header(100, 100, 1000)
        assert header == "bytes 100-100/1000"
        
        # Large file
        header = create_content_range_header(1000000, 1999999, 10000000)
        assert header == "bytes 1000000-1999999/10000000"
    
    def test_content_range_parsing(self):
        """Test parsing Content-Range headers"""
        
        from app.utils import parse_content_range
        
        # Basic range
        result = parse_content_range("bytes 0-499/1000")
        assert result == (0, 499, 1000)
        
        # Single byte
        result = parse_content_range("bytes 100-100/1000")
        assert result == (100, 100, 1000)
        
        # Unknown total size
        result = parse_content_range("bytes 0-499/*")
        assert result == (0, 499, -1)
        
        # Invalid format
        assert parse_content_range("invalid") is None
        assert parse_content_range("bytes abc-def/1000") is None
        assert parse_content_range("") is None
        assert parse_content_range(None) is None
    
    def test_real_world_scenarios(self):
        """Test real-world range request scenarios"""
        
        # Browser requesting first chunk of video
        result = parse_http_range("bytes=0-1048575")  # First 1MB
        assert result is not None
        start, end = result.resolve(100000000)  # 100MB file
        assert start == 0
        assert end == 1048575
        
        # Media player seeking to middle
        result = parse_http_range("bytes=50000000-")  # From 50MB to end
        assert result is not None
        start, end = result.resolve(100000000)
        assert start == 50000000
        assert end == 99999999
        
        # Download manager resuming download
        result = parse_http_range("bytes=75000000-")  # Resume from 75MB
        assert result is not None
        start, end = result.resolve(100000000)
        assert start == 75000000
        assert end == 99999999
        
        # Getting last portion for preview
        result = parse_http_range("bytes=-1048576")  # Last 1MB
        assert result is not None
        start, end = result.resolve(100000000)
        assert start == 98951424  # 100MB - 1MB
        assert end == 99999999
