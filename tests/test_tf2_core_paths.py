#!/usr/bin/env python3
"""
test_tf2_core_paths.py - Tests for tf2_core path handling and validation.

Tests the following functions from tf2_core:
- resolve_tf2() - TF2 installation detection
- Path normalization and validation
- Class filtering and keyword matching

Author: Melancholy Sky
License : GPL v3
"""

import os
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Import core module
import tf2_core as core


class TestResolveTF2:
    """Test TF2 installation path detection."""
    
    def test_resolve_tf2_with_override(self, tf2_paths):
        """Test that --tf2 PATH override is used when provided."""
        tf2_path = str(tf2_paths["tf"])
        result = core.resolve_tf2(override=tf2_path)
        assert result == tf2_path, "Override path should be returned unchanged"
    
    def test_resolve_tf2_with_invalid_override(self):
        """Test that invalid override path raises TF2NotFound."""
        with pytest.raises(core.TF2NotFound):
            core.resolve_tf2(override="/nonexistent/path/to/tf")
    
    def test_resolve_tf2_checks_misc_vpk(self, tf2_paths):
        """Test that resolve_tf2 verifies presence of tf2_misc_dir.vpk."""
        # Delete the marker file
        os.remove(tf2_paths["misc_vpk"])
        
        # Should fail now
        with pytest.raises(core.TF2NotFound):
            core.resolve_tf2(override=str(tf2_paths["tf"]))
    
    def test_resolve_tf2_error_message(self):
        """Test that TF2NotFound error has helpful message."""
        with pytest.raises(core.TF2NotFound) as exc_info:
            core.resolve_tf2(override="/fake/path")
        
        assert "tf2 not found" in str(exc_info.value).lower()


class TestPathNormalization:
    """Test path normalization and handling."""
    
    def test_class_path_terms_complete(self):
        """Test that all 9 classes have path term mappings."""
        expected_classes = {
            "scout", "soldier", "pyro", "demoman", "heavy",
            "engineer", "medic", "sniper", "spy"
        }
        actual_classes = set(core._CLASS_PATH_TERMS.keys())
        assert actual_classes == expected_classes, \
            f"Missing or extra class mappings: {actual_classes ^ expected_classes}"
    
    def test_all_class_path_terms_valid(self):
        """Test that all class path terms are non-empty strings."""
        for class_name, terms in core._CLASS_PATH_TERMS.items():
            assert isinstance(terms, list), f"{class_name} terms should be a list"
            for term in terms:
                assert isinstance(term, str) and len(term) > 0, \
                    f"{class_name} has invalid term: {term}"
    
    def test_shortened_class_names_recognized(self):
        """Test that shortened class names are properly mapped."""
        # Engineer -> engi
        assert "engi" in core._CLASS_PATH_TERMS["engineer"]
        
        # Demoman -> demo
        assert "demo" in core._CLASS_PATH_TERMS["demoman"]
        
        # Soldier -> solly
        assert "solly" in core._CLASS_PATH_TERMS["soldier"]
    
    def test_all_class_path_terms_compiled(self):
        """Test that _ALL_CLASS_PATH_TERMS contains all individual terms."""
        all_terms = core._ALL_CLASS_PATH_TERMS
        
        # Should be sorted
        assert all_terms == sorted(all_terms), "Terms should be sorted"
        
        # Should contain all unique terms from the mapping
        expected_terms = set()
        for terms in core._CLASS_PATH_TERMS.values():
            expected_terms.update(terms)
        
        assert set(all_terms) == expected_terms, \
            "Compiled list should contain all unique terms"


class TestWeaponVariantFiltering:
    """Test weapon variant suffix filtering."""
    
    def test_variant_suffixes_defined(self):
        """Test that weapon variant suffixes are defined."""
        suffixes = core._WEAPON_VARIANT_SUFFIXES
        assert len(suffixes) > 0, "Should have at least one variant suffix"
        
        # Should include common ones
        assert "_festivizer" in suffixes
        assert "_xmas" in suffixes
    
    def test_variant_suffixes_are_strings(self):
        """Test that all variant suffixes are non-empty strings."""
        for suffix in core._WEAPON_VARIANT_SUFFIXES:
            assert isinstance(suffix, str) and len(suffix) > 0, \
                f"Invalid suffix: {suffix}"


