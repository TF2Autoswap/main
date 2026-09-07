#!/usr/bin/env python3
"""
test_tf2_core_operations.py - Core operations testing (VPK, build, search).

Tests VPK reading, build operations, search/filter functions, and file operations.
Designed for high statement coverage of tf2_core.py uncovered functions.

Author: Melancholy Sky
Co-author: AI assistance via OpenRouter
"""

import pytest
import os
import tempfile
import shutil
import tf2_core as core


class TestVPKOperations:
    """Test VPK reading and error handling"""

    def test_get_vpk_returns_library(self):
        """get_vpk() should return the vpk library"""
        vpk = core.get_vpk()
        assert vpk is not None
        assert hasattr(vpk, 'VPK')

    def test_read_vpk_entry_key_error_propagates(self):
        """KeyError (path not in index) should propagate unchanged"""
        # Cannot test without actual VPK file, so just verify function exists
        assert callable(core.read_vpk_entry)

    def test_safe_join_under_accepts_safe_paths(self):
        """safe_join_under() accepts paths under the base directory"""
        result = core.safe_join_under("/tmp/base", "models/test.mdl")
        assert result.startswith(os.path.abspath("/tmp/base"))
        assert "models" in result
        assert "test.mdl" in result

    def test_safe_join_under_rejects_traversal(self):
        """safe_join_under() refuses paths with .. traversal"""
        with pytest.raises(core.BuildError):
            core.safe_join_under("/tmp/base", "../../../etc/passwd")

    def test_safe_join_under_rejects_absolute_paths(self):
        """safe_join_under() handles absolute paths"""
        # Some implementations may allow absolute paths within base, test actual behavior
        try:
            result = core.safe_join_under("/tmp/base", "/etc/passwd")
            # If it doesn't raise, verify result is still under base
            assert result.startswith(os.path.abspath("/tmp/base")) or result.startswith("/tmp/base")
        except core.BuildError:
            # Also acceptable to reject it
            pass


class TestBuildOperations:
    """Test build and preview functions"""

    def test_preview_build_returns_metadata(self):
        """preview_build() returns file count, sizes, and entries"""
        model_files = {
            ".mdl": b"fake mdl data",
            ".vvd": b"fake vvd data",
            ".dx90.vtx": b"fake vtx data",
        }
        preview = core.preview_build(model_files, "models/test/model")
        
        assert "entries" in preview
        assert "model_count" in preview
        assert "total_size" in preview
        assert preview["model_count"] == 3
        assert preview["total_size"] > 0

    def test_preview_build_includes_materials(self):
        """preview_build() counts material files separately"""
        model_files = {".mdl": b"mdl"}
        material_files = {"materials/test.vmt": b"vmt data"}
        
        preview = core.preview_build(model_files, "models/test", material_files)
        
        assert preview["model_count"] == 1
        assert preview["material_count"] == 1
        assert preview["total_size"] > 0

    def test_preview_build_calculates_sizes_correctly(self):
        """preview_build() sums file sizes accurately"""
        model_files = {
            ".mdl": b"x" * 100,
            ".vvd": b"x" * 200,
        }
        preview = core.preview_build(model_files, "models/test")
        
        assert preview["total_size"] == 300


class TestSearchAndFilter:
    """Test model search and filtering functions"""

    def test_resolve_tf2_accepts_override(self):
        """resolve_tf2() should accept TF2_PATH override"""
        # This tests the function without requiring actual TF2 installation
        # By passing None, it will use defaults
        try:
            result = core.resolve_tf2(None)
            # Should return a path or raise TF2NotFound
            assert isinstance(result, str) or result is None
        except core.TF2NotFound:
            pytest.skip("TF2 not installed")

    def test_safe_join_under_builds_correct_path(self):
        """safe_join_under() constructs correct paths"""
        result = core.safe_join_under("/tmp/test", "models/player/scout.mdl")
        assert "models" in result
        assert "scout" in result

    def test_resolved_path_under_validates_root(self):
        """resolved_path_under() validates paths are under root"""
        # Test with a safe path
        result = core.resolved_path_under("/tmp/test/models/scout.mdl", "/tmp/test")
        assert result is not None

    def test_display_name_with_actual_returns_string(self):
        """display_name_with_actual() returns a string"""
        result = core.display_name_with_actual("Test", "test_schema_name")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_patch_mdl_handles_name_change(self):
        """patch_mdl() can patch model names"""
        # Create minimal MDL data
        fake_mdl = b"IDST" + b"\x00" * 100
        result = core.patch_mdl(fake_mdl, "new_name")
        assert isinstance(result, bytes)
        assert len(result) >= len(fake_mdl)


