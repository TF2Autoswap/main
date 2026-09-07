#!/usr/bin/env python3
"""
tf2_schema.py — TF2 item definitions and friendly name lookup.

Developed with: AI assistance via OpenRouter
Project : https://github.com/TF2Autoswap/autoswap
License : GPL v3 — see LICENSE for details

--- Background ---
Team Fortress 2 stores definitions for every item in the game (weapons, hats,
clothing, etc.) in a single human-readable text file called 'items_game.txt',
located inside the game's 'scripts/items/' folder. This file is in Valve's
proprietary 'KeyValues' text format — a simple nested key-value structure
similar to JSON.

This module reads that file and builds a fast lookup table mapping each item's
model file path to a structured record of its metadata. That metadata is used by
the interface to:
  - Display friendly item names (e.g. "Scattergun") instead of internal file
    names (e.g. "c_scattergun")
  - Warn users about potentially problematic swaps before they happen
  - Filter weapon searches by loadout slot and character class

Parsing items_game.txt takes a few seconds because it is a very large file
(over 550,000 lines). To avoid this delay on every run, the parsed index is
serialised to a JSON cache file. Subsequent runs load the cache instead of
re-parsing, making startup much faster. The cache is automatically invalidated
and rebuilt if TF2 updates items_game.txt.

Provides:
    load_schema(tf2_path)          -> parsed schema dict (raw, from VDF parser)
    build_index(schema)            -> { model_path_stem: ItemInfo }
    lookup(index, model_path)      -> ItemInfo or None
    build_defindex_index(schema)   -> { defindex: {name, item_type, item_slot,
                                         stems, classes, per_class_slot} }
                                       same data build_index() provides, keyed
                                       the other direction — by numeric item
                                       definition index rather than model path.
                                       Used by own-inventory mode, which starts
                                       from a Steam inventory item (a defindex,
                                       no model path) rather than a keyword.
    resolve_class_slot(item_slot, per_class_slot, class_name)
                                    -> the loadout slot for a specific class,
                                       accounting for weapons that sit in a
                                       different slot per class (see ItemInfo
                                       fields below)
    save_schema_cache() / load_schema_cache()
    save_defindex_cache() / load_defindex_cache()
                                    -> JSON cache pairs for the two indexes
                                       above, so items_game.txt (550,000+
                                       lines) doesn't get re-parsed every run

ItemInfo fields:
    name           friendly display name (e.g. "A Head Full of Hot Air")
    equip_region   the area of the player character model this item occupies,
                   e.g. "hat" (top of head) or "whole_head" (replaces head entirely)
    hides_head     True if equipping this item replaces/hides the player's default
                   head model (relevant for detecting visual overlap between items)
    classes        list of character class names that can equip this item
    item_type      "cosmetic", "weapon", or "unknown"
    item_slot      the loadout slot name: "primary", "secondary", "melee" for
                   weapons; "head", "misc" etc. for cosmetics — this is the
                   schema's flat/default value; see per_class_slot below for
                   weapons where the real answer depends on which class
    animation_risk True for melee weapons, which use a different animation rig
                   (control system for how the character holds and swings the item)
                   than other weapon types; swapping across this boundary can cause
                   visual animation errors
    per_class_slot dict of {class_name: slot_name} overrides for weapons shared
                   across classes that sit in a different slot for each — e.g.
                   the Shotgun is Engineer's primary weapon but Soldier/Pyro/
                   Heavy's secondary. Empty for the vast majority of items,
                   which have no such variance. Use resolve_class_slot() rather
                   than reading item_slot directly when a specific class is
                   known, to get the slot that's actually correct for them.
"""

import os
import json
from dataclasses import dataclass, field

# These sets define how we categorise items by their loadout slot name.
# TF2's item schema identifies items by the slot they occupy in the player's
# loadout — the slot name is the primary indicator of whether something is
# a weapon or a cosmetic.
WEAPON_SLOTS = {"primary", "secondary", "melee", "utility", "pda", "pda2", "building"}
COSMETIC_SLOTS = {"head", "misc", "action", "taunt"}
_ALL_SLOTS = WEAPON_SLOTS | COSMETIC_SLOTS

