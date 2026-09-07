#!/usr/bin/env python3
"""
tf2_material.py - Material / skin swap engine and safety layer (v4.8).

Developed with: AI assistance via OpenRouter
Project : https://github.com/TF2Autoswap/autoswap
License : GPL v3 (see LICENSE / repository root)

------------------------------------------------------------------------------
WHAT THIS MODULE DOES
------------------------------------------------------------------------------
TF2autoswap already swaps *models* (the 3D shapes: .mdl / .vvd / .vtx). This
module adds the v4.8 base layer: swapping an item's *materials* — the look of a
surface rather than its shape.

A "material" in Source-engine terms is two file types working together:
    .vmt  (Valve Material Type)  - a small text file describing how a surface
                                   is drawn: which texture, how shiny, how lit.
    .vtf  (Valve Texture Format) - the actual image data the .vmt points at.

This is the groundwork the v4.75 war-paint work builds on, because war paints
are themselves a texture/material operation, just scoped to paintkit textures.

------------------------------------------------------------------------------
WHY THERE IS A SAFETY LAYER (read this before changing anything)
------------------------------------------------------------------------------
Material editing is the one place in this project where a careless feature could
produce a genuine cheat. The classic abuse is a "wallhack": editing a material
so a surface renders through walls or glows, letting a player see enemies they
should not. That abuse needs one of a small, well-known set of conditions:

    * Editing WORLD / MAP / BRUSH materials  (transparent or fullbright walls)
    * Editing the BASE PLAYER BODY material  (enemy "chams" / ESP)
    * Setting render flags that defeat depth testing or lighting, e.g.
        $ignorez 1        - draw through geometry (the core wallhack flag)
        $additive 1       - glow / see-through compositing
        $translucent / $alpha on a normally-opaque surface
        an Unlit / fullbright shader on a player-visible material

So this module is deliberately scoped:

    ALLOWED swap targets : weapon viewmodel materials, cosmetic item materials.
    BLOCKED swap targets : world / map / brush materials, base player body
                           materials. These are refused outright.
    BLOCKED VMT content  : the render-flag set above, refused (or, for a
                           first-person weapon where there is no ESP vector,
                           downgraded to a warning).

sv_pure (TF2's server-side file check) already rejects unauthorised materials in
real multiplayer. This layer is the belt to that braces: it refuses to *produce*
the exploit material in the first place, so the tool stays safe even on a
private sv_pure 0 server where sv_pure would not protect anyone.

None of this is user-configurable. There is no flag to turn it off.
"""

import os
import re
import struct
from dataclasses import dataclass, field

import tf2_core as core

# Size validation for material files
try:
    from tf2_size_limits import (
        MAX_TOTAL_MATERIAL_SIZE, validate_files_total_size
    )
except ImportError:
    MAX_TOTAL_MATERIAL_SIZE = 500 * 1024 * 1024
    def validate_files_total_size(file_dict, max_total, description="Files"):
        total = sum(len(data) if isinstance(data, bytes) else 0 for data in file_dict.values())
        if total > max_total:
            raise core.BuildError(f"{description} too large: {total/1024/1024:.1f}MB")
        return total


# ===========================================================================
# scope: which material paths this tool is allowed to touch
# ===========================================================================
#
# Paths are compared in archive form: forward slashes, lowercase, e.g.
#   materials/models/weapons/c_models/c_scattergun/c_scattergun.vmt
#
# Allowed roots are where weapon and cosmetic materials live. Blocked roots are
# the wallhack vectors. Anything not clearly allowed is treated as out of scope.

_ALLOWED_ROOTS = (
    "materials/models/weapons/",            # weapon viewmodels + worldmodels
    "materials/models/player/items/",       # cosmetics (hats, miscs)
    "materials/models/workshop/weapons/",   # workshop-imported weapons
    "materials/models/workshop/player/items/",  # workshop cosmetics
)

# Blocked roots: presence of any of these in a swap = refuse. Order matters only
# for the reason string; classification checks the most specific first.
_BLOCKED_ROOTS = (
    "materials/maps/",        # baked map lighting / cubemaps
    "materials/brick/",
    "materials/concrete/",
    "materials/metal/",
    "materials/nature/",
    "materials/wood/",
    "materials/tile/",
    "materials/plaster/",
    "materials/glass/",
    "materials/skybox/",
    "materials/effects/",     # tracers, sprites, overlays
    "materials/decals/",
    "materials/overlays/",
)


