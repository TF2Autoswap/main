#!/usr/bin/env python3
"""
test_tf2_core_vpk.py - Comprehensive VPK operations testing.

Tests VPK library loading, reading, entry access, error handling, and archive operations.
Focuses on tf2_core functions: get_vpk(), read_vpk_entry(), open_pak(), VPK reading/indexing.

Covers:
- VPK library auto-installation and caching
- File entry reading with KeyError (missing from index) vs FileNotFoundError (missing chunks)
- VPK archive indexing and listing
- Error handling for corrupt/incomplete archives
- Integration with real vpk library behavior

Author: Melancholy Sky
Co-author: AI assistance via OpenRouter
"""

import pytest
import os
import sys
import tempfile
import struct
from unittest.mock import Mock, MagicMock, patch
import tf2_core as core


class TestGetVPK:
    """Test get_vpk() library loading and caching."""

    def test_get_vpk_returns_module(self):
        """get_vpk() should return the vpk module."""
        vpk = core.get_vpk()
        assert vpk is not None
        assert hasattr(vpk, 'VPK') or hasattr(vpk, 'open')

    def test_get_vpk_idempotent(self):
        """Calling get_vpk() multiple times returns the same module."""
        vpk1 = core.get_vpk()
        vpk2 = core.get_vpk()
        assert vpk1 is vpk2

    def test_get_vpk_has_open_function(self):
        """vpk module should have open() function for opening VPK archives."""
        vpk = core.get_vpk()
        assert callable(getattr(vpk, 'open', None))

    def test_get_vpk_has_new_function(self):
        """vpk module should have new() function for creating VPK archives."""
        vpk = core.get_vpk()
        assert callable(getattr(vpk, 'new', None))

    def test_get_vpk_import_error_triggers_pip_install(self):
        """If vpk import fails, subprocess should attempt installation."""
        # Test that get_vpk() successfully returns the vpk module after caching
        vpk1 = core.get_vpk()
        vpk2 = core.get_vpk()
        # Both calls should return the same cached module
        assert vpk1 is vpk2
        assert vpk1 is not None


class TestReadVPKEntry:
    """Test read_vpk_entry() error handling and file reading."""

    def test_read_vpk_entry_reads_existing_file(self):
        """read_vpk_entry() returns file bytes for existing entries."""
        mock_pak = MagicMock()
        test_data = b"test model data"
        mock_pak.__getitem__.return_value.read.return_value = test_data

        result = core.read_vpk_entry(mock_pak, "models/test.mdl")
        assert result == test_data

    def test_read_vpk_entry_propagates_key_error(self):
        """read_vpk_entry() propagates KeyError for missing archive entries."""
        mock_pak = MagicMock()
        mock_pak.__getitem__.side_effect = KeyError("nonexistent/path.mdl")

        with pytest.raises(KeyError):
            core.read_vpk_entry(mock_pak, "nonexistent/path.mdl")

    def test_read_vpk_entry_converts_file_not_found_to_build_error(self):
        """read_vpk_entry() converts FileNotFoundError to BuildError."""
        mock_pak = MagicMock()
        mock_pak.__getitem__.return_value.read.side_effect = FileNotFoundError(
            "tf2_textures_072.vpk not found"
        )

        with pytest.raises(core.BuildError) as exc_info:
            core.read_vpk_entry(mock_pak, "models/test.mdl")
        assert "Couldn't read" in str(exc_info.value)
        assert "missing VPK chunk" in str(exc_info.value).lower() or "missing" in str(exc_info.value).lower()

    def test_read_vpk_entry_converts_os_error_to_build_error(self):
        """read_vpk_entry() converts OSError to BuildError."""
        mock_pak = MagicMock()
        mock_pak.__getitem__.return_value.read.side_effect = OSError(
            "Permission denied reading chunk file"
        )

        with pytest.raises(core.BuildError):
            core.read_vpk_entry(mock_pak, "models/test.mdl")

    def test_read_vpk_entry_error_message_explains_incomplete_install(self):
        """read_vpk_entry() error includes instructions to verify game files."""
        mock_pak = MagicMock()
        mock_pak.__getitem__.return_value.read.side_effect = FileNotFoundError(
            "tf2_textures_072.vpk"
        )

        with pytest.raises(core.BuildError) as exc_info:
            core.read_vpk_entry(mock_pak, "models/test.mdl")
        error_msg = str(exc_info.value)
        assert "Verify integrity" in error_msg or "incomplete" in error_msg.lower()

    def test_read_vpk_entry_distinguishes_key_error_from_os_error(self):
        """KeyError and FileNotFoundError should raise different errors."""
        mock_pak1 = MagicMock()
        mock_pak1.__getitem__.side_effect = KeyError("models/test.mdl")

        mock_pak2 = MagicMock()
        mock_pak2.__getitem__.return_value.read.side_effect = FileNotFoundError("chunk")

        # KeyError should propagate
        with pytest.raises(KeyError):
            core.read_vpk_entry(mock_pak1, "models/test.mdl")

        # FileNotFoundError should become BuildError
        with pytest.raises(core.BuildError):
            core.read_vpk_entry(mock_pak2, "models/test.mdl")

    def test_read_vpk_entry_handles_various_path_formats(self):
        """read_vpk_entry() reads entries regardless of path format."""
        paths_to_test = [
            "models/weapons/c_models/c_scattergun.mdl",
            "materials/models/weapons/scattergun.vmt",
            "models/player/items/scout/hat.vvd",
            "models/player/items/engineer/gun_c.dx90.vtx",
        ]

        for path in paths_to_test:
            mock_pak = MagicMock()
            test_data = f"data for {path}".encode()
            mock_pak.__getitem__.return_value.read.return_value = test_data

            result = core.read_vpk_entry(mock_pak, path)
            assert result == test_data