# Security: Schema file size limit (DoS protection).
# Real items_game.txt is ~20MB. 200MB allows substantial growth while
# preventing memory exhaustion attacks from malicious oversized files.
MAX_SCHEMA_SIZE = 200 * 1024 * 1024  # 200MB

# Security: Cache file size limit (cache poisoning protection).
# Real schema cache is ~5MB. 100MB allows growth while preventing
# memory exhaustion from maliciously replaced cache files.
MAX_CACHE_SIZE = 100 * 1024 * 1024  # 100MB


def _per_class_slot_overrides(resolved):
    """
    Some weapons are shared across multiple classes but occupy a different
    loadout slot for each — e.g. the Shotgun is Engineer's primary weapon
    but Soldier/Pyro/Heavy's secondary. TF2's schema encodes this directly
    in the used_by_classes block: instead of a plain "1" used-flag, the
    value for each class IS the slot name itself, when it differs by class.
    Confirmed directly against a real items_game.txt — the Shotgun's entry
    looks like:
        "used_by_classes"
        {
                "engineer"      "primary"
                "pyro"          "secondary"
                "soldier"       "secondary"
                "heavy"         "secondary"
        }
    There is no separate "per_class_loadout_slot" key — it's folded into
    used_by_classes itself.

    Returns {class_name_lower: slot_name_lower} for any class whose value
    is itself a recognised slot name. Items with no per-class variance
    (the vast majority — used_by_classes values are just "1"/"0" truthy
    flags there) return an empty dict; callers should fall back to the
    item's normal flat item_slot value in that case (see resolve_class_slot).
    """
    overrides = {}
    used_by = resolved.get("used_by_classes", {})
    if isinstance(used_by, dict):
        for class_name, value in used_by.items():
            if isinstance(value, str) and value.lower() in _ALL_SLOTS:
                overrides[class_name.lower()] = value.lower()
    return overrides


def resolve_class_slot(item_slot, per_class_slot, class_name):
    """
    Return the loadout slot for a specific class, accounting for per-class
    overrides (see _per_class_slot_overrides()). Falls back to the item's
    flat item_slot when that class has no override on record — which covers
    both "this item has no per-class slot variance at all" and "this
    particular class wasn't one of the ones listed with an explicit slot".
    class_name may be None/empty/"all", in which case the flat item_slot is
    always returned, since there's no specific class to resolve against.
    """
    if class_name and class_name != "all" and per_class_slot:
        override = per_class_slot.get(class_name.lower())
        if override:
            return override
    return item_slot


@dataclass
class ItemInfo:
    """
    Structured record of the schema metadata we store for each item.

    Uses Python's dataclass decorator, which automatically generates an
    __init__ method from the field annotations — no manual constructor needed.

    All instances are created by build_index() from parsed schema data.
    The 'field(default_factory=list)' syntax for 'classes' creates a new
    empty list for each instance rather than sharing one list object across
    all instances (a common Python gotcha with mutable defaults).
    """
    name: str                # Friendly display name as it appears in-game
    equip_region: str = ""   # Body area the item occupies on the player character
    hides_head: bool = False # True = this item replaces the player's default head
    classes: list = field(default_factory=list)  # Which character classes can use it
    item_type: str = "unknown"   # "cosmetic", "weapon", or "unknown"
    item_slot: str = ""          # Loadout slot ("primary", "head", "misc", etc.)
    animation_risk: bool = False # True for melee weapons — different animation rig
                                 # from other weapon types; cross-slot swaps can
                                 # cause the character to hold the item incorrectly
    per_class_slot: dict = field(default_factory=dict)
    # Per-class loadout slot overrides, e.g. {"engineer": "primary",
    # "soldier": "secondary"} for the Shotgun. Some weapons are shared
    # across classes but sit in a different slot for each — item_slot above
    # is only the schema's flat/default value (see _per_class_slot_overrides()
    # for where this dict comes from and resolve_class_slot() for how to use
    # it). Empty for items with no per-class slot variance, which is most of
    # them — callers should fall back to item_slot in that case.


