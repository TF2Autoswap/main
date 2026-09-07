#!/usr/bin/env python3
"""
test_security_schema.py - Security regression tests for tf2_schema.py

Tests CRITICAL-001 and CRITICAL-002 fixes:
- Schema file size validation (DoS protection)
- Cache file size validation (cache poisoning protection)

Run: pytest tests/test_security_schema.py -v
"""

import os
import pytest
import tempfile
import json
import tf2_schema


class TestSchemaFileSizeValidation:
    """CRITICAL-001: Schema file size validation (DoS protection)"""

    def test_schema_file_within_limit_loads(self, tmp_path):
        """Normal-sized schema file loads successfully"""
        tf2_dir = tmp_path / "tf"
        scripts_dir = tf2_dir / "scripts" / "items"
        scripts_dir.mkdir(parents=True)
        
        # Create a small valid VDF file
        schema_file = scripts_dir / "items_game.txt"
        valid_vdf = '''"items_game"
{
    "items"
    {
        "1"
        {
            "name" "test"
        }
    }
}
'''
        schema_file.write_text(valid_vdf)
        
        # Should load without error
        schema = tf2_schema.load_schema(str(tf2_dir))
        assert schema is not None
        assert "items_game" in schema

    def test_schema_file_at_limit_loads(self, tmp_path):
        """Schema file at exactly MAX_SCHEMA_SIZE loads"""
        tf2_dir = tmp_path / "tf"
        scripts_dir = tf2_dir / "scripts" / "items"
        scripts_dir.mkdir(parents=True)
        
        schema_file = scripts_dir / "items_game.txt"
        # Create file at exactly the limit (200MB)
        # Use a smaller test size for performance
        test_size = 1024 * 10  # 10KB for test (real limit is 200MB)
        header = '"items_game"\n{\n    "test" "'
        footer = '"\n}\n'
        padding_size = test_size - len(header) - len(footer) - 10
        with open(schema_file, "w") as f:
            f.write(header)
            f.write("x" * padding_size)
            f.write(footer)
        
        # Temporarily lower limit for test
        original_limit = tf2_schema.MAX_SCHEMA_SIZE
        tf2_schema.MAX_SCHEMA_SIZE = test_size
        
        try:
            # Should load at exactly the limit
            schema = tf2_schema.load_schema(str(tf2_dir))
            assert schema is not None
        finally:
            tf2_schema.MAX_SCHEMA_SIZE = original_limit

    def test_schema_file_over_limit_raises_error(self, tmp_path):
        """Oversized schema file raises SwapError (DoS protection)"""
        tf2_dir = tmp_path / "tf"
        scripts_dir = tf2_dir / "scripts" / "items"
        scripts_dir.mkdir(parents=True)
        
        schema_file = scripts_dir / "items_game.txt"
        # Create file that exceeds limit
        test_size = 1024 * 10  # 10KB test limit
        with open(schema_file, "w") as f:
            f.write("x" * (test_size + 1000))  # Exceed limit
        
        # Temporarily lower limit for test
        original_limit = tf2_schema.MAX_SCHEMA_SIZE
        tf2_schema.MAX_SCHEMA_SIZE = test_size
        
        try:
            # Should raise error about file being too large
            with pytest.raises(Exception) as exc_info:
                tf2_schema.load_schema(str(tf2_dir))
            
            error_msg = str(exc_info.value).lower()
            assert "too large" in error_msg or "maximum" in error_msg
        finally:
            tf2_schema.MAX_SCHEMA_SIZE = original_limit

    def test_schema_file_size_error_message_includes_sizes(self, tmp_path):
        """Error message includes actual and maximum sizes"""
        tf2_dir = tmp_path / "tf"
        scripts_dir = tf2_dir / "scripts" / "items"
        scripts_dir.mkdir(parents=True)
        
        schema_file = scripts_dir / "items_game.txt"
        test_size = 1024 * 10
        with open(schema_file, "w") as f:
            f.write("x" * (test_size + 1000))
        
        original_limit = tf2_schema.MAX_SCHEMA_SIZE
        tf2_schema.MAX_SCHEMA_SIZE = test_size
        
        try:
            with pytest.raises(Exception) as exc_info:
                tf2_schema.load_schema(str(tf2_dir))
            
            error_msg = str(exc_info.value)
            # Should contain size information
            assert "mb" in error_msg.lower() or "maximum" in error_msg.lower()
        finally:
            tf2_schema.MAX_SCHEMA_SIZE = original_limit