def classify_material_path(archive_path):
    """
    Bucket a material archive path so the validator knows whether it is in
    scope. Returns one of:
        "weapon"       - weapon viewmodel/worldmodel material   (allowed)
        "cosmetic"     - hat / misc material                    (allowed)
        "player_base"  - base player body material              (BLOCKED: ESP)
        "world"        - map / brush / effect material          (BLOCKED: wallhack)
        "prop"         - world prop material                    (out of scope here)
        "other"        - anything unrecognised                  (out of scope)

    SECURITY NOTE — path traversal: archive_path can originate from raw
    bytes parsed out of a third-party .mdl file (its cdmaterials directory
    string — see tf2_material.read_mdl_material_refs() and
    candidate_vmt_paths()), which makes it untrusted input, not just an
    internal label. A string like
        "materials/models/weapons/c_models/../../../maps/de_dust/wall.vmt"
    textually starts with the allowed weapon prefix, but actually resolves
    (once ".." is collapsed) to a blocked map material — exactly the
    wallhack vector this whole function exists to keep out. posixpath.
    normpath() below collapses ".." BEFORE any prefix check runs, so the
    classification is always based on where the path actually resolves to,
    not what it superficially starts with. Found and fixed during review;
    confirmed against a working proof-of-concept before this fix landed.
    """
    import posixpath
    p = archive_path.replace("\\", "/").lower().lstrip("/")
    if not p.startswith("materials/"):
        p = "materials/" + p
    p = posixpath.normpath(p)
    # normpath can strip a trailing slash or collapse to "." for degenerate
    # input — neither is a valid materials/ path, so route to the fail-safe
    # "world" bucket rather than letting an empty/odd string slip through
    # the allow-list checks below on a technicality.
    if not p.startswith("materials/"):
        return "world"

    # Base player body sits at materials/models/player/<class>/ (NOT /items/).
    # This is the chams/ESP vector, so it must be caught before the generic
    # "player" allow check.
    if p.startswith("materials/models/player/") and "/items/" not in p:
        return "player_base"

    for root in _ALLOWED_ROOTS:
        if p.startswith(root):
            # weapons/ are weapon materials
            return "weapon" if "weapons/" in root else "cosmetic"

    if p.startswith("materials/models/props_") or p.startswith("materials/props"):
        return "prop"

    for root in _BLOCKED_ROOTS:
        if p.startswith(root):
            return "world"

    # A bare materials/<word>/ path with no models/ segment is almost always a
    # world/brush texture set. Treat as world (blocked) to fail safe.
    rest = p[len("materials/"):]
    if rest and "/" in rest and not rest.startswith("models/"):
        return "world"

    return "other"


# ===========================================================================
# VMT safety scan: detect render flags that enable see-through / ESP
# ===========================================================================

# Risky parameters, with a severity and a plain-language reason. Severity:
#   "critical" - the defining wallhack flag; always blocks.
#   "high"     - strong ESP/see-through vector; blocks on world-visible targets,
#                downgraded to a warning only for first-person weapon viewmodels.
#   "info"     - worth surfacing but not itself an exploit.
_RISKY_PARAMS = {
    "$ignorez":        ("critical", "draws the surface through walls (the core wallhack flag)"),
    "$ignorez1":       ("critical", "draws the surface through walls"),
    "$additive":       ("high",     "additive blending makes the surface glow / see-through"),
    "$translucent":    ("high",     "forces transparency on the surface"),
    "$alphatest":      ("info",     "alpha cut-out; harmless on its own, noted for context"),
    "$nofog":          ("info",     "disables fog on the surface"),
    "$selfillumfresnel": ("high",   "fresnel self-illum can act as an outline/chams effect"),
}

# Shaders that remove normal lighting. On a player-visible material this makes
# the model fullbright (always clearly visible) which is a soft ESP.
_UNLIT_SHADERS = {"unlitgeneric", "unlittwotexture", "cable", "spritecard"}


@dataclass
class Finding:
    param: str
    severity: str      # "critical" | "high" | "info"
    reason: str