def _need_vdf():
    """
    Return the 'vdf' Python library, installing it automatically if needed.

    VDF (Valve Data Format), also called KeyValues, is a simple text format
    Valve uses for many game configuration files. It looks like this:
        "key"
        {
            "subkey"  "value"
        }

    The 'vdf' library (by ValvePython) parses VDF text into Python dicts.
    It is imported lazily here so it can be auto-installed on first run,
    consistent with how the 'vpk' library is handled in tf2_core.py.
    """
    try:
        import vdf
        return vdf
    except ImportError:
        import sys, subprocess
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "vdf", "--no-warn-script-location"],
            check=True
        )
        import vdf
        return vdf


def load_schema(tf2_path):
    """
    Read and parse items_game.txt from the game's scripts/items/ folder.

    items_game.txt is a large Valve KeyValues text file (~550,000 lines) that
    defines every item available in TF2: weapons, cosmetics, and various
    internal items. For each item it stores the display name, which character
    classes can use it, what area of the player model it occupies, where its
    3D model files are located, and many other properties.

    Returns the raw parsed Python dict. This is large and slow to query directly
    — call build_index() on the result to get a fast lookup table.
    """
    vdf = _need_vdf()
    igt = os.path.join(tf2_path, "scripts", "items", "items_game.txt")
    if not os.path.isfile(igt):
        raise FileNotFoundError(f"items_game.txt not found at {igt}")
    
    # Security check: refuse to load oversized files (DoS protection)
    size = os.path.getsize(igt)
    if size > MAX_SCHEMA_SIZE:
        # Import SwapError from tf2_core if available, otherwise use generic Exception
        try:
            from tf2_core import SwapError
        except ImportError:
            SwapError = Exception
        raise SwapError(
            f"Schema file too large ({size / 1024 / 1024:.1f}MB). "
            f"Maximum allowed is {MAX_SCHEMA_SIZE / 1024 / 1024:.0f}MB. "
            "This may indicate a corrupted or malicious file."
        )
    
    with open(igt, encoding="utf-8", errors="replace") as f:
        return vdf.loads(f.read())


def _deep_merge(base, overlay):
    """
    Recursively merge two dicts, with overlay values taking precedence over base.
    Returns a new dict — neither input dict is modified.

    For keys where both sides hold a dict value, those dicts are merged
    recursively. For any other value type, the overlay wins.

    Used by _resolve_prefabs() to layer inherited default properties onto items,
    then let the item's own explicit properties override those defaults.
    """
    out = dict(base)
    for k, v in overlay.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            # Both sides are dicts — merge them recursively rather than replacing
            out[k] = _deep_merge(out[k], v)
        else:
            # Overlay value wins for all non-dict types
            out[k] = v
    return out


def _resolve_prefabs(item, prefabs, _seen=None):
    """
    Resolve an item's inherited properties through TF2's prefab system.

    Background: TF2's item schema uses 'prefabs' as a form of property
    inheritance. Rather than repeating the same properties (such as which
    body area an item occupies, or which character classes can use it) for
    every individual item, Valve defines shared templates called 'prefabs'
    and items reference them by name.

    An item's 'prefab' field is a space-separated list of prefab names. Each
    prefab can itself inherit from other prefabs, forming a chain. Properties
    flow from the most-base prefab upward, with each level able to override
    inherited values, and the item's own explicit properties taking final
    precedence over everything inherited.

    Example chain:
        item has prefab "scout_wearable_misc"
        "scout_wearable_misc" has prefab "wearable_misc"
        "wearable_misc" has prefab "wearable"
        "wearable" has equip_region "hat"
        -> item inherits equip_region "hat" unless it explicitly overrides it

    The _seen set prevents infinite loops in case a prefab accidentally
    references itself or creates a circular chain in the schema data.
    """
    if _seen is None:
        _seen = set()

    prefab_names = item.get("prefab", "")
    if not prefab_names:
        # This item has no prefab — return its properties as-is
        return dict(item)

    merged = {}
    for pname in prefab_names.split():
        if pname in _seen or pname not in prefabs:
            continue  # Skip: already processed (cycle protection) or doesn't exist
        _seen.add(pname)
        # Recursively resolve this prefab's own inheritance chain first
        resolved_prefab = _resolve_prefabs(prefabs[pname], prefabs, _seen)
        merged = _deep_merge(merged, resolved_prefab)

    # Item's own explicit properties always override anything inherited
    return _deep_merge(merged, item)


