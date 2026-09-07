#!/usr/bin/env python3
"""
tf2_core.py - Core logic for the TF2 cosmetic and weapon swap tool.

Developed with: AI assistance via OpenRouter
Project : https://github.com/TF2Autoswap/autoswap
License : GPL v3 — see LICENSE for details

--- What this tool does (plain language) ---
Team Fortress 2 (TF2) is a multiplayer video game by Valve Software. Players
can equip cosmetic items (hats, clothing) and weapons, each represented by 3D
model files stored inside the game's data archives.

This tool swaps one item's model files for another's, client-side. "Client-side"
means the change is only visible on the local machine — other players in the game
see the original item. No game files are permanently modified.

The output is a file in Valve's VPK archive format, loaded by a third-party
mod manager called the Casual Preloader which handles injecting it into the game
at launch.

--- Architecture ---
This file (tf2_core.py) contains only pure logic: functions that take inputs,
do work, and return data. It has no print() or input() calls. Any user interface
(the current CLI, or a future GUI) sits on top of this file and handles all
user interaction separately. This separation makes the code easier to test,
maintain, and extend with new frontends.
"""

# Standard library only at the top level. The third-party 'vpk' library is
# imported lazily inside get_vpk() so it can be auto-installed on first run.
import os, tempfile, shutil, subprocess, sys, json, struct

# Size validation imports (will be completed after SwapError is defined below)
_size_limits_available = False


# ---------- exceptions ----------
# Custom exception types let calling code distinguish between different failure
# modes and show appropriate messages to the user — rather than exposing raw
# Python exceptions like FileNotFoundError or KeyError.

class SwapError(Exception):
    """Base class for all expected, user-facing errors in this tool."""

# Size validation setup (now that SwapError is defined)
try:
    from tf2_size_limits import (
        MAX_MODEL_FILE_SIZE, MAX_MATERIAL_FILE_SIZE, MAX_TEXTURE_FILE_SIZE,
        MAX_TOTAL_MATERIAL_SIZE, validate_file_size, validate_files_total_size,
        SizeValidationError
    )
    _size_limits_available = True
except ImportError:
    # Fallback if module not available
    MAX_MODEL_FILE_SIZE = 500 * 1024 * 1024
    MAX_MATERIAL_FILE_SIZE = 50 * 1024 * 1024
    MAX_TEXTURE_FILE_SIZE = 256 * 1024 * 1024
    MAX_TOTAL_MATERIAL_SIZE = 500 * 1024 * 1024
    _size_limits_available = False
    
    class SizeValidationError(SwapError):
        pass
    
    def validate_file_size(path, max_size, description="File"):
        size = os.path.getsize(path)
        if size > max_size:
            raise SizeValidationError(
                f"{description} too large: {size/1024/1024:.1f}MB "
                f"(limit: {max_size/1024/1024:.0f}MB)"
            )
        return size
    
    def validate_files_total_size(file_dict, max_total, description="Files"):
        total_size = sum(len(data) if isinstance(data, bytes) else 0 for data in file_dict.values())
        if total_size > max_total:
            raise SizeValidationError(
                f"{description} set too large: {total_size/1024/1024:.1f}MB "
                f"(limit: {max_total/1024/1024:.0f}MB)"
            )
        return total_size

class TF2NotFound(SwapError):
    """Raised when the game's installation directory cannot be located."""
    pass

class ModelNotFound(SwapError):
    """Raised when a search keyword returns no matching model files."""
    pass

class BuildError(SwapError):
    """Raised when something goes wrong while constructing the output archive."""
    pass

class InventoryError(SwapError):
    """
    Raised when a Steam inventory JSON file cannot be read or understood.

    Covers: missing or unreadable files, invalid JSON, and cases where the
    contents don't match either inventory JSON shape this tool knows how to
    read (see load_inventory_file() for why there are two).
    """
    pass


# ---------- constants ----------

# TF2 stores its game files inside a 'tf' subdirectory within the Steam
# installation. The exact path varies by operating system and Steam library
# location. These are the most common default locations across Linux, Windows,
# and macOS. The ~ character is a shorthand for the user's home directory.
TF2_PATHS = [
    "~/.steam/steam/steamapps/common/Team Fortress 2/tf",
    "~/.local/share/Steam/steamapps/common/Team Fortress 2/tf",
    "C:/Program Files (x86)/Steam/steamapps/common/Team Fortress 2/tf",
    "C:/Program Files/Steam/steamapps/common/Team Fortress 2/tf",
    "~/Library/Application Support/Steam/steamapps/common/Team Fortress 2/tf",
]

# The nine playable character classes in TF2. Used to build class filter menus
# in the interface, and to understand per-class model path naming conventions.
CLASSES = ["scout", "soldier", "pyro", "demoman", "heavy",
           "engineer", "medic", "sniper", "spy"]

# TF2 model files sometimes use shortened class names in their folder paths
# rather than the full class name. For example, the Engineer's items use 'engi'
# and the Demoman's use 'demo'. This mapping lets the class filter work
# correctly when paths use these shortened forms.
_CLASS_PATH_TERMS = {
    "scout":    ["scout"],
    "soldier":  ["soldier", "solly"],
    "pyro":     ["pyro"],
    "demoman":  ["demoman", "demo"],
    "heavy":    ["heavy"],
    "engineer": ["engineer", "engi"],
    "medic":    ["medic"],
    "sniper":   ["sniper"],
    "spy":      ["spy"],
}

# A flat sorted list of every class term across all classes.
# Used in find_models() to detect whether an all-class item has per-class
# variants that should be excluded from searches for other classes.
_ALL_CLASS_PATH_TERMS = sorted(set(
    term for terms in _CLASS_PATH_TERMS.values() for term in terms
))

# Weapon model files sometimes have extra variants stored alongside the base
# weapon model: festive versions (with decorations), seasonal holiday reskins,
# animation-only rigs, arm models, and other non-standard files. These suffixes
# identify those variants. They are filtered from normal weapon searches so
# results only show the base weapon models, not every variant of every weapon.
# If a user explicitly searches for one of these terms, the filter is skipped.
_WEAPON_VARIANT_SUFFIXES = (
    "_festivizer", "_xmas", "_helloween",
    "_animations", "_arms", "_screen", "_bonemerge",
)

# Own-inventory mode lists everything the player owns at once (see
# match_owned_items()), which surfaces items that technically have a real
# loadout slot but aren't what a player means by "cosmetic" — event passes
# being the main case (Activated Campaign Pass, Operation Pass, etc., all
# sit in the 'action' slot same as legitimate wearables). Badges and medals
# are deliberately NOT excluded here — those are kept, since they're closer
# to genuine collectibles a player might reasonably want to swap.
# Matched as a whole word (not substring) to avoid excluding something like
# a hypothetical "Compass"-named item by accident.
_OWNED_ITEM_NAME_EXCLUDE_WORDS = {"pass"}

# TF2 3D models are split across multiple files, each serving a different purpose:
#   .mdl      — the main model descriptor: references geometry, defines animations,
#               stores the internal model name that TF2 uses to identify it
#   .vvd      — vertex data: the actual 3D point positions, surface normals, and
#               UV coordinates (texture mapping coordinates)
#   .dx80.vtx — triangle strip data for DirectX 8 (legacy hardware fallback)
#   .dx90.vtx — triangle strip data for DirectX 9 (the standard renderer)
#   .sw.vtx   — triangle strip data for the software renderer
#   .phy      — collision/physics geometry. Not every model has one (most
#               cosmetics/weapons don't need separate collision from the
#               player model they attach to), but for props it's often the
#               difference between "collidable" and "walk-through", and for
#               breakable props (found via real-world reference content —
#               e.g. a custom MVM mission's breakable tank pieces) it's what
#               actually defines how the prop shatters. Previously missing
#               from this list entirely, silently dropped on every swap.
# All files must be present for TF2 to load the model fully and correctly. Not
# all models have all six — missing files are silently skipped during reading.
EXTS = [".mdl", ".vvd", ".dx80.vtx", ".dx90.vtx", ".sw.vtx", ".phy"]


# ---------- setup ----------

def get_vpk():
    """
    Return the 'vpk' Python library, installing it automatically if needed.

    VPK (Valve Package) is the archive format Valve uses to store game assets.
    A VPK file works like a ZIP file — it contains many files packed together
    for efficient distribution and loading. TF2's model files, textures, and
    configuration data all live inside VPK archives.

    The 'vpk' library (by ValvePython) provides Python-level read/write access
    to these archives. We import it lazily here (not at the top of the file)
    so the tool can automatically install it via pip on first run, without
    requiring the user to set anything up manually.

    The --no-warn-script-location flag suppresses a harmless but alarming
    Windows message about pip-installed scripts not being on the system PATH.
    """
    try:
        import vpk
        return vpk
    except ImportError:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "vpk", "--no-warn-script-location"],
            check=True
        )
        import vpk
        return vpk


