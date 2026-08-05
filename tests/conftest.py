#!/usr/bin/env python3
"""
conftest.py - Shared test fixtures and utilities for TF2autoswap tests.

This file is automatically loaded by pytest and provides:
- Temporary directory fixtures for safe file operations
- Mock VPK builder for testing without actual TF2
- Mock schema parser for testing schema loading
- Test data and assertion helpers
"""

import os
import sys
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

import pytest

# Add parent directory to path so we can import tf2autoswap modules
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(TEST_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ========== Directory Fixtures ==========

@pytest.fixture
def temp_dir():
    """
    Provide a temporary directory that is cleaned up after the test.
    
    This fixture creates a temporary directory for file operations,
    automatically cleaning it up when the test completes.
    
    Returns:
        pathlib.Path: Path to the temporary directory
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def tf2_paths(temp_dir):
    """
    Create a mock TF2 directory structure for testing.
    
    Creates the directory layout expected by tf2autoswap without
    needing an actual TF2 installation. Includes mock VPK files.
    
    Returns:
        dict: Keys are 'root', 'tf', 'misc_vpk' pointing to created paths
    """
    tf2_root = temp_dir / "Team Fortress 2" / "tf"
    tf2_root.mkdir(parents=True, exist_ok=True)
    
    # Create the marker file that resolve_tf2() checks for
    misc_vpk = tf2_root / "tf2_misc_dir.vpk"
    misc_vpk.touch()
    
    return {
        "root": temp_dir,
        "tf": tf2_root,
        "misc_vpk": misc_vpk,
    }


# ========== Mock VPK Fixtures ==========

@pytest.fixture
def mock_vpk_data():
    """
    Create minimal mock VPK data for testing file reading.
    
    This is a simple dict-like object that mimics the vpk.VPK interface
    without needing the actual vpk library or a real VPK file.
    
    Returns:
        dict: Mock VPK with cosmetic and weapon model paths
    """
    return {
        # Cosmetic models
        "root/models/player/items/scout/a_backwards_ballcap.mdl": b"mock_mdl_data",
        "root/models/player/items/scout/a_backwards_ballcap.vvd": b"mock_vvd_data",
        "root/models/player/items/scout/a_backwards_ballcap.dx90.vtx": b"mock_vtx_data",
        
        # Weapon models (viewmodel)
        "root/models/weapons/c_models/c_scattergun_scout.mdl": b"mock_weapon_mdl",
        "root/models/weapons/c_models/c_scattergun_scout.vvd": b"mock_weapon_vvd",
        
        # Weapon models (worldmodel)
        "root/models/weapons/w_models/w_scattergun_scout.mdl": b"mock_world_mdl",
        "root/models/weapons/w_models/w_scattergun_scout.vvd": b"mock_world_vvd",
    }


@pytest.fixture
def mock_vpk_object(mock_vpk_data):
    """
    Create a mock VPK object that behaves like vpk.VPK.
    
    This provides a vpk-like interface for testing without needing
    the actual vpk library or real VPK files.
    
    Returns:
        MagicMock: Mock object with VPK-like methods
    """
    mock_vpk = MagicMock()
    
    # Implement __getitem__ to return file data
    mock_vpk.__getitem__.side_effect = lambda key: mock_vpk_data.get(key, b"")
    
    # Implement __contains__ for membership testing
    mock_vpk.__contains__.side_effect = lambda key: key in mock_vpk_data
    
    # Implement .keys() for iteration
    mock_vpk.keys.return_value = mock_vpk_data.keys()
    
    return mock_vpk


# ========== Mock Schema Fixtures ==========

@pytest.fixture
def mock_schema_data():
    """
    Create minimal mock item schema for testing schema parsing.
    
    This is a minimal items_game.txt-like structure for testing
    the schema parser without needing TF2 installed.
    
    Returns:
        str: JSON-formatted mock schema data
    """
    schema = {
        "items": {
            "0": {
                "name": "Scout",
                "item_class": "all",
                "item_slot": "primary",
            },
            "1": {
                "name": "Scattergun",
                "item_class": "scout",
                "item_slot": "primary",
                "model_player": "models/weapons/c_models/c_scattergun_scout.mdl",
            },
            "3": {
                "name": "Bat",
                "item_class": "scout",
                "item_slot": "melee",
            },
        }
    }
    return json.dumps(schema)


@pytest.fixture
def mock_schema_file(temp_dir, mock_schema_data):
    """
    Create a temporary mock schema file.
    
    Writes the mock schema to a temporary JSON file and returns its path.
    
    Returns:
        pathlib.Path: Path to the mock schema file
    """
    schema_file = temp_dir / "mock_schema.json"
    schema_file.write_text(mock_schema_data)
    return schema_file


# ========== Import Patches ==========

@pytest.fixture
def patch_vpk_import():
    """
    Patch the vpk library import to avoid dependency on actual vpk installation.
    
    Yields:
        MagicMock: Mock vpk module
    """
    with patch.dict("sys.modules", {"vpk": MagicMock()}):
        yield


# ========== Assertion Helpers ==========

class VPKAssertions:
    """Helper methods for asserting VPK structure and contents."""
    
    @staticmethod
    def assert_vpk_contains_file(vpk_obj, file_path):
        """Assert that a VPK object contains a specific file."""
        assert file_path in vpk_obj, f"VPK does not contain {file_path}"
    
    @staticmethod
    def assert_vpk_file_size(vpk_obj, file_path, expected_size):
        """Assert that a VPK file has the expected size."""
        actual_size = len(vpk_obj[file_path])
        assert actual_size == expected_size, \
            f"File {file_path} size mismatch: expected {expected_size}, got {actual_size}"
    
    @staticmethod
    def assert_vpk_has_all_model_files(vpk_obj, model_base):
        """
        Assert that a VPK contains all required model files for a base path.
        
        TF2 models require: .mdl, .vvd, .dx90.vtx, .dx80.vtx (optional), .sw.vtx (optional)
        """
        required_exts = [".mdl", ".vvd", ".dx90.vtx"]
        for ext in required_exts:
            file_path = model_base + ext
            assert file_path in vpk_obj, f"Missing {ext} for model {model_base}"


@pytest.fixture
def vpk_assertions():
    """Provide VPK assertion helpers to tests."""
    return VPKAssertions()


# ========== Test Data ==========

@pytest.fixture
def test_cosmetics():
    """
    Provide test cosmetic item data.
    
    Returns:
        dict: Cosmetic item paths and properties
    """
    return {
        "backwards_ballcap": {
            "path": "models/player/items/scout/a_backwards_ballcap.mdl",
            "class": "scout",
            "replaces_head": False,
        },
        "demoman_helmet": {
            "path": "models/player/items/demoman/a_helmet_demo.mdl",
            "class": "demoman",
            "replaces_head": True,
        },
    }


@pytest.fixture
def test_weapons():
    """
    Provide test weapon item data.
    
    Returns:
        dict: Weapon item paths, slots, and properties
    """
    return {
        "scattergun": {
            "viewmodel": "models/weapons/c_models/c_scattergun_scout.mdl",
            "worldmodel": "models/weapons/w_models/w_scattergun_scout.mdl",
            "class": "scout",
            "slot": "primary",
        },
        "shotgun": {
            "viewmodel": "models/weapons/c_models/c_shotgun_soldier.mdl",
            "worldmodel": "models/weapons/w_models/w_shotgun_soldier.mdl",
            "class": "soldier",
            "slot": "primary",
        },
    }


# ========== Security & Adversarial Test Fixtures ==========

@pytest.fixture
def oversized_file(temp_dir):
    """
    Create a file larger than MAX_SCHEMA_SIZE (200 MB).
    Uses sparse file to avoid actual disk usage.
    
    Returns:
        pathlib.Path: Path to oversized file
    """
    oversized = temp_dir / "oversized_schema.json"
    # Create a sparse file by writing only start/end, not the full 200+MB
    with open(oversized, 'wb') as f:
        f.write(b'{"items": {')
        f.seek(210 * 1024 * 1024)  # Seek to 210 MB
        f.write(b'}}')  # Write end marker
    return oversized


@pytest.fixture
def truncated_json_file(temp_dir):
    """
    Create a truncated JSON file (incomplete, no closing brace).
    
    Returns:
        pathlib.Path: Path to truncated JSON file
    """
    truncated = temp_dir / "truncated_schema.json"
    truncated.write_text('{"items": {"1": {"name": "Test"')
    return truncated


@pytest.fixture
def malformed_utf8_file(temp_dir):
    """
    Create a file with invalid UTF-8 byte sequences.
    
    Returns:
        pathlib.Path: Path to malformed UTF-8 file
    """
    malformed = temp_dir / "malformed_utf8.json"
    with open(malformed, 'wb') as f:
        f.write(b'{"items": {"1": {"name": "')
        f.write(b'\xff\xfe')  # Invalid UTF-8 sequence
        f.write(b'"}}}')
    return malformed


@pytest.fixture
def path_traversal_attempt():
    """
    Return dangerous path strings for path traversal testing.
    
    Returns:
        list: Malicious path patterns
    """
    return [
        "../../../etc/passwd",
        "..\\..\\..\\windows\\system32",
        "/etc/passwd",
        "C:\\Windows\\System32\\config\\SAM",
        "./../../sensitive_file.txt",
        "models/../../../../etc/passwd",
    ]


@pytest.fixture
def valid_schema_minimal():
    """
    Create a minimal but valid schema for positive testing.
    
    Returns:
        dict: Valid schema structure
    """
    return {
        "items": {
            "30": {
                "name": "Scattergun",
                "item_class": "scout",
                "item_slot": "primary",
                "model_player": "models/weapons/c_models/c_scattergun_scout.mdl",
                "used_by_classes": {"scout": 1},
            },
            "60": {
                "name": "Bonk! Atomic Punch",
                "item_class": "scout",
                "item_slot": "secondary",
                "model_player": "models/weapons/c_models/c_atomicpunch_scout.mdl",
            },
            "40": {
                "name": "Scout Bat",
                "item_class": "scout",
                "item_slot": "melee",
            },
            "154": {
                "name": "Backwards Ballcap",
                "item_class": "scout",
                "item_slot": "head",
                "model_player": "models/player/items/scout/a_backwards_ballcap.mdl",
            },
        },
        "prefabs": {
            "mvm_upgrades": {},
        },
    }


@pytest.fixture
def schema_file_missing_fields(temp_dir, valid_schema_minimal):
    """
    Create a schema with incomplete item definitions (missing required fields).
    
    Returns:
        pathlib.Path: Path to incomplete schema file
    """
    incomplete = temp_dir / "incomplete_schema.json"
    schema = valid_schema_minimal.copy()
    schema["items"]["999"] = {"name": "Incomplete Item"}  # Missing item_class, item_slot
    incomplete.write_text(json.dumps(schema))
    return incomplete


@pytest.fixture
def corrupt_cache_file(temp_dir):
    """
    Create a corrupted cache file (valid JSON but wrong structure).
    
    Returns:
        pathlib.Path: Path to corrupted cache file
    """
    corrupt = temp_dir / "corrupt_cache.json"
    # Valid JSON but not the expected cache structure
    corrupt.write_text('{"not_a_schema": "this_is_wrong", "has_no_items": true}')
    return corrupt


@pytest.fixture
def empty_file(temp_dir):
    """
    Create an empty file.
    
    Returns:
        pathlib.Path: Path to empty file
    """
    empty = temp_dir / "empty.json"
    empty.touch()
    return empty


@pytest.fixture
def fixture_directory(temp_dir):
    """
    Create and return the fixtures directory used for test data files.
    Creates the directory structure needed for all test files.
    
    Returns:
        pathlib.Path: Path to fixtures directory
    """
    fixtures_dir = temp_dir / "fixtures"
    fixtures_dir.mkdir(exist_ok=True)
    
    # Create subdirectories for organized test data
    (fixtures_dir / "schemas").mkdir(exist_ok=True)
    (fixtures_dir / "models").mkdir(exist_ok=True)
    (fixtures_dir / "materials").mkdir(exist_ok=True)
    
    return fixtures_dir


@pytest.fixture
def sample_valid_schema_file(fixture_directory, valid_schema_minimal):
    """
    Create a valid schema file in fixtures directory.
    
    Returns:
        pathlib.Path: Path to valid schema file
    """
    schema_file = fixture_directory / "schemas" / "valid_schema.json"
    schema_file.write_text(json.dumps(valid_schema_minimal, indent=2))
    return schema_file


@pytest.fixture
def sample_oversized_schema_file(fixture_directory):
    """
    Create an oversized schema file in fixtures directory (sparse, >200MB).
    
    Returns:
        pathlib.Path: Path to oversized schema file
    """
    schema_file = fixture_directory / "schemas" / "oversized_schema.json"
    # Use sparse file to avoid actual disk usage
    with open(schema_file, 'wb') as f:
        f.write(b'{"items": {')
        f.seek(210 * 1024 * 1024)  # Seek to 210 MB
        f.write(b'}}')  # Write end marker
    return schema_file


@pytest.fixture
def null_bytes_file(temp_dir):
    """
    Create a file with null bytes embedded in JSON.
    
    Returns:
        pathlib.Path: Path to file with null bytes
    """
    null_file = temp_dir / "null_bytes.json"
    with open(null_file, 'wb') as f:
        f.write(b'{"items": {"1": {"name": "Test')
        f.write(b'\x00')  # Null byte in middle
        f.write(b'Item"}}}')
    return null_file