def _model_stems(resolved):
    """
    Extract model file path stems from a resolved item definition.

    A 'stem' is a file path with no extension and no leading slash, normalised
    to lowercase with forward slashes — matching the format used inside VPK
    archives and our lookup index.
    Example: 'models/player/items/scout/some_hat' (no .mdl extension)

    Items in the schema reference their 3D model in one of two ways:

    1. model_player: a single path used for all character classes
       e.g. "models/player/items/all_class/balloon_hat"

    2. model_player_per_class: per-character-class paths, in one of two sub-formats:
       a) Template format (newer): a 'basename' string with '%s' as a placeholder
          for the class name, expanded for each class that can use the item
          e.g. basename "models/player/items/%s/fancy_hat" with classes [scout, pyro]
               -> "models/player/items/scout/fancy_hat"
                  "models/player/items/pyro/fancy_hat"
       b) Explicit format (older): individual key-value pairs per class
          e.g. "scout" "models/player/items/scout/fancy_hat_scout"
               "pyro"  "models/player/items/pyro/fancy_hat_pyro"

    All paths are normalised: backslashes to forward slashes, lowercase, .mdl stripped.
    """
    stems = []

    # Single shared model for all classes
    mp = resolved.get("model_player")
    if mp:
        stems.append(mp)

    # Per-class models
    per = resolved.get("model_player_per_class")
    if isinstance(per, dict):
        basename = per.get("basename")
        if basename and "%s" in basename:
            # Template format: expand %s with each class name
            classes = list(resolved.get("used_by_classes", {}).keys())
            for c in classes:
                stems.append(basename.replace("%s", c))
        else:
            # Explicit format: each key is a class name, value is the model path
            for k, v in per.items():
                if k != "basename" and isinstance(v, str):
                    stems.append(v)

    # Normalise all paths to the standard index format
    out = []
    for s in stems:
        s = s.replace("\\", "/").lower()
        if s.endswith(".mdl"):
            s = s[:-4]
        out.append(s)
    return out


def _item_type(resolved):
    """
    Determine whether an item is a weapon, cosmetic, or unknown.

    The item's loadout slot name is the primary indicator. Items with a model
    path but no recognised slot are conservatively classified as cosmetics —
    this handles unusual internal items that don't fit neatly into either
    category but still have a visual representation.
    """
    slot = resolved.get("item_slot", "").lower()
    if slot in WEAPON_SLOTS:
        return "weapon"
    if slot in COSMETIC_SLOTS:
        return "cosmetic"
    # Has a model path but no recognised slot — treat as cosmetic (safe fallback)
    if resolved.get("model_player") or resolved.get("model_player_per_class"):
        return "cosmetic"
    return "unknown"


def _hides_head(resolved):
    """
    Determine whether an item replaces the player character's default head model.

    Background: some cosmetic items in TF2 (full helmets, character head
    replacements) are designed to completely replace the player's default head
    geometry. When one of these items is equipped, the game hides the player's
    normal head so the two don't overlap visually.

    If a model that replaces the head is swapped onto a cosmetic slot that does
    NOT hide the head, both the replacement model and the player's default head
    will render simultaneously and visually overlap (called 'clipping').

    Two mechanisms in the schema can indicate head replacement:

    1. equip_region / equip_regions: a text field (or block of fields for items
       that occupy multiple regions) naming which body area the item occupies.
       Head-replacement items always have a region name containing 'head_replacement'
       (the exact name varies by class, e.g. 'pyro_head_replacement').

    2. player_bodygroups: some items use a different mechanism — they directly
       manipulate a 'bodygroup', which is a named visibility toggle on the 3D
       player model. Setting the 'head' bodygroup to hidden achieves the same
       visual effect as an equip region head replacement.

    Both mechanisms are checked to avoid false negatives.
    """
    region = resolved.get("equip_region", "")
    regions = resolved.get("equip_regions", {})  # Some items use a block for multiple regions
    region_names = [region] + (list(regions.keys()) if isinstance(regions, dict) else [])

    # Check for head replacement region name (always contains 'head_replacement')
    if any("head_replacement" in r for r in region_names if r):
        return True

    # Check for direct bodygroup manipulation that hides the head
    bg = resolved.get("visuals", {}).get("player_bodygroups", {})
    if isinstance(bg, dict) and "head" in bg:
        return True

    return False


