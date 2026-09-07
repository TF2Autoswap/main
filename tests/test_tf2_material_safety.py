#!/usr/bin/env python3
"""
test_tf2_material_safety.py - Pytest version of material safety tests.

Exercises the v4.8 safety layer and MDL parser with adversarial inputs.
Converted from assertion-style to pytest format for coverage measurement.

Author: Melancholy Sky
Co-author: AI assistance via OpenRouter
"""

import struct
import pytest
import tf2_material as m
import tf2_core as core


class TestPathClassification:
    """Test material path classification (security-critical)"""

    def test_weapon_viewmodel_classified_as_weapon(self):
        assert m.classify_material_path(
            "materials/models/weapons/c_models/c_scattergun/c_scattergun.vmt"
        ) == "weapon"


    def test_cosmetic_item_classified_as_cosmetic(self):
        assert m.classify_material_path(
            "materials/models/player/items/scout/hat.vmt"
        ) == "cosmetic"

    def test_base_player_body_blocked(self):
        assert m.classify_material_path(
            "materials/models/player/scout.vmt"
        ) == "player_base"

    def test_hwm_base_body_blocked(self):
        assert m.classify_material_path(
            "materials/models/player/hwm/scout.vmt"
        ) == "player_base"

    def test_map_material_classified_as_world(self):
        assert m.classify_material_path(
            "materials/maps/cp_dustbowl/something.vmt"
        ) == "world"

    def test_brush_texture_classified_as_world(self):
        assert m.classify_material_path(
            "materials/concrete/concretewall001.vmt"
        ) == "world"

    def test_workshop_cosmetic_classified_as_cosmetic(self):
        assert m.classify_material_path(
            "materials/models/workshop/player/items/pyro/x.vmt"
        ) == "cosmetic"

    def test_prop_material_classified_as_prop(self):
        assert m.classify_material_path(
            "materials/models/props_gameplay/x.vmt"
        ) == "prop"


class TestVMTSafetyScan:
    """Test VMT content scanning for wallhack/ESP flags"""

    def test_clean_weapon_vmt_no_findings(self):
        clean = b'"VertexLitGeneric"\n{\n  "$basetexture" "models/weapons/w_scattergun"\n  "$phong" "1"\n}\n'
        assert len(m.scan_vmt_safety(clean)) == 0

    def test_ignorez_flagged_as_critical(self):
        ignorez = b'"VertexLitGeneric"\n{\n  "$basetexture" "x"\n  "$ignorez" "1"\n}\n'
        findings = m.scan_vmt_safety(ignorez)
        assert any(x.param == "$ignorez" and x.severity == "critical" for x in findings)

    def test_unlit_shader_flagged_as_high(self):
        unlit = b'"UnlitGeneric"\n{\n  "$basetexture" "x"\n}\n'
        findings = m.scan_vmt_safety(unlit)
        assert any(x.severity == "high" for x in findings)

    def test_translucent_flagged_as_high(self):
        trans = b'"VertexLitGeneric"\n{\n  "$basetexture" "x"\n  "$translucent" "1"\n}\n'
        findings = m.scan_vmt_safety(trans)
        assert any(x.param == "$translucent" and x.severity == "high" for x in findings)

    def test_alpha_below_1_flagged_as_high(self):
        alpha = b'"VertexLitGeneric"{ "$basetexture" "x" "$alpha" "0.3" }'
        findings = m.scan_vmt_safety(alpha)
        assert any(x.param == "$alpha" and x.severity == "high" for x in findings)

    def test_selfillum_flagged(self):
        selfillum = b'"VertexLitGeneric"{ "$basetexture" "x" "$selfillum" "1" }'
        findings = m.scan_vmt_safety(selfillum)
        assert any(x.param == "$selfillum" for x in findings)

    def test_additive_flagged_as_high(self):
        additive = b'"VertexLitGeneric"{ "$basetexture" "x" "$additive" "1" }'
        findings = m.scan_vmt_safety(additive)
        assert any(x.param == "$additive" and x.severity == "high" for x in findings)