def read_vmt_keyvalues(vmt_bytes):
    """
    Parse a .vmt into (shader_name, {lowercase_key: value}).

    VMTs are VDF-style key/value text but are frequently hand-written and loosely
    formatted, so a tolerant line scan is used rather than a strict VDF parser
    (which tends to choke on real-world files). Block contents like "proxies"
    are flattened into the same dict; we only need to know which keys appear.
    """
    try:
        text = vmt_bytes.decode("utf-8", errors="replace")
    except Exception:
        return "", {}

    # Strip // line comments
    text = re.sub(r"//[^\n]*", "", text)

    shader = ""
    m = re.search(r'^\s*"?([A-Za-z_][\w]*)"?\s*\{', text, re.MULTILINE)
    if m:
        shader = m.group(1).lower()

    kv = {}
    # Match  "$key" "value"   or   $key value   (quotes optional on both sides)
    for key, val in re.findall(r'("?\$[\w]+"?)\s+("?[^"\n{}]*"?)', text):
        k = key.strip().strip('"').lower()
        v = val.strip().strip('"').strip().lower()
        kv[k] = v
    return shader, kv


def _truthy(v):
    return str(v).strip().strip('"') not in ("", "0", "0.0", "false", "no")


_RISKY_PROXY_TARGETS = {
    "$alpha", "$translucent", "$ignorez", "$additive",
    "$selfillum", "$selfillumfresnel",
}


def find_risky_proxy_targets(vmt_text):
    """
    Find any "resultVar" inside a Proxies block that targets a render
    parameter capable of affecting depth-testing, transparency, or
    visibility (see _RISKY_PROXY_TARGETS). Returns the set of matched
    parameter names — empty if the file has no Proxies block, or its
    proxies only target unrelated, purely cosmetic parameters.

    resultVar is the proxy keyword naming which parameter a proxy's
    computed/animated value gets written into, so scanning for it
    (without needing to parse exact block boundaries — a tolerant scan,
    consistent with read_vmt_keyvalues()'s approach elsewhere in this
    file) reliably finds what a proxy actually *affects*, which is the
    part that matters here. See has_proxies_block()'s docstring for why
    "does a Proxies block exist at all" turned out to be the wrong
    question to ask.
    """
    targets = set()
    for m in re.finditer(r'"?resultvar"?\s+"?(\$[\w]+)"?', vmt_text, re.IGNORECASE):
        param = m.group(1).lower()
        if param in _RISKY_PROXY_TARGETS:
            targets.add(param)
    return targets


def has_proxies_block(vmt_text):
    """
    Detect whether a .vmt contains a "Proxies" block at all. Informational
    only — does NOT by itself mean anything is wrong; see the history
    below and find_risky_proxy_targets() for the actual safety check.

    HISTORY: this function originally was the safety check itself — any
    Proxies block at all was treated as unverifiable and blocked outright,
    on the reasoning that a proxy can animate a parameter like $alpha at
    runtime while its static value reads as clean (confirmed with a
    working proof-of-concept before either version of this check existed).

    That blanket version turned out to be far too broad once tested
    against a real, ordinary TF2 cosmetic — a simple custom hat reskin
    using "weapon_invis" (Valve's own standard proxy for fading correctly
    during a Spy's cloak), "AnimatedTexture" (an animated detail pattern),
    and "BurnLevel" (a standard fire-status tint proxy). All three are
    completely ordinary and present on a huge fraction of real TF2
    content, including Valve's own official items — none of them within
    reach of a transparency or depth-test parameter. Blocking on Proxies-
    block-presence alone would have refused that file, and by extension
    an enormous amount of otherwise entirely normal community content,
    for no actual safety benefit.

    The real risk is specific to what a proxy *targets*, not whether
    proxies exist — see find_risky_proxy_targets(). This function is kept
    only to surface an informational note when proxies are present but
    target nothing risky, for transparency, not to block anything itself.
    """
    return bool(re.search(r'"?proxies"?\s*\{', vmt_text, re.IGNORECASE))