class TestModelFileExtensions:
    """Test model file extension requirements."""
    
    def test_exts_defined(self):
        """Test that required model extensions are defined."""
        assert core.EXTS is not None
        assert len(core.EXTS) > 0
    
    def test_exts_includes_mdl(self):
        """Test that .mdl extension is in EXTS."""
        assert ".mdl" in core.EXTS, "Must include .mdl for model descriptor"
    
    def test_exts_includes_vvd(self):
        """Test that .vvd extension is in EXTS."""
        assert ".vvd" in core.EXTS, "Must include .vvd for vertex data"
    
    def test_exts_includes_vtx(self):
        """Test that DirectX 9 VTX extension is in EXTS."""
        assert ".dx90.vtx" in core.EXTS, "Must include .dx90.vtx (standard renderer)"


class TestModelPathPatterns:
    """Test expected model path patterns."""
    
    def test_cosmetic_model_path_structure(self, test_cosmetics):
        """Test that cosmetic paths follow expected structure."""
        for name, data in test_cosmetics.items():
            path = data["path"]
            
            # Should contain models/player/items/
            assert "models/player/items/" in path, \
                f"Cosmetic {name} path should contain models/player/items/"
            
            # Should contain class directory
            assert f"/{data['class']}/" in path, \
                f"Cosmetic {name} should contain /{data['class']}/"
    
    def test_weapon_viewmodel_path_structure(self, test_weapons):
        """Test that weapon viewmodel paths follow expected structure."""
        for name, data in test_weapons.items():
            path = data["viewmodel"]
            
            # Should be in c_models (client/viewmodel)
            assert "c_models" in path, \
                f"Weapon {name} viewmodel should be in c_models"
            
            # Should start with c_
            assert os.path.basename(path).startswith("c_"), \
                f"Weapon {name} viewmodel basename should start with c_"
    
    def test_weapon_worldmodel_path_structure(self, test_weapons):
        """Test that weapon worldmodel paths follow expected structure."""
        for name, data in test_weapons.items():
            path = data["worldmodel"]
            
            # Should be in w_models (world)
            assert "w_models" in path, \
                f"Weapon {name} worldmodel should be in w_models"
            
            # Should start with w_
            assert os.path.basename(path).startswith("w_"), \
                f"Weapon {name} worldmodel basename should start with w_"


class TestTF2Classes:
    """Test TF2 class constants and definitions."""
    
    def test_classes_defined(self):
        """Test that all 9 TF2 classes are defined."""
        expected = 9
        actual = len(core.CLASSES)
        assert actual == expected, f"Expected {expected} classes, got {actual}"
    
    def test_all_class_names_valid(self):
        """Test that all class names are lowercase."""
        for class_name in core.CLASSES:
            assert class_name.islower(), f"Class name should be lowercase: {class_name}"
            assert len(class_name) > 0, "Class name should not be empty"
    
    def test_classes_in_order(self):
        """Test that classes are in expected order."""
        # This is loose — just verify the first and last
        assert core.CLASSES[0] == "scout"
        assert core.CLASSES[-1] == "spy"


class TestExceptionTypes:
    """Test that custom exception types are properly defined."""
    
    def test_swap_error_base(self):
        """Test that SwapError is the base exception."""
        assert issubclass(core.SwapError, Exception)
    
    def test_tf2_not_found_exception(self):
        """Test that TF2NotFound is a SwapError."""
        assert issubclass(core.TF2NotFound, core.SwapError)
    
    def test_model_not_found_exception(self):
        """Test that ModelNotFound is a SwapError."""
        assert issubclass(core.ModelNotFound, core.SwapError)
    
    def test_build_error_exception(self):
        """Test that BuildError is a SwapError."""
        assert issubclass(core.BuildError, core.SwapError)
    
    def test_inventory_error_exception(self):
        """Test that InventoryError is a SwapError."""
        assert issubclass(core.InventoryError, core.SwapError)