class TestMaterialSetValidation:
    """Test full material set validation (scope + content combined)"""

    def test_clean_cosmetic_set_allowed(self):
        clean = b'"VertexLitGeneric"\n{\n  "$basetexture" "models/weapons/w_scattergun"\n  "$phong" "1"\n}\n'
        ok_set = {
            "materials/models/player/items/scout/hat.vmt": clean,
            "materials/models/player/items/scout/hat.vtf": b"VTF\x00fakebytes",
        }
        verdict = m.validate_material_set(ok_set, target_class="cosmetic")
        assert verdict.ok and not verdict.blocked

    def test_ignorez_on_cosmetic_blocked(self):
        ignorez = b'"VertexLitGeneric"\n{\n  "$basetexture" "x"\n  "$ignorez" "1"\n}\n'
        bad_cos = {"materials/models/player/items/scout/hat.vmt": ignorez}
        verdict = m.validate_material_set(bad_cos, target_class="cosmetic")
        assert (not verdict.ok) and verdict.blocked

    def test_transparency_on_weapon_warned_not_blocked(self):
        trans = b'"VertexLitGeneric"\n{\n  "$basetexture" "x"\n  "$translucent" "1"\n}\n'
        warn_wep = {"materials/models/weapons/c_models/c_x/c_x.vmt": trans}
        verdict = m.validate_material_set(warn_wep, target_class="weapon")
        assert verdict.ok and not verdict.blocked and any("$translucent" in w for w in verdict.warnings)

    def test_ignorez_on_weapon_still_blocked(self):
        ignorez = b'"VertexLitGeneric"\n{\n  "$basetexture" "x"\n  "$ignorez" "1"\n}\n'
        crit_wep = {"materials/models/weapons/c_models/c_x/c_x.vmt": ignorez}
        verdict = m.validate_material_set(crit_wep, target_class="weapon")
        assert not verdict.ok

    def test_world_material_in_set_blocks_whole_set(self):
        clean = b'"VertexLitGeneric"\n{\n  "$basetexture" "models/weapons/w_scattergun"\n  "$phong" "1"\n}\n'
        world_set = {
            "materials/models/player/items/scout/hat.vmt": clean,
            "materials/maps/cp_x/wall.vmt": clean,
        }
        verdict = m.validate_material_set(world_set)
        assert (not verdict.ok) and any("world" in b for b in verdict.blocked)

    def test_base_player_body_material_blocked(self):
        clean = b'"VertexLitGeneric"\n{\n  "$basetexture" "models/weapons/w_scattergun"\n  "$phong" "1"\n}\n'
        pb_set = {"materials/models/player/scout.vmt": clean}
        verdict = m.validate_material_set(pb_set)
        assert (not verdict.ok) and any("ESP" in b or "player body" in b for b in verdict.blocked)