def scan_vmt_safety(vmt_bytes):
    """
    Inspect one .vmt and return a list of Finding objects for any render flags
    that could enable see-through or ESP behaviour. An empty list means clean.
    """
    text = vmt_bytes.decode("utf-8", errors="replace") if isinstance(vmt_bytes, bytes) else vmt_bytes
    shader, kv = read_vmt_keyvalues(vmt_bytes)
    findings = []

    risky_proxy_targets = find_risky_proxy_targets(text)
    if risky_proxy_targets:
        findings.append(Finding(
            "Proxies->" + ",".join(sorted(risky_proxy_targets)), "critical",
            f"a runtime Proxies block targets {', '.join(sorted(risky_proxy_targets))} via "
            "resultVar — this can animate that parameter at runtime in a way a static scan "
            "can't verify, even if its static declared value looks clean"
        ))
    elif has_proxies_block(text):
        findings.append(Finding(
            "Proxies", "info",
            "material uses a runtime Proxies block, but only for parameters unrelated to "
            "transparency/depth (e.g. animated detail textures, status tints) — noted for "
            "visibility, not blocking"
        ))

    for param, (sev, reason) in _RISKY_PARAMS.items():
        if param in kv and (_truthy(kv[param]) or sev == "info"):
            findings.append(Finding(param, sev, reason))

    # $alpha < 1 on an opaque surface = forced transparency.
    if "$alpha" in kv:
        try:
            if float(kv["$alpha"]) < 1.0:
                findings.append(Finding("$alpha", "high",
                                        "alpha below 1 forces partial transparency"))
        except ValueError:
            pass

    # Unlit / fullbright shader on a player-visible material.
    if shader in _UNLIT_SHADERS:
        findings.append(Finding(f"shader:{shader}", "high",
                                "unlit shader removes lighting (fullbright / always-visible)"))

    # Source's "Patch" shader inherits from another VMT via Include, then
    # overrides specific keys via Insert — found in real war-paint pattern
    # content during review. The actual rendering shader (and any params
    # not overridden here) live in that included file, which this scanner
    # never reads. This is NOT treated as risky by itself — any genuinely
    # dangerous keyvalue still has to exist as a real, static declaration
    # somewhere in the bundle to have any effect in-game, and every .vmt in
    # a bundle gets scanned independently regardless of Include
    # relationships, so a risky base file is still caught on its own merits
    # when the scan reaches it. This is purely an informational note for
    # human review, flagging that this particular file's own scan is
    # necessarily incomplete — it can't see what shader this ultimately
    # resolves to without also having and reading the included file.
    if shader == "patch":
        include_target = kv.get("include") or kv.get("$include") or "(unknown)"
        findings.append(Finding(
            "shader:patch", "info",
            f"Patch shader inherits from '{include_target}' — that file's own "
            "content determines the actual rendering shader and isn't read by "
            "this scan; ensure it's scanned too if it's part of the same bundle"
        ))

    # Strong self-illum (effectively fullbright).
    if "$selfillum" in kv and _truthy(kv["$selfillum"]):
        tint = kv.get("$selfillumtint", "")
        bright = tint.replace("[", "").replace("]", "").split()
        is_bright = False
        try:
            is_bright = all(float(x) >= 0.9 for x in bright) if bright else True
        except ValueError:
            is_bright = True
        findings.append(Finding("$selfillum", "high" if is_bright else "info",
                                "self-illumination can act as a fullbright / chams effect"))

    return findings


# ===========================================================================
# overall verdict for a whole material set
# ===========================================================================

@dataclass
class Verdict:
    ok: bool                          # safe to build as-is
    blocked: list = field(default_factory=list)   # hard reasons it was refused
    warnings: list = field(default_factory=list)  # softer notes for the user
    safe_files: dict = field(default_factory=dict)  # the subset that passed