def read_vpk_entry(pak, path):
    """
    Read one file's bytes from an open VPK, distinguishing two genuinely
    different failure modes that look similar but mean very different
    things:

    - KeyError: the path simply isn't in the archive's directory index.
      Normal and expected — not every model has every extension, not
      every keyword matches something real. Re-raised unchanged so
      callers can keep treating it as "this one doesn't exist, move on".

    - FileNotFoundError / OSError: the path IS in the directory index,
      but the actual numbered chunk file it points into (e.g.
      tf2_textures_072.vpk) isn't present on disk. This means the
      index is telling the truth about what *should* be there while the
      install itself is missing data — most likely an incomplete or
      partially verified Steam download, or files moved/deleted after
      install. Confirmed as a real, reachable failure mode by testing
      against actual game VPKs with only some numbered chunks present.

    Without this distinction, a missing chunk falls through every
    existing "except KeyError: skip it" handler uncaught, propagates as
    a raw OS-level exception, and surfaces to the user as a generic
    "Unexpected error" with no indication of what actually went wrong or
    how to fix it. This raises a clear BuildError instead.
    """
    try:
        return pak[path].read()
    except KeyError:
        raise
    except (FileNotFoundError, OSError) as e:
        raise BuildError(
            f"Couldn't read '{path}' from the game archive — a required VPK "
            f"chunk file appears to be missing ({e}). This usually means an "
            f"incomplete or corrupted TF2 install. Try 'Verify integrity of "
            f"game files' in Steam (right-click Team Fortress 2 -> Properties "
            f"-> Installed Files), then try again."
        ) from e


def resolve_tf2(override=None):
    """
    Locate TF2's 'tf' directory and return its path, or raise TF2NotFound.

    If override is provided (from the --tf2 command-line flag), only that
    path is checked. Otherwise, all common default installation paths are tried.

    We verify the path by checking for 'tf2_misc_dir.vpk' — this is the main
    game asset archive that contains the model files we need. Its presence
    confirms we have found the correct TF2 directory rather than some other
    folder that happens to be at a similar path.
    """
    paths = [override] if override else [os.path.expanduser(p) for p in TF2_PATHS]
    for path in paths:
        if path and os.path.isfile(os.path.join(path, "tf2_misc_dir.vpk")):
            return path
    raise TF2NotFound("TF2 not found. Set the path manually with the tf/ directory.")


def open_pak(tf2_path):
    """
    Open tf2_misc_dir.vpk and return an object for reading its contents.

    tf2_misc_dir.vpk is TF2's primary game asset archive. It contains:
    - All cosmetic item model files (hats, clothing, misc items)
    - All weapon model files
    - Material definition files (.vmt) and some texture files (.vtf)
    - The item schema (items_game.txt) used for friendly names

    The returned object supports dictionary-style access: pak["path/to/file"]
    returns a file-like object whose .read() method yields the raw bytes.
    """
    vpk = get_vpk()
    return vpk.open(os.path.join(tf2_path, "tf2_misc_dir.vpk"))


# ---------- own inventory (own-items mode) ----------
# Lets the user search items they actually own on Steam, instead of every
# item that exists in the game's archive. This is JSON-file-only by design:
# the user exports their own inventory data from Steam manually and points
# the tool at the file. There is no live network fetch and no Steam cookie
# / session handling anywhere in this tool. That's a deliberate scope cut,
# not a missing feature — a tool that asks for or stores a Steam session
# cookie looks identical, from the outside, to the credential-stealing
# "trading tools" that drain backpacks in this community, regardless of how
# trustworthy the actual code behind it is. The file-only path sidesteps
# that risk entirely: nothing is ever sent to or received from Steam by
# this tool directly, and the tool never fetches-then-caches inventory data
# on its own initiative. (The imports/inventory/ drop folder and the
# --debug-inventory report file do write to disk — but only the user's own
# file they placed there themselves, or a report they explicitly asked for;
# neither is the tool quietly persisting something it fetched on its own.)
#
# To get the file: while logged into Steam in a browser, visit
#   https://steamcommunity.com/inventory/<steamid64>/440/2?l=english&count=5000
# and save the page as a .json file. See load_inventory_file() below.

def _normalise_legacy_inventory(data):
    """
    Parse the older TF2-specific inventory JSON shape:
        { "rgInventory": {assetid: {classid, instanceid, ...}},
          "rgDescriptions": {"<classid>_<instanceid>": {app_data: {def_index, quality}, ...}} }
    This shape is the easiest to read — defindex and quality are already
    plain integers in app_data, no further decoding needed.
    Returns a list of owned items, or None if the shape doesn't match
    (so the caller knows to try the other endpoint instead).
    """
    if not isinstance(data, dict):
        # Steam (or a browser save gone wrong) can hand back null, an empty
        # body, or HTML-that-happened-to-parse-as-something-odd instead of
        # the expected JSON object. Treat anything that isn't a dict as
        # "not this shape" rather than crashing.
        return None

    inventory = data.get("rgInventory")
    descriptions = data.get("rgDescriptions")
    if not inventory or not descriptions:
        return None

    items = []
    for asset_id, asset in inventory.items():
        key = f"{asset.get('classid')}_{asset.get('instanceid', '0')}"
        desc = descriptions.get(key)
        if not desc:
            continue
        app_data = desc.get("app_data") or {}
        defindex = app_data.get("def_index")
        if defindex is None:
            continue
        quality = app_data.get("quality")
        items.append({
            "id": asset_id,
            "defindex": int(defindex),
            "quality": int(quality) if quality is not None else None,
            "name_hint": desc.get("name") or desc.get("market_hash_name"),
        })
    return items


def _normalise_modern_inventory(data):
    """
    Parse the modern generic inventory JSON shape:
        { "assets": [{classid, instanceid, assetid, ...}],
          "descriptions": [{classid, instanceid, app_data: {def_index, quality}, ...}] }
    TF2 still attaches the same app_data block in this shape as the legacy
    one — the difference is descriptions is a list here, not a dict, so it
    needs to be indexed by classid+instanceid first.
    Returns a list of owned items, or None if the shape doesn't match.
    """
    if not isinstance(data, dict):
        return None

    assets = data.get("assets")
    descriptions = data.get("descriptions")
    if not assets or not descriptions:
        return None

    desc_lookup = {
        f"{d.get('classid')}_{d.get('instanceid', '0')}": d for d in descriptions
    }

    items = []
    for asset in assets:
        key = f"{asset.get('classid')}_{asset.get('instanceid', '0')}"
        desc = desc_lookup.get(key)
        if not desc:
            continue
        app_data = desc.get("app_data") or {}
        defindex = app_data.get("def_index")
        if defindex is None:
            continue
        quality = app_data.get("quality")
        items.append({
            "id": asset.get("assetid"),
            "defindex": int(defindex),
            "quality": int(quality) if quality is not None else None,
            "name_hint": desc.get("name") or desc.get("market_hash_name"),
        })
    return items


def _parse_inventory_payload(data):
    """Try both known inventory JSON shapes against already-loaded data.
    Used by load_inventory_file() — kept as its own function in case a
    second source of inventory data is ever added later."""
    items = _normalise_legacy_inventory(data)
    if items:
        return items
    items = _normalise_modern_inventory(data)
    if items:
        return items
    return []


def load_inventory_file(path):
    """
    Load TF2 inventory data from a JSON file saved manually by the user.

    This is the only way own-inventory mode gets data — there is no live
    network fetch anywhere in this tool (see the own-inventory section
    header above for why that's a deliberate choice, not a missing one).

    1. While logged into Steam, visit:
       https://steamcommunity.com/inventory/<steamid64>/440/2?l=english&count=5000
    2. Save the resulting page as a .json file (Ctrl+S in most browsers,
       or copy the raw text into a text editor and save it).
    3. Pass that file's path here (or via --inventory-file on the command line).

    Accepts either of the two JSON shapes Steam may return — see
    _parse_inventory_payload() for the shared parsing logic.

    Raises InventoryError if the file can't be read, isn't valid JSON, or
    doesn't match either known shape.
    """
    if not os.path.isfile(path):
        raise InventoryError(f"Inventory file not found: {path}")
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise InventoryError(f"File is not valid JSON: {e}") from e

    if data is None or not isinstance(data, dict):
        # The file parsed as valid JSON but came out empty/null rather than
        # an actual inventory object. This usually means Steam served an
        # empty or "null" response when the page was saved — most commonly
        # because the browser wasn't actually logged in for that request,
        # or the inventory privacy setting hadn't taken effect yet. It is
        # NOT the same as "wrong shape" (handled below), so it gets its own
        # clearer message.
        raise InventoryError(
            "The file parsed as JSON but contained no inventory data "
            f"(got {data!r}). This usually means the page wasn't actually "
            "logged in when it was saved, or Steam returned an empty "
            "response. Make sure you're logged into Steam in the browser "
            "tab before saving the page, then try again."
        )

    items = _parse_inventory_payload(data)
    if not items:
        raise InventoryError(
            "File was read but didn't match a known inventory format. "
            "Make sure it's a direct save of the Steam inventory JSON page, "
            "not the regular HTML inventory page."
        )
    return items