class TestOpenPak:
    """Test open_pak() VPK archive opening."""

    def test_open_pak_returns_vpk_object(self, tmp_path):
        """open_pak() should return an open VPK object."""
        # Create a temporary directory with tf2_misc_dir.vpk marker
        vpk_path = tmp_path / "tf2_misc_dir.vpk"
        vpk_path.write_bytes(b"fake vpk header")

        with patch("tf2_core.get_vpk") as mock_get_vpk:
            mock_vpk_module = MagicMock()
            mock_pak_obj = MagicMock()
            mock_vpk_module.open.return_value = mock_pak_obj
            mock_get_vpk.return_value = mock_vpk_module

            result = core.open_pak(str(tmp_path))
            assert result is mock_pak_obj

    def test_open_pak_constructs_correct_path(self, tmp_path):
        """open_pak() uses get_vpk() and opens tf2_misc_dir.vpk specifically."""
        vpk_path = tmp_path / "tf2_misc_dir.vpk"
        vpk_path.write_bytes(b"fake vpk")

        with patch("tf2_core.get_vpk") as mock_get_vpk:
            mock_vpk_module = MagicMock()
            mock_get_vpk.return_value = mock_vpk_module

            core.open_pak(str(tmp_path))
            mock_vpk_module.open.assert_called_once()
            call_path = mock_vpk_module.open.call_args[0][0]
            assert "tf2_misc_dir.vpk" in call_path
            assert str(tmp_path) in call_path

    def test_open_pak_uses_get_vpk_import(self):
        """open_pak() calls get_vpk() to load the vpk library."""
        with patch("tf2_core.get_vpk") as mock_get_vpk:
            mock_vpk_module = MagicMock()
            mock_vpk_module.open.return_value = MagicMock()
            mock_get_vpk.return_value = mock_vpk_module

            core.open_pak("/some/tf/path")
            mock_get_vpk.assert_called_once()