def validate_material_set(material_files, target_class=None):
    """
    Run the full safety check on a set of {archive_path: bytes} material files.

    target_class tunes both scope and severity:
      - "weapon": a forced transparency or unlit shader on a first-person
        weapon viewmodel has no ESP vector (it's your own gun), so those
        are downgraded from blocking to a warning. $ignorez stays blocked
        regardless — it draws through geometry no matter what it's on.
      - "cosmetic": no downgrades — a cosmetic is visible on every player
        wearing it, including enemies.
      - "prop": treats prop-shaped material paths (models/props_*) as
        in-scope and runs the normal VMT content scan on them, the same
        as weapon/cosmetic — appropriate when importing a complete new
        prop model together with its own materials (bringing in a new
        asset), as opposed to retexturing a prop ALREADY placed in a map
        (the actual see-through-prop wallhack vector this module exists
        to keep out). Without target_class="prop", prop-shaped paths are
        skipped rather than packed, same as any unrecognised path.
      - None / anything else: prop-shaped paths are skipped, no severity
        downgrades apply.

    Returns a Verdict. ok=False means do not build; read .blocked for why.
    """
    verdict = Verdict(ok=True)

    for path, data in material_files.items():
        cls = classify_material_path(path)

        # 1) path scope. World and base-player materials are never allowed.
        if cls == "world":
            verdict.blocked.append(
                f"{path}: world / map / brush material (out of scope, wallhack vector)")
            continue
        if cls == "player_base":
            verdict.blocked.append(
                f"{path}: base player body material (out of scope, ESP/chams vector)")
            continue
        if cls == "prop" and target_class != "prop":
            # A prop-shaped material path showing up where target_class isn't
            # "prop" is out of scope — retexturing an EXISTING in-game prop
            # in place is the see-through-prop wallhack vector. But when
            # target_class IS "prop" (the prop disk-import feature), this
            # means the user is importing a whole NEW prop model together
            # with its own materials — the same risk category as a cosmetic
            # or weapon disk import (bringing in a new asset, not retexturing
            # one already placed in a map) — so it falls through to the
            # normal VMT content scan below instead of being skipped here.
            verdict.warnings.append(
                f"{path}: not a recognised weapon/cosmetic material path — skipped, not packed")
            continue
        if cls == "other":
            # Found during real-world testing: a path lands in "other" when
            # it's a materials/models/<something>/ path that doesn't match
            # any recognised prefix — including completely legitimate custom
            # prop content organized under a creator's own folder name rather
            # than the props_* convention classify_material_path() checks
            # for (e.g. materials/models/dabmasterars/rack.vmt). The world/
            # player_base checks above and the explicit _BLOCKED_ROOTS check
            # below already run before this point, so reaching "other" with
            # target_class="prop" set means: not blocked by name, not
            # matching a known prop prefix, but explicitly known from context
            # to be part of a prop being imported as a whole new asset — same
            # reasoning as the "prop" branch just above, just for a path the
            # classifier didn't have a name pattern for. Falls through to the
            # normal VMT scan rather than being silently skipped.
            if target_class == "prop":
                pass  # falls through to the VMT content scan below
            else:
                verdict.warnings.append(
                    f"{path}: not a recognised weapon/cosmetic material path — skipped, not packed")
                continue

        # 2) VMT content. Only .vmt files carry render flags.
        was_blocked = False
        if path.lower().endswith(".vmt"):
            findings = scan_vmt_safety(data)
            for f in findings:
                weapon_firstperson = (cls == "weapon")
                if f.severity == "critical":
                    verdict.blocked.append(f"{path}: {f.param} — {f.reason}")
                    was_blocked = True
                elif f.severity == "high":
                    if weapon_firstperson:
                        verdict.warnings.append(
                            f"{path}: {f.param} — {f.reason} (allowed: first-person weapon, no ESP vector)")
                    else:
                        verdict.blocked.append(f"{path}: {f.param} — {f.reason}")
                        was_blocked = True
                else:  # info
                    verdict.warnings.append(f"{path}: {f.param} — {f.reason}")

        # Use the explicit per-file flag set above rather than a substring search
        # through verdict.blocked — the latter is a correctness footgun in
        # security-relevant code, since one path could appear as a substring of
        # a different file's blocked-reason string and be incorrectly excluded.
        if not was_blocked:
            verdict.safe_files[path] = data

    verdict.ok = len(verdict.blocked) == 0 and len(verdict.safe_files) > 0
    
    # Validate total material set size to prevent disk exhaustion
    if verdict.ok and verdict.safe_files:
        validate_files_total_size(verdict.safe_files, MAX_TOTAL_MATERIAL_SIZE,
                                 "Material file set")
    
    return verdict


# ===========================================================================
# reading materials: from disk (reskin folders) and from the game archive
# ===========================================================================

_MATERIAL_EXTS = (".vmt", ".vtf")