class TestMDLParser:
    """Test MDL material reference parser (synthetic headers)"""

    @staticmethod
    def build_synth_mdl(tex_names, cd_dirs):
        """Construct a minimal valid .mdl exercising the texture tables."""
        buf = bytearray(0x100)
        buf[0:4] = b"IDST"
        struct.pack_into("<i", buf, 0x04, 48)

        body = bytearray()
        base = 0x100

        cd_str_offsets = []
        for d in cd_dirs:
            cd_str_offsets.append(base + len(body))
            body += d.encode("ascii") + b"\x00"

        tex_str_offsets = []
        for n in tex_names:
            tex_str_offsets.append(base + len(body))
            body += n.encode("ascii") + b"\x00"

        cdtextureindex = base + len(body)
        for off in cd_str_offsets:
            body += struct.pack("<i", off)

        textureindex = base + len(body)
        tex_table = bytearray(64 * len(tex_names))
        for i, str_off in enumerate(tex_str_offsets):
            tex_off = textureindex + i * 64
            struct.pack_into("<i", tex_table, i * 64, str_off - tex_off)
        body += tex_table

        struct.pack_into("<i", buf, 0xCC, len(tex_names))
        struct.pack_into("<i", buf, 0xD0, textureindex)
        struct.pack_into("<i", buf, 0xD4, len(cd_dirs))
        struct.pack_into("<i", buf, 0xD8, cdtextureindex)

        return bytes(buf) + bytes(body)

    def test_parser_recovers_texture_names(self):
        names_in = ["c_scattergun", "c_scattergun_back"]
        dirs_in = ["models/weapons/c_models/c_scattergun/"]
        mdl = self.build_synth_mdl(names_in, dirs_in)
        got_names, got_dirs = m.read_mdl_material_refs(mdl)
        assert got_names == names_in

    def test_parser_recovers_cdmaterials_dirs(self):
        names_in = ["c_scattergun", "c_scattergun_back"]
        dirs_in = ["models/weapons/c_models/c_scattergun/"]
        mdl = self.build_synth_mdl(names_in, dirs_in)
        got_names, got_dirs = m.read_mdl_material_refs(mdl)
        assert got_dirs == dirs_in

    def test_candidate_path_built_correctly(self):
        names_in = ["c_scattergun", "c_scattergun_back"]
        dirs_in = ["models/weapons/c_models/c_scattergun/"]
        mdl = self.build_synth_mdl(names_in, dirs_in)
        got_names, got_dirs = m.read_mdl_material_refs(mdl)
        cands = m.candidate_vmt_paths(got_names, got_dirs)
        assert "materials/models/weapons/c_models/c_scattergun/c_scattergun.vmt" in cands

    def test_non_mdl_bytes_return_empty(self):
        assert m.read_mdl_material_refs(b"not a model") == ([], [])


class TestPathTraversal:
    """Test path traversal protection (security regression tests)"""

    def test_traversal_disguised_as_weapon_path_blocked(self):
        traversal_to_map = "materials/models/weapons/c_models/../../../maps/de_dust/wallmat.vmt"
        assert m.classify_material_path(traversal_to_map) == "world"

    def test_traversal_escaping_materials_root_blocked(self):
        traversal_escapes_root = "materials/models/weapons/../../../../../../../etc/passwd"
        assert m.classify_material_path(traversal_escapes_root) == "world"

    def test_mixed_case_traversal_caught(self):
        mixed_case_traversal = "MATERIALS/MODELS/WEAPONS/c_models/../../../maps/x.vmt"
        assert m.classify_material_path(mixed_case_traversal) == "world"

    def test_legit_weapon_path_unaffected_by_traversal_fix(self):
        assert m.classify_material_path(
            "materials/models/weapons/c_models/c_scattergun/c_scattergun.vmt"
        ) == "weapon"

    def test_legit_cosmetic_path_unaffected_by_traversal_fix(self):
        assert m.classify_material_path(
            "materials/models/player/items/scout/hat.vmt"
        ) == "cosmetic"

    def test_safe_join_under_refuses_escaping_path(self):
        traversal_escapes_root = "materials/models/weapons/../../../../../../../etc/passwd"
        with pytest.raises(core.BuildError):
            core.safe_join_under("/tmp/fake_build_dir", traversal_escapes_root)

    def test_safe_join_under_accepts_legitimate_path(self):
        import os
        safe_path = core.safe_join_under(
            "/tmp/fake_build_dir",
            "materials/models/weapons/c_models/c_scattergun/c_scattergun.vmt"
        )
        assert safe_path.startswith(os.path.abspath("/tmp/fake_build_dir"))