def _is_custom_name_tag(name_hint):
    """
    Detect whether name_hint represents a player-applied custom Name Tag,
    rather than the item's normal display name (which can itself be a
    Strange/Unusual variant name that legitimately differs from the
    schema's generic base name without being a custom tag at all).

    Steam/TF2 wraps a custom-named item's display name in a pair of single
    quotes (e.g. "''Mr. Fahrenheit''") — this is specific to Name Tags.
    Valve's own item names, including every non-tag weapon variant, are
    never wrapped this way. That makes the quote wrapper a reliable
    signal here; comparing name_hint against the schema name is NOT —
    a variant name legitimately differs from the schema's base name
    without being a tag, and would be a false positive under that approach.
    """
    if not name_hint:
        return False
    s = name_hint.strip()
    return len(s) >= 4 and s.startswith("''") and s.endswith("''")


def display_name_with_actual(name_hint, schema_name):
    """
    Build the display label for an owned item, showing the schema's actual
    base item name alongside a custom Name Tag when one is applied.

    Steam shows a custom-named item using only the player-chosen name (e.g.
    "''Mr. Fahrenheit''" for what's actually a Degreaser) — fine for a
    single item, but genuinely ambiguous in a list where several owned
    items might have custom names. Appending the real item name resolves
    that without losing the custom name itself.

    Non-tag variant names are correctly left alone — see
    _is_custom_name_tag() for why detection is based on Steam's
    quote-wrapping convention rather than a string comparison.
    """
    if name_hint and _is_custom_name_tag(name_hint):
        return f"{name_hint}  (Actual name: {schema_name})"
    return name_hint or schema_name


def match_owned_items(owned_items, defindex_index, pak, class_filter=None, slot_filter=None):
    """
    Cross-reference owned inventory items against the schema's defindex index
    and the actual VPK archive, returning only items that can genuinely be
    used as a swap source or target.

    class_filter narrows multi-class items to one class's model variant (see
    point 3 below). slot_filter narrows weapons to one loadout slot —
    primary, secondary, melee, etc. — matching the slot filter already
    chosen at Step 2 of the weapon swap flow. Without this, an owned
    secondary weapon would still show up while browsing a primary-only
    weapon swap, which isn't wrong exactly, but doesn't match what the rest
    of that flow has already committed to.

    Five things narrow the owned-items list down to usable ones:
    1. The item's defindex must be in the schema index (defindex_index from
       tf2_schema.build_defindex_index()) — this gives us the model path
       stem(s) for that item.
    2. At least one of those stems must actually exist as a .mdl file in the
       VPK — some owned items (tools, currency, crates) have no 3D model at
       all and can't be a swap source or target.
    3. class_filter, if given, narrows down to items usable by that class.
       Cosmetics and weapons need different matching here, because TF2
       organises their model paths completely differently:
         - Cosmetics: per-class path matching, identical to find_models().
           An all-class item with per-class model variants (most all-class
           cosmetics work this way) only shows the one stem for the chosen
           class, rather than once per class it supports.
         - Weapons: checked against the schema's allowed-classes list for
           that defindex (entry["classes"], from build_defindex_index()).
           Weapon model paths have no class-folder structure at all — e.g.
           a Minigun's path never contains "/heavy/" anywhere — so the
           cosmetic-style folder check would (and, before this fix, did)
           wrongly exclude every weapon the moment a specific class was
           chosen, regardless of whether the player actually owned it.
    4. slot_filter, if given, requires the item's loadout slot to match
       exactly — but for weapons, "the item's loadout slot" is resolved
       per the chosen class first (see point 3's weapon case above and
       resolve_class_slot() in tf2_schema.py), since some weapons sit in a
       different slot per class (the Shotgun: primary for Engineer,
       secondary for everyone else who can use it). Using the entry's flat
       item_slot here unconditionally would silently misfilter every such
       weapon for every class except whichever one the schema's default
       value happens to match.
    5. Duplicate stems are collapsed — owning five of the same hat only
       needs to show up once in a picker.

    Returns a list of dicts: [{stem, model_path, name, item_type, owned_item}]
    sorted by name, ready to feed into the same picker flow used for the
    full-catalog search (label_for / label_for_weapon already work against
    these the same way, since 'name' and 'item_type' match the schema's
    normal ItemInfo shape).
    """
    pak_mdl_paths = {p.lower() for p in pak if p.endswith(".mdl")}

    cf_terms = None
    cf_lower = None
    if class_filter and class_filter != "all":
        cf_terms = _CLASS_PATH_TERMS.get(class_filter.lower(), [class_filter.lower()])
        cf_lower = class_filter.lower()

    seen_stems = set()
    matched = []
    for owned in owned_items:
        entry = defindex_index.get(owned["defindex"])
        if not entry:
            continue  # not in schema — no model data, can't be used

        # Exclude event passes by name (see _OWNED_ITEM_NAME_EXCLUDE_WORDS above).
        # Whole-word match against lowercased name tokens, not substring —
        # "Activated Campaign 3 Pass" excluded, a hypothetical "Compass"
        # cosmetic would not be.
        name_words = set(entry["name"].lower().replace("'", " ").split())
        if name_words & _OWNED_ITEM_NAME_EXCLUDE_WORDS:
            continue

        is_weapon = entry.get("item_type") == "weapon"

        if slot_filter and slot_filter != "all":
            # Weapons: resolve the effective slot for the chosen class first.
            # Some weapons (the Shotgun, confirmed against a real
            # items_game.txt) sit in a different slot per class — e.g.
            # Engineer's primary but Heavy's secondary — and the entry's
            # flat item_slot is only the schema's default/fallback value,
            # not necessarily correct for every class that can use it.
            effective_slot = entry.get("item_slot", "")
            if is_weapon and cf_lower is not None:
                override = entry.get("per_class_slot", {}).get(cf_lower)
                if override:
                    effective_slot = override
            if effective_slot.lower() != slot_filter.lower():
                continue

        # Weapon class filtering: a straight allowed-classes check against
        # the whole entry, same convention search_and_pick_weapons() uses
        # for catalog search. No per-stem folder logic — weapons don't have
        # class-specific model variants the way cosmetics can.
        if is_weapon and cf_lower is not None:
            entry_classes = [c.lower() for c in entry.get("classes", [])]
            if cf_lower not in entry_classes:
                continue

        for stem in entry["stems"]:
            stem_lower = stem.lower()

            # Cosmetic class filtering: per-stem path matching, since a
            # single all-class entry can list multiple stems (one per class
            # variant) and the right one for the chosen class needs picking
            # out specifically, not just permission-checked.
            if not is_weapon and cf_terms is not None:
                # Same two-case logic as find_models(): a class-specific
                # stem must be in that class's own folder; an all-class
                # stem either has a matching per-class suffix, or has no
                # class-specific variants at all (shared by everyone).
                in_class_folder = any(f"/{t}/" in stem_lower for t in cf_terms)
                if "/all_class/" in stem_lower:
                    has_our_class = any(f"_{t}" in stem_lower for t in cf_terms)
                    has_other_class = any(
                        f"_{t}" in stem_lower for t in _ALL_CLASS_PATH_TERMS if t not in cf_terms
                    )
                    if not (has_our_class or not has_other_class):
                        continue
                elif not in_class_folder:
                    continue

            full_path = stem_lower + ".mdl"
            if full_path not in pak_mdl_paths:
                continue  # schema lists a stem but the VPK doesn't have it
            if stem_lower in seen_stems:
                continue
            seen_stems.add(stem_lower)
            # Steam's own inventory data carries a more specific name per
            # owned asset than the schema does (e.g. a war-painted variant
            # vs the schema's generic base name) — that's used as-is,
            # since it's still genuinely identifying.
            # A custom name TAG is different: Steam replaces the whole
            # display name with the player's chosen text (e.g.
            # "''Mr. Fahrenheit''" for an actual Degreaser), which is
            # ambiguous on its own if multiple owned items have name tags.
            # display_name_with_actual() appends the real item name in
            # that case; for everything else it's just name_hint or the
            # schema name, unchanged. Either way this is display-only — the
            # model path used for the swap is unaffected.
            display_name = display_name_with_actual(owned.get("name_hint"), entry["name"])
            matched.append({
                "stem": stem,
                "model_path": stem + ".mdl",
                "name": display_name,
                "item_type": entry["item_type"],
                "owned_item": owned,
            })

    return sorted(matched, key=lambda m: m["name"])


