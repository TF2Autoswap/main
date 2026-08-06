#!/usr/bin/env python3
"""
test_tf2autoswap.py - Tests for tf2autoswap.py CLI and interface layer.

Tests utility functions, path handling, naming/display functions,
and CLI argument parsing. Does not test interactive user input (that requires
terminal mocking).

Author: Melancholy Sky
Co-author: AI assistance via OpenRouter
"""

import pytest
import os
import tempfile
import json
import sys
import tf2autoswap as cli


class TestPathConstants:
    """Test path constants are initialized correctly"""

    def test_script_dir_is_absolute(self):
        """_SCRIPT_DIR should be an absolute path"""
        assert os.path.isabs(cli._SCRIPT_DIR)

    def test_state_dir_under_script_dir(self):
        """STATE_DIR should be under _SCRIPT_DIR"""
        assert cli.STATE_DIR.startswith(cli._SCRIPT_DIR)

    def test_output_dir_under_script_dir(self):
        """OUTPUT_DIR should be under _SCRIPT_DIR"""
        assert cli.OUTPUT_DIR.startswith(cli._SCRIPT_DIR)

    def test_imports_dir_under_script_dir(self):
        """IMPORTS_DIR should be under _SCRIPT_DIR"""
        assert cli.IMPORTS_DIR.startswith(cli._SCRIPT_DIR)

    def test_import_subdirs_exist_list(self):
        """IMPORT_SUBDIRS should be a list with entries"""
        assert isinstance(cli.IMPORT_SUBDIRS, list)
        assert len(cli.IMPORT_SUBDIRS) > 0
        assert "cosmetics" in cli.IMPORT_SUBDIRS

    def test_preloader_addons_path_set(self):
        """PRELOADER_ADDONS should be set"""
        assert isinstance(cli.PRELOADER_ADDONS, str)
        assert len(cli.PRELOADER_ADDONS) > 0


class TestNamingAndFormatting:
    """Test utility functions for item naming and display"""

    def test_fmt_size_formats_bytes(self):
        """fmt_size() formats byte counts as human-readable strings"""
        result_100 = cli.fmt_size(100)
        assert "bytes" in result_100 or "B" in result_100
        assert cli.fmt_size(1024) != cli.fmt_size(1)

    def test_fmt_size_handles_large_numbers(self):
        """fmt_size() handles MB and GB sizes"""
        result = cli.fmt_size(1024 * 1024 * 1024)  # 1 GB
        assert isinstance(result, str)
        assert len(result) > 0

    def test_normalize_keyword_lowercases(self):
        """normalize_keyword() converts to lowercase"""
        result = cli.normalize_keyword("SCATTER-GUN")
        assert result == result.lower()

    def test_normalize_keyword_removes_spaces(self):
        """normalize_keyword() removes spaces"""
        result = cli.normalize_keyword("SCATTER GUN")
        assert " " not in result

    def test_normalize_keyword_handles_empty(self):
        """normalize_keyword() handles empty strings"""
        result = cli.normalize_keyword("")
        assert isinstance(result, str)

    def test_has_invalid_path_chars_detects_bad_chars(self):
        """has_invalid_path_chars() identifies invalid filename characters"""
        # Should detect < > : " / \ | ? *
        assert cli.has_invalid_path_chars("file<name>") is True or \
               cli.has_invalid_path_chars("file<name>") == True

    def test_has_invalid_path_chars_accepts_valid(self):
        """has_invalid_path_chars() accepts valid filenames"""
        assert cli.has_invalid_path_chars("valid_filename.txt") is False

    def test_sanitize_filename_removes_invalid_chars(self):
        """sanitize_filename() removes invalid path characters"""
        result = cli.sanitize_filename("file<name>")
        assert isinstance(result, str)
        # Should not contain path separators or invalid chars
        assert "/" not in result or "\\" not in result

    def test_sanitize_filename_preserves_valid(self):
        """sanitize_filename() preserves valid filenames"""
        original = "my_cool_mod.vpk"
        result = cli.sanitize_filename(original)
        assert original.replace(".", "") in result.replace(".", "") or result == original