def build_index(schema):
    """
    Build a fast lookup index from the parsed items_game.txt schema.

    Iterates over every item definition, resolves inherited prefab properties,
    extracts the fields we care about, and maps each model file path stem to an
    ItemInfo record.

    The resulting index is a plain Python dict: {stem: ItemInfo}
    where 'stem' is a lowercase, extension-free model path matching the format
    used inside VPK archives. This makes lookup() an O(1) dict lookup rather
    than an O(n) scan through thousands of items.

    Items without a name or model path are silently skipped — the schema contains
    many internal bookkeeping entries that do not correspond to actual in-game items.
    """
    root = schema["items_game"]
    prefabs = root.get("prefabs", {})
    items = root["items"]

    index = {}
    for defidx, item in items.items():
        # Skip internal schema entries that aren't actual game items
        if not isinstance(item, dict) or "name" not in item:
            continue

        # Merge the item's own properties with everything it inherits from prefabs
        resolved = _resolve_prefabs(item, prefabs)

        info = ItemInfo(
            name=item.get("name", "?"),
            equip_region=resolved.get("equip_region", ""),
            hides_head=_hides_head(resolved),
            classes=list(resolved.get("used_by_classes", {}).keys()),
            item_slot=resolved.get("item_slot", "").lower(),
            item_type=_item_type(resolved),
            # Melee weapons use a distinct animation control rig from other weapon
            # types. Swapping a non-melee model into a melee slot (or vice versa)
            # can cause the character to hold the weapon at the wrong angle or
            # play the wrong animations.
            animation_risk=resolved.get("item_slot", "").lower() == "melee",
            per_class_slot=_per_class_slot_overrides(resolved),
        )

        # Map every model path stem for this item to the same ItemInfo object
        for stem in _model_stems(resolved):
            index[stem] = info

    return index


def build_defindex_index(schema):
    """
    Build a {defindex: {...}} lookup, the mirror image of build_index().

    build_index() maps model path -> item metadata, which is what the normal
    keyword-search flow needs (the user names a model, we look up details
    about it). This function maps the other direction: numeric item
    definition index -> model path stem(s) and metadata, which is what's
    needed when starting from a Steam inventory item (which has a defindex,
    but no model path) and working out what that item actually is and where
    its model files live.

    Returns: {defindex (int): {"name": str, "item_type": str, "item_slot": str,
                               "stems": [str, ...], "classes": [str, ...],
                               "per_class_slot": {str: str, ...}}}

    Items with a name but no model path (e.g. some tools, currency items)
    are skipped — they have nothing to swap with as either a source or
    target, so there is no use including them here.

    Stricter than build_index() in one respect: an item is only included if
    it has a genuinely recognised loadout slot (WEAPON_SLOTS or
    COSMETIC_SLOTS). build_index() falls back to guessing "cosmetic" for
    anything with a model and no recognised slot, because that guess is
    harmless when it's only ever reached after a specific keyword search
    (nobody searches "tour of duty badge" looking for a hat). Own-inventory
    mode lists everything the player owns at once though, and that same
    lenient guess turns into visible junk in the list — crates, passes, and
    badges all have a backpack icon model, so the fallback was calling them
    "cosmetic" too. Requiring a real slot here filters those out without
    touching build_index()'s behaviour anywhere else.

    Shares the same prefab-resolution and stem-extraction logic as
    build_index(), so the two stay consistent with each other as the
    schema's prefab system evolves.
    """
    root = schema["items_game"]
    prefabs = root.get("prefabs", {})
    items = root["items"]

    index = {}
    for defidx, item in items.items():
        if not isinstance(item, dict) or "name" not in item:
            continue
        try:
            d = int(defidx)
        except ValueError:
            continue  # the "default" entry and similar non-numeric keys

        resolved = _resolve_prefabs(item, prefabs)
        stems = _model_stems(resolved)
        if not stems:
            continue  # no model — not usable as a swap source or target

        item_slot = resolved.get("item_slot", "").lower()
        if item_slot not in WEAPON_SLOTS and item_slot not in COSMETIC_SLOTS:
            continue  # no genuine loadout slot — likely a badge/crate/pass, not wearable gear

        index[d] = {
            "name": item.get("name", "?"),
            "item_type": _item_type(resolved),
            "item_slot": item_slot,
            "stems": stems,
            # Needed for weapon class filtering (see match_owned_items() in
            # tf2_core.py) — weapon model paths aren't organised into
            # class-named folders the way cosmetics are, so class filtering
            # for weapons has to go via the schema's allowed-classes list
            # instead of path matching.
            "classes": list(resolved.get("used_by_classes", {}).keys()),
            # Per-class loadout slot overrides — see _per_class_slot_overrides().
            # item_slot above is only the flat/default value; some weapons
            # (the Shotgun, confirmed against a real items_game.txt) sit in
            # a different slot per class and need this to filter correctly.
            "per_class_slot": _per_class_slot_overrides(resolved),
        }

    return index


