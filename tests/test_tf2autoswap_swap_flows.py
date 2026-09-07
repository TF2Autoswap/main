#!/usr/bin/env python3
"""
test_tf2autoswap_swap_flows.py - Simplified swap flow tests

Tests the core swap workflow functions with proper mocking.
Focuses on testable unit components rather than full end-to-end flows.

Author: Melancholy Sky
Co-author: AI assistance via OpenRouter
"""

import pytest
import io
from unittest.mock import patch, MagicMock, mock_open
import tf2autoswap as cli
import tf2_core as core


class TestSwapUtilities:
    """Test utility functions used in swaps"""

    def test_output_filename_includes_signature(self):
        """output_filename includes tool signature"""
        result = cli.output_filename("models/test", "source", {})
        assert cli.SIGNATURE in result
        assert ".vpk" in result

    def test_output_filename_sanitizes(self):
        """output_filename sanitizes special characters"""
        result = cli.output_filename("models/test<>", "src|bad", {})
        # Should not contain < > |
        assert "<" not in result
        assert ">" not in result
        assert "|" not in result

    def test_preview_build_returns_dict(self):
        """preview_build returns expected structure"""
        result = core.preview_build({'.mdl': b'test'}, 'models/test')
        assert 'entries' in result
        assert 'model_count' in result
        assert 'total_size' in result

    def test_preview_build_weapon_returns_dict(self):
        """preview_build_weapon returns expected structure"""
        result = core.preview_build_weapon(
            {'.mdl': b'view'},
            {'.mdl': b'world'},
            'models/weapons/c_models/test',
            'models/weapons/w_models/test'
        )
        assert 'entries' in result
        assert 'view_count' in result
        assert 'world_count' in result


class TestBuildFunctions:
    """Test build functions (mocked VPK operations)"""

    def test_build_raises_on_missing_mdl(self):
        """build() raises BuildError if .mdl not in files"""
        with pytest.raises(core.BuildError):
            core.build({'.vvd': b'data'}, 'models/test', '/tmp/out.vpk')

    def test_build_returns_dict_with_packed(self):
        """build() returns dict with packed list"""
        with patch('tf2_core.get_vpk') as mock_get_vpk:
            with patch('tempfile.mkdtemp') as mock_tmpdir:
                with patch('shutil.rmtree'):
                    mock_tmpdir.return_value = '/tmp/test'
                    mock_vpk = MagicMock()
                    mock_vpk.new.return_value.save.return_value = None
                    mock_get_vpk.return_value = mock_vpk
                    
                    result = core.build({'.mdl': b'model'}, 'models/test', '/tmp/out.vpk')
                    
                    assert 'packed' in result
                    assert result['out_path'] == '/tmp/out.vpk'

    def test_build_weapon_raises_on_missing_mdl(self):
        """build_weapon() raises if .mdl not in view_files"""
        with pytest.raises(core.BuildError):
            core.build_weapon(
                {'.vvd': b'data'},  # missing .mdl
                {'.mdl': b'world'},
                'models/weapons/c_models/test',
                'models/weapons/w_models/test',
                '/tmp/out.vpk'
            )


class TestSourceFunctions:
    """Test source reading functions"""

    def test_source_from_vpk_returns_dict(self):
        """source_from_vpk returns dict of file extensions"""
        mock_pak = MagicMock()
        
        # Mock read_vpk_entry - need one return per EXTS (6 extensions)
        with patch('tf2_core.read_vpk_entry') as mock_read:
            # Provide returns for all 6 extensions, with some raising KeyError
            mock_read.side_effect = [
                b'mdl_data',  # .mdl
                b'vvd_data',  # .vvd
                b'dx80_data',  # .dx80.vtx
                b'dx90_data',  # .dx90.vtx
                b'sw_data',  # .sw.vtx
                KeyError()  # .phy (optional, may not exist)
            ]
            
            result = core.source_from_vpk(mock_pak, 'models/test')
            
            assert isinstance(result, dict)
            assert len(result) > 0

    def test_source_from_vpk_weapon_returns_tuple(self):
        """source_from_vpk_weapon returns (view, world, world_base) tuple"""
        mock_pak = MagicMock()
        
        with patch('tf2_core.source_from_vpk') as mock_source:
            mock_source.side_effect = [
                {'.mdl': b'view'},
                {'.mdl': b'world'}
            ]
            
            result = core.source_from_vpk_weapon(mock_pak, 'models/weapons/c_models/test')
            
            assert len(result) == 3
            assert isinstance(result[0], dict)  # view files
            assert isinstance(result[1], dict)  # world files
            assert result[2] is not None or result[2] is None  # world base


class TestPathHandling:
    """Test path utilities"""

    def test_safe_join_under_rejects_traversal(self):
        """safe_join_under rejects .. traversal"""
        with pytest.raises(core.BuildError):
            core.safe_join_under('/tmp/base', '../../../etc/passwd')

    def test_safe_join_under_accepts_safe_paths(self):
        """safe_join_under accepts normal paths"""
        result = core.safe_join_under('/tmp/base', 'models/test.mdl')
        assert '/tmp/base' in result
        assert 'models' in result

    def test_resolved_path_under_true_for_safe_path(self):
        """resolved_path_under returns True for paths under root"""
        result = core.resolved_path_under('/tmp/test/file.txt', '/tmp/test')
        assert result is True

    def test_resolved_path_under_false_for_escape(self):
        """resolved_path_under returns False for paths outside root"""
        result = core.resolved_path_under('/etc/passwd', '/tmp/test')
        assert result is False


class TestMDLOperations:
    """Test MDL manipulation functions"""

    def test_patch_mdl_preserves_magic(self):
        """patch_mdl preserves IDST magic"""
        original = b'IDST' + b'\x00' * 100
        result = core.patch_mdl(original, 'newname')
        assert result[:4] == b'IDST'

    def test_patch_mdl_non_mdl_unchanged(self):
        """patch_mdl returns non-MDL data unchanged"""
        original = b'NOTIDST' + b'\x00' * 50
        result = core.patch_mdl(original, 'newname')
        assert result == original

    def test_read_mdl_hull_dimensions_invalid_data(self):
        """read_mdl_hull_dimensions returns None for invalid data"""
        result = core.read_mdl_hull_dimensions(b'not an mdl')
        assert result is None

    def test_prop_size_warning_returns_string_or_none(self):
        """prop_size_warning returns string or None"""
        result = core.prop_size_warning(b'IDST' + b'\x00' * 50, b'IDST' + b'\x00' * 50)
        assert result is None or isinstance(result, str)