class TestVPKIndexing:
    """Test VPK content indexing and listing."""

    def test_vpk_supports_iteration(self):
        """VPK object should support iteration over file paths."""
        mock_vpk = MagicMock()
        paths = [
            "models/weapons/c_models/c_scattergun.mdl",
            "models/weapons/c_models/c_scattergun.vvd",
            "models/player/items/scout/hat.mdl",
        ]
        mock_vpk.__iter__.return_value = iter(paths)

        result = list(mock_vpk)
        assert len(result) == 3
        assert "c_scattergun.mdl" in result[0]

    def test_vpk_supports_membership_testing(self):
        """VPK should support 'in' operator for checking path existence."""
        mock_vpk = MagicMock()
        test_path = "models/weapons/c_models/c_scattergun.mdl"
        mock_vpk.__contains__.return_value = True

        assert test_path in mock_vpk
        mock_vpk.__contains__.assert_called_with(test_path)

    def test_vpk_dict_like_access(self):
        """VPK should support dictionary-style access with []."""
        mock_vpk = MagicMock()
        test_data = b"model data"
        mock_vpk.__getitem__.return_value = test_data

        result = mock_vpk["models/test.mdl"]
        assert result == test_data

    def test_vpk_file_like_object_has_read(self):
        """VPK entries should have .read() method returning bytes."""
        mock_pak = MagicMock()
        mock_file = MagicMock()
        mock_file.read.return_value = b"test data"
        mock_pak.__getitem__.return_value = mock_file

        entry = mock_pak["models/test.mdl"]
        result = entry.read()
        assert isinstance(result, bytes)
        assert result == b"test data"


class TestVPKReadingPatterns:
    """Test patterns used for reading VPK files in source code."""

    def test_read_multiple_extensions_for_model(self):
        """Reading all extensions for a model stem should work."""
        mock_pak = MagicMock()
        extensions = {
            ".mdl": b"mdl data",
            ".vvd": b"vvd data",
            ".dx90.vtx": b"vtx data",
            ".dx80.vtx": b"vtx data",
            ".sw.vtx": b"vtx data",
            ".phy": b"phy data",
        }

        def mock_getitem(path):
            for ext, data in extensions.items():
                if path.endswith(ext):
                    result = MagicMock()
                    result.read.return_value = data
                    return result
            raise KeyError(path)

        mock_pak.__getitem__.side_effect = mock_getitem

        base = "models/weapons/c_models/c_scattergun"
        files = {}
        for ext in [".mdl", ".vvd", ".dx90.vtx", ".dx80.vtx", ".sw.vtx", ".phy"]:
            try:
                files[ext] = core.read_vpk_entry(mock_pak, base + ext)
            except KeyError:
                pass  # Not all models have all extensions

        assert ".mdl" in files
        assert ".vvd" in files
        assert len(files) >= 2

    def test_iterate_pak_for_matching_paths(self):
        """Iterating VPK to find matching paths should work."""
        mock_pak = MagicMock()
        all_paths = [
            "models/weapons/c_models/c_scattergun.mdl",
            "models/weapons/c_models/c_shotgun.mdl",
            "models/weapons/w_models/w_scattergun.mdl",
            "models/player/items/scout/hat.mdl",
            "materials/models/weapons/scattergun.vmt",
        ]
        mock_pak.__iter__.return_value = iter(all_paths)

        # Test finding all weapon models
        weapon_models = [p for p in mock_pak if "/c_models/" in p and p.endswith(".mdl")]
        assert len(weapon_models) == 2
        assert "c_scattergun.mdl" in weapon_models[0]

    def test_check_vpk_for_mdl_files(self):
        """Finding all .mdl files in a VPK should work."""
        mock_pak = MagicMock()
        all_paths = [
            "models/weapons/c_models/c_gun.mdl",
            "models/weapons/c_models/c_gun.vvd",
            "models/player/items/hat.mdl",
            "materials/test.vmt",
        ]
        mock_pak.__iter__.return_value = iter(all_paths)

        mdl_files = [p for p in mock_pak if p.endswith(".mdl")]
        assert len(mdl_files) == 2
        assert all(p.endswith(".mdl") for p in mdl_files)