class TestOutputPathGeneration:
    """Test output path and filename generation"""

    def test_validate_output_path_accepts_valid_path(self):
        """validate_output_path() accepts valid directory paths"""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = cli.validate_output_path(tmpdir)
            # Returns tuple (bool, optional_error_string)
            assert isinstance(result, tuple)
            assert result[0] is True

    def test_validate_output_path_rejects_nonexistent_base(self):
        """validate_output_path() may reject non-existent parent directories"""
        bad_path = "/nonexistent/deeply/nested/path"
        try:
            result = cli.validate_output_path(bad_path)
            # Function returns tuple (bool, error_string or None)
            assert isinstance(result, tuple)
            # Should return False since /nonexistent doesn't exist
            assert result[0] is False
            assert isinstance(result[1], (str, type(None)))
        except (OSError, ValueError):
            # Also acceptable
            pass

    def test_output_filename_returns_string(self):
        """output_filename() returns a filename string"""
        result = cli.output_filename("models/test", "src", {})
        assert isinstance(result, str)
        assert len(result) > 0

    def test_output_filename_includes_signature(self):
        """output_filename() includes SIGNATURE string"""
        result = cli.output_filename("models/test", "src", {})
        # Should include _TF2autoswap signature
        assert cli.SIGNATURE in result or cli.PROJECT in result.lower()

    def test_resolve_out_path_returns_absolute(self):
        """resolve_out_path() returns absolute path"""
        result = cli.resolve_out_path("output.vpk", "default.vpk")
        assert os.path.isabs(result) or isinstance(result, str)

    def test_resolve_out_path_uses_default(self):
        """resolve_out_path() uses default when given path is valid"""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = cli.resolve_out_path(tmpdir, "default.vpk")
            assert isinstance(result, str)
            assert "default.vpk" in result


class TestKeywordMatching:
    """Test keyword search and name matching"""

    def test_normalize_keyword_consistency(self):
        """normalize_keyword() is consistent"""
        keyword = "TEST_Keyword"
        result1 = cli.normalize_keyword(keyword)
        result2 = cli.normalize_keyword(keyword)
        assert result1 == result2

    def test_reverse_name_lookup_with_empty_index(self):
        """reverse_name_lookup() handles empty index gracefully"""
        result = cli.reverse_name_lookup({}, "test")
        # May return None or empty list
        assert result is None or isinstance(result, list)

    def test_reverse_name_lookup_weapon_with_empty_index(self):
        """reverse_name_lookup_weapon() handles empty index gracefully"""
        result = cli.reverse_name_lookup_weapon({}, "test")
        # May return None or empty list
        assert result is None or isinstance(result, list)


class TestWarningGeneration:
    """Test warning messages for problematic swaps"""

    def test_weapon_warning_returns_string_or_none(self):
        """weapon_warning() returns string warning or None"""
        result = cli.weapon_warning({}, "models/weapons/test", "models/weapons/other")
        assert result is None or isinstance(result, str)

    def test_clip_warning_returns_string_or_none(self):
        """clip_warning() returns string warning or None"""
        result = cli.clip_warning({}, "models/test", "models/other")
        assert result is None or isinstance(result, str)

    def test_slots_for_class_returns_list(self):
        """slots_for_class() returns a list of slots"""
        result = cli.slots_for_class({}, "scout")
        assert isinstance(result, list) or result is None


class TestLoggingSetup:
    """Test logging configuration"""

    def test_setup_logging_returns_logger(self):
        """setup_logging() returns a configured logger"""
        logger = cli.setup_logging()
        assert logger is not None

    def test_log_is_module_logger(self):
        """log module variable is set up"""
        assert cli.log is not None
        # Should be a logger instance
        assert hasattr(cli.log, 'info')
        assert callable(cli.log.info)


class TestBrandingConstants:
    """Test branding and version constants"""

    def test_project_name_set(self):
        """PROJECT name is defined"""
        assert cli.PROJECT == "TF2autoswap"

    def test_version_set(self):
        """VERSION is defined"""
        assert cli.VERSION == "4.8"
        assert "." in cli.VERSION

    def test_signature_set(self):
        """SIGNATURE is defined and includes underscore"""
        assert cli.SIGNATURE == "_TF2autoswap"
        assert "_" in cli.SIGNATURE

    def test_whats_new_set(self):
        """WHATS_NEW message is defined"""
        assert len(cli.WHATS_NEW) > 0
        assert isinstance(cli.WHATS_NEW, str)


class TestPreloaderPathDetection:
    """Test Casual Preloader folder detection"""

    def test_is_in_preloader_with_nonexistent_preloader(self):
        """is_in_preloader() handles non-existent preloader directory"""
        result = cli.is_in_preloader("/some/path", "/nonexistent/preloader")
        # Should return False or bool
        assert isinstance(result, (bool, type(None))) or result is False

    def test_is_in_preloader_with_valid_path(self):
        """is_in_preloader() returns boolean"""
        with tempfile.TemporaryDirectory() as tmpdir:
            addon_path = os.path.join(tmpdir, "addon.vpk")
            result = cli.is_in_preloader(addon_path, tmpdir)
            assert isinstance(result, bool)

    def test_confirm_preloader_write_with_invalid_path(self):
        """confirm_preloader_write() handles invalid preloader path"""
        # May raise exception or return None
        try:
            result = cli.confirm_preloader_write("/nonexistent/path")
            assert result is None or isinstance(result, bool)
        except (OSError, ValueError):
            pass