class TestProxyDetection:
    """Test runtime proxy detection (animated transparency attacks)"""

    def test_proxy_animated_alpha_flagged_as_critical(self):
        proxy_vmt = (b'"VertexLitGeneric"{ "$basetexture" "x" "$alpha" "1" '
                     b'"Proxies" { "Sine" { "sineperiod" "1" "sinemin" "0" '
                     b'"sinemax" "0.3" "resultVar" "$alpha" } } }')
        findings = m.scan_vmt_safety(proxy_vmt)
        assert any(x.severity == "critical" and "roxies" in x.param.lower() for x in findings)

    def test_proxy_block_blocked_even_on_weapon(self):
        proxy_vmt = (b'"VertexLitGeneric"{ "$basetexture" "x" "$alpha" "1" '
                     b'"Proxies" { "Sine" { "sineperiod" "1" "sinemin" "0" '
                     b'"sinemax" "0.3" "resultVar" "$alpha" } } }')
        verdict = m.validate_material_set(
            {"materials/models/weapons/c_models/c_x/c_x.vmt": proxy_vmt},
            target_class="weapon"
        )
        assert not verdict.ok

    def test_ordinary_proxies_not_blocked(self):
        """Test that real-world ordinary proxies (cloak/detail/burn tint) are allowed"""
        ordinary_proxy_vmt = (
            b'"VertexlitGeneric"\n{\n'
            b'  "$basetexture" "x"\n'
            b'  "$cloakPassEnabled" "1"\n'
            b'  "Proxies"\n  {\n'
            b'    "weapon_invis" {}\n'
            b'    "AnimatedTexture" {\n'
            b'      "animatedtexturevar" "$detail"\n'
            b'      "animatedtextureframenumvar" "$detailframe"\n'
            b'      "animatedtextureframerate" 30\n'
            b'    }\n'
            b'    "BurnLevel" { "resultVar" "$detailblendfactor" }\n'
            b'    "YellowLevel" { "resultVar" "$yellow" }\n'
            b'    "Equals" { "srcVar1" "$yellow" "resultVar" "$color2" }\n'
            b'  }\n}\n'
        )
        findings = m.scan_vmt_safety(ordinary_proxy_vmt)
        assert not any(x.severity == "critical" for x in findings)

    def test_ordinary_proxies_get_info_note(self):
        """Ordinary proxies should get an informational note, not silence"""
        ordinary_proxy_vmt = (
            b'"VertexlitGeneric"\n{\n'
            b'  "$basetexture" "x"\n'
            b'  "Proxies"\n  {\n'
            b'    "weapon_invis" {}\n'
            b'  }\n}\n'
        )
        findings = m.scan_vmt_safety(ordinary_proxy_vmt)
        assert any(x.param == "Proxies" and x.severity == "info" for x in findings)

    def test_real_world_shaped_reskin_passes_validation(self):
        ordinary_proxy_vmt = (
            b'"VertexlitGeneric"\n{\n'
            b'  "$basetexture" "x"\n'
            b'  "Proxies"\n  {\n'
            b'    "weapon_invis" {}\n'
            b'  }\n}\n'
        )
        verdict = m.validate_material_set(
            {"materials/models/player/items/heavy/dreamy_heavy.vmt": ordinary_proxy_vmt},
            target_class="cosmetic"
        )
        assert verdict.ok


class TestPropTargetClass:
    """Test prop target_class behavior (disk-import support)"""

    def test_prop_path_without_target_class_skipped(self):
        clean = b'"VertexLitGeneric"\n{\n  "$basetexture" "models/weapons/w_scattergun"\n  "$phong" "1"\n}\n'
        prop_clean_set = {"materials/models/props_gameplay/crate01.vmt": clean}
        verdict = m.validate_material_set(prop_clean_set)
        assert verdict.safe_files == {} and not verdict.ok

    def test_prop_path_with_target_class_allowed(self):
        clean = b'"VertexLitGeneric"\n{\n  "$basetexture" "models/weapons/w_scattergun"\n  "$phong" "1"\n}\n'
        prop_clean_set = {"materials/models/props_gameplay/crate01.vmt": clean}
        verdict = m.validate_material_set(prop_clean_set, target_class="prop")
        assert verdict.ok and "materials/models/props_gameplay/crate01.vmt" in verdict.safe_files

    def test_malicious_prop_material_still_blocked(self):
        ignorez = b'"VertexLitGeneric"\n{\n  "$basetexture" "x"\n  "$ignorez" "1"\n}\n'
        prop_evil_set = {"materials/models/props_gameplay/crate01.vmt": ignorez}
        verdict = m.validate_material_set(prop_evil_set, target_class="prop")
        assert not verdict.ok and verdict.safe_files == {}

    def test_creator_named_folder_without_target_class_skipped(self):
        clean = b'"VertexLitGeneric"\n{\n  "$basetexture" "models/weapons/w_scattergun"\n  "$phong" "1"\n}\n'
        custom_named_prop_set = {
            "materials/models/dabmasterars/rack.vmt": clean,
            "materials/models/dabmasterars/tools/toolsblack.vmt": clean,
        }
        verdict = m.validate_material_set(custom_named_prop_set)
        assert verdict.safe_files == {}

    def test_creator_named_folder_with_target_class_allowed(self):
        clean = b'"VertexLitGeneric"\n{\n  "$basetexture" "models/weapons/w_scattergun"\n  "$phong" "1"\n}\n'
        custom_named_prop_set = {
            "materials/models/dabmasterars/rack.vmt": clean,
            "materials/models/dabmasterars/tools/toolsblack.vmt": clean,
        }
        verdict = m.validate_material_set(custom_named_prop_set, target_class="prop")
        assert verdict.ok and len(verdict.safe_files) == 2

    def test_world_path_stays_blocked_with_prop_target_class(self):
        clean = b'"VertexLitGeneric"\n{\n  "$basetexture" "models/weapons/w_scattergun"\n  "$phong" "1"\n}\n'
        mixed_set = {
            "materials/models/dabmasterars/rack.vmt": clean,
            "materials/overlays/locker.vmt": clean,
        }
        verdict = m.validate_material_set(mixed_set, target_class="prop")
        assert any("overlays/locker.vmt" in b for b in verdict.blocked) and \
               "materials/models/dabmasterars/rack.vmt" in verdict.safe_files