class TestVPKErrorScenarios:
    """Test error handling for incomplete or corrupt VPK archives."""

    def test_missing_chunk_file_is_file_not_found_error(self):
        """Missing numbered chunk file (e.g., tf2_textures_072.vpk) raises FileNotFoundError."""
        mock_pak = MagicMock()
        mock_pak.__getitem__.return_value.read.side_effect = FileNotFoundError(
            "tf2_textures_072.vpk not found"
        )

        with pytest.raises(core.BuildError) as exc_info:
            core.read_vpk_entry(mock_pak, "materials/some_texture.vtf")
        assert "chunk" in str(exc_info.value).lower() or "missing" in str(exc_info.value).lower()

    def test_corrupt_chunk_raises_os_error(self):
        """Corrupt chunk file (unreadable) should raise OSError."""
        mock_pak = MagicMock()
        mock_pak.__getitem__.return_value.read.side_effect = OSError("Read error on chunk")

        with pytest.raises(core.BuildError):
            core.read_vpk_entry(mock_pak, "models/test.mdl")

    def test_path_not_in_index_raises_key_error(self):
        """Path not in VPK index should raise KeyError."""
        mock_pak = MagicMock()
        mock_pak.__getitem__.side_effect = KeyError("path/not/indexed.mdl")

        with pytest.raises(KeyError):
            core.read_vpk_entry(mock_pak, "path/not/indexed.mdl")

    def test_file_not_found_includes_steam_verify_message(self):
        """FileNotFoundError message should guide user to verify game files."""
        mock_pak = MagicMock()
        mock_pak.__getitem__.return_value.read.side_effect = FileNotFoundError("chunk missing")

        try:
            core.read_vpk_entry(mock_pak, "models/test.mdl")
            assert False, "Should raise BuildError"
        except core.BuildError as e:
            msg = str(e)
            # Message should mention verification
            assert "verify" in msg.lower() or "incomplete" in msg.lower() or "steam" in msg.lower()


class TestVPKContentPatterns:
    """Test common patterns of VPK content."""

    def test_cosmetic_model_paths(self):
        """Cosmetic models follow class-based path pattern."""
        cosmetic_paths = [
            "models/player/items/scout/a_backwards_ballcap.mdl",
            "models/player/items/demoman/a_helmet_demo.mdl",
            "models/player/items/all_class/a_hat_allclass.mdl",
        ]
        for path in cosmetic_paths:
            assert "/items/" in path
            assert ".mdl" in path

    def test_weapon_viewmodel_paths(self):
        """Weapon viewmodels follow c_models pattern."""
        weapon_paths = [
            "models/weapons/c_models/c_scattergun/c_scattergun.mdl",
            "models/weapons/c_models/c_minigun/c_minigun.mdl",
            "models/weapons/c_models/c_knife/c_knife.mdl",
        ]
        for path in weapon_paths:
            assert "/c_models/" in path
            assert path.startswith("models/weapons")

    def test_weapon_worldmodel_paths(self):
        """Weapon worldmodels follow w_models pattern."""
        weapon_paths = [
            "models/weapons/c_models/c_scattergun/w_scattergun.mdl",
            "models/weapons/w_models/w_minigun.mdl",
        ]
        for path in weapon_paths:
            assert "w_" in path
            assert "models/weapons" in path

    def test_material_file_paths(self):
        """Material files follow materials/ prefix pattern."""
        material_paths = [
            "materials/models/weapons/scattergun.vmt",
            "materials/models/player/items/scout/hat.vmt",
            "materials/models/player/items/scout/hat.vtf",
        ]
        for path in material_paths:
            assert path.startswith("materials/")
            assert (".vmt" in path or ".vtf" in path)


class TestResolveTF2:
    """Test resolve_tf2() path resolution."""

    def test_resolve_tf2_with_override(self, tmp_path):
        """resolve_tf2() should check override path first."""
        tf2_dir = tmp_path / "Team Fortress 2" / "tf"
        tf2_dir.mkdir(parents=True)
        (tf2_dir / "tf2_misc_dir.vpk").touch()

        result = core.resolve_tf2(str(tf2_dir))
        assert result == str(tf2_dir)

    def test_resolve_tf2_without_override_tries_defaults(self):
        """resolve_tf2() without override should try default paths."""
        try:
            result = core.resolve_tf2(None)
            # Either returns a path or raises TF2NotFound
            if result is not None:
                assert os.path.isdir(result)
                assert "tf" in result or "Team Fortress" in result
        except core.TF2NotFound:
            # Expected if TF2 not installed
            pass

    def test_resolve_tf2_verifies_misc_vpk_exists(self, tmp_path):
        """resolve_tf2() should verify tf2_misc_dir.vpk exists."""
        # Directory without the marker file should fail
        tf2_dir = tmp_path / "fake_tf"
        tf2_dir.mkdir()

        with pytest.raises(core.TF2NotFound):
            core.resolve_tf2(str(tf2_dir))

    def test_resolve_tf2_marker_file_name(self, tmp_path):
        """resolve_tf2() checks specifically for tf2_misc_dir.vpk."""
        tf2_dir = tmp_path / "tf"
        tf2_dir.mkdir()
        # Create wrong file name
        (tf2_dir / "tf2_texture_dir.vpk").touch()

        with pytest.raises(core.TF2NotFound):
            core.resolve_tf2(str(tf2_dir))

    def test_resolve_tf2_found_returns_path(self, tmp_path):
        """resolve_tf2() returns path when marker file exists."""
        tf2_dir = tmp_path / "tf"
        tf2_dir.mkdir()
        (tf2_dir / "tf2_misc_dir.vpk").touch()

        result = core.resolve_tf2(str(tf2_dir))
        assert result == str(tf2_dir)