def read_disk_material_set(folder):
    """
    Walk a folder and collect every .vmt/.vtf file as {archive_path: bytes}.

    The folder is expected to contain (or sit beside) a 'materials' directory,
    exactly like a Gamebanana reskin download:
        reskin_root/
            materials/models/weapons/.../thing.vmt
            materials/models/weapons/.../thing.vtf

    Paths are normalised to archive form (forward slashes, rooted at 'materials').
    Raises core.BuildError if no materials are found.
    """
    folder = os.path.expanduser(folder)
    if not os.path.isdir(folder):
        raise core.BuildError(f"Not a folder: {folder}")

    # Find the 'materials' directory: either this folder is it, contains it,
    # or is inside it.
    mats = None
    base = folder
    if os.path.basename(os.path.normpath(folder)).lower() == "materials":
        mats = folder
        base = os.path.dirname(os.path.normpath(folder))
    elif os.path.isdir(os.path.join(folder, "materials")):
        mats = os.path.join(folder, "materials")
        base = folder
    else:
        # search downward for the first 'materials' dir
        for dp, dns, _ in os.walk(folder):
            if "materials" in [d.lower() for d in dns]:
                real = next(d for d in dns if d.lower() == "materials")
                mats = os.path.join(dp, real)
                base = dp
                break
    if not mats:
        raise core.BuildError("No 'materials' folder found in that location.")

    out = {}
    for dp, _, fns in os.walk(mats):
        for fn in fns:
            if fn.lower().endswith(_MATERIAL_EXTS):
                full = os.path.join(dp, fn)
                rel = os.path.relpath(full, base).replace(os.sep, "/").lower()
                out[rel] = open(full, "rb").read()
    if not out:
        raise core.BuildError("Found a materials folder but no .vmt/.vtf files in it.")
    return out


def open_textures_pak(tf2_path):
    """
    Open tf2_textures_dir.vpk and return a vpk handle, or None if it is not
    present. Materials and textures live here, separate from the models in
    tf2_misc_dir.vpk that core.open_pak() handles.
    """
    vpk = core.get_vpk()
    path = os.path.join(tf2_path, "tf2_textures_dir.vpk")
    if not os.path.isfile(path):
        return None
    try:
        return vpk.open(path)
    except Exception:
        return None


def read_mdl_material_refs(mdl_bytes):
    """
    Parse a compiled .mdl header to discover which materials it references.

    A .mdl stores two lists we need:
        * texture names      (e.g. "c_scattergun")
        * cdmaterials dirs   (search folders, e.g. "models/weapons/c_models/c_scattergun/")
    The engine looks for  materials/<cdmaterials_dir>/<texture_name>.vmt  for each
    combination. Returning both lists lets us reconstruct candidate VMT paths.

    Returns (texture_names, cdmaterials_dirs). Returns ([], []) on any anomaly,
    so callers can fall back to convention-based resolution rather than crash.

    NOTE: the studiohdr_t texture-table offsets below are stable across the MDL
    versions TF2 ships (v48/v49). This parser is defensive but should still be
    validated against real game files on first use — see the project notes.
    """
    if len(mdl_bytes) < 0x100 or mdl_bytes[:4] != b"IDST":
        return [], []

    def i32(off):
        return struct.unpack_from("<i", mdl_bytes, off)[0]

    def cstr(off):
        end = mdl_bytes.find(b"\x00", off)
        if end < 0:
            end = off
        return mdl_bytes[off:end].decode("ascii", errors="replace")

    try:
        numtextures   = i32(0xCC)
        textureindex  = i32(0xD0)
        numcdtextures = i32(0xD4)
        cdtextureindex = i32(0xD8)
    except struct.error:
        return [], []

    # Sanity bounds: reject absurd values (wrong offsets / corrupt file).
    if not (0 <= numtextures <= 4096 and 0 <= numcdtextures <= 256):
        return [], []
    if not (0 <= textureindex < len(mdl_bytes) and 0 <= cdtextureindex <= len(mdl_bytes)):
        return [], []

    tex_names = []
    for i in range(numtextures):
        tex_off = textureindex + i * 64        # sizeof(mstudiotexture_t) == 64
        if tex_off + 4 > len(mdl_bytes):
            break
        name_off = tex_off + i32(tex_off)      # sznameindex is relative to struct
        if 0 <= name_off < len(mdl_bytes):
            nm = cstr(name_off).strip().replace("\\", "/")
            if nm:
                tex_names.append(nm)

    cd_dirs = []
    for i in range(numcdtextures):
        ptr = cdtextureindex + i * 4
        if ptr + 4 > len(mdl_bytes):
            break
        str_off = i32(ptr)                     # absolute offset to the dir string
        if 0 <= str_off < len(mdl_bytes):
            d = cstr(str_off).strip().replace("\\", "/")
            if d and not d.endswith("/"):
                d += "/"
            if d:
                cd_dirs.append(d)

    return tex_names, cd_dirs


