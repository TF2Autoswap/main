#!/usr/bin/env python3
"""
test_material_safety.py - exercises the v4.8 safety layer and MDL parser.

The safety logic is deterministic and must be right, so it is unit tested here
with crafted inputs. The MDL parser is verified against a synthetic header built
to the documented studiohdr_t layout.

Run: python3 test_material_safety.py
"""

import struct
import sys
import tf2_material as m

PASS, FAIL = 0, 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}")


# ---------------------------------------------------------------------------
# 1. path classification
# ---------------------------------------------------------------------------
print("path classification")
check("weapon viewmodel -> weapon",
      m.classify_material_path("materials/models/weapons/c_models/c_scattergun/c_scattergun.vmt") == "weapon")
check("decorated weapon per-variant -> other (paintkits removed from allowed roots)",
      m.classify_material_path("materials/models/paintkits/powerhouse_minigun_brickhouse/c_minigun.vmt") == "other")
check("cosmetic item -> cosmetic",
      m.classify_material_path("materials/models/player/items/scout/hat.vmt") == "cosmetic")
check("base player body -> player_base (BLOCK)",
      m.classify_material_path("materials/models/player/scout.vmt") == "player_base")
check("hwm base body -> player_base (BLOCK)",
      m.classify_material_path("materials/models/player/hwm/scout.vmt") == "player_base")
check("map material -> world (BLOCK)",
      m.classify_material_path("materials/maps/cp_dustbowl/something.vmt") == "world")
check("brush texture -> world (BLOCK)",
      m.classify_material_path("materials/concrete/concretewall001.vmt") == "world")
check("workshop cosmetic -> cosmetic",
      m.classify_material_path("materials/models/workshop/player/items/pyro/x.vmt") == "cosmetic")
check("prop material -> prop",
      m.classify_material_path("materials/models/props_gameplay/x.vmt") == "prop")


# ---------------------------------------------------------------------------
# 2. VMT scan: clean materials pass, wallhack materials get flagged
# ---------------------------------------------------------------------------
print("\nVMT safety scan")

clean = b'"VertexLitGeneric"\n{\n  "$basetexture" "models/weapons/w_scattergun"\n  "$phong" "1"\n}\n'
check("clean weapon vmt -> no findings", len(m.scan_vmt_safety(clean)) == 0)

ignorez = b'"VertexLitGeneric"\n{\n  "$basetexture" "x"\n  "$ignorez" "1"\n}\n'
f = m.scan_vmt_safety(ignorez)
check("$ignorez -> critical", any(x.param == "$ignorez" and x.severity == "critical" for x in f))

unlit = b'"UnlitGeneric"\n{\n  "$basetexture" "x"\n}\n'
f = m.scan_vmt_safety(unlit)
check("unlit shader -> high", any(x.severity == "high" for x in f))

trans = b'"VertexLitGeneric"\n{\n  "$basetexture" "x"\n  "$translucent" "1"\n}\n'
check("$translucent -> high", any(x.param == "$translucent" and x.severity == "high"
                                  for x in m.scan_vmt_safety(trans)))

alpha = b'"VertexLitGeneric"{ "$basetexture" "x" "$alpha" "0.3" }'
check("$alpha < 1 -> high", any(x.param == "$alpha" and x.severity == "high"
                                for x in m.scan_vmt_safety(alpha)))

selfillum = b'"VertexLitGeneric"{ "$basetexture" "x" "$selfillum" "1" }'
check("$selfillum -> flagged", any(x.param == "$selfillum" for x in m.scan_vmt_safety(selfillum)))

additive = b'"VertexLitGeneric"{ "$basetexture" "x" "$additive" "1" }'
check("$additive -> high", any(x.param == "$additive" and x.severity == "high"
                               for x in m.scan_vmt_safety(additive)))


# ---------------------------------------------------------------------------
# 3. full-set validation: scope + content combined
# ---------------------------------------------------------------------------
print("\nmaterial-set validation")

# a clean cosmetic retexture should be allowed
ok_set = {
    "materials/models/player/items/scout/hat.vmt": clean,
    "materials/models/player/items/scout/hat.vtf": b"VTF\x00fakebytes",
}
v = m.validate_material_set(ok_set, target_class="cosmetic")
check("clean cosmetic set -> ok", v.ok and not v.blocked)

# a wallhack on a cosmetic must be blocked
bad_cos = {"materials/models/player/items/scout/hat.vmt": ignorez}
v = m.validate_material_set(bad_cos, target_class="cosmetic")
check("ignorez on cosmetic -> blocked", (not v.ok) and v.blocked)