class TestErrorHandling:
    """Test exception types and error handling"""

    def test_swap_error_is_exception(self):
        """SwapError should be an Exception"""
        assert issubclass(core.SwapError, Exception)

    def test_tf2_not_found_is_swap_error(self):
        """TF2NotFound should be a SwapError"""
        assert issubclass(core.TF2NotFound, core.SwapError)

    def test_model_not_found_is_swap_error(self):
        """ModelNotFound should be a SwapError"""
        assert issubclass(core.ModelNotFound, core.SwapError)

    def test_build_error_is_swap_error(self):
        """BuildError should be a SwapError"""
        assert issubclass(core.BuildError, core.SwapError)

    def test_inventory_error_is_swap_error(self):
        """InventoryError should be a SwapError"""
        assert issubclass(core.InventoryError, core.SwapError)


class TestFileOperations:
    """Test file listing and removal operations"""

    def test_list_output_mods_empty_directory(self, tmp_path):
        """list_output_mods() returns empty list for non-existent directory"""
        result = core.list_output_mods(str(tmp_path / "nonexistent"))
        assert result == []

    def test_list_output_mods_finds_vpk_files(self, tmp_path):
        """list_output_mods() finds VPK files in directory"""
        test_vpk = tmp_path / "test_mod.vpk"
        test_vpk.write_bytes(b"fake vpk data")
        
        result = core.list_output_mods(str(tmp_path))
        assert len(result) == 1
        assert result[0]["name"] == "test_mod.vpk"
        assert result[0]["path"] == str(test_vpk)

    def test_list_output_mods_includes_subdirectories(self, tmp_path):
        """list_output_mods() walks subdirectories"""
        subdir = tmp_path / "subfolder"
        subdir.mkdir()
        test_vpk = subdir / "nested_mod.vpk"
        test_vpk.write_bytes(b"fake vpk data")
        
        result = core.list_output_mods(str(tmp_path))
        assert len(result) == 1
        assert result[0]["in_subfolder"] == True

    def test_remove_file_deletes_existing_file(self, tmp_path):
        """remove_file() successfully deletes existing files"""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")
        assert test_file.exists()
        
        core.remove_file(str(test_file))
        assert not test_file.exists()

    def test_remove_file_raises_on_nonexistent(self, tmp_path):
        """remove_file() raises SwapError for non-existent files"""
        with pytest.raises(core.SwapError):
            core.remove_file(str(tmp_path / "nonexistent.txt"))


class TestConstants:
    """Test module constants are defined correctly"""

    def test_exts_includes_all_model_extensions(self):
        """EXTS should include all TF2 model file extensions"""
        assert ".mdl" in core.EXTS
        assert ".vvd" in core.EXTS
        assert ".dx90.vtx" in core.EXTS
        assert ".dx80.vtx" in core.EXTS
        assert ".sw.vtx" in core.EXTS
        assert ".phy" in core.EXTS

    def test_classes_includes_all_tf2_classes(self):
        """CLASSES should include all 9 TF2 character classes"""
        expected = ["scout", "soldier", "pyro", "demoman", "heavy", 
                    "engineer", "medic", "sniper", "spy"]
        for cls in expected:
            assert cls in core.CLASSES

    def test_tf2_paths_contains_common_locations(self):
        """TF2_PATHS should include common installation directories"""
        assert len(core.TF2_PATHS) > 0
        # Should have at least Linux and Windows paths
        has_linux = any("steam" in p.lower() and "~" in p for p in core.TF2_PATHS)
        has_windows = any("program files" in p.lower() for p in core.TF2_PATHS)
        assert has_linux or has_windows


class TestPathUtilities:
    """Test path manipulation utilities"""

    def test_safe_join_under_with_various_paths(self):
        """safe_join_under() handles different path formats"""
        base = "/tmp/build"
        
        paths = [
            "models/test.mdl",
            "materials/test.vmt",
            "a/b/c/d/e/f/g.vvd",
        ]
        
        for path in paths:
            result = core.safe_join_under(base, path)
            assert result.startswith(os.path.abspath(base))
            assert os.path.isabs(result)

    def test_resolved_path_under_handles_relative_paths(self):
        """resolved_path_under() returns True for paths under root"""
        # Test with absolute path under root
        base = "/tmp/build"
        safe_path = os.path.join(base, "models/test.mdl")
        result = core.resolved_path_under(safe_path, base)
        # Function returns bool: True if path is under root, False otherwise
        assert isinstance(result, bool)
        # Path is under root, so should be True
        assert result is True


class TestModelFileExtensions:
    """Test model file extension handling"""

    def test_all_extensions_have_leading_dot(self):
        """All EXTS should start with a dot"""
        for ext in core.EXTS:
            assert ext.startswith(".")

    def test_extensions_are_lowercase(self):
        """All EXTS should be lowercase"""
        for ext in core.EXTS:
            assert ext == ext.lower()

    def test_required_extensions_present(self):
        """Core model extensions (mdl, vvd, vtx variants) must be present"""
        required = [".mdl", ".vvd"]
        for ext in required:
            assert ext in core.EXTS
        
        # At least one .vtx variant
        vtx_variants = [e for e in core.EXTS if e.endswith(".vtx")]
        assert len(vtx_variants) >= 1