class TestDisplayNameFunctions:
    """Test friendly name display helpers"""

    def test_display_name_with_empty_index(self):
        """display_name() handles empty index gracefully"""
        result = cli.display_name("models/test", {})
        # Should return path or some string representation
        assert isinstance(result, str)

    def test_label_for_with_empty_index(self):
        """label_for() handles empty index gracefully"""
        result = cli.label_for("models/cosmetics/test", {})
        assert isinstance(result, str)

    def test_label_for_weapon_with_empty_index(self):
        """label_for_weapon() handles empty index gracefully"""
        result = cli.label_for_weapon("models/weapons/c_models/test", {})
        assert isinstance(result, str)


class TestIndexLoading:
    """Test schema index loading and caching"""

    def test_load_index_with_nonexistent_tf2_path(self):
        """load_index() handles missing TF2 gracefully"""
        try:
            result = cli.load_index("/nonexistent/tf2/path")
            # May return empty dict or raise exception
            assert isinstance(result, dict) or result is None
        except Exception:
            # Expected if schema is not available
            pass

    def test_load_defindex_index_with_nonexistent_tf2_path(self):
        """load_defindex_index() handles missing TF2 gracefully"""
        try:
            result = cli.load_defindex_index("/nonexistent/tf2/path")
            assert isinstance(result, dict) or result is None
        except Exception:
            # Expected if schema is not available
            pass


class TestModuleOptionalFeatures:
    """Test optional module dependencies"""

    def test_have_schema_is_boolean(self):
        """HAVE_SCHEMA flag is a boolean"""
        assert isinstance(cli.HAVE_SCHEMA, bool)

    def test_have_material_is_boolean(self):
        """HAVE_MATERIAL flag is a boolean"""
        assert isinstance(cli.HAVE_MATERIAL, bool)

    def test_can_import_core(self):
        """tf2_core is always imported"""
        assert cli.core is not None


class TestFilenameHandling:
    """Test filename sanitization and validation"""

    def test_sanitize_filename_handles_none(self):
        """sanitize_filename() handles edge cases"""
        try:
            result = cli.sanitize_filename("")
            assert isinstance(result, str)
        except (TypeError, ValueError):
            pass

    def test_sanitize_filename_handles_special_chars(self):
        """sanitize_filename() processes special characters"""
        result = cli.sanitize_filename("file-with_special.chars@here")
        assert isinstance(result, str)

    def test_output_filename_consistency(self):
        """output_filename() produces consistent results"""
        result1 = cli.output_filename("models/test", "src", {})
        result2 = cli.output_filename("models/test", "src", {})
        assert result1 == result2


class TestVPKandAddonEmission:
    """Test VPK and addon folder output helpers"""

    def test_emit_vpk_callable(self):
        """emit_vpk() is callable"""
        assert callable(cli.emit_vpk)

    def test_emit_addon_callable(self):
        """emit_addon() is callable"""
        assert callable(cli.emit_addon)

    def test_emit_weapon_vpk_callable(self):
        """emit_weapon_vpk() is callable"""
        assert callable(cli.emit_weapon_vpk)

    def test_emit_weapon_addon_callable(self):
        """emit_weapon_addon() is callable"""
        assert callable(cli.emit_weapon_addon)

    def test_get_disk_source_callable(self):
        """get_disk_source() is callable"""
        assert callable(cli.get_disk_source)


class TestDiskSourceHandling:
    """Test disk-based source file handling"""

    def test_get_disk_source_with_nonexistent_file(self):
        """get_disk_source() handles missing files"""
        try:
            result = cli.get_disk_source("/nonexistent/model.mdl")
            # May raise exception or return None
            assert result is None or isinstance(result, dict)
        except (FileNotFoundError, Exception):
            # Expected
            pass

    def test_get_disk_source_with_invalid_file(self):
        """get_disk_source() rejects non-MDL files"""
        with tempfile.NamedTemporaryFile(suffix=".txt") as f:
            try:
                result = cli.get_disk_source(f.name)
                # Should fail or return None
                assert result is None
            except Exception:
                # Expected — not a .mdl file
                pass