# the SAME transparency flag on a first-person weapon is a warning, not a block
warn_wep = {"materials/models/weapons/c_models/c_x/c_x.vmt": trans}
v = m.validate_material_set(warn_wep, target_class="weapon")
check("transparency on weapon -> warned, not blocked",
      v.ok and not v.blocked and any("$translucent" in w for w in v.warnings))

# ...but $ignorez is critical and blocks even on a weapon
crit_wep = {"materials/models/weapons/c_models/c_x/c_x.vmt": ignorez}
v = m.validate_material_set(crit_wep, target_class="weapon")
check("ignorez on weapon -> still blocked", not v.ok)

# a world material anywhere in the set blocks the whole set
world_set = {
    "materials/models/player/items/scout/hat.vmt": clean,
    "materials/maps/cp_x/wall.vmt": clean,
}
v = m.validate_material_set(world_set)
check("world material in set -> blocked", (not v.ok) and any("world" in b for b in v.blocked))

# base player body material blocks
pb_set = {"materials/models/player/scout.vmt": clean}
v = m.validate_material_set(pb_set)
check("base player body -> blocked", (not v.ok) and any("ESP" in b or "player body" in b for b in v.blocked))


# ---------------------------------------------------------------------------
# 4. MDL parser against a synthetic header built to the studiohdr_t layout
# ---------------------------------------------------------------------------
print("\nMDL material-ref parser (synthetic)")

def build_synth_mdl(tex_names, cd_dirs):
    """Construct a minimal valid-enough .mdl exercising the texture tables."""
    buf = bytearray(0x100)            # header region, zero-filled
    buf[0:4] = b"IDST"
    struct.pack_into("<i", buf, 0x04, 48)   # version

    body = bytearray()
    base = 0x100                       # everything after the header

    # cdmaterials strings
    cd_str_offsets = []
    for d in cd_dirs:
        cd_str_offsets.append(base + len(body))
        body += d.encode("ascii") + b"\x00"

    # texture-name strings
    tex_str_offsets = []
    for n in tex_names:
        tex_str_offsets.append(base + len(body))
        body += n.encode("ascii") + b"\x00"

    # cdtextures int array (absolute offsets)
    cdtextureindex = base + len(body)
    for off in cd_str_offsets:
        body += struct.pack("<i", off)

    # texture table: numtextures * 64-byte mstudiotexture_t
    textureindex = base + len(body)
    tex_table = bytearray(64 * len(tex_names))
    for i, str_off in enumerate(tex_str_offsets):
        tex_off = textureindex + i * 64
        # sznameindex is RELATIVE to the start of this struct
        struct.pack_into("<i", tex_table, i * 64, str_off - tex_off)
    body += tex_table

    # fill header table pointers
    struct.pack_into("<i", buf, 0xCC, len(tex_names))      # numtextures
    struct.pack_into("<i", buf, 0xD0, textureindex)        # textureindex
    struct.pack_into("<i", buf, 0xD4, len(cd_dirs))        # numcdtextures
    struct.pack_into("<i", buf, 0xD8, cdtextureindex)      # cdtextureindex

    return bytes(buf) + bytes(body)

names_in = ["c_scattergun", "c_scattergun_back"]
dirs_in = ["models/weapons/c_models/c_scattergun/"]
mdl = build_synth_mdl(names_in, dirs_in)
got_names, got_dirs = m.read_mdl_material_refs(mdl)
check("parser recovers texture names", got_names == names_in)
check("parser recovers cdmaterials dirs", got_dirs == dirs_in)

cands = m.candidate_vmt_paths(got_names, got_dirs)
check("candidate path built correctly",
      "materials/models/weapons/c_models/c_scattergun/c_scattergun.vmt" in cands)

# garbage / non-MDL input must not crash and returns empties
check("non-mdl bytes -> empty", m.read_mdl_material_refs(b"not a model") == ([], []))


# ---------------------------------------------------------------------------
# 5. path traversal — found during review, must never silently regress
# ---------------------------------------------------------------------------
# archive_path strings here can originate from raw bytes parsed out of a
# third-party .mdl file (its cdmaterials directory string), making them
# untrusted input. A naive prefix check on the raw string is not enough:
# "materials/models/weapons/.../../../maps/x.vmt" textually starts with the
# allowed weapon prefix but actually resolves to a blocked map path once
# ".." is collapsed — exactly the wallhack vector this module exists to
# keep out. classify_material_path() must resolve the path BEFORE checking
# prefixes, and safe_join_under() (tf2_core.py) must independently refuse to
# write outside its intended base directory even if something got past
# classification — two separate barriers, neither relying on the other.
print("\npath traversal (security regression)")