def diagnose_owned_items(owned_items, defindex_index, pak):
    """
    Per-item breakdown of why each owned item does or doesn't show up in
    own-inventory mode. Not used by the normal swap flow — a troubleshooting
    aid for cases where an item the user knows they own isn't appearing.

    The likely culprit for weapons: War Paint weapons don't
    carry resolvable model data in items_game.txt the way a stock-model
    weapon does — the model stays the base weapon's .mdl, with the paint
    applied as a separate material layer. That gap is the reason war paint
    support is scoped to its own pipeline (see the roadmap) rather than
    being part of own-inventory mode. This function exists to confirm
    that's actually what's happening for a given inventory file, rather
    than assuming it.

    Returns a list of dicts, one per owned item:
        defindex, quality, name_hint  — as given in the inventory data
        in_schema      — whether the defindex was found in defindex_index at all
        schema_name    — the schema's name for it, if found
        item_type      — "weapon" / "cosmetic", if found
        item_slot      — loadout slot, if found
        stems          — model path stem(s) the schema lists for it, if found
        stems_in_vpk   — which of those stems actually exist as a .mdl file
                         in the archive (the final, decisive usability check)
        usable         — True only if at least one stem is in the VPK
    """
    pak_mdl_paths = {p.lower() for p in pak if p.endswith(".mdl")}
    rows = []
    for owned in owned_items:
        entry = defindex_index.get(owned["defindex"])
        row = {
            "defindex": owned["defindex"],
            "quality": owned.get("quality"),
            "name_hint": owned.get("name_hint"),
            "in_schema": entry is not None,
            "schema_name": entry["name"] if entry else None,
            "item_type": entry["item_type"] if entry else None,
            "item_slot": entry.get("item_slot") if entry else None,
            "stems": entry["stems"] if entry else [],
            "stems_in_vpk": [],
            "usable": False,
        }
        if entry:
            row["stems_in_vpk"] = [
                s for s in entry["stems"] if (s.lower() + ".mdl") in pak_mdl_paths
            ]
            row["usable"] = bool(row["stems_in_vpk"])
        rows.append(row)
    return rows


# ---------- model search ----------

def find_models(pak, keyword, class_filter=None):
    """
    Search the game archive for cosmetic item model files matching a keyword.
    Returns a sorted, deduplicated list of matching .mdl file paths.

    Paths inside the archive look like:
        models/player/items/scout/some_hat.mdl

    The class filter narrows results by character class. It handles two cases:

    Case 1 — Items belonging to a specific class:
        These live in a folder named after the class (e.g. /scout/, /demoman/)
        and are included only when searching for that class.

    Case 2 — Items usable by all classes ('all-class' items):
        These live in an /all_class/ folder and may have per-class model variants
        identified by a class name suffix (e.g. _demo, _engi). An all-class item
        is included for a class search if it either has a variant matching that
        class, or has no class-specific variants at all (meaning one model is
        shared by everyone).
    """
    # Normalise the keyword to match the underscore-separated naming style
    # used in archive paths (e.g. "hot air" becomes "hot_air")
    kw = keyword.lower().replace(" ", "_")
    hits = [p for p in pak if p.endswith(".mdl") and kw in p.lower()]

    if class_filter and class_filter != "all":
        cf = class_filter.lower()
        cf_terms = _CLASS_PATH_TERMS.get(cf, [cf])
        filtered = []
        for h in hits:
            hl = h.lower()
            # Case 1: model lives in a class-specific subfolder
            if any(f"/{t}/" in hl for t in cf_terms):
                filtered.append(h)
            # Case 2: all-class item — check for class-specific suffix variants
            elif "/all_class/" in hl:
                has_our_class = any(f"_{t}" in hl for t in cf_terms)
                has_other_class = any(
                    f"_{t}" in hl for t in _ALL_CLASS_PATH_TERMS if t not in cf_terms
                )
                # Include if it has a variant for our class, or no class variants at all
                if has_our_class or not has_other_class:
                    filtered.append(h)
        hits = filtered
    return sorted(set(hits))


def all_stems(pak):
    """
    Return every unique model filename stem (filename without path or extension).
    For example, 'models/player/items/scout/some_hat.mdl' yields 'some_hat'.
    Used by the typo-suggestion system: when a search finds nothing, we compare
    the user's keyword against this list to suggest similar-sounding names.
    """
    return sorted(set(os.path.basename(p)[:-4] for p in pak if p.endswith(".mdl")))


def all_weapon_stems(pak):
    """
    Return unique filename stems for weapon viewmodel files only.
    Weapon viewmodels (the first-person models shown in the player's hands) are
    stored under a 'c_models' subfolder in the archive — the 'c' stands for
    'client' (i.e. the local player's view). Scoping suggestions to this folder
    keeps weapon typo hints relevant and excludes unrelated models.
    """
    return sorted(set(
        os.path.basename(p)[:-4]
        for p in pak
        if "/c_models/" in p.lower() and p.endswith(".mdl")
    ))


def safe_join_under(base_dir, archive_path):
    """
    Join an archive-style path ("models/weapons/.../thing.mdl") onto a real
    base directory, and refuse if the result would land outside that base
    directory. Raises BuildError if it would.

    Why this exists: every build function below writes files at a path
    taken from a dict key — and several of those dict keys ultimately
    trace back to strings parsed out of *raw bytes* in a binary file the
    user imported from a third party (a model's cdmaterials directory
    string, read directly off disk by a different module that reads
    material data). A string like that is not just an internal-path
    annotation, it's untrusted input — nothing stops a maliciously crafted
    file from embedding something like
        "../../../../../home/user/.bashrc"
    as its own cdmaterials value. Plain os.path.join() does not protect
    against this: joining a base directory with a path containing ".."
    segments happily walks back out of that directory, and the file gets
    written wherever the ".." segments point — not where the caller
    intended, and not necessarily somewhere safe to write to.

    This normalises the joined result and checks it's still inside
    base_dir using os.path.commonpath, which is the same technique already
    used by tf2autoswap.py's is_in_preloader() for an analogous problem.
    Every build function that writes from an archive-path dict key should
    route through this rather than calling os.path.join() directly,
    regardless of whether today's actual callers happen to only ever
    supply safe paths — the paths a function MIGHT be called with, not
    just the ones it currently is, are what this needs to hold up against.
    """
    base_abs = os.path.abspath(base_dir)
    joined = os.path.join(base_abs, *archive_path.split("/"))
    resolved = os.path.abspath(joined)
    try:
        if os.path.commonpath([resolved, base_abs]) != base_abs:
            raise BuildError(
                f"Refusing to write outside the build directory: '{archive_path}' "
                f"resolves to a path escaping {base_dir}"
            )
    except ValueError:
        # commonpath raises ValueError comparing across drives on Windows —
        # different drives can never share a common path, so that's an
        # escape by definition, not a case to let through.
        raise BuildError(
            f"Refusing to write outside the build directory: '{archive_path}' "
            f"resolves to a different drive than {base_dir}"
        )
    return resolved


def resolved_path_under(path, allowed_root):
    """
    Return True if path, once any symlinks are fully resolved, is still
    located under allowed_root.

    Why this exists: a downloaded mod (Gamebanana or similar) is a folder
    of files the user did not create and is very unlikely to inspect file
    by file before importing. If one of those files is a symlink pointing
    outside the mod's own folder — say, at the user's SSH keys, browser
    data, or any other local file — code that just calls open(path).read()
    on every file it finds will silently read whatever the symlink
    actually points to, not the file the user thinks they're importing.
    Confirmed with a working proof-of-concept before this check was added:
    a planted symlink disguised as a .vtf texture had an arbitrary local
    file's real contents read straight into the tool's in-memory data, on
    track to end up packed into the output VPK.

    Banning symlinks outright would be the blunt fix, but it isn't the
    right one here — symlinked folders are an entirely normal way to
    organise files (a synced cloud folder, a shared asset library, a
    deliberately symlinked downloads directory), and refusing all of them
    would break real workflows for no safety benefit, since a symlink
    pointing to another file *within* the same legitimate folder structure
    isn't a threat. The actual risk is specifically a symlink whose target
    resolves *outside* the folder the user pointed the importer at — so
    that's the one thing this checks, the same "must resolve inside the
    expected root" approach safe_join_under() uses for writes, applied
    here to reads instead.
    """
    real_path = os.path.realpath(path)
    real_root = os.path.realpath(allowed_root)
    try:
        return os.path.commonpath([real_path, real_root]) == real_root
    except ValueError:
        # commonpath raises ValueError comparing across drives on Windows —
        # different drives can never share a common path, so that's outside
        # the allowed root by definition.
        return False


def patch_mdl(data, new_name):
    """
    Rewrite the internal name stored inside a model's .mdl file header.

    Background: every TF2 .mdl file contains a copy of its own archive path
    embedded in the file's binary header. When TF2 loads a model, it reads
    this internal name and uses it to find related files (textures, physics
    data, etc.). If the internal name doesn't match the path the file was
    loaded from, TF2 will refuse to load the model or render it incorrectly.

    When we copy a model to a different path in the output archive (the core
    of what this tool does), we must update this embedded name to match the
    new destination path — otherwise the game will reject it.

    MDL binary header layout (the fields relevant to this operation):
        Bytes  0-3   : Magic number 'IDST' — identifies this as a compiled
                       Source Engine model file (Source is Valve's game engine)
        Bytes  4-7   : Model format version number (we leave this unchanged)
        Bytes  8-11  : Checksum (we leave this unchanged)
        Bytes 12-75  : Internal name string, null-terminated, 64 bytes maximum
                       (63 characters + one null terminator byte)
        Bytes 76+    : Remaining header data (we leave this unchanged)

    If the magic bytes 'IDST' are not present, the data is not a valid model
    file and is returned unchanged to avoid corrupting it.
    """
    if data[:4] != b'IDST':
        # Not a valid Source Engine model file — pass through unchanged
        return data
    # Replace the name field: encode the new path as bytes, truncate to 63
    # characters, and pad to exactly 64 bytes with null bytes
    return data[:12] + new_name.encode()[:63].ljust(64, b'\x00') + data[76:]