class TestPatchShader:
    """Test Patch shader (Include/Insert) - found in war-paint pattern content"""

    def test_nested_keys_inside_insert_extracted(self):
        patch_vmt = (b'"Patch"\n{\n  "Include" "materials/patterns/patch_opaque01.vmt"\n'
                     b'  "Insert"\n  {\n    "$basetexture" "patterns/mtp/pyr_offwhite"\n'
                     b'    "$surfaceprop" "metal"\n  }\n}\n')
        shader, kv = m.read_vmt_keyvalues(patch_vmt)
        assert kv.get("$basetexture") == "patterns/mtp/pyr_offwhite"

    def test_patch_shader_gets_info_note(self):
        patch_vmt = (b'"Patch"\n{\n  "Include" "materials/patterns/patch_opaque01.vmt"\n'
                     b'  "Insert"\n  {\n    "$basetexture" "patterns/mtp/pyr_offwhite"\n'
                     b'    "$surfaceprop" "metal"\n  }\n}\n')
        findings = m.scan_vmt_safety(patch_vmt)
        assert any(x.param == "shader:patch" and x.severity == "info" for x in findings)

    def test_clean_patch_vmt_not_blocked(self):
        patch_vmt = (b'"Patch"\n{\n  "Include" "materials/patterns/patch_opaque01.vmt"\n'
                     b'  "Insert"\n  {\n    "$basetexture" "patterns/mtp/pyr_offwhite"\n'
                     b'    "$surfaceprop" "metal"\n  }\n}\n')
        verdict = m.validate_material_set(
            {"materials/models/weapons/c_models/c_pistol/c_pistol.vmt": patch_vmt},
            target_class="weapon"
        )
        assert verdict.ok and "materials/models/weapons/c_models/c_pistol/c_pistol.vmt" in verdict.safe_files

    def test_malicious_base_file_with_patch_wrapper_caught(self):
        patch_vmt = (b'"Patch"\n{\n  "Include" "materials/patterns/patch_opaque01.vmt"\n'
                     b'  "Insert"\n  {\n    "$basetexture" "patterns/mtp/pyr_offwhite"\n  }\n}\n')
        evil_base_vmt = b'"VertexLitGeneric"\n{\n  "$basetexture" "x"\n  "$ignorez" "1"\n}\n'
        bundle = {
            "materials/models/weapons/c_models/c_pistol/c_pistol.vmt": patch_vmt,
            "materials/models/weapons/c_models/c_pistol/evil_base.vmt": evil_base_vmt,
        }
        verdict = m.validate_material_set(bundle, target_class="weapon")
        assert not verdict.ok and any("evil_base.vmt" in b for b in verdict.blocked)