traversal_to_map = "materials/models/weapons/c_models/../../../maps/de_dust/wallmat.vmt"
check("traversal disguised as weapon path -> world (BLOCK)",
      m.classify_material_path(traversal_to_map) == "world")

traversal_escapes_root = "materials/models/weapons/../../../../../../../etc/passwd"
check("traversal escaping materials/ entirely -> world (BLOCK)",
      m.classify_material_path(traversal_escapes_root) == "world")

mixed_case_traversal = "MATERIALS/MODELS/WEAPONS/c_models/../../../maps/x.vmt"
check("mixed-case traversal still caught -> world (BLOCK)",
      m.classify_material_path(mixed_case_traversal) == "world")

# legitimate paths must be completely unaffected by the traversal fix
check("legit weapon path unaffected by traversal fix",
      m.classify_material_path("materials/models/weapons/c_models/c_scattergun/c_scattergun.vmt") == "weapon")
check("legit cosmetic path unaffected by traversal fix",
      m.classify_material_path("materials/models/player/items/scout/hat.vmt") == "cosmetic")

# second, independent barrier: even a path that somehow got past
# classification must not be able to escape the build directory at write
# time. This exercises tf2_core.safe_join_under() directly (the function
# every build() variant routes through) rather than the full VPK build, so
# the test has no dependency on the optional 'vpk' package being installed.
#
# Note this uses traversal_escapes_root, not traversal_to_map — the two
# barriers check genuinely different things. traversal_to_map's "..." only
# walks back into a different subfolder of the SAME build directory (still
# classified "world" by barrier 1, for an unrelated reason: it semantically
# resolves to a map path), so barrier 2 has nothing to object to there on
# its own terms. traversal_escapes_root has enough ".." to leave the build
# directory entirely, which is what barrier 2 specifically exists to catch.
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import tf2_core as core

try:
    core.safe_join_under("/tmp/fake_build_dir", traversal_escapes_root)
    check("safe_join_under refuses an escaping path", False)
except core.BuildError:
    check("safe_join_under refuses an escaping path", True)

safe_path = core.safe_join_under("/tmp/fake_build_dir",
                                  "materials/models/weapons/c_models/c_scattergun/c_scattergun.vmt")
check("safe_join_under accepts a legitimate path",
      safe_path.startswith(_os.path.abspath("/tmp/fake_build_dir")))


# a VMT can declare $alpha 1 (clean) while a runtime Proxies block animates
# it toward transparency — a real technique for evading static analysis.
# Found during review; must never silently regress.
proxy_vmt = (b'"VertexLitGeneric"{ "$basetexture" "x" "$alpha" "1" '
             b'"Proxies" { "Sine" { "sineperiod" "1" "sinemin" "0" '
             b'"sinemax" "0.3" "resultVar" "$alpha" } } }')
f = m.scan_vmt_safety(proxy_vmt)
check("proxy-animated alpha -> critical (static value alone looked clean)",
      any(x.severity == "critical" and "roxies" in x.param for x in f))

v = m.validate_material_set({"materials/models/weapons/c_models/c_x/c_x.vmt": proxy_vmt},
                             target_class="weapon")
check("proxy block blocked even on a weapon (no severity downgrade)", not v.ok)

# Found during testing against a REAL downloaded TF2 hat reskin: ordinary,
# completely standard proxies (weapon_invis for Spy-cloak fading,
# AnimatedTexture for a detail pattern, BurnLevel for fire-status tint —
# all present on a huge fraction of real TF2 content, official Valve
# items included) must NOT be blocked just because a Proxies block exists.
# The original blanket "any Proxies block = blocked" version of this check
# would have wrongly refused this file; only a proxy whose resultVar
# targets an actually risky parameter should block.
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
f2 = m.scan_vmt_safety(ordinary_proxy_vmt)
check("ordinary real-world proxies (cloak/detail/burn tint) are NOT blocked",
      not any(x.severity == "critical" for x in f2))
check("ordinary proxies still get an informational note, not silence",
      any(x.param == "Proxies" and x.severity == "info" for x in f2))

v2 = m.validate_material_set(
    {"materials/models/player/items/heavy/dreamy_heavy.vmt": ordinary_proxy_vmt},
    target_class="cosmetic")