# ---------- weapon model helpers ----------

def find_weapons(pak, keyword):
    """
    Search the game archive for weapon viewmodel files matching a keyword.

    TF2 weapons have two separate 3D models:
    - Viewmodel: the first-person model the local player sees in their own
      hands while playing. Stored in archive paths containing 'c_models'
      (where 'c' stands for 'client' — the local player's view).
    - Worldmodel: the third-person model that other players see when looking
      at you. Stored in archive paths containing 'w_models'.

    This function searches only for viewmodel files (c_models), because the
    viewmodel path is used as the primary identifier for a weapon swap. The
    corresponding worldmodel is located separately using the world model helper
    functions below.

    Variant files (festive decorations, seasonal reskins, animation-only rigs,
    arm models) are filtered from results by default — they are not base weapon
    models and would clutter the results. If the user explicitly searches for
    a variant term (e.g. 'festivizer'), filtering is skipped so they can still
    find those files.

    Deduplication by filename handles the case where the same weapon model
    appears at multiple paths inside the archive (e.g. in both the base game
    data and a workshop override section) — these represent the same asset and
    would otherwise appear as duplicate results.
    """
    kw = keyword.lower().replace(" ", "_")
    hits = [
        p for p in pak
        if "/c_models/" in p.lower() and p.endswith(".mdl") and kw in p.lower()
    ]

    # Only filter variant suffixes if the user isn't explicitly searching for one
    variant_search = any(v.strip("_") in kw for v in _WEAPON_VARIANT_SUFFIXES)
    if not variant_search:
        hits = [
            h for h in hits
            if not any(
                os.path.basename(h[:-4]).lower().endswith(s)
                for s in _WEAPON_VARIANT_SUFFIXES
            )
        ]

    # Deduplicate by filename — same weapon at multiple archive paths = one result
    seen_bases = set()
    deduped = []
    for h in sorted(set(hits)):
        base = os.path.basename(h[:-4]).lower()
        if base not in seen_bases:
            seen_bases.add(base)
            deduped.append(h)
    return deduped


def find_props(pak, keyword):
    """
    Search the game archive for world prop model files matching a keyword.

    Props are the static and dynamic set-dressing models placed in maps —
    crates, barrels, payload carts, control-point models, and so on. They
    live under models/props_* (and a few under models/props/ directly).
    They are ordinary model files like any cosmetic or weapon, so a prop
    swap reuses exactly the same model-swap pipeline (read source, patch
    the .mdl name, pack a VPK) — only the search differs.

    Prop *model* swaps are low risk: sv_pure rejects non-whitelisted prop
    models in matchmaking, and the only client-side effect is how a prop
    looks to you. The one fairness consideration — swapping a large prop
    for a much smaller one can open a sightline — is the interface's job to
    warn about, not this search function's. Prop *material* swaps are
    intentionally out of scope project-wide (see tf2_material.py's safety
    layer) — that's the see-through-prop wallhack vector.
    """
    kw = keyword.lower().replace(" ", "_")
    hits = [
        p for p in pak
        if p.endswith(".mdl")
        and ("/props_" in p.lower() or "/props/" in p.lower())
        and kw in p.lower()
    ]
    seen, deduped = set(), []
    for h in sorted(set(hits)):
        base = os.path.basename(h[:-4]).lower()
        if base not in seen:
            seen.add(base)
            deduped.append(h)
    return deduped


def read_mdl_hull_dimensions(mdl_bytes):
    """
    Read a compiled .mdl's hull bounding box (hull_min, hull_max) — the
    model's overall size in game units, used by the engine for collision
    and view-culling. Returns (hull_min, hull_max) as two (x, y, z) tuples,
    or None if mdl_bytes isn't a valid .mdl.

    Why this exists: a prop swap is client-side-only, so it can never
    disadvantage or affect other players directly — their clients never
    load or see the swapped model at all. But it CAN create a real
    fairness issue in a different way: swapping a large, visually-blocking
    prop for something much smaller (or absent) removes a sightline
    obstruction that everyone else still believes is there, while your
    own collision is unaffected (still governed by the server's original,
    unswapped data) — you gain visual information into an area others
    expect to be blocked, without changing what you can actually walk
    through. This is the real mechanism behind the project's existing
    "keep replacements similar in size" guidance; this function is what
    lets that be an actual computed check instead of just static text.

    Byte layout, per the documented Source SDK studiohdr_t struct:
        id(4) version(4) checksum(4) name(64) dataLength(4)
        eyeposition(12) illumposition(12) hull_min(12) hull_max(12) ...
    giving hull_min at byte offset 104 and hull_max at offset 116, each
    three little-endian floats (x, y, z). This is the same struct
    patch_mdl() already relies on for the name field's boundaries (bytes
    12-75) — consistent with, not separate from, what's already verified
    elsewhere in this file. Confirmed against six real .mdl files spanning
    hats (~10-50 units) through furniture (~25-90) through vehicle-scale
    props (~150-650) before being relied on here — all came back
    physically sane and consistent with what each model actually looks
    like in-game.
    """
    if mdl_bytes[:4] != b"IDST" or len(mdl_bytes) < 128:
        return None
    hull_min_offset = 4 + 4 + 4 + 64 + 4 + 12 + 12  # = 104
    try:
        hull_min = struct.unpack("<3f", mdl_bytes[hull_min_offset:hull_min_offset + 12])
        hull_max = struct.unpack("<3f", mdl_bytes[hull_min_offset + 12:hull_min_offset + 24])
    except struct.error:
        return None
    return hull_min, hull_max


def prop_size_warning(src_mdl_bytes, dst_mdl_bytes, threshold=2.5):
    """
    Compare two models' hull bounding boxes and return a warning string if
    a prop swap would substantially change the prop's size — the real
    fairness concern behind "keep replacements similar in size to play
    fair" (see read_mdl_hull_dimensions() for the full reasoning). Returns
    None if either model's hull data can't be read, or if the sizes are
    within `threshold` of each other.

    Uses each model's longest single axis (length, width, or height,
    whichever is biggest) as the size comparison, rather than volume —
    volume is skewed by thin, flat objects (a large board has tiny volume
    but a large visible footprint, which is exactly the case that
    actually matters for sightlines), so the longest axis is a more
    robust proxy for "how much does this block a view or a path."

    threshold is a ratio: 2.5 means one model's longest axis is at least
    2.5x the other's before this warns. Chosen to flag genuinely
    substantial swaps (crate-for-shed, barrel-for-truck) without firing
    on completely ordinary size variation between similar-category props.
    """
    src_hull = read_mdl_hull_dimensions(src_mdl_bytes) if src_mdl_bytes else None
    dst_hull = read_mdl_hull_dimensions(dst_mdl_bytes) if dst_mdl_bytes else None
    if not src_hull or not dst_hull:
        return None

    def longest_axis(hull):
        hmin, hmax = hull
        return max(hmax[i] - hmin[i] for i in range(3))

    src_size = longest_axis(src_hull)
    dst_size = longest_axis(dst_hull)
    if src_size <= 0 or dst_size <= 0:
        return None

    ratio = max(src_size, dst_size) / min(src_size, dst_size)
    if ratio < threshold:
        return None

    bigger = "replacement" if src_size > dst_size else "original"
    return (f"sizes differ substantially (~{src_size:.0f} vs ~{dst_size:.0f} units on their "
            f"longest side, {ratio:.1f}x) — the {bigger} is much bigger. Your collision stays "
            f"where the original prop was either way, but a big size mismatch can open or "
            f"block sightlines that everyone else still expects to be the original size.")


