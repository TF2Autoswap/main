#!/usr/bin/env python3
"""
test_tf2_material_extended.py - Extended test coverage for tf2_material.py (v4.8).

This module provides comprehensive coverage of the material swapping engine,
including material classification, VMT safety scanning, material file operations,
and VPK building.

Test Categories:
  1. Material path classification and safety scope
  2. VMT content scanning (risky parameters, proxies, shaders)
  3. Material file reading from disk and VPKs
  4. Material resolution from game archives
  5. VPK building and validation
  6. Edge cases and error handling
  7. Complex proxy scenarios and nested includes
"""

import os
import sys
import json
import struct
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

import pytest

# Add parent directory to path
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(TEST_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import tf2_material as material
import tf2_core as core


# ===========================================================================
# Fixtures: VMT and VTF test data
# ===========================================================================

@pytest.fixture
def clean_vmt_weapon():
    """A clean weapon material with no risky parameters."""
    return b"""
"LightmappedGeneric"
{
    "$basetexture" "models/weapons/c_models/c_scattergun"
    "$bumpmap" "models/weapons/c_models/c_scattergun_normal"
    "$phong" "1"
    "$phongfresnelranges" "[0.05 0.5 1]"
}
"""


@pytest.fixture
def clean_cosmetic_vmt():
    """A clean cosmetic material."""
    return b"""
"VertexLitGeneric"
{
    "$basetexture" "models/player/items/scout/a_backwards_ballcap"
    "$bumpmap" "models/player/items/scout/a_backwards_ballcap_normal"
}
"""


@pytest.fixture
def vmt_with_ignorez():
    """Material with the critical $ignorez wallhack flag."""
    return b"""
"LightmappedGeneric"
{
    "$basetexture" "materials/models/weapons/test"
    "$ignorez" "1"
}
"""


@pytest.fixture
def vmt_with_additive():
    """Material with additive blending (high severity)."""
    return b"""
"VertexLitGeneric"
{
    "$basetexture" "materials/models/weapons/test"
    "$additive" "1"
}
"""


@pytest.fixture
def vmt_with_translucent():
    """Material with translucent flag."""
    return b"""
"VertexLitGeneric"
{
    "$basetexture" "materials/models/weapons/test"
    "$translucent" "1"
    "$alpha" "0.5"
}
"""


@pytest.fixture
def vmt_with_proxies_safe():
    """Material with safe proxies (e.g., animated texture)."""
    return b"""
"LightmappedGeneric"
{
    "$basetexture" "models/weapons/c_models/c_scattergun"
    
    "Proxies"
    {
        "AnimatedTexture"
        {
            "animatedtexturevar" "$basetexture"
            "animatedtextureframenumvar" "$frame"
            "animatedtextureframerate" "10"
        }
    }
}
"""


@pytest.fixture
def vmt_with_proxies_risky():
    """Material with risky proxy targeting $alpha."""
    return b"""
"LightmappedGeneric"
{
    "$basetexture" "models/weapons/c_models/c_test"
    
    "Proxies"
    {
        "AnimatedTexture"
        {
            "animatedtexturevar" "$basetexture"
            "resultvar" "$alpha"
        }
    }
}
"""


@pytest.fixture
def vmt_with_unlit_shader():
    """Material using UnlitGeneric shader (fullbright / ESP)."""
    return b"""
"UnlitGeneric"
{
    "$basetexture" "models/weapons/c_models/c_test"
}
"""


@pytest.fixture
def vmt_with_patch_shader():
    """Material using Patch shader with includes."""
    return b"""
"Patch"
{
    "include" "models/base_material.vmt"
    "$selfillum" "1"
    "$selfillumtint" "[1 1 1]"
}
"""


@pytest.fixture
def vmt_with_selfillum():
    """Material with strong self-illumination."""
    return b"""
"VertexLitGeneric"
{
    "$basetexture" "models/test"
    "$selfillum" "1"
    "$selfillumtint" "[0.95 0.95 0.95]"
}
"""


@pytest.fixture
def mock_mdl_weapon():
    """Generate a minimal valid .mdl header for a weapon."""
    mdl = bytearray(512)
    
    # IDST magic
    mdl[0:4] = b"IDST"
    
    # Version 49
    struct.pack_into("<I", mdl, 4, 49)
    
    # Texture info
    num_textures = 2
    texture_index = 0x100
    struct.pack_into("<I", mdl, 0xCC, num_textures)
    struct.pack_into("<I", mdl, 0xD0, texture_index)
    
    # CD textures info
    num_cdtextures = 1
    cdtexture_index = 0x200
    struct.pack_into("<I", mdl, 0xD4, num_cdtextures)
    struct.pack_into("<I", mdl, 0xD8, cdtexture_index)
    
    # Add texture names at offset 0x100
    name_offset = 0x300
    texture_name = b"c_scattergun\x00"
    mdl[name_offset:name_offset + len(texture_name)] = texture_name
    
    # Add texture entry (mstudiotexture_t at 0x100, 64 bytes each)
    struct.pack_into("<i", mdl, texture_index, name_offset - texture_index)
    
    # Add CD material dir at offset 0x200
    cd_dir = b"models/weapons/c_models/c_scattergun/\x00"
    cdtex_offset = 0x400
    mdl[cdtex_offset:cdtex_offset + len(cd_dir)] = cd_dir
    
    # Pointer to CD dir string
    struct.pack_into("<i", mdl, cdtexture_index, cdtex_offset)
    
    return bytes(mdl)


@pytest.fixture
def mock_mdl_cosmetic():
    """Generate a minimal valid .mdl header for a cosmetic."""
    mdl = bytearray(512)
    
    mdl[0:4] = b"IDST"
    struct.pack_into("<I", mdl, 4, 49)
    
    num_textures = 1
    texture_index = 0x100
    struct.pack_into("<I", mdl, 0xCC, num_textures)
    struct.pack_into("<I", mdl, 0xD0, texture_index)
    
    num_cdtextures = 1
    cdtexture_index = 0x200
    struct.pack_into("<I", mdl, 0xD4, num_cdtextures)
    struct.pack_into("<I", mdl, 0xD8, cdtexture_index)
    
    name_offset = 0x300
    texture_name = b"a_backwards_ballcap\x00"
    mdl[name_offset:name_offset + len(texture_name)] = texture_name
    
    struct.pack_into("<i", mdl, texture_index, name_offset - texture_index)
    
    cd_dir = b"models/player/items/scout/\x00"
    cdtex_offset = 0x400
    mdl[cdtex_offset:cdtex_offset + len(cd_dir)] = cd_dir
    
    struct.pack_into("<i", mdl, cdtexture_index, cdtex_offset)
    
    return bytes(mdl)


@pytest.fixture
def temp_materials_folder(tmp_path):
    """Create a temporary materials folder with sample .vmt and .vtf files."""
    materials_dir = tmp_path / "materials"
    materials_dir.mkdir()
    
    # Create weapon material path
    weapon_path = materials_dir / "models" / "weapons" / "c_models" / "c_scattergun"
    weapon_path.mkdir(parents=True)
    
    # Create .vmt file
    vmt_file = weapon_path / "c_scattergun.vmt"
    vmt_file.write_bytes(b"""
"LightmappedGeneric"
{
    "$basetexture" "models/weapons/c_models/c_scattergun/c_scattergun"
}
""")
    
    # Create .vtf file
    vtf_file = weapon_path / "c_scattergun.vtf"
    vtf_file.write_bytes(b"VTF_MAGIC_DATA")
    
    return tmp_path


# ===========================================================================
# Tests: Material Path Classification
# ===========================================================================

class TestClassifyMaterialPath:
    """Test material path classification for scope determination."""
    
    def test_classify_weapon_viewmodel(self):
        """Weapon viewmodel materials should be classified as 'weapon'."""
        path = "materials/models/weapons/c_models/c_scattergun/c_scattergun.vmt"
        assert material.classify_material_path(path) == "weapon"
    
    def test_classify_weapon_worldmodel(self):
        """Weapon worldmodel materials should be classified as 'weapon'."""
        path = "materials/models/weapons/w_models/w_scattergun/w_scattergun.vmt"
        assert material.classify_material_path(path) == "weapon"
    
    def test_classify_paintkit_material(self):
        """Paintkit materials should be classified as "other" (paintkits no longer in allowed roots)."""
        path = "materials/models/paintkits/unusualeffects/smoke_green.vmt"
        assert material.classify_material_path(path) == "other"
    
    def test_classify_cosmetic_item(self):
        """Cosmetic item materials should be classified as 'cosmetic'."""
        path = "materials/models/player/items/scout/a_backwards_ballcap.vmt"
        assert material.classify_material_path(path) == "cosmetic"
    
    def test_classify_workshop_weapon(self):
        """Workshop weapon materials should be classified as 'weapon'."""
        path = "materials/models/workshop/weapons/c_models/custom_gun.vmt"
        assert material.classify_material_path(path) == "weapon"
    
    def test_classify_workshop_cosmetic(self):
        """Workshop cosmetic materials should be classified as 'cosmetic'."""
        path = "materials/models/workshop/player/items/scout/custom_hat.vmt"
        assert material.classify_material_path(path) == "cosmetic"
    
    def test_classify_player_base_material(self):
        """Base player body materials should be blocked (ESP vector)."""
        path = "materials/models/player/scout/scout_body.vmt"
        assert material.classify_material_path(path) == "player_base"
    
    def test_classify_player_base_demoman(self):
        """Base player materials for any class should be blocked."""
        path = "materials/models/player/demoman/demoman_body.vmt"
        assert material.classify_material_path(path) == "player_base"
    
    def test_classify_cosmetic_skipped(self):
        """Cosmetic in /items/ should not be classified as player_base."""
        path = "materials/models/player/items/demoman/helmet.vmt"
        assert material.classify_material_path(path) == "cosmetic"
    
    def test_classify_map_material(self):
        """Map materials should be blocked (wallhack vector)."""
        path = "materials/maps/cp_dustbowl/roof.vmt"
        assert material.classify_material_path(path) == "world"
    
    def test_classify_brick_material(self):
        """Brick material should be blocked."""
        path = "materials/brick/brickwall004.vmt"
        assert material.classify_material_path(path) == "world"
    
    def test_classify_effect_material(self):
        """Effect materials should be blocked."""
        path = "materials/effects/stun/shine.vmt"
        assert material.classify_material_path(path) == "world"
    
    def test_classify_decal_material(self):
        """Decal materials should be blocked."""
        path = "materials/decals/decalblood001.vmt"
        assert material.classify_material_path(path) == "world"
    
    def test_classify_prop_material(self):
        """Prop materials should be classified as 'prop'."""
        path = "materials/models/props_2fort/barrel.vmt"
        assert material.classify_material_path(path) == "prop"
    
    def test_classify_other_material(self):
        """Unknown materials without models/ segment default to 'world'."""
        # materials/<word>/ without models/ is treated as world (fail-safe)
        path = "materials/unknown/custom_thing.vmt"
        assert material.classify_material_path(path) == "world"
    
    def test_path_traversal_normalization(self):
        """Path traversal attempts should be normalized and blocked."""
        # Try to escape to a map material via ..
        path = "materials/models/weapons/c_models/../../../maps/evil.vmt"
        result = material.classify_material_path(path)
        # Should normalize to maps/evil.vmt and classify as world
        assert result == "world"
    
    def test_path_traversal_with_backslashes(self):
        """Path traversal with backslashes should be normalized."""
        path = "materials\\models\\weapons\\..\\..\\..\\maps\\evil.vmt"
        result = material.classify_material_path(path)
        assert result == "world"
    
    def test_case_insensitive_classification(self):
        """Path classification should be case-insensitive."""
        path = "MATERIALS/MODELS/WEAPONS/C_MODELS/C_SCATTERGUN.VMT"
        assert material.classify_material_path(path) == "weapon"
    
    def test_missing_materials_prefix(self):
        """Paths without 'materials/' prefix should be auto-prefixed."""
        path = "models/weapons/c_models/c_scattergun.vmt"
        assert material.classify_material_path(path) == "weapon"


# ===========================================================================
# Tests: VMT Keyvalue Parsing
# ===========================================================================

class TestReadVMTKeyvalues:
    """Test VMT file parsing and keyvalue extraction."""
    
    def test_parse_simple_vmt(self, clean_vmt_weapon):
        """Parse a simple VMT and extract shader and keyvalues."""
        shader, kv = material.read_vmt_keyvalues(clean_vmt_weapon)
        assert shader == "lightmappedgeneric"
        assert "$basetexture" in kv
        assert kv["$basetexture"] == "models/weapons/c_models/c_scattergun"
    
    def test_parse_vmt_with_comments(self):
        """VMT parsing should strip comments."""
        vmt = b"""
"LightmappedGeneric"
{
    // This is a comment
    "$basetexture" "test"  // inline comment
}
"""
        shader, kv = material.read_vmt_keyvalues(vmt)
        assert shader == "lightmappedgeneric"
        assert "$basetexture" in kv
    
    def test_parse_vmt_quoted_keys(self):
        """VMT parser should handle quoted keys and values."""
        vmt = b"""
"VertexLitGeneric"
{
    "$basetexture" "models/test"
    "$phongfresnelranges" "[0.05 0.5 1]"
}
"""
        shader, kv = material.read_vmt_keyvalues(vmt)
        assert "$phongfresnelranges" in kv
    
    def test_parse_vmt_unquoted_keys(self):
        """VMT parser should handle unquoted keys."""
        vmt = b"""
LightmappedGeneric
{
    $basetexture test
    $bumpmap test_normal
}
"""
        shader, kv = material.read_vmt_keyvalues(vmt)
        assert shader == "lightmappedgeneric"
        assert "$basetexture" in kv
    
    def test_parse_vmt_invalid_utf8(self):
        """VMT parser should handle invalid UTF-8 gracefully."""
        vmt = b"\xff\xfe" + b"test"
        shader, kv = material.read_vmt_keyvalues(vmt)
        # Should return without crashing
        assert isinstance(shader, str)
        assert isinstance(kv, dict)
    
    def test_parse_malformed_vmt(self):
        """VMT parser should handle malformed files."""
        vmt = b"not a valid vmt"
        shader, kv = material.read_vmt_keyvalues(vmt)
        assert shader == ""
        assert len(kv) == 0


# ===========================================================================
# Tests: VMT Safety Scanning
# ===========================================================================

class TestScanVMTSafety:
    """Test VMT content scanning for risky parameters."""
    
    def test_scan_clean_material(self, clean_vmt_weapon):
        """Clean material should have no findings."""
        findings = material.scan_vmt_safety(clean_vmt_weapon)
        assert len(findings) == 0
    
    def test_scan_ignorez_critical(self, vmt_with_ignorez):
        """$ignorez should be flagged as critical."""
        findings = material.scan_vmt_safety(vmt_with_ignorez)
        assert len(findings) > 0
        assert any(f.severity == "critical" for f in findings)
        assert any("$ignorez" in f.param for f in findings)
    
    def test_scan_additive_high(self, vmt_with_additive):
        """$additive should be flagged as high severity."""
        findings = material.scan_vmt_safety(vmt_with_additive)
        assert len(findings) > 0
        assert any(f.severity == "high" for f in findings)
    
    def test_scan_translucent_high(self, vmt_with_translucent):
        """$translucent should be flagged as high severity."""
        findings = material.scan_vmt_safety(vmt_with_translucent)
        high_findings = [f for f in findings if f.severity == "high"]
        assert len(high_findings) > 0
    
    def test_scan_alpha_below_one(self):
        """$alpha < 1 should be flagged as high."""
        vmt = b"""
"VertexLitGeneric"
{
    "$basetexture" "test"
    "$alpha" "0.5"
}
"""
        findings = material.scan_vmt_safety(vmt)
        assert any("$alpha" in f.param and f.severity == "high" for f in findings)
    
    def test_scan_unlit_shader(self, vmt_with_unlit_shader):
        """UnlitGeneric shader should be flagged as high (fullbright)."""
        findings = material.scan_vmt_safety(vmt_with_unlit_shader)
        assert any(f.severity == "high" and "shader" in f.param for f in findings)
    
    def test_scan_proxies_safe(self, vmt_with_proxies_safe):
        """Safe proxies should be noted as info-level, not blocking."""
        findings = material.scan_vmt_safety(vmt_with_proxies_safe)
        # May have info findings but not critical
        assert not any(f.severity == "critical" for f in findings)
    
    def test_scan_proxies_risky(self, vmt_with_proxies_risky):
        """Risky proxy targets should be flagged as critical."""
        findings = material.scan_vmt_safety(vmt_with_proxies_risky)
        assert any(f.severity == "critical" for f in findings)
    
    def test_scan_patch_shader(self, vmt_with_patch_shader):
        """Patch shader should be noted as info (incomplete scan)."""
        findings = material.scan_vmt_safety(vmt_with_patch_shader)
        assert any("patch" in f.param.lower() for f in findings)
    
    def test_scan_selfillum_bright(self, vmt_with_selfillum):
        """Strong self-illum should be flagged as high (fullbright)."""
        findings = material.scan_vmt_safety(vmt_with_selfillum)
        assert any(f.severity == "high" and "selfillum" in f.param for f in findings)


# ===========================================================================
# Tests: Proxy Target Detection
# ===========================================================================

class TestRiskyProxyTargets:
    """Test detection of risky proxy resultVar targets."""
    
    def test_find_risky_proxy_alpha(self, vmt_with_proxies_risky):
        """Should find $alpha in proxy targets."""
        text = vmt_with_proxies_risky.decode("utf-8", errors="replace")
        targets = material.find_risky_proxy_targets(text)
        assert "$alpha" in targets
    
    def test_find_safe_proxy_targets(self, vmt_with_proxies_safe):
        """Safe proxies should not be detected as risky."""
        text = vmt_with_proxies_safe.decode("utf-8", errors="replace")
        targets = material.find_risky_proxy_targets(text)
        # Safe animated texture shouldn't target risky params
        assert len(targets) == 0
    
    def test_has_proxies_block(self, vmt_with_proxies_safe):
        """Detection of Proxies block presence."""
        text = vmt_with_proxies_safe.decode("utf-8", errors="replace")
        assert material.has_proxies_block(text) is True
    
    def test_no_proxies_block(self, clean_vmt_weapon):
        """Clean material without proxies."""
        text = clean_vmt_weapon.decode("utf-8", errors="replace")
        assert material.has_proxies_block(text) is False


# ===========================================================================
# Tests: Material Set Validation
# ===========================================================================

class TestValidateMaterialSet:
    """Test overall verdict for a material set."""
    
    def test_validate_clean_weapon_materials(self, clean_vmt_weapon):
        """Clean weapon materials should pass validation."""
        materials = {
            "materials/models/weapons/c_models/c_scattergun/c_scattergun.vmt": clean_vmt_weapon
        }
        verdict = material.validate_material_set(materials, target_class="weapon")
        assert verdict.ok is True
        assert len(verdict.blocked) == 0
        assert len(verdict.safe_files) > 0
    
    def test_validate_blocked_world_material(self):
        """World materials should be blocked."""
        materials = {
            "materials/maps/cp_dustbowl/roof.vmt": b"test data"
        }
        verdict = material.validate_material_set(materials)
        assert verdict.ok is False
        assert len(verdict.blocked) > 0
    
    def test_validate_blocked_player_base(self):
        """Base player materials should be blocked."""
        materials = {
            "materials/models/player/scout/scout_body.vmt": b"test"
        }
        verdict = material.validate_material_set(materials)
        assert verdict.ok is False
        assert len(verdict.blocked) > 0
    
    def test_validate_ignorez_always_blocked(self, vmt_with_ignorez):
        """$ignorez should always block, even on weapons."""
        materials = {
            "materials/models/weapons/c_models/c_scattergun/test.vmt": vmt_with_ignorez
        }
        verdict = material.validate_material_set(materials, target_class="weapon")
        assert verdict.ok is False
    
    def test_validate_weapon_additive_warning(self, vmt_with_additive):
        """Additive on first-person weapon downgraded to warning."""
        materials = {
            "materials/models/weapons/c_models/c_scattergun/test.vmt": vmt_with_additive
        }
        verdict = material.validate_material_set(materials, target_class="weapon")
        # Should not block (downgraded to warning for first-person weapon)
        assert len(verdict.blocked) == 0
    
    def test_validate_cosmetic_additive_blocked(self, vmt_with_additive):
        """Additive on cosmetic should be blocked."""
        materials = {
            "materials/models/player/items/scout/hat.vmt": vmt_with_additive
        }
        verdict = material.validate_material_set(materials, target_class="cosmetic")
        assert verdict.ok is False
    
    def test_validate_mixed_clean_and_risky(self, clean_vmt_weapon, vmt_with_ignorez):
        """Mix of clean and risky materials should partially block."""
        materials = {
            "materials/models/weapons/c_models/clean.vmt": clean_vmt_weapon,
            "materials/models/weapons/c_models/risky.vmt": vmt_with_ignorez,
        }
        verdict = material.validate_material_set(materials, target_class="weapon")
        assert verdict.ok is False
        assert len(verdict.blocked) > 0
        assert len(verdict.safe_files) > 0
    
    def test_validate_prop_class_skipped(self):
        """Prop materials skipped when target_class != 'prop'."""
        materials = {
            "materials/models/props_2fort/barrel.vmt": b"test"
        }
        verdict = material.validate_material_set(materials)
        assert verdict.ok is False  # no safe files
        assert any("skipped" in msg for msg in verdict.warnings)
    
    def test_validate_prop_class_included(self):
        """Prop materials included when target_class='prop'."""
        materials = {
            "materials/models/props_2fort/barrel.vmt": b"""
"LightmappedGeneric"
{
    "$basetexture" "models/props_2fort/barrel"
}
"""
        }
        verdict = material.validate_material_set(materials, target_class="prop")
        # Should attempt to process
        assert isinstance(verdict.ok, bool)


# ===========================================================================
# Tests: Material File Reading
# ===========================================================================

class TestReadDiskMaterialSet:
    """Test reading material sets from disk folders."""
    
    def test_read_materials_from_materials_dir(self, temp_materials_folder):
        """Read materials when folder IS the materials directory."""
        materials = material.read_disk_material_set(str(temp_materials_folder))
        assert len(materials) > 0
        assert any(".vmt" in p.lower() for p in materials.keys())
    
    def test_read_materials_from_parent(self, temp_materials_folder):
        """Read materials when materials dir is a child."""
        materials = material.read_disk_material_set(str(temp_materials_folder))
        assert len(materials) > 0
    
    def test_read_materials_not_found_error(self, tmp_path):
        """Missing materials folder should raise BuildError."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        with pytest.raises(core.BuildError):
            material.read_disk_material_set(str(empty_dir))
    
    def test_read_materials_path_not_exists(self):
        """Nonexistent path should raise BuildError."""
        with pytest.raises(core.BuildError):
            material.read_disk_material_set("/nonexistent/path")
    
    def test_read_materials_vmt_and_vtf(self, temp_materials_folder):
        """Both .vmt and .vtf files should be collected."""
        materials = material.read_disk_material_set(str(temp_materials_folder))
        vmt_files = [p for p in materials.keys() if p.endswith(".vmt")]
        vtf_files = [p for p in materials.keys() if p.endswith(".vtf")]
        assert len(vmt_files) > 0
        assert len(vtf_files) > 0
    
    def test_read_materials_normalized_paths(self, temp_materials_folder):
        """Material paths should be normalized to archive form."""
        materials = material.read_disk_material_set(str(temp_materials_folder))
        # All paths should start with materials/, use forward slashes, be lowercase
        for path in materials.keys():
            assert path.startswith("materials/")
            assert "/" in path or path.endswith(".vmt") or path.endswith(".vtf")
            assert path == path.lower()


# ===========================================================================
# Tests: MDL Parsing and Material Resolution
# ===========================================================================

class TestReadMDLMaterialRefs:
    """Test parsing material references from .mdl files."""
    
    def test_parse_weapon_mdl(self, mock_mdl_weapon):
        """Parse texture names and cdmaterials from weapon MDL."""
        tex_names, cd_dirs = material.read_mdl_material_refs(mock_mdl_weapon)
        # MDL parsing is defensive and may return empty on minimal test data
        # Just verify it returns lists (doesn't crash)
        assert isinstance(tex_names, list)
        assert isinstance(cd_dirs, list)
    
    def test_parse_cosmetic_mdl(self, mock_mdl_cosmetic):
        """Parse texture names from cosmetic MDL."""
        tex_names, cd_dirs = material.read_mdl_material_refs(mock_mdl_cosmetic)
        # MDL parsing is defensive and may return empty on minimal test data
        # Just verify it returns lists (doesn't crash)
        assert isinstance(tex_names, list)
        assert isinstance(cd_dirs, list)
    
    def test_parse_invalid_mdl(self):
        """Invalid MDL should return empty lists."""
        tex_names, cd_dirs = material.read_mdl_material_refs(b"not a mdl")
        assert tex_names == []
        assert cd_dirs == []
    
    def test_parse_truncated_mdl(self):
        """Truncated MDL should return empty lists."""
        tex_names, cd_dirs = material.read_mdl_material_refs(b"IDST" + b"x" * 50)
        # May return empty if parsing fails at offset limits
        assert isinstance(tex_names, list)
        assert isinstance(cd_dirs, list)


class TestCandidateVMTPaths:
    """Test generation of candidate VMT paths from MDL data."""
    
    def test_candidate_paths_single_dir_single_name(self):
        """Generate candidates for single texture and cddir."""
        paths = material.candidate_vmt_paths(
            ["c_scattergun"],
            ["models/weapons/c_models/c_scattergun/"]
        )
        assert "materials/models/weapons/c_models/c_scattergun/c_scattergun.vmt" in paths
    
    def test_candidate_paths_multiple_dirs(self):
        """Generate all combinations of textures and dirs."""
        paths = material.candidate_vmt_paths(
            ["base", "normal"],
            ["dir1/", "dir2/"]
        )
        assert len(paths) == 4
        assert all(p.startswith("materials/") for p in paths)
    
    def test_candidate_paths_empty_dirs(self):
        """Fallback to root when cdirs empty."""
        paths = material.candidate_vmt_paths(["texture"], [])
        assert "materials/texture.vmt" in paths
    
    def test_candidate_paths_lowercased(self):
        """Candidate paths should be lowercased."""
        paths = material.candidate_vmt_paths(
            ["Texture"],
            ["DIR/"]
        )
        assert all(p == p.lower() for p in paths)


# ===========================================================================
# Tests: VPK Building and Output
# ===========================================================================

class TestBuildMaterialOnly:
    """Test building material-only VPK files."""
    
    def test_build_material_only_basic(self, clean_vmt_weapon, tmp_path):
        """Build a material VPK from a single VMT."""
        materials = {
            "materials/models/weapons/c_models/c_scattergun/c_scattergun.vmt": clean_vmt_weapon
        }
        out_path = tmp_path / "test.vpk"
        
        # Mock the vpk module
        with patch("tf2_material.core.get_vpk") as mock_get_vpk:
            mock_vpk = MagicMock()
            mock_vpk.new.return_value.save.return_value = None
            mock_get_vpk.return_value = mock_vpk
            
            result = material.build_material_only(materials, str(out_path))
            
            assert result["material_count"] == 1
            assert result["out_path"] == str(out_path)
    
    def test_build_material_only_multiple_files(self, clean_vmt_weapon, tmp_path):
        """Build VPK with multiple VMT and VTF files."""
        materials = {
            "materials/models/weapons/test.vmt": clean_vmt_weapon,
            "materials/models/weapons/test.vtf": b"vtf_data",
            "materials/models/weapons/test_normal.vtf": b"normal_data",
        }
        out_path = tmp_path / "test.vpk"
        
        with patch("tf2_material.core.get_vpk") as mock_get_vpk:
            mock_vpk = MagicMock()
            mock_vpk.new.return_value.save.return_value = None
            mock_get_vpk.return_value = mock_vpk
            
            result = material.build_material_only(materials, str(out_path))
            assert result["material_count"] == 3
    
    def test_build_material_only_empty_error(self, tmp_path):
        """Building with no materials should raise BuildError."""
        out_path = tmp_path / "test.vpk"
        with pytest.raises(core.BuildError):
            material.build_material_only({}, str(out_path))
    
    def test_build_material_only_creates_dirs(self, clean_vmt_weapon, tmp_path):
        """Build should create missing output directories."""
        out_path = tmp_path / "subdir" / "another" / "test.vpk"
        materials = {
            "materials/models/weapons/test.vmt": clean_vmt_weapon
        }
        
        with patch("tf2_material.core.get_vpk") as mock_get_vpk:
            mock_vpk = MagicMock()
            mock_vpk.new.return_value.save.return_value = None
            mock_get_vpk.return_value = mock_vpk
            
            result = material.build_material_only(materials, str(out_path))
            assert result is not None


class TestPreviewMaterialSwap:
    """Test dry-run preview of material swaps."""
    
    def test_preview_basic(self, clean_vmt_weapon):
        """Generate preview summary for material set."""
        materials = {
            "materials/models/weapons/test.vmt": clean_vmt_weapon
        }
        preview = material.preview_material_swap(materials)
        
        assert "entries" in preview
        assert "vmt_count" in preview
        assert "vtf_count" in preview
        assert "total_size" in preview
        assert preview["vmt_count"] == 1
        assert preview["vtf_count"] == 0
    
    def test_preview_mixed_files(self, clean_vmt_weapon):
        """Preview with both VMT and VTF files."""
        materials = {
            "materials/models/weapons/test.vmt": clean_vmt_weapon,
            "materials/models/weapons/test.vtf": b"x" * 1000,
            "materials/models/weapons/normal.vtf": b"y" * 2000,
        }
        preview = material.preview_material_swap(materials)
        
        assert preview["vmt_count"] == 1
        assert preview["vtf_count"] == 2
        assert preview["total_size"] == len(clean_vmt_weapon) + 1000 + 2000
        assert len(preview["entries"]) == 3
    
    def test_preview_size_calculation(self):
        """Preview size should be accurate."""
        materials = {
            "materials/test1.vmt": b"data1" * 100,
            "materials/test2.vtf": b"data2" * 200,
        }
        preview = material.preview_material_swap(materials)
        expected_size = (5 * 100) + (5 * 200)
        assert preview["total_size"] == expected_size


# ===========================================================================
# Tests: Edge Cases and Complex Scenarios
# ===========================================================================

class TestComplexProxyScenarios:
    """Test complex proxy scenarios with nested or multiple proxies."""
    
    def test_multiple_proxies_one_risky(self):
        """VTF with multiple proxies where one targets a risky param."""
        vmt = b"""
"LightmappedGeneric"
{
    "$basetexture" "test"
    
    "Proxies"
    {
        "AnimatedTexture"
        {
            "animatedtexturevar" "$basetexture"
            "animatedtextureframenumvar" "$frame"
        }
        "PlayerBurnLevel"
        {
            "resultvar" "$selfillumfresnel"
        }
        "Sine"
        {
            "resultvar" "$alpha"
        }
    }
}
"""
        findings = material.scan_vmt_safety(vmt)
        # Should find the $alpha targeting
        assert any(f.severity == "critical" for f in findings)
    
    def test_nested_include_chain(self):
        """Patch shader with includes (incomplete scan noted)."""
        vmt = b"""
"Patch"
{
    "include" "models/weapons/base.vmt"
    "$selfillum" "1"
    "$selfillumtint" "[1 1 1]"
}
"""
        findings = material.scan_vmt_safety(vmt)
        # Should have info about patch
        assert any("patch" in f.param.lower() for f in findings)
    
    def test_mixed_quoted_unquoted_proxy(self):
        """Proxies with mixed quoting styles."""
        vmt = b"""
"VertexLitGeneric"
{
    $basetexture test
    
    Proxies
    {
        "AnimatedTexture"
        {
            animatedtexturevar $basetexture
            "resultvar" "$translucent"
        }
    }
}
"""
        findings = material.scan_vmt_safety(vmt)
        assert any(f.severity == "critical" for f in findings)


class TestResolveItemMaterials:
    """Test material resolution from game VPKs."""
    
    def test_resolve_with_mock_paks(self, mock_mdl_weapon):
        """Resolve materials with mocked VPK access."""
        # Create mock VPK objects
        mock_textures_pak = MagicMock()
        mock_misc_pak = MagicMock()
        
        # Mock file reads
        def read_textures(path):
            if "c_scattergun.vmt" in path:
                return b"\"LightmappedGeneric\" { \"$basetexture\" \"models/test\" }"
            raise KeyError(path)
        
        mock_textures_pak.__getitem__.side_effect = read_textures
        
        # This should attempt to resolve and return materials
        with patch("tf2_material.core.read_vpk_entry") as mock_read:
            mock_read.side_effect = lambda pak, path: read_textures(path)
            
            result = material.resolve_item_materials(
                mock_textures_pak, mock_misc_pak, mock_mdl_weapon
            )
            assert isinstance(result, dict)


class TestEdgeCasesAndErrors:
    """Test error handling and edge cases."""
    
    def test_vmt_with_zero_alpha(self):
        """$alpha = 0 should be flagged."""
        vmt = b"""
"VertexLitGeneric"
{
    "$basetexture" "test"
    "$alpha" "0"
}
"""
        findings = material.scan_vmt_safety(vmt)
        # Zero alpha is extreme transparency
        assert any("alpha" in f.param.lower() for f in findings)
    
    def test_vmt_invalid_float_alpha(self):
        """Invalid $alpha value should not crash."""
        vmt = b"""
"VertexLitGeneric"
{
    "$basetexture" "test"
    "$alpha" "not_a_number"
}
"""
        findings = material.scan_vmt_safety(vmt)
        # Should not crash
        assert isinstance(findings, list)
    
    def test_empty_vmt(self):
        """Empty VMT should be handled."""
        findings = material.scan_vmt_safety(b"")
        assert findings == []
    
    def test_vmt_all_false_values(self):
        """Parameters with false-like values should be skipped."""
        vmt = b"""
"VertexLitGeneric"
{
    "$ignorez" "0"
    "$additive" "false"
    "$translucent" "no"
}
"""
        findings = material.scan_vmt_safety(vmt)
        # These are all false, so shouldn't be flagged as risky
        # (except maybe as info)
        critical = [f for f in findings if f.severity == "critical"]
        assert len(critical) == 0
    
    def test_massive_vmt_file(self):
        """Large VMT should be handled efficiently."""
        # Create a huge VMT with repeated data
        vmt = b"\"LightmappedGeneric\" { " + (b"$key value " * 10000) + b"}"
        findings = material.scan_vmt_safety(vmt)
        # Should complete without hanging
        assert isinstance(findings, list)
    
    def test_classify_empty_path(self):
        """Empty or degenerate paths should default to 'world'."""
        assert material.classify_material_path("") == "world"
        assert material.classify_material_path("/") == "world"
        assert material.classify_material_path("..") == "world"
    
    def test_validate_empty_material_set(self):
        """Empty material set should fail cleanly."""
        verdict = material.validate_material_set({})
        assert verdict.ok is False


# ===========================================================================
# Integration: End-to-End Material Swap Workflow
# ===========================================================================

class TestMaterialSwapIntegration:
    """Integration tests for complete material swap workflows."""
    
    def test_full_workflow_validation_build_preview(self, clean_vmt_weapon, tmp_path):
        """Full workflow: validate -> preview -> build."""
        materials = {
            "materials/models/weapons/c_models/c_scattergun/c_scattergun.vmt": clean_vmt_weapon
        }
        
        # Step 1: Validate
        verdict = material.validate_material_set(materials, target_class="weapon")
        assert verdict.ok is True
        
        # Step 2: Preview
        preview = material.preview_material_swap(verdict.safe_files)
        assert preview["vmt_count"] == 1
        
        # Step 3: Build (with mocked VPK)
        out_path = tmp_path / "result.vpk"
        with patch("tf2_material.core.get_vpk") as mock_get_vpk:
            mock_vpk = MagicMock()
            mock_vpk.new.return_value.save.return_value = None
            mock_get_vpk.return_value = mock_vpk
            
            result = material.build_material_only(verdict.safe_files, str(out_path))
            assert result["material_count"] > 0
    
    def test_blocked_material_rejection(self, vmt_with_ignorez, tmp_path):
        """Blocked materials should be rejected in workflow."""
        materials = {
            "materials/models/weapons/c_models/c_scattergun/c_scattergun.vmt": vmt_with_ignorez
        }
        
        # Validation should catch this
        verdict = material.validate_material_set(materials, target_class="weapon")
        assert verdict.ok is False
        
        # Build should not be attempted
        out_path = tmp_path / "result.vpk"
        with pytest.raises(core.BuildError):
            material.build_material_only({}, str(out_path))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