def lookup(index, model_path):
    """
    Look up an item's metadata in the index by its model file path.

    Accepts paths in any format — with or without .mdl extension, forward or
    backslashes, any capitalisation — and normalises them before looking up.
    Returns the ItemInfo record if found, or None if the path is not in the index
    (which is normal for internal/unlisted items and for VPK-only models).
    """
    s = model_path.replace("\\", "/").lower()
    if s.endswith(".mdl"):
        s = s[:-4]
    return index.get(s)


def clip_warning(source_info, target_info):
    """
    Return a warning string if swapping source onto target may cause visual clipping.
    Returns None if the swap appears safe.

    'Clipping' in 3D graphics refers to two separate objects occupying the same
    space and visually overlapping — one appears to pass through the other.
    In TF2, this is a cosmetic issue (it looks wrong but does not affect gameplay).

    Two cases are checked, in order of severity:

    1. Head replacement conflict: the source item replaces the player's head model,
       but the target slot does not hide the player's default head. When both are
       active simultaneously, the replacement head and the default head overlap.
       This is a high-confidence warning — the outcome is always visually wrong.

    2. Equip region mismatch: the source and target items are designed for different
       areas of the player character model (e.g. a hat swapped onto a neck item slot).
       Items designed for one body region may extend into space occupied by items in
       adjacent regions. This is a lower-confidence warning — whether actual clipping
       occurs depends on the specific items and the player's other equipped items.

    Both source_info and target_info must be non-None for warnings to be generated.
    If either is None (item not in schema), the function returns None — we do not
    warn when we lack the data to make a confident assessment.
    """
    if not (source_info and target_info):
        return None

    # Case 1: head-replacement model swapped onto a non-head-hiding slot
    if source_info.hides_head and not target_info.hides_head:
        return (f"'{source_info.name}' replaces the head, but "
                f"'{target_info.name}' doesn't hide the default head — "
                f"it will clip through. An over-the-head model would fit better.")

    # Case 2: items occupy different areas of the player character model
    src_region = source_info.equip_region
    tgt_region = target_info.equip_region
    if src_region and tgt_region and src_region != tgt_region:
        return (f"'{source_info.name}' uses the '{src_region}' equip region "
                f"but '{target_info.name}' uses '{tgt_region}' — "
                f"these cover different areas and may clip with other equipped items.")

    return None