def _world_base_candidates(view_base):
    """
    Derive possible archive paths for a weapon's worldmodel from its viewmodel path.

    Background: TF2 weapon assets come in two model variants:
    - Viewmodel (prefix 'c_'): the first-person hand view only the local player sees
    - Worldmodel (prefix 'w_'): the third-person model other players see you holding

    These are separate 3D model files stored at different archive paths. We need
    both when building a weapon swap so the change looks correct from both perspectives.

    The problem: Valve uses two different folder structures for worldmodels depending
    on the weapon, and there is no way to determine which structure a given weapon
    uses just from the viewmodel path alone. We must try both and check which exists.

    Structure A — Shared subfolder (most older weapons):
        Viewmodel:  models/weapons/c_models/c_scattergun/c_scattergun
        Worldmodel: models/weapons/c_models/c_scattergun/w_scattergun
        (worldmodel sits alongside the viewmodel in the same subfolder)

    Structure B — Separate top-level folder (some newer weapons, e.g. minigun):
        Viewmodel:  models/weapons/c_models/c_minigun/c_minigun
        Worldmodel: models/weapons/w_models/w_minigun
        (worldmodel is in a completely separate 'w_models' folder, no subfolder)

    This function returns both candidate paths, most likely first. The caller
    checks which one actually exists in the archive.

    Returns an empty list if the viewmodel filename does not start with 'c_',
    since non-viewmodel paths cannot have a corresponding worldmodel path derived
    this way.
    """
    parts = view_base.split("/")
    vname = parts[-1]

    # Only viewmodel files (prefixed 'c_') have corresponding worldmodels
    if not vname.lower().startswith("c_"):
        return []

    # Derive the worldmodel filename: replace the 'c_' prefix with 'w_'
    w_name = "w_" + vname[2:]
    candidates = []

    # Structure A candidate: worldmodel in the same subfolder as the viewmodel
    if len(parts) >= 2:
        candidates.append("/".join(parts[:-1] + [w_name]))

    # Structure B candidate: worldmodel in a separate top-level 'w_models' folder.
    # This requires finding the 'c_models' segment of the path and replacing the
    # entire 'c_models/c_<name>' portion with 'w_models'.
    # e.g. models/weapons/c_models/c_minigun/c_minigun
    #   -> models/weapons/w_models/w_minigun
    c_idx = next((i for i, p in enumerate(parts) if p == "c_models"), None)
    if c_idx is not None:
        flat = "/".join(parts[:c_idx] + ["w_models", w_name])
        if flat not in candidates:
            candidates.append(flat)

    return candidates


def find_disk_weapon_worldmodel(view_mdl_path):
    """
    Given the local disk path to a weapon's viewmodel .mdl, try to find a
    sibling worldmodel .mdl in the same downloaded mod folder — the local-
    filesystem equivalent of _world_base_candidates() above, which does
    the same thing for in-game archive paths. Same two structures, just
    checked as real files on disk rather than VPK archive entries:

    Structure A — worldmodel alongside the viewmodel in the same folder
        c_thing.mdl  and  w_thing.mdl, both in the same directory
    Structure B — worldmodel in a sibling 'w_models' folder
        .../c_models/c_thing/c_thing.mdl  and  .../w_models/w_thing.mdl

    Returns the worldmodel's local path if found, or None — None is the
    normal, expected result for melee weapons, which typically have no
    separate worldmodel at all, same as for catalog-sourced weapons.
    """
    fname = os.path.basename(view_mdl_path)
    if not fname.lower().startswith("c_"):
        return None
    w_name = "w_" + fname[2:]
    folder = os.path.dirname(os.path.abspath(view_mdl_path))

    # Structure A: same folder
    candidate_a = os.path.join(folder, w_name)
    if os.path.isfile(candidate_a):
        return candidate_a

    # Structure B: sibling 'w_models' folder, replacing the 'c_models/c_<name>'
    # portion of the path entirely, same convention as the archive-path version
    parts = folder.split(os.sep)
    if "c_models" in parts:
        idx = parts.index("c_models")
        candidate_b = os.sep.join(parts[:idx] + ["w_models", w_name])
        if os.path.isfile(candidate_b):
            return candidate_b

    return None


def derive_world_base(view_base):
    """
    Return the most likely worldmodel base path for a given viewmodel path.

    This is a best-guess estimate that does not consult the game archive. Use
    resolve_world_base_from_vpk() when the archive is available — it checks
    which path actually exists and is therefore accurate rather than guessed.
    """
    candidates = _world_base_candidates(view_base)
    return candidates[0] if candidates else None


def resolve_world_base_from_vpk(pak, view_base):
    """
    Find the actual worldmodel archive path by checking the game archive.

    Tries both possible folder structures (see _world_base_candidates) and
    returns the one that has files present. If neither structure yields results,
    returns the first candidate as a fallback.

    This should be used when building weapon swaps, because the output archive
    must contain files at the correct paths — a wrong path would produce a mod
    that loads but has no visible effect for the worldmodel.
    """
    for candidate in _world_base_candidates(view_base):
        if source_from_vpk(pak, candidate):
            return candidate
    # Neither structure found — return the primary guess as a fallback
    candidates = _world_base_candidates(view_base)
    return candidates[0] if candidates else None


def source_from_vpk_weapon(pak, view_base):
    """
    Read both the viewmodel and worldmodel files for a weapon from the game archive.

    Tries both possible worldmodel folder structures and uses whichever has files.

    Returns a 3-tuple:
        view_files  — dict of {extension: bytes} for the viewmodel
        world_files — dict of {extension: bytes} for the worldmodel,
                      or an empty dict if no worldmodel was found
        world_base  — the archive base path where the worldmodel was found,
                      or None if no worldmodel exists

    An empty world_files is a normal and expected result for melee weapons
    (knives, bats, wrenches etc.) — they typically do not have a separate
    worldmodel in TF2.
    """
    view_files = source_from_vpk(pak, view_base)
    for candidate in _world_base_candidates(view_base):
        world_files = source_from_vpk(pak, candidate)
        if world_files:
            return view_files, world_files, candidate
    # No worldmodel found — return empty dict, not an error
    return view_files, {}, None


# ---------- source readers ----------

def source_from_vpk(pak, src_base):
    """
    Read all model component files for a given base path from the game archive.

    'base path' means the path without any file extension. For example:
        models/player/items/scout/some_hat
    would read:
        models/player/items/scout/some_hat.mdl
        models/player/items/scout/some_hat.vvd
        models/player/items/scout/some_hat.dx80.vtx
        (and so on for all extensions in EXTS)

    Returns a dict of {extension: bytes}. Extensions that do not exist in the
    archive for this particular model are silently skipped — not all models
    have all five file types, and missing files are handled gracefully elsewhere.
    """
    files = {}
    for ext in EXTS:
        try:
            files[ext] = read_vpk_entry(pak, src_base + ext)
        except KeyError:
            pass  # This file type simply does not exist for this model
    return files


def find_mod_materials(mdl_path):
    """
    Find the 'materials' folder that belongs to a mod imported from disk.

    When players download custom mods (from sites like Gamebanana), the
    folder structure varies more than any single fixed assumption can
    cover. Two common shapes, among others:
        Mirrors the in-game archive path:
            mod_root/
                models/...thing.mdl
                materials/...thing.vmt
        Flat (especially common for simple single-item reskins):
            mod_root/
                thing.mdl
                materials/...thing.vmt

    This walks upward from the .mdl's own directory, checking at each
    level for a sibling 'materials' folder, and returns the first one
    found. That naturally covers both shapes above (and anything in
    between) without depending on a literal 'models' folder name
    appearing anywhere in the path — confirmed by testing against a flat
    structure, which an earlier version of this function (relying on
    finding a 'models' path segment) missed entirely, silently treating a
    perfectly valid materials folder as if it didn't exist.

    The walk is capped at a few levels (MAX_UP) so a .mdl picked from deep
    inside an unrelated folder tree doesn't accidentally pick up some
    unrelated 'materials' folder several directories up that has nothing
    to do with the actual mod — five levels covers the deepest realistic
    archive-mirroring structure (mod_root/materials/models/player/items/
    <class>/thing.vmt) with room to spare.

    Returns the full path to the materials folder if found, or None.
    """
    MAX_UP = 5
    current = os.path.dirname(os.path.abspath(mdl_path))
    for _ in range(MAX_UP + 1):
        candidate = os.path.join(current, "materials")
        if os.path.isdir(candidate):
            return candidate
        parent = os.path.dirname(current)
        if parent == current:
            break  # reached filesystem root — nowhere further up to check
        current = parent
    return None