def candidate_vmt_paths(tex_names, cd_dirs):
    """
    Build the list of  materials/<cd_dir><tex_name>.vmt  archive paths the engine
    would look for, given a model's texture names and cdmaterials dirs.
    """
    out = []
    for d in (cd_dirs or [""]):
        for n in tex_names:
            p = f"materials/{d}{n}.vmt".replace("//", "/").lower()
            if p not in out:
                out.append(p)
    return out


def resolve_item_materials(textures_pak, misc_pak, mdl_bytes):
    """
    Given a model's bytes, resolve and read its material set (the .vmt files it
    references, plus the .vtf textures those VMTs point at) from the game's VPKs.

    Best-effort: looks in tf2_textures_dir.vpk first, then tf2_misc_dir.vpk.
    Returns {archive_path: bytes}. May be empty if the model uses an unusual
    layout — callers should treat empty as "could not resolve" rather than error.

    This is the read side that lets a swap copy one in-game item's look onto
    another. It needs real VPKs to exercise fully and should be validated on a
    live install.
    """
    tex_names, cd_dirs = read_mdl_material_refs(mdl_bytes)
    if not tex_names:
        return {}

    def read_any(path):
        for pak in (textures_pak, misc_pak):
            if pak is None:
                continue
            try:
                return core.read_vpk_entry(pak, path)
            except KeyError:
                continue
            except core.BuildError:
                # A chunk being missing from THIS archive doesn't mean the
                # other one can't still satisfy the lookup — keep trying.
                # If both fail, the caller already handles an empty result
                # as "couldn't resolve, suggest disk import instead" (see
                # this function's docstring) rather than needing a hard
                # exception here.
                continue
        return None

    out = {}
    for vmt_path in candidate_vmt_paths(tex_names, cd_dirs):
        data = read_any(vmt_path)
        if data is None:
            continue
        out[vmt_path] = data
        # pull the .vtf files this VMT references
        _, kv = read_vmt_keyvalues(data)
        for key in ("$basetexture", "$bumpmap", "$detail",
                    "$phongexponenttexture", "$selfillummask", "$blendmodulatetexture"):
            tex = kv.get(key, "").strip().strip('"')
            if not tex:
                continue
            vtf_path = f"materials/{tex}.vtf".replace("//", "/").lower()
            if vtf_path not in out:
                vdata = read_any(vtf_path)
                if vdata is not None:
                    out[vtf_path] = vdata
    return out


# ===========================================================================
# building a material-only swap VPK
# ===========================================================================

def build_material_only(material_files, out_path):
    """
    Pack a validated material set into a VPK with no model files (a pure
    retexture). Mirrors core.build()'s material-writing and VPK packing, but
    without the .mdl requirement, since a material swap changes look not shape.

    Always run validate_material_set() and pass only verdict.safe_files here.
    Returns {"material_count": n, "out_path": path}.
    """
    if not material_files:
        raise core.BuildError("No material files to pack.")

    import tempfile, shutil
    tmpdir = tempfile.mkdtemp()
    try:
        for vpk_path, data in material_files.items():
            out = os.path.join(tmpdir, *vpk_path.split("/"))
            os.makedirs(os.path.dirname(out), exist_ok=True)
            open(out, "wb").write(data)
        vpk = core.get_vpk()
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        vpk.new(tmpdir).save(out_path)
    except core.SwapError:
        raise
    except Exception as e:
        raise core.BuildError(f"Failed to build material VPK: {e}") from e
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    return {"material_count": len(material_files), "out_path": out_path}


def preview_material_swap(material_files):
    """Dry-run summary of a material set: file list and total size."""
    entries = [{"path": p, "size": len(d)} for p, d in material_files.items()]
    return {
        "entries": entries,
        "vmt_count": sum(1 for p in material_files if p.lower().endswith(".vmt")),
        "vtf_count": sum(1 for p in material_files if p.lower().endswith(".vtf")),
        "total_size": sum(e["size"] for e in entries),
    }