def weapon_swap_warning(source_info, target_info):
    """
    Return a warning string if swapping source onto target may cause weapon issues.
    Returns None if the swap appears safe.

    The primary check is loadout slot mismatch. TF2 weapons are categorised into
    loadout slots (primary, secondary, melee, etc.), and each slot uses a different
    animation rig — the system that controls how the player character holds and
    operates the weapon. Swapping a weapon model across slot boundaries (e.g.
    putting a primary weapon's model into the melee slot) can cause the character
    to hold it at the wrong position or play the wrong animations.

    This is a visual issue, not a game-breaking one, but it is worth flagging
    so the user can make an informed decision before building the swap.
    """
    if source_info and target_info:
        src_slot = source_info.item_slot or "unknown"
        tgt_slot = target_info.item_slot or "unknown"
        if src_slot != tgt_slot:
            return (f"'{source_info.name}' is a {src_slot} weapon "
                    f"but '{target_info.name}' is {tgt_slot} — "
                    f"slot mismatch may cause animation or behaviour issues.")
    return None


# ---------- schema cache ----------
# Parsing items_game.txt from scratch takes several seconds because it is a
# very large file. To avoid this delay on every run, we serialise the parsed
# index to a JSON file and reload it on subsequent runs.
#
# The cache stores the file modification time (mtime) of items_game.txt
# alongside the index data. On load, we compare the stored mtime with the
# current mtime — if they differ, the game has updated its item definitions
# and we rebuild the cache from scratch.

# Bump whenever ItemInfo's fields change shape (new/removed fields). The
# cache check below discards anything saved under an older version
# automatically — same pattern as _DEFINDEX_CACHE_FORMAT_VERSION. Added
# retroactively: this cache previously had no version guard at all, only
# the mtime check, so a code change to ItemInfo's fields (such as adding
# per_class_slot) would silently keep loading old entries missing that
# field from a still-valid-by-mtime cache, rather than rebuilding.
_SCHEMA_CACHE_FORMAT_VERSION = 2


def _index_to_dict(index):
    """
    Serialise the {stem: ItemInfo} index to a plain dict suitable for JSON export.

    Uses getattr with default values rather than direct attribute access, so that
    index entries built with an older version of ItemInfo (missing newer fields)
    do not cause errors during serialisation.
    """
    return {
        stem: {
            "name": info.name,
            "equip_region": info.equip_region,
            "hides_head": info.hides_head,
            "classes": info.classes,
            "item_slot": getattr(info, "item_slot", ""),
            "item_type": getattr(info, "item_type", ""),
            "animation_risk": getattr(info, "animation_risk", False),
            "per_class_slot": getattr(info, "per_class_slot", {}),
        }
        for stem, info in index.items()
    }


def _dict_to_index(data):
    """
    Deserialise a JSON-loaded dict back to a {stem: ItemInfo} index.

    Uses .get() with safe defaults throughout so that cache files written by
    an older version of the tool (which may lack newer fields) load without
    errors — missing fields simply get their default values.
    """
    index = {}
    for stem, d in data.items():
        index[stem] = ItemInfo(
            name=d.get("name", "?"),
            equip_region=d.get("equip_region", ""),
            hides_head=d.get("hides_head", False),
            classes=d.get("classes", []),
            item_slot=d.get("item_slot", ""),
            item_type=d.get("item_type", "unknown"),
            animation_risk=d.get("animation_risk", False),
            per_class_slot=d.get("per_class_slot", {}),
        )
    return index


def save_schema_cache(index, items_game_path, cache_path):
    """
    Serialise the parsed index to a JSON file alongside the current mtime
    and the cache format version. Creates the cache directory if it does
    not already exist. Failures are silently ignored — the tool works
    without a cache, just slower.
    """
    try:
        mtime = os.path.getmtime(items_game_path)
        payload = {
            "mtime": mtime,
            "format_version": _SCHEMA_CACHE_FORMAT_VERSION,
            "index": _index_to_dict(index),
        }
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
    except Exception:
        pass  # Non-fatal — tool still works, just rebuilds from scratch next run