def source_from_disk(mdl_path):
    """
    Read a locally stored model file and its associated material files from disk.

    Used when importing custom mods downloaded from the internet (e.g. Gamebanana)
    or created by the user. This is the path that enables 'material transport' —
    bundling custom textures alongside the model so they're included in the output
    and the mod looks correct in-game.

    Reads all five model file components (.mdl, .vvd, .vtx variants), then walks
    the sibling materials folder to collect all material and texture files.

    Material file paths are stored relative to the mod root (the parent of the
    materials/ folder) so they match the archive path format that TF2 expects:
        materials/models/player/items/thing.vtf  <- correct archive path format

    Returns a 3-tuple:
        model_files    — dict of {extension: bytes} for the model components
        material_files — dict of {archive_path: bytes} for all material/texture files,
                         keyed by their correct archive path
        meta           — dict with 'materials_dir' (path or None) and 'material_count'
                         (integer), used by the interface to report what was found
    """
    if not os.path.isfile(mdl_path) or not mdl_path.endswith(".mdl"):
        raise BuildError(f"Not a .mdl file: {mdl_path}")

    mod_root = os.path.dirname(mdl_path)
    skipped = []

    # Read all five model file types that exist alongside the .mdl. Each
    # sibling is checked against resolved_path_under() — see that function's
    # docstring for why (a downloaded mod's .vvd/.vtx files could just as
    # easily be a disguised symlink as a material file could).
    base = mdl_path[:-4]
    model_files = {}
    for ext in EXTS:
        p = base + ext
        if not os.path.isfile(p):
            continue
        if not resolved_path_under(p, mod_root):
            skipped.append(p)
            continue
        # Validate file size before reading
        validate_file_size(p, MAX_MODEL_FILE_SIZE, f"Model component {ext}")
        model_files[ext] = open(p, "rb").read()

    # Walk the materials folder and collect every file in it
    material_files = {}
    mats = find_mod_materials(mdl_path)
    if mats:
        root = os.path.dirname(mats)  # The mod root — parent of materials/
        for dirpath, _, filenames in os.walk(mats):
            for fn in filenames:
                full = os.path.join(dirpath, fn)
                if not resolved_path_under(full, root):
                    skipped.append(full)
                    continue
                # Validate individual file size before reading
                is_texture = fn.lower().endswith(".vtf")
                max_size = MAX_TEXTURE_FILE_SIZE if is_texture else MAX_MATERIAL_FILE_SIZE
                validate_file_size(full, max_size, f"Material file {fn}")
                # Build the archive-format path: forward slashes, relative to mod root
                rel = os.path.relpath(full, root).replace(os.sep, "/")
                material_files[rel] = open(full, "rb").read()
    
    # Validate total material set size
    validate_files_total_size(material_files, MAX_TOTAL_MATERIAL_SIZE, 
                             "Material file set")

    meta = {
        "materials_dir": mats,
        "material_count": len(material_files),
        # Files found but refused because a symlink among them resolved
        # outside the mod's own folder — see resolved_path_under(). The
        # interface should tell the user these were skipped rather than
        # silently dropping them with no explanation.
        "skipped_symlinks": skipped,
    }
    return model_files, material_files, meta


# ---------- build ----------

def build(model_files, dst_base, out_path, material_files=None):
    """
    Construct the output VPK archive file containing the swapped model.

    A VPK (Valve Package) archive works like a ZIP file — it packs multiple
    files into a single distributable file. The Casual Preloader (the third-party
    mod manager this tool targets) loads VPK files and injects their contents
    into TF2 at game launch.

    Build process:
    1. Create a temporary working directory on disk
    2. Write each model component file to the correct path within that directory,
       matching the archive path structure TF2 expects
    3. Patch the .mdl file's internal name header to reflect the destination path
       (see patch_mdl() — without this TF2 rejects the model)
    4. Write any accompanying material/texture files at their archive paths
    5. Pack the entire temporary directory into a single VPK file at out_path
    6. Delete the temporary directory (in a finally block so it always runs,
       even if something goes wrong)

    Returns a dict: {"packed": [list of extensions included], "material_count": n,
                     "out_path": path to the written VPK file}
    Raises BuildError if anything goes wrong during construction.
    """
    if ".mdl" not in model_files:
        raise BuildError("No .mdl found in the source model.")

    tmpdir = tempfile.mkdtemp()
    packed = []
    try:
        # Write model files into the temp directory at the destination path structure
        for ext, data in model_files.items():
            if ext == ".mdl":
                # Patch the internal model name to match where it's going in the archive
                data = patch_mdl(data, dst_base)
            # Split the forward-slash archive path into OS-appropriate folder segments
            out = safe_join_under(tmpdir, dst_base + ext)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            open(out, "wb").write(data)
            packed.append(ext)

        # Write material/texture files at their archive paths (already in correct format)
        for vpk_path, data in (material_files or {}).items():
            out = safe_join_under(tmpdir, vpk_path)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            open(out, "wb").write(data)

        # Pack the temp directory into a VPK archive file
        vpk = get_vpk()
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        vpk.new(tmpdir).save(out_path)

    except SwapError:
        raise  # Re-raise our own errors unchanged — don't wrap them again
    except Exception as e:
        raise BuildError(f"Failed to build VPK: {e}") from e
    finally:
        # Always clean up the temp directory, even if an exception occurred
        shutil.rmtree(tmpdir, ignore_errors=True)

    return {
        "packed": packed,
        "material_count": len(material_files or {}),
        "out_path": out_path,
    }