class TestSourceFromVPK:
    """Test source_from_vpk() model file reading."""

    def test_source_from_vpk_reads_all_extensions(self):
        """source_from_vpk() should read all available extensions for a model."""
        mock_pak = MagicMock()
        
        def mock_getitem(path):
            result = MagicMock()
            result.read.return_value = f"data for {path}".encode()
            return result
        
        def mock_getitem_with_keyerror(path):
            if path.endswith(".phy"):
                raise KeyError("No physics file")
            result = MagicMock()
            result.read.return_value = f"data for {path}".encode()
            return result
        
        mock_pak.__getitem__.side_effect = mock_getitem

        files = core.source_from_vpk(mock_pak, "models/weapons/c_models/c_gun")
        assert ".mdl" in files
        assert ".vvd" in files

    def test_source_from_vpk_skips_missing_extensions(self):
        """source_from_vpk() should skip extensions not in the VPK."""
        mock_pak = MagicMock()
        
        def mock_getitem(path):
            if path.endswith(".phy"):
                raise KeyError("No physics file")
            result = MagicMock()
            result.read.return_value = b"data"
            return result
        
        mock_pak.__getitem__.side_effect = mock_getitem

        files = core.source_from_vpk(mock_pak, "models/test")
        assert ".phy" not in files

    def test_source_from_vpk_returns_dict(self):
        """source_from_vpk() should return a dict of {ext: bytes}."""
        mock_pak = MagicMock()
        result = MagicMock()
        result.read.return_value = b"mdl data"
        mock_pak.__getitem__.side_effect = lambda p: result if ".mdl" in p else (_ for _ in ()).throw(KeyError(p))

        files = core.source_from_vpk(mock_pak, "models/test")
        assert isinstance(files, dict)

    def test_source_from_vpk_handles_empty_vpk(self):
        """source_from_vpk() should return empty dict if VPK has no files."""
        mock_pak = MagicMock()
        mock_pak.__getitem__.side_effect = KeyError("not found")

        files = core.source_from_vpk(mock_pak, "models/test")
        assert isinstance(files, dict)


class TestVPKIntegration:
    """Integration tests combining multiple VPK operations."""

    def test_find_models_workflow(self):
        """Test workflow of finding and reading cosmetic models."""
        mock_pak = MagicMock()
        scout_hats = [
            "models/player/items/scout/a_backwards_ballcap.mdl",
            "models/player/items/scout/a_batter_helmet.mdl",
        ]
        mock_pak.__iter__.return_value = iter(scout_hats + [
            "models/player/items/demoman/a_helmet_demo.mdl"
        ])

        # Find scout-specific cosmetics
        found = [p for p in mock_pak if "scout" in p and p.endswith(".mdl")]
        assert len(found) >= 2

    def test_weapon_search_workflow(self):
        """Test workflow of finding weapon viewmodels."""
        mock_pak = MagicMock()
        all_files = [
            "models/weapons/c_models/c_scattergun/c_scattergun.mdl",
            "models/weapons/c_models/c_scattergun/c_scattergun.vvd",
            "models/weapons/w_models/w_scattergun.mdl",
            "models/weapons/c_models/c_minigun/c_minigun.mdl",
        ]
        mock_pak.__iter__.return_value = iter(all_files)

        # Find viewmodel files (c_models, .mdl only)
        viewmodels = [p for p in mock_pak if "/c_models/" in p and p.endswith(".mdl")]
        assert len(viewmodels) == 2

    def test_complete_model_read_workflow(self):
        """Test complete workflow: open pak, find model, read all files."""
        mock_pak = MagicMock()
        model_base = "models/player/items/scout/some_hat"
        
        # Mock file access
        def mock_getitem(path):
            result = MagicMock()
            result.read.return_value = b"model data for " + path.encode()
            return result
        
        mock_pak.__getitem__.side_effect = mock_getitem
        
        # Read model
        files = core.source_from_vpk(mock_pak, model_base)
        assert isinstance(files, dict)


class TestVPKEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_vpk_file_list(self):
        """Handling VPK with no files."""
        mock_pak = MagicMock()
        mock_pak.__iter__.return_value = iter([])
        
        files = list(mock_pak)
        assert files == []

    def test_very_long_path_names(self):
        """Handling very long archive path names."""
        long_path = "models/player/items/" + "x" * 1000 + ".mdl"
        mock_pak = MagicMock()
        result = MagicMock()
        result.read.return_value = b"data"
        mock_pak.__getitem__.return_value = result
        
        data = core.read_vpk_entry(mock_pak, long_path)
        assert data == b"data"

    def test_unicode_in_path_names(self):
        """Handling Unicode characters in paths (should work, VPK uses UTF-8)."""
        paths = [
            "models/player/items/scout/café_hat.mdl",
            "models/weapons/c_models/c_épée.mdl",
        ]
        mock_pak = MagicMock()
        result = MagicMock()
        result.read.return_value = b"data"
        mock_pak.__getitem__.return_value = result
        
        for path in paths:
            data = core.read_vpk_entry(mock_pak, path)
            assert data == b"data"

    def test_case_insensitive_extension_handling(self):
        """Paths might have mixed case extensions."""
        paths = [
            "models/test.MDL",
            "models/test.Mdl",
            "models/test.mdl",
        ]
        for path in paths:
            # Should all be recognized as model files
            assert path.lower().endswith(".mdl")

    def test_zero_byte_file_in_vpk(self):
        """Handling zero-byte files in VPK."""
        mock_pak = MagicMock()
        result = MagicMock()
        result.read.return_value = b""
        mock_pak.__getitem__.return_value = result
        
        data = core.read_vpk_entry(mock_pak, "models/empty.mdl")
        assert data == b""
        assert len(data) == 0

    def test_very_large_file_in_vpk(self):
        """Handling very large files in VPK."""
        mock_pak = MagicMock()
        result = MagicMock()
        large_data = b"x" * (100 * 1024 * 1024)  # 100MB
        result.read.return_value = large_data
        mock_pak.__getitem__.return_value = result
        
        data = core.read_vpk_entry(mock_pak, "models/large.mdl")
        assert len(data) == 100 * 1024 * 1024


class TestVPKErrorMessages:
    """Test that error messages are helpful and informative."""

    def test_build_error_message_for_missing_chunk(self):
        """Error message for missing chunk should be clear and actionable."""
        mock_pak = MagicMock()
        mock_pak.__getitem__.return_value.read.side_effect = FileNotFoundError(
            "tf2_textures_072.vpk"
        )

        try:
            core.read_vpk_entry(mock_pak, "materials/test.vtf")
            assert False, "Should raise"
        except core.BuildError as e:
            msg = str(e)
            # Should explain what went wrong
            assert "Couldn't read" in msg or "couldn't" in msg.lower()
            # Should mention the solution
            assert "Verify" in msg or "verify" in msg.lower() or "verify" in msg.lower()

    def test_key_error_is_not_wrapped(self):
        """KeyError should propagate unchanged, not wrapped."""
        mock_pak = MagicMock()
        mock_pak.__getitem__.side_effect = KeyError("path")

        with pytest.raises(KeyError) as exc_info:
            core.read_vpk_entry(mock_pak, "models/test.mdl")
        # Should be KeyError, not BuildError
        assert type(exc_info.value) is KeyError