check("a real-world-shaped ordinary reskin passes validation cleanly", v2.ok)


print("\nprop target_class behaviour (added when prop disk-import support was built)")

prop_clean_set = {"materials/models/props_gameplay/crate01.vmt": clean}
v_noprop = m.validate_material_set(prop_clean_set)
check("prop path WITHOUT target_class='prop' -> skipped, not packed (existing behaviour preserved)",
      v_noprop.safe_files == {} and not v_noprop.ok)

v_prop = m.validate_material_set(prop_clean_set, target_class="prop")
check("prop path WITH target_class='prop' -> scanned and allowed (new disk-import feature)",
      v_prop.ok and "materials/models/props_gameplay/crate01.vmt" in v_prop.safe_files)

prop_evil_set = {"materials/models/props_gameplay/crate01.vmt": ignorez}
v_prop_evil = m.validate_material_set(prop_evil_set, target_class="prop")
check("malicious prop material still blocked even with target_class='prop'",
      not v_prop_evil.ok and v_prop_evil.safe_files == {})


print("\nprop 'other' classification fix (creator-named folders, not props_*)")

custom_named_prop_set = {
    "materials/models/dabmasterars/rack.vmt": clean,
    "materials/models/dabmasterars/tools/toolsblack.vmt": clean,
}
v_custom_noprop = m.validate_material_set(custom_named_prop_set)
check("creator-named folder WITHOUT target_class='prop' -> skipped (existing behaviour preserved)",
      v_custom_noprop.safe_files == {})

v_custom_prop = m.validate_material_set(custom_named_prop_set, target_class="prop")
check("creator-named folder WITH target_class='prop' -> scanned and allowed",
      v_custom_prop.ok and len(v_custom_prop.safe_files) == 2)

# A genuinely risky path must still be blocked even with target_class='prop' —
# confirms the fix didn't widen the net past what's actually safe to widen.
mixed_set = dict(custom_named_prop_set)
mixed_set["materials/overlays/locker.vmt"] = clean
v_mixed = m.validate_material_set(mixed_set, target_class="prop")
check("a world-classified path stays blocked even alongside an allowed creator-named prop path",
      any("overlays/locker.vmt" in b for b in v_mixed.blocked) and
      "materials/models/dabmasterars/rack.vmt" in v_mixed.safe_files)


print("\nPatch shader (Include/Insert) — found in real war-paint pattern content")

patch_vmt = (b'"Patch"\n{\n  "Include" "materials/patterns/patch_opaque01.vmt"\n'
             b'  "Insert"\n  {\n    "$basetexture" "patterns/mtp/pyr_offwhite"\n'
             b'    "$surfaceprop" "metal"\n  }\n}\n')

shader, kv = m.read_vmt_keyvalues(patch_vmt)
check("nested $-keys inside Insert{} are still correctly extracted",
      kv.get("$basetexture") == "patterns/mtp/pyr_offwhite")

f = m.scan_vmt_safety(patch_vmt)
check("Patch shader gets an info-level transparency note, not silence",
      any(x.param == "shader:patch" and x.severity == "info" for x in f))

v = m.validate_material_set(
    {"materials/models/weapons/c_models/c_pistol/c_pistol.vmt": patch_vmt}, target_class="weapon")
check("a clean Patch VMT on a properly-scoped path is NOT blocked (info only)",
      v.ok and "materials/models/weapons/c_models/c_pistol/c_pistol.vmt" in v.safe_files)

# The actual safety guarantee this relies on: a risky property still has to
# exist as a real static keyvalue somewhere in the bundle to have any
# in-game effect, and every .vmt gets scanned independently regardless of
# Include relationships — so a malicious "base" file is still caught on
# its own merits, wherever it sits in the same bundle.
evil_base_vmt = b'"VertexLitGeneric"\n{\n  "$basetexture" "x"\n  "$ignorez" "1"\n}\n'
bundle_with_patch_and_evil_base = {
    "materials/models/weapons/c_models/c_pistol/c_pistol.vmt": patch_vmt,
    "materials/models/weapons/c_models/c_pistol/evil_base.vmt": evil_base_vmt,
}
v2 = m.validate_material_set(bundle_with_patch_and_evil_base, target_class="weapon")
check("a malicious base file bundled alongside a clean Patch wrapper is still caught independently",
      not v2.ok and any("evil_base.vmt" in b for b in v2.blocked))


# ---------------------------------------------------------------------------
print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