def build_addon_folder(model_files, dst_base, addons_dir, addon_name, material_files=None):
    """
    Write a mod as a 'native addon folder' — the Casual Preloader's own internal format.

    Background: The Casual Preloader is a third-party mod manager for TF2. It can
    load mods from VPK archive files, but it also has its own 'extracted' format:
    a folder containing the mod files laid out at their correct paths, plus a
    'mod.json' manifest file describing the mod. When a mod is in this format and
    placed in the preloader's addons directory, it appears in the preloader's list
    ready to enable — no manual import step required.

    This function writes directly to that format, producing:
        addons_dir/addon_name/models/.../<model component files>
        addons_dir/addon_name/materials/.../<material files, if any>
        addons_dir/addon_name/mod.json

    The advantage over the VPK approach: the user doesn't need to drag the file
    into the preloader manually — it shows up ready to use.

    Returns a dict: {"addon_dir": full path to the created folder, "packed": [extensions],
                     "material_count": n}
    """
    if ".mdl" not in model_files:
        raise BuildError("No .mdl found in the source model.")

    addon_root = os.path.join(addons_dir, addon_name)
    packed = []
    try:
        os.makedirs(addon_root, exist_ok=True)

        # Write model files at their correct paths inside the addon folder
        for ext, data in model_files.items():
            if ext == ".mdl":
                data = patch_mdl(data, dst_base)
            out = safe_join_under(addon_root, dst_base + ext)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            open(out, "wb").write(data)
            packed.append(ext)

        # Write material files at their archive paths inside the addon folder
        for vpk_path, data in (material_files or {}).items():
            out = safe_join_under(addon_root, vpk_path)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            open(out, "wb").write(data)

        # Write the mod.json manifest the Casual Preloader expects.
        # 'type' and 'contents' use category strings defined by the preloader.
        # 'Unknown' and 'Custom content' are the generic fallback values.
        manifest = {
            "addon_name": addon_name,
            "type": "Unknown",
            "description": f"Content extracted from {addon_name}.vpk",
            "contents": ["Custom content"],
        }
        with open(os.path.join(addon_root, "mod.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

    except SwapError:
        raise
    except Exception as e:
        raise BuildError(f"Failed to write addon folder: {e}") from e

    return {
        "addon_dir": addon_root,
        "packed": packed,
        "material_count": len(material_files or {}),
    }


# ---------- weapon build ----------

def build_weapon(view_files, world_files, dst_view_base, dst_world_base, out_path, material_files=None):
    """
    Construct a VPK archive containing both the viewmodel and worldmodel for a
    weapon swap.

    Because TF2 weapons are represented by two separate 3D model sets (one for
    the local player's first-person view, one for what other players see), both
    must be swapped together for the change to look consistent. See the module
    docstring and find_weapons() for more on viewmodel vs worldmodel.

    Both model sets have their .mdl header names patched to match the destination
    archive paths (see patch_mdl()).

    The worldmodel is optional — if world_files is empty or dst_world_base is None,
    the archive is built with the viewmodel only. This is normal behaviour for
    melee weapons in TF2, which typically have no worldmodel.

    material_files, if given, are written at their own archive paths unchanged
    (same as build()'s cosmetic material handling) — used for weapon disk
    imports, where the source model may bring its own custom textures. Callers
    must run these through tf2_material.validate_material_set() first and pass
    only verdict.safe_files, same requirement as every other material-bundling
    build function.

    Returns a dict: {"packed": [list of labels], "out_path": path}
    Labels are prefixed with 'view' or 'world' so the output is readable:
        e.g. ["view.mdl", "view.vvd", "world.mdl", "world.vvd", ...]
    """
    if ".mdl" not in view_files:
        raise BuildError("No .mdl found in the source viewmodel.")

    tmpdir = tempfile.mkdtemp()
    packed = []
    try:
        # Write viewmodel files
        for ext, data in view_files.items():
            if ext == ".mdl":
                data = patch_mdl(data, dst_view_base)
            out = safe_join_under(tmpdir, dst_view_base + ext)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            open(out, "wb").write(data)
            packed.append(f"view{ext}")

        # Write worldmodel files if they exist
        if world_files and dst_world_base:
            for ext, data in world_files.items():
                if ext == ".mdl":
                    data = patch_mdl(data, dst_world_base)
                out = safe_join_under(tmpdir, dst_world_base + ext)
                os.makedirs(os.path.dirname(out), exist_ok=True)
                open(out, "wb").write(data)
                packed.append(f"world{ext}")

        # Write material/texture files at their archive paths (already in correct format)
        for vpk_path, data in (material_files or {}).items():
            out = safe_join_under(tmpdir, vpk_path)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            open(out, "wb").write(data)

        vpk = get_vpk()
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        vpk.new(tmpdir).save(out_path)

    except SwapError:
        raise
    except Exception as e:
        raise BuildError(f"Failed to build weapon VPK: {e}") from e
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    return {"packed": packed, "out_path": out_path}


def build_weapon_addon_folder(view_files, world_files, dst_view_base, dst_world_base, addons_dir, addon_name, material_files=None):
    """
    Write a weapon swap as a Casual Preloader native addon folder.

    The same as build_addon_folder() but handles the dual-model structure that
    weapon swaps require (viewmodel + worldmodel). Both model sets are written
    at their correct archive paths inside the addon folder:
        addon_root/models/weapons/c_models/...  (viewmodel — first-person view)
        addon_root/models/weapons/w_models/...  (worldmodel — third-person view)
        addon_root/mod.json                     (preloader manifest)

    material_files, if given, are written the same way build_addon_folder()
    handles them — see build_weapon()'s docstring above for the same note
    about running them through the safety validator first.

    See build_addon_folder() for an explanation of the native addon folder format.
    Returns a dict: {"addon_dir": path, "packed": [labels]}
    """
    if ".mdl" not in view_files:
        raise BuildError("No .mdl found in the source viewmodel.")

    addon_root = os.path.join(addons_dir, addon_name)
    packed = []
    try:
        os.makedirs(addon_root, exist_ok=True)

        # Viewmodel files (first-person, 'c_' prefix in archive path)
        for ext, data in view_files.items():
            if ext == ".mdl":
                data = patch_mdl(data, dst_view_base)
            out = safe_join_under(addon_root, dst_view_base + ext)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            open(out, "wb").write(data)
            packed.append(f"view{ext}")

        # Worldmodel files (third-person, 'w_' prefix) — optional, skipped if absent
        if world_files and dst_world_base:
            for ext, data in world_files.items():
                if ext == ".mdl":
                    data = patch_mdl(data, dst_world_base)
                out = safe_join_under(addon_root, dst_world_base + ext)
                os.makedirs(os.path.dirname(out), exist_ok=True)
                open(out, "wb").write(data)
                packed.append(f"world{ext}")

        # Material files (custom weapon disk-imports only — same as cosmetics)
        for vpk_path, data in (material_files or {}).items():
            out = safe_join_under(addon_root, vpk_path)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            open(out, "wb").write(data)

        manifest = {
            "addon_name": addon_name,
            "type": "Unknown",
            "description": f"Content extracted from {addon_name}.vpk",
            "contents": ["Custom content"],
        }
        with open(os.path.join(addon_root, "mod.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

    except SwapError:
        raise
    except Exception as e:
        raise BuildError(f"Failed to write weapon addon folder: {e}") from e

    return {"addon_dir": addon_root, "packed": packed}


def preview_build_weapon(view_files, world_files, dst_view_base, dst_world_base):
    """
    Return a summary of what build_weapon() would produce, without writing anything.
    Used at the confirmation step in the interface to show the user what they are
    about to build before they commit to it.
    dst_world_base may be None if no worldmodel path could be determined.

    Returns a dict with:
        entries     — list of {path, ext, size} for each file that would be written
        view_count  — number of viewmodel files
        world_count — number of worldmodel files (0 if no worldmodel)
        total_size  — total bytes across all files
    """
    entries = []
    for ext, data in view_files.items():
        entries.append({"path": dst_view_base + ext, "ext": f"view{ext}", "size": len(data)})
    for ext, data in (world_files or {}).items():
        if dst_world_base:
            entries.append({"path": dst_world_base + ext, "ext": f"world{ext}", "size": len(data)})
    return {
        "entries": entries,
        "view_count": len(view_files),
        "world_count": len(world_files or {}),
        "total_size": sum(e["size"] for e in entries),
    }


# ---------- mod management ----------

def read_target_stem(vpk_path):
    """
    Open a previously built output VPK and read back the model's archive path.

    When we build a swap, we patch the destination archive path into the .mdl
    header (see patch_mdl()). This function reads that patched path back out,
    which tells us which game item the mod replaces. Used by list_output_mods()
    to show what each built mod is for.

    Returns the path stem (archive path without extension, lowercased), or None
    if the file cannot be read or contains no .mdl file.
    """
    vpk = get_vpk()
    try:
        pak = vpk.open(vpk_path)
        for p in pak:
            if p.endswith(".mdl"):
                return p[:-4].lower()
    except Exception:
        return None
    return None


def list_output_mods(output_dir):
    """
    List all output VPK files in the output directory, including subdirectories.

    Subdirectories are walked so mods the user has manually organised into
    subfolders still appear in the list.

    Returns a list of dicts sorted so root-level mods appear before
    subdirectory mods:
        [{path, name, rel, in_subfolder, target_stem}]

    'target_stem' is read from inside each VPK — it reflects the destination
    path we wrote at build time, telling us which game item the mod replaces.
    """
    if not os.path.isdir(output_dir):
        return []
    mods = []
    for dirpath, _, filenames in os.walk(output_dir):
        for fn in sorted(filenames):
            if fn.lower().endswith(".vpk"):
                path = os.path.join(dirpath, fn)
                rel = os.path.relpath(path, output_dir)
                mods.append({
                    "path": path,
                    "name": fn,
                    "rel": rel,
                    # Flag subdirectory mods so the interface can group them separately
                    "in_subfolder": os.path.abspath(dirpath) != os.path.abspath(output_dir),
                    "target_stem": read_target_stem(path),
                })
    return sorted(mods, key=lambda m: (m["in_subfolder"], m["rel"]))


def remove_file(path):
    """
    Delete a file from disk. Raises SwapError if the file does not exist.
    Wraps os.remove in a SwapError so the interface can catch it consistently
    alongside other tool errors without handling OS-level exceptions separately.
    """
    if not os.path.isfile(path):
        raise SwapError(f"File not found: {path}")
    os.remove(path)


def list_preloader_addons(addons_dir, signature):
    """
    List what is present in the Casual Preloader's addons folder.

    The Casual Preloader is a third-party mod manager for TF2 that injects
    mod files into the game at launch. It stores mods in an 'addons' directory.
    Mods can be in one of two formats:
    - Native addon folder: a directory containing extracted files plus a
      mod.json manifest (the format this tool writes when outputting directly
      to the preloader)
    - Loose VPK file: a plain archive file placed in the folder manually;
      the preloader may not recognise these without an explicit import step

    Returns a list of dicts: [{kind, name, rel, is_ours}] where:
        kind    — 'addon' for a native folder, 'vpk' for a loose archive
        is_ours — True if the name contains this tool's signature string,
                  indicating it was created by TF2autoswap

    Raises SwapError if the addons folder does not exist.

    Note: this reflects what files exist on disk. The preloader has its own
    internal enabled/disabled toggle that is separate from file presence —
    a mod being listed here does not mean it is currently active in-game.

    Implementation note: dirs[:] = [] prevents os.walk from descending into
    the contents of a native addon folder after we have identified it — we
    do not want to mistake files inside the addon for other addons.
    """
    if not os.path.isdir(addons_dir):
        raise SwapError(f"Preloader addons folder not found: {addons_dir}")

    out = []
    # Find native addon folders by looking for the mod.json manifest file
    for root, dirs, files in os.walk(addons_dir):
        if "mod.json" in files:
            name = os.path.basename(root)
            out.append({
                "kind": "addon",
                "name": name,
                "rel": os.path.relpath(root, addons_dir),
                "is_ours": signature.lower() in name.lower(),
            })
            # Stop descending — the addon's own contents are not other addons
            dirs[:] = []
    # Find loose VPK archive files
    for root, _, files in os.walk(addons_dir):
        for fn in sorted(files):
            if fn.lower().endswith(".vpk"):
                full = os.path.join(root, fn)
                out.append({
                    "kind": "vpk",
                    "name": fn,
                    "rel": os.path.relpath(full, addons_dir),
                    "is_ours": signature.lower() in fn.lower(),
                })
    return sorted(out, key=lambda a: (a["kind"], a["rel"]))


# ---------- dry run / preview ----------

def preview_build(model_files, dst_base, material_files=None):
    """
    Return a summary of what build() would produce, without writing anything.

    Used at the confirmation step in interactive mode to show the user a
    compact summary (file count, total size) of what is about to be built.
    Also used by the --dry-run command-line flag to show a detailed file-by-file
    breakdown without performing any disk writes.

    Returns a dict with:
        entries        — list of {path, ext, size} for each file that would be packed
        model_count    — number of model component files
        material_count — number of material/texture files
        total_size     — total bytes across all files
    """
    entries = []
    for ext, data in model_files.items():
        entries.append({"path": dst_base + ext, "ext": ext, "size": len(data)})
    for vpk_path, data in (material_files or {}).items():
        entries.append({"path": vpk_path, "ext": "material", "size": len(data)})
    return {
        "entries": entries,
        "model_count": len(model_files),
        "material_count": len(material_files or {}),
        "total_size": sum(e["size"] for e in entries),
    }