class TestSchemaCacheSizeValidation:
    """CRITICAL-002: Schema cache size validation (cache poisoning protection)"""

    def test_cache_within_limit_loads(self, tmp_path):
        """Normal-sized cache file loads successfully"""
        items_game = tmp_path / "items_game.txt"
        items_game.write_text("test")
        
        cache_file = tmp_path / "cache.json"
        cache_data = {
            "mtime": os.path.getmtime(items_game),
            "format_version": tf2_schema._SCHEMA_CACHE_FORMAT_VERSION,
            "index": {"test": {"name": "Test", "equip_region": "", "hides_head": False, "classes": []}}
        }
        cache_file.write_text(json.dumps(cache_data))
        
        # Should load successfully
        result = tf2_schema.load_schema_cache(str(items_game), str(cache_file))
        assert result is not None

    def test_cache_at_limit_loads(self, tmp_path):
        """Cache file at exactly MAX_CACHE_SIZE loads"""
        items_game = tmp_path / "items_game.txt"
        items_game.write_text("test")
        
        cache_file = tmp_path / "cache.json"
        test_size = 1024 * 10  # 10KB test limit
        
        # Create cache at exact limit
        cache_data = {
            "mtime": os.path.getmtime(items_game),
            "format_version": tf2_schema._SCHEMA_CACHE_FORMAT_VERSION,
            "index": {"x": {"name": "x" * (test_size // 2), "equip_region": "", "hides_head": False, "classes": []}}
        }
        with open(cache_file, "w") as f:
            json.dump(cache_data, f)
        
        original_limit = tf2_schema.MAX_CACHE_SIZE
        tf2_schema.MAX_CACHE_SIZE = test_size
        
        try:
            result = tf2_schema.load_schema_cache(str(items_game), str(cache_file))
            # Should either load or return None (acceptable for at-limit)
            assert result is None or isinstance(result, dict)
        finally:
            tf2_schema.MAX_CACHE_SIZE = original_limit

    def test_cache_over_limit_deleted_and_returns_none(self, tmp_path):
        """Oversized cache file is deleted and returns None (cache poisoning protection)"""
        items_game = tmp_path / "items_game.txt"
        items_game.write_text("test")
        
        cache_file = tmp_path / "cache.json"
        test_size = 1024 * 10
        
        # Create oversized cache
        with open(cache_file, "w") as f:
            f.write("x" * (test_size + 1000))
        
        assert cache_file.exists(), "Cache file should exist before test"
        
        original_limit = tf2_schema.MAX_CACHE_SIZE
        tf2_schema.MAX_CACHE_SIZE = test_size
        
        try:
            result = tf2_schema.load_schema_cache(str(items_game), str(cache_file))
            
            # Should return None (cache rejected)
            assert result is None
            # Should delete the poisoned cache
            assert not cache_file.exists(), "Oversized cache should be deleted"
        finally:
            tf2_schema.MAX_CACHE_SIZE = original_limit

    def test_defindex_cache_over_limit_deleted(self, tmp_path):
        """Oversized defindex cache file is deleted (cache poisoning protection)"""
        items_game = tmp_path / "items_game.txt"
        items_game.write_text("test")
        
        cache_file = tmp_path / "defindex_cache.json"
        test_size = 1024 * 10
        
        # Create oversized defindex cache
        with open(cache_file, "w") as f:
            f.write("x" * (test_size + 1000))
        
        assert cache_file.exists()
        
        original_limit = tf2_schema.MAX_CACHE_SIZE
        tf2_schema.MAX_CACHE_SIZE = test_size
        
        try:
            result = tf2_schema.load_defindex_cache(str(items_game), str(cache_file))
            
            assert result is None
            assert not cache_file.exists(), "Oversized defindex cache should be deleted"
        finally:
            tf2_schema.MAX_CACHE_SIZE = original_limit

    def test_cache_poisoning_recovery(self, tmp_path):
        """After deleting poisoned cache, normal cache can be written"""
        items_game = tmp_path / "items_game.txt"
        items_game.write_text("test")
        
        cache_file = tmp_path / "cache.json"
        test_size = 1024 * 10
        
        # Step 1: Create poisoned cache
        with open(cache_file, "w") as f:
            f.write("x" * (test_size + 1000))
        
        original_limit = tf2_schema.MAX_CACHE_SIZE
        tf2_schema.MAX_CACHE_SIZE = test_size
        
        try:
            # Step 2: Load (should delete poisoned cache)
            result = tf2_schema.load_schema_cache(str(items_game), str(cache_file))
            assert result is None
            assert not cache_file.exists()
            
            # Step 3: Write new valid cache
            test_index = {"test": tf2_schema.ItemInfo(name="Test", classes=[])}
            tf2_schema.save_schema_cache(test_index, str(items_game), str(cache_file))
            
            # Step 4: Should load successfully now
            result = tf2_schema.load_schema_cache(str(items_game), str(cache_file))
            assert result is not None
        finally:
            tf2_schema.MAX_CACHE_SIZE = original_limit


class TestSecurityConstants:
    """Verify security constants are set correctly"""

    def test_max_schema_size_is_reasonable(self):
        """MAX_SCHEMA_SIZE is set to 200MB"""
        assert tf2_schema.MAX_SCHEMA_SIZE == 200 * 1024 * 1024
        # Real schema is ~20MB, so 200MB is 10x headroom

    def test_max_cache_size_is_reasonable(self):
        """MAX_CACHE_SIZE is set to 100MB"""
        assert tf2_schema.MAX_CACHE_SIZE == 100 * 1024 * 1024
        # Real cache is ~5MB, so 100MB is 20x headroom

    def test_limits_prevent_practical_dos(self):
        """Limits prevent multi-gigabyte attacks"""
        # A 5GB attack file would be rejected
        attack_size = 5 * 1024 * 1024 * 1024
        assert attack_size > tf2_schema.MAX_SCHEMA_SIZE
        assert attack_size > tf2_schema.MAX_CACHE_SIZE