def load_schema_cache(items_game_path, cache_path):
    """
    Load the cached index if it is still valid.

    Two things must match for the cache to be used: the items_game.txt
    mtime (a mismatch means the game updated its item definitions and the
    cache must be rebuilt), and the cache format version (a mismatch means
    this version of the tool stores different/additional fields per item
    than whatever wrote the cache, e.g. per_class_slot being added — see
    _SCHEMA_CACHE_FORMAT_VERSION above).

    Also returns None if the cache file is missing, unreadable, or corrupted.
    """
    if not os.path.isfile(cache_path):
        return None
    
    # Security check: refuse to load oversized cache files (cache poisoning protection)
    try:
        size = os.path.getsize(cache_path)
        if size > MAX_CACHE_SIZE:
            # Corrupted or poisoned cache — delete it and regenerate
            os.remove(cache_path)
            return None
    except Exception:
        return None
    
    try:
        mtime = os.path.getmtime(items_game_path)
        with open(cache_path, encoding="utf-8") as f:
            payload = json.load(f)
        if payload.get("mtime") != mtime:
            # Schema has changed since the cache was written — rebuild required
            return None
        if payload.get("format_version") != _SCHEMA_CACHE_FORMAT_VERSION:
            # Older/newer tool version wrote this cache — fields may not match
            return None
        return _dict_to_index(payload["index"])
    except Exception:
        # Corrupt or otherwise unreadable cache — return None to trigger rebuild
        return None


# Bump this whenever build_defindex_index()'s output shape changes (new or
# removed fields per entry). The cache check below discards anything saved
# under an older version automatically, so a structural change here never
# needs the user to manually delete the cache folder — it just rebuilds
# once on the first run after the change.
_DEFINDEX_CACHE_FORMAT_VERSION = 4


def save_defindex_cache(defindex_index, items_game_path, cache_path):
    """
    Save the {defindex: {...}} index to a JSON cache file, same approach as
    save_schema_cache() but for build_defindex_index()'s output. Kept as a
    separate cache file (rather than merged into the existing one) so the
    two stay independent — own-inventory mode is an optional feature, and a
    user who never uses it never pays the cost of building or storing this.
    """
    try:
        mtime = os.path.getmtime(items_game_path)
        # JSON object keys must be strings — defindex_index uses int keys
        payload = {
            "mtime": mtime,
            "format_version": _DEFINDEX_CACHE_FORMAT_VERSION,
            "index": {str(k): v for k, v in defindex_index.items()},
        }
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
    except Exception:
        pass  # Non-fatal — tool works without a cache, just rebuilds next run


def load_defindex_cache(items_game_path, cache_path):
    """
    Load the cached {defindex: {...}} index if still valid.

    Two things must match for the cache to be used: the items_game.txt
    mtime (same staleness check as load_schema_cache()), and the cache
    format version (see _DEFINDEX_CACHE_FORMAT_VERSION above) — this second
    check means a code change to what build_defindex_index() stores per
    entry self-invalidates old caches automatically, rather than silently
    loading entries that are missing a field the new code expects.

    Returns None if missing, stale, wrong format version, or unreadable.
    """
    if not os.path.isfile(cache_path):
        return None
    
    # Security check: refuse to load oversized cache files (cache poisoning protection)
    try:
        size = os.path.getsize(cache_path)
        if size > MAX_CACHE_SIZE:
            # Corrupted or poisoned cache — delete it and regenerate
            os.remove(cache_path)
            return None
    except Exception:
        return None
    
    try:
        mtime = os.path.getmtime(items_game_path)
        with open(cache_path, encoding="utf-8") as f:
            payload = json.load(f)
        if payload.get("mtime") != mtime:
            return None
        if payload.get("format_version") != _DEFINDEX_CACHE_FORMAT_VERSION:
            return None
        # Convert string keys back to int defindexes
        return {int(k): v for k, v in payload["index"].items()}
    except Exception:
        return None


# ---------- self-test ----------
# When this file is run directly (python3 tf2_schema.py /path/to/items_game.txt),
# it parses the given file and prints a summary of every indexed item.
# Useful for verifying the parser is working correctly against a real schema file.
if __name__ == "__main__":
    import sys, vdf
    path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/real_sample.txt"
    with open(path, encoding="utf-8", errors="replace") as f:
        schema = vdf.loads(f.read())
    idx = build_index(schema)
    print(f"Indexed {len(idx)} model paths\n")
    for stem, info in idx.items():
        print(f"  {info.name}")
        print(f"    stem: {stem}")
        print(f"    region: {info.equip_region}  hides_head: {info.hides_head}  classes: {info.classes}")
