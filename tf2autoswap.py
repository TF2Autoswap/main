#!/usr/bin/env python3
"""
TF2autoswap — swap any TF2 cosmetic or weapon model for another, client-side.
Creates a VPK archive ready to load with the Casual Preloader.

Developed with: AI assistance via OpenRouter
Project : https://github.com/TF2Autoswap/autoswap
License : GPL v3 — see LICENSE for details

--- What this file does ---
This is the user interface layer of TF2autoswap. It handles all interaction
with the user: displaying menus, reading input, showing results, and routing
to the correct core function. It contains no business logic of its own — all
file reading, patching, and archive construction is handled by tf2_core.py.

--- How to use ---
Interactive menu (guided step-by-step):
    python3 tf2autoswap.py

Non-interactive swap (command line):
    python3 tf2autoswap.py <source_keyword> <target_keyword> [--filter pyro] [--out path]

Import a mod from disk (e.g. downloaded from Gamebanana):
    python3 tf2autoswap.py --import /path/to/mod/models/.../thing.mdl <target_keyword>

    Works for cosmetics, weapons, and props. For weapons, point --import at
    the viewmodel (c_*.mdl) — the worldmodel, if any, is auto-detected
    alongside it (see core.find_disk_weapon_worldmodel()); add --weapon.
    For props, add --prop. Any custom materials found are run through the
    same safety check as the dedicated skin-swap tool before being bundled
    (see tf2_material.py) — this applies regardless of swap type.

Other commands:
    --list             search the game's items without building anything
    --list-mods        list the mods you have built
    --list-installed   list addons in the Casual Preloader folder
    --debug-inventory  diagnose why items in an inventory JSON file aren't
                       matching as swap sources (see imports/inventory/)
    --skin             skin / material swap (interactive only — see
                       tf2_material.py for the non-optional safety layer)
    --prop             map prop model swap; alone it opens an interactive
                       picker, or pair with source/target keywords for
                       scripted use, e.g. tf2autoswap.py crate barrel --prop
    --preloader PATH   set the Casual Preloader addons folder path
    --tf2 PATH         set the TF2 installation tf/ directory path

Requires tf2_core.py in the same directory. Friendly item names and safety
warnings also require tf2_schema.py and the 'vdf' library (both optional —
the tool still works without them, but shows internal path names instead of
friendly names and cannot warn about problematic swaps). Skin/material swaps
and map prop swaps additionally require tf2_material.py — optional in the
same way; without it, menu options (skin and prop swaps)
and CLI flags simply don't appear, and the rest of the
tool runs exactly as before.
"""

# Standard library imports — all built into Python, no installation required
import os, sys, re, argparse, difflib, logging, subprocess, json

# tf2_core handles all file operations and archive building.
# Keeping it separate means any future GUI can use it directly without
# pulling in this CLI-specific code.
import tf2_core as core

# tf2_schema is optional. Without it, the tool still works but shows internal
# model path names instead of friendly item names, and cannot check for
# potentially problematic swaps. The HAVE_SCHEMA flag lets every function
# that uses schema data degrade gracefully when it is unavailable.
try:
    import tf2_schema
    HAVE_SCHEMA = True
except ImportError:
    HAVE_SCHEMA = False

# tf2_material adds the skin/material swap engine and its non-optional safety
# layer (see that module's docstring for why the safety layer exists and what
# it refuses). Optional like the schema: if it's missing, the skin and prop
# swap menu options are hidden and the rest of the tool runs unchanged.
try:
    import tf2_material as material
    HAVE_MATERIAL = True
except ImportError:
    HAVE_MATERIAL = False


# ---------- branding / paths ----------

PROJECT = "TF2autoswap"
VERSION = "4.8"

# One-line description of what changed in this release. Shown in the
# interactive menu header so returning users can see at a glance what is new.
# Update this string with each release.
WHATS_NEW = "Skin/material swaps + prop size checking + security hardening + organised imports"

# A unique string appended to every output filename. This makes files created
# by this tool identifiable in the Casual Preloader's addons folder and
# distinguishable from mods created by other tools.
SIGNATURE = "_TF2autoswap"

# The directory containing this script. Used as the base for all tool-relative
# paths below, making the tool fully portable — it can be moved anywhere and
# all paths remain correct relative to its location.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Hidden state directory: stores the user acknowledgement flag file and the
# item schema cache. Kept separate from the output folder so internal tool
# state is not mixed with user-created mod files.
# Named with a leading dot (dotfolder convention) — hidden by default on
# Linux and macOS. The Windows hidden attribute is set explicitly by
# _hide_on_windows() at startup.
STATE_DIR = os.path.join(_SCRIPT_DIR, ".tf2autoswap")

# Where built VPK output files are saved. This folder is NOT created at
# startup — it is created only on the first actual build, so a fresh
# installation has a clean, minimal folder structure.
OUTPUT_DIR = os.path.join(_SCRIPT_DIR, "output")

# Where users drop mod files for import. Created at startup with organised
# subdirectories so users have a clear, consistent location for their mods.
IMPORTS_DIR = os.path.join(_SCRIPT_DIR, "imports")

# The subfolder structure within IMPORTS_DIR.
# Each subdirectory corresponds to a type of asset the tool can import.
# 'props' is created now even though map prop support is not yet implemented —
# it reserves the location for a future release and makes the intended
# structure visible to users from the start.
IMPORT_SUBDIRS = [
    "cosmetics",
    os.path.join("weapons", "viewmodel"),
    os.path.join("weapons", "worldmodel"),
    os.path.join("weapons", "materials"),
    "props",
    "inventory",
]

# Where own-inventory mode looks for a user-dropped inventory JSON export,
# and where its accompanying how-to guide lives. This is a plain folder the
# user places their own file into themselves — the tool only ever reads
# from it, never writes inventory data into it, and nothing here is ever
# sent anywhere. See load_owned_items_interactive() / write_inventory_guide().
INVENTORY_IMPORT_DIR = os.path.join(IMPORTS_DIR, "inventory")
INVENTORY_GUIDE_PATH = os.path.join(INVENTORY_IMPORT_DIR, "HOW_TO_GET_YOUR_INVENTORY.txt")

# Default installation path for the Casual Preloader's addons folder on Linux.
# The Casual Preloader is a third-party mod manager for TF2 that loads mods at
# game launch. Users on other platforms or with non-standard installations can
# override this with --preloader.
PRELOADER_ADDONS = os.path.expanduser("~/.local/share/casual-pre-loader/mods/addons")

# Log file location. Sits alongside the scripts so the entire tool folder is
# self-contained and portable (zip the folder and everything moves with it).
LOG_PATH = os.path.join(_SCRIPT_DIR, "tf2autoswap.log")

# Module-level logger. Configured by setup_logging() at startup, but declared
# here so all functions can reference it at module import time without errors.
log = logging.getLogger(PROJECT)


# ---------- logging ----------

def setup_logging():
    """
    Configure file-based logging for error tracking and build history.
    Failures are silently ignored — a broken log path should never prevent
    the tool from running. The log records what mods were built, any errors
    that occurred, and when the user accepted the risk acknowledgement.
    """
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        logging.basicConfig(
            filename=LOG_PATH, level=logging.INFO,
            format="%(asctime)s  %(levelname)s  %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    except Exception:
        pass  # Non-fatal — tool runs correctly without a log file
    return logging.getLogger(PROJECT)


# ---------- naming helpers (presentation) ----------

# The schema cache is stored in the hidden state directory so it is not visible
# alongside the user's built mod files in the output folder.
SCHEMA_CACHE_PATH = os.path.join(STATE_DIR, "schema_cache.json")


def load_index(tf2_path):
    """
    Load the item name index from cache, or build it fresh from the schema file.

    The item schema (items_game.txt) defines every item's friendly name and
    metadata. Parsing it takes several seconds, so a JSON cache is kept in the
    hidden state directory. The cache is checked first — if TF2 has not been
    updated since the cache was written (checked via file modification time),
    the cached version is returned immediately.

    If no valid cache exists, the schema is parsed fresh and a new cache is saved.
    Either way, the result is an index dict: {model_path_stem: ItemInfo}.

    Failures at any stage are non-fatal — the tool still works without friendly
    names, it just shows internal path names instead.
    Returns the index dict, or None if the schema is unavailable.
    """
    if not HAVE_SCHEMA:
        print("(tf2_schema.py not found — friendly names and swap warnings off)")
        return None
    try:
        items_game_path = os.path.join(tf2_path, "scripts", "items", "items_game.txt")
        cached = tf2_schema.load_schema_cache(items_game_path, SCHEMA_CACHE_PATH)
        if cached is not None:
            print("Loading item names (cached)...")
            return cached
        # No valid cache — parse from scratch and save a new cache
        print("Loading item names (first run, this may take a moment)...")
        index = tf2_schema.build_index(tf2_schema.load_schema(tf2_path))
        tf2_schema.save_schema_cache(index, items_game_path, SCHEMA_CACHE_PATH)
        return index
    except Exception as e:
        print(f"(Item names unavailable: {e})")
        log.warning(f"Schema load failed: {e}")
        return None


DEFINDEX_CACHE_PATH = os.path.join(STATE_DIR, "defindex_cache.json")


def load_defindex_index(tf2_path):
    """
    Load the {defindex: {...}} index from cache, or build it fresh.

    Mirrors load_index() exactly, but for build_defindex_index() — the
    direction needed by own-inventory mode (defindex -> model path), rather
    than the keyword-search direction (model path -> friendly name) that
    load_index() serves. Kept as a fully separate function and cache file:
    own-inventory mode is optional, so a user who never uses it never builds
    or stores this index.

    Returns the index dict, or None if the schema is unavailable.
    """
    if not HAVE_SCHEMA:
        print("(tf2_schema.py not found — own-inventory mode unavailable)")
        return None
    try:
        items_game_path = os.path.join(tf2_path, "scripts", "items", "items_game.txt")
        cached = tf2_schema.load_defindex_cache(items_game_path, DEFINDEX_CACHE_PATH)
        if cached is not None:
            return cached
        index = tf2_schema.build_defindex_index(tf2_schema.load_schema(tf2_path))
        tf2_schema.save_defindex_cache(index, items_game_path, DEFINDEX_CACHE_PATH)
        return index
    except Exception as e:
        print(f"(Own-inventory mode unavailable: {e})")
        log.warning(f"Defindex index load failed: {e}")
        return None



def display_name(path_or_stem, index):
    """
    Return the friendly display name for an item, given its model path.
    Falls back to the filename stem (e.g. 'c_scattergun') if the schema
    does not have an entry for this path.
    Used in filenames and summary lines where no extra decoration is needed.
    """
    base = os.path.basename(path_or_stem)
    if base.endswith(".mdl"):
        base = base[:-4]
    if index and HAVE_SCHEMA:
        info = tf2_schema.lookup(index, path_or_stem)
        if info:
            return info.name
    return base


def label_for(mdl_path, index):
    """
    Return a decorated label for a cosmetic item suitable for menu display.
    Format: 'The Towering Pillar of Hats  (towering_pillar_of_hats)  [replaces head]'

    The filename stem in parentheses helps users distinguish items with similar
    friendly names. The '[replaces head]' tag (shown when applicable) gives an
    early visual warning that this item replaces the character's head model,
    so the user can anticipate potential clipping before selecting it.
    Falls back to the filename stem if schema data is unavailable.
    """
    base = os.path.basename(mdl_path)[:-4]
    if index and HAVE_SCHEMA:
        info = tf2_schema.lookup(index, mdl_path)
        if info:
            tag = "  [replaces head]" if info.hides_head else ""
            return f"{info.name}  ({base}){tag}"
    return base


def label_for_weapon(mdl_path, index):
    """
    Return a decorated label for a weapon suitable for menu display.
    Format: 'Scattergun  (c_scattergun)  [primary]'

    The loadout slot tag in brackets lets the user verify they are picking from
    the right category before confirming, without needing to know the item schema.
    Falls back to the filename stem if schema data is unavailable.
    """
    base = os.path.basename(mdl_path)[:-4]
    if index and HAVE_SCHEMA:
        info = tf2_schema.lookup(index, mdl_path)
        if info:
            slot_tag = f"  [{info.item_slot}]" if info.item_slot else ""
            return f"{info.name}  ({base}){slot_tag}"
    return base


def fmt_size(n):
    """Format a byte count as a human-readable size string (bytes/KB/MB)."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f} MB"
    if n >= 1_000:
        return f"{n / 1_000:.1f} KB"
    return f"{n} bytes"


def normalize_keyword(kw):
    """
    Normalise a search keyword to match the naming style used in archive paths.

    Three transformations are applied:
    - Lowercase: archive paths are lowercase, so comparison must be too
    - Spaces to underscores: TF2 uses underscores as word separators in paths
    - Punctuation stripped: apostrophes and similar characters are removed so
      that "crusader's" matches "crusaders" in the archive path

    Examples:
        "Crusader's Crossbow" -> "crusaders_crossbow"
        "Head Full of Hot Air" -> "head_full_of_hot_air"
    """
    kw = kw.lower().strip()
    kw = kw.replace(" ", "_")
    kw = re.sub(r"[^a-z0-9_]", "", kw)
    return kw


def _did_you_mean(kw, stems, n=3, cutoff=0.4):
    """
    Return a list of close matches for a keyword, for typo correction suggestions.

    Uses Python's difflib.get_close_matches to find strings with similar
    character sequences. Before running difflib (which compares against every
    string in the list), we pre-filter to strings that share the first three
    characters of the keyword — this makes suggestions much more relevant, since
    difflib would otherwise sometimes match completely unrelated strings that
    happen to have a similar edit distance.
    Falls back to searching the full list if no strings share the prefix.
    """
    prefix = kw[:3] if len(kw) >= 3 else kw
    candidates = [s for s in stems if s.startswith(prefix)]
    if not candidates:
        candidates = stems  # Broaden to full list if prefix filter finds nothing
    return difflib.get_close_matches(kw, candidates, n=n, cutoff=cutoff)


def reverse_name_lookup(index, keyword):
    """
    Search item schema friendly names for a keyword (cosmetics only).

    This is a fallback for when a direct archive path search finds nothing.
    Users often type the in-game display name (e.g. "Head Full of Hot Air")
    rather than the internal archive path name (e.g. "hwn2015_medic_balloon_hat").
    This function searches the friendly names and returns the corresponding
    internal filename stems, which can then be used in a follow-up archive search.

    Returns a list of filename stems (not full paths) to retry the search with.
    """
    if not (index and HAVE_SCHEMA):
        return []
    kw = normalize_keyword(keyword)
    basenames = []
    seen = set()  # Deduplicate — the same filename may appear under multiple stems
    for stem, info in index.items():
        if info.item_type == "weapon":
            continue  # Cosmetics only — keep weapon and cosmetic searches separate
        if kw in normalize_keyword(info.name):
            base = os.path.basename(stem)
            if base and base not in seen:
                basenames.append(base)
                seen.add(base)
    return basenames


def reverse_name_lookup_weapon(index, keyword):
    """
    Same as reverse_name_lookup() but searches weapon items only.
    Searching weapons and cosmetics separately prevents results from one
    category contaminating searches for the other.
    """
    if not (index and HAVE_SCHEMA):
        return []
    kw = normalize_keyword(keyword)
    basenames = []
    seen = set()
    for stem, info in index.items():
        if info.item_type != "weapon":
            continue
        if kw in normalize_keyword(info.name):
            base = os.path.basename(stem)
            if base and base not in seen:
                basenames.append(base)
                seen.add(base)
    return basenames


def validate_output_path(path):
    """
    Check whether a file path is writable before attempting to build to it.

    Creates any intermediate directories needed, then writes and immediately
    deletes a small test file. This catches permission errors, paths on
    read-only filesystems, paths on drives that don't exist (Windows), and
    other OS-level issues before the tool spends time building the output.

    Returns (True, None) if the path is writable.
    Returns (False, reason_string) if it is not.
    """
    try:
        dir_path = os.path.dirname(os.path.abspath(path))
        os.makedirs(dir_path, exist_ok=True)
        test = os.path.join(dir_path, ".tf2autoswap_writetest")
        with open(test, "w") as f:
            f.write("")
        os.remove(test)
        return True, None
    except Exception as e:
        return False, str(e)


def sanitize_filename(name):
    """
    Remove characters that are illegal in filenames on Windows, or that would
    split the name across directory levels on any platform. These are the
    characters that Windows Explorer blocks in filenames, plus forward and
    backslash which are path separators.
    """
    for ch in '/\\:*?"<>|':
        name = name.replace(ch, "")
    return name.strip()


def output_filename(target_mdl, source_clean, index):
    """
    Generate the output filename for a built mod archive.
    Format: 'Target replacement mod (Source)_TF2autoswap.vpk'
    Example: 'Scattergun replacement mod (Shortstop)_TF2autoswap.vpk'

    The SIGNATURE suffix (_TF2autoswap) makes files created by this tool
    identifiable in the Casual Preloader's addons folder and distinguishable
    from mods built by other tools.
    """
    tgt = display_name(target_mdl, index)
    return sanitize_filename(f"{tgt} replacement mod ({source_clean}){SIGNATURE}.vpk")


def output_path_for(target_mdl, source_clean, index):
    """Return the full default output path for a swap (in the output directory)."""
    return os.path.join(OUTPUT_DIR, output_filename(target_mdl, source_clean, index))


def resolve_out_path(given, default_filename):
    """
    Resolve a user-provided path to a full .vpk output file path.

    If the given path is an existing directory, ends with a path separator,
    or does not end in '.vpk', the generated filename is appended to it.
    This allows users to pass a directory (e.g. ~/Desktop) and have the file
    placed there with the correct auto-generated name.
    """
    given = os.path.expanduser(given)
    if os.path.isdir(given) or given.endswith(("/", os.sep)) or not given.lower().endswith(".vpk"):
        return os.path.join(given, default_filename)
    return given


def has_invalid_path_chars(path):
    """
    Return True if the path string contains characters likely to cause problems.

    Two categories are checked:
    - Control characters (Unicode code points below 32): null bytes and other
      non-printable characters that can cause path handling to behave unexpectedly
      or silently fail on some operating systems
    - Shell metacharacters (|, &, ;, etc.): characters that have special meaning
      in command shells; if a path containing these were ever passed to a shell
      subprocess, output could be silently redirected to an unintended location

    Used to validate paths entered by the user before attempting to write to them.
    """
    shell_special = set('|&;`$><!')
    return any(ord(c) < 32 or c in shell_special for c in path)


def clip_warning(index, src_base, dst_base):
    """
    Check whether swapping source onto target may cause visual clipping,
    and return a warning string if so, or None if the swap looks safe.

    Thin wrapper around tf2_schema.clip_warning() that handles the index
    lookup and schema availability check, so callers do not need to.
    See tf2_schema.clip_warning() for full details of what is checked.
    """
    if not (index and HAVE_SCHEMA):
        return None
    return tf2_schema.clip_warning(
        tf2_schema.lookup(index, src_base),
        tf2_schema.lookup(index, dst_base),
    )


def weapon_warning(index, src_base, dst_base):
    """
    Check whether swapping source weapon onto target may cause animation issues,
    and return a warning string if so, or None if the swap looks safe.

    Thin wrapper around tf2_schema.weapon_swap_warning().
    See tf2_schema.weapon_swap_warning() for full details.
    """
    if not (index and HAVE_SCHEMA):
        return None
    return tf2_schema.weapon_swap_warning(
        tf2_schema.lookup(index, src_base),
        tf2_schema.lookup(index, dst_base),
    )


def slots_for_class(index, class_name):
    """
    Return the loadout slot names available for a given character class,
    in the standard display order.

    Used to populate the slot filter menu in the weapon swap flow so the
    user can narrow their search by slot (e.g. show only primary weapons).

    Falls back to the three universal slots (primary, secondary, melee) if
    the schema is not available. The fixed display order keeps the menu
    consistent regardless of the order slots happen to appear in the schema.
    """
    if not (index and HAVE_SCHEMA):
        return ["primary", "secondary", "melee"]
    found = set()
    for info in index.values():
        if info.item_type != "weapon":
            continue
        if class_name and class_name != "all":
            if class_name.lower() not in [c.lower() for c in info.classes]:
                continue
        effective_slot = tf2_schema.resolve_class_slot(info.item_slot, info.per_class_slot, class_name)
        if effective_slot:
            found.add(effective_slot)
    slot_order = ["primary", "secondary", "melee", "utility", "pda", "pda2", "building"]
    return [s for s in slot_order if s in found] or ["primary", "secondary", "melee"]


# ---------- build reporting ----------
# The emit_* functions are thin wrappers around the core build functions.
# Their only responsibilities are: call the right core function, print the
# results to the terminal for the user, and log what was built. Keeping build
# logic in tf2_core.py and output reporting here maintains the clean separation
# between logic and interface.

def emit_vpk(model_files, dst_base, out_vpk, material_files, src_label, target_label):
    """
    Build a cosmetic swap VPK archive and report the result to the user.
    The resulting file can be loaded by the Casual Preloader mod manager.
    """
    result = core.build(model_files, dst_base, out_vpk, material_files)
    for ext in result["packed"]:
        print(f"  OK  {ext}")
    print(f"\nSaved VPK: {result['out_path']}")
    print("Drag it onto the Casual Preloader, tick it, hit Install.")
    log.info(f"Built VPK '{out_vpk}'  ({src_label} replaces {target_label})")
    return result


def emit_addon(model_files, dst_base, addons_dir, addon_name, material_files, src_label, target_label):
    """
    Build a cosmetic swap in the Casual Preloader's native addon folder format
    and report the result. The mod appears in the preloader's list ready to enable.
    See tf2_core.build_addon_folder() for an explanation of the native format.
    """
    result = core.build_addon_folder(model_files, dst_base, addons_dir, addon_name, material_files)
    for ext in result["packed"]:
        print(f"  OK  {ext}")
    print(f"\nInstalled to preloader: {result['addon_dir']}")
    print("It should show in the preloader's addons list, ready to enable.")
    log.info(f"Installed addon '{result['addon_dir']}'  ({src_label} replaces {target_label})")
    return result


def emit_weapon_vpk(view_files, world_files, dst_view_base, dst_world_base, out_vpk, src_label, target_label, world_note=None, material_files=None):
    """
    Build a weapon swap VPK archive (viewmodel + worldmodel) and report the result.
    world_note is shown if no worldmodel was packed, explaining whether this was
    expected (melee weapons normally have no worldmodel) or unexpected.
    material_files, if given (weapon disk-imports only), are bundled the same
    way cosmetic material transport already works.
    """
    result = core.build_weapon(view_files, world_files, dst_view_base, dst_world_base, out_vpk, material_files)
    for ext in result["packed"]:
        print(f"  OK  {ext}")
    if not any("world" in e for e in result["packed"]) and world_note:
        print(f"  ({world_note})")
    print(f"\nSaved VPK: {result['out_path']}")
    print("Drag it onto the Casual Preloader, tick it, hit Install.")
    log.info(f"Built weapon VPK '{out_vpk}'  ({src_label} replaces {target_label})")
    return result


def emit_weapon_addon(view_files, world_files, dst_view_base, dst_world_base, addons_dir, addon_name, src_label, target_label, world_note=None, material_files=None):
    """
    Build a weapon swap in the Casual Preloader's native addon folder format
    and report the result. material_files, if given, same as emit_weapon_vpk().
    """
    result = core.build_weapon_addon_folder(view_files, world_files, dst_view_base, dst_world_base, addons_dir, addon_name, material_files)
    for ext in result["packed"]:
        print(f"  OK  {ext}")
    if not any("world" in e for e in result["packed"]) and world_note:
        print(f"  ({world_note})")
    print(f"\nInstalled to preloader: {result['addon_dir']}")
    print("It should show in the preloader's addons list, ready to enable.")
    log.info(f"Installed weapon addon '{result['addon_dir']}'  ({src_label} replaces {target_label})")
    return result


def is_in_preloader(path, preloader_dir):
    """
    Return True if the given path is located inside the Casual Preloader's
    addons directory. Used to detect when a user has entered a custom output
    path that points inside the preloader folder, so we can automatically
    use the native addon format instead of producing a plain VPK file.

    Uses os.path.commonpath rather than string prefix matching so paths with
    different normalisation (trailing slashes, mixed case on Windows, symlinks)
    still compare correctly.

    ValueError is raised by commonpath on Windows when comparing paths on
    different drives — caught and treated as 'not inside the preloader folder'.
    """
    try:
        a, b = os.path.abspath(path), os.path.abspath(preloader_dir)
        return os.path.commonpath([a, b]) == b
    except ValueError:
        return False


def confirm_preloader_write(preloader_dir):
    """
    Show a mandatory warning before writing directly to the Casual Preloader folder.

    The Casual Preloader maintains its own internal state. Writing files into
    unexpected locations within its folder structure could corrupt that state.
    The safest approach is always to save a VPK file and import it via the
    preloader's own interface.

    This function requires the user to type 'yes' (not just 'y') to make the
    confirmation deliberate — a casual Enter keypress should not be enough to
    proceed with a potentially disruptive write operation.

    Returns True if the user confirmed, False if they declined.
    """
    print("\n  !! WARNING !!")
    print("  Writing directly to the Casual Preloader folder may silently")
    print("  break the preloader if its internal structure is not as expected.")
    print("  It is safer to save a VPK and import it into the preloader manually.")
    print(f"\n  Target folder: {preloader_dir}")
    print()
    answer = input("  Type 'yes' to proceed anyway, or anything else to cancel: ").strip().lower()
    if answer != "yes":
        print("  Cancelled — no files written.")
        return False
    return True


def get_disk_source(mdl_path, target_class=None):
    """
    Read a model file and its materials from disk, reporting what was found.

    Thin wrapper around tf2_core.source_from_disk() that adds user-facing
    terminal output about the materials, and — this is the important part —
    runs any bundled materials through tf2_material's safety layer before
    returning them, the same check interactive_skin_swap() already applies.

    Found during a pipeline audit: this function bundles arbitrary
    third-party materials from a downloaded mod folder exactly the same
    way the dedicated skin-swap feature does, but until this fix it never
    ran them through the wallhack/ESP safety check at all — only the
    newer dedicated feature did. A malicious $ignorez material smuggled
    in alongside a disk-imported cosmetic or weapon model would have been
    bundled completely unchecked. This closes that gap by routing through
    the same validate_material_set() call here, so every place this tool
    bundles third-party materials gets the same safety coverage,
    regardless of which menu option got it there.

    target_class ("weapon", "cosmetic", or "prop") is passed straight
    through to validate_material_set() — see that function's docstring
    for how it affects both scope and severity. Pass None for callers
    that don't yet have a meaningful category; the materials still get
    scanned, just without the context-aware severity tuning.

    If tf2_material.py isn't available (HAVE_MATERIAL is False), bundled
    materials are skipped entirely rather than bundled unchecked — the
    model still imports, just without custom textures, with a message
    explaining why. Fail-safe: no safety scanner available means no
    custom materials get bundled, not "bundle and hope."

    Also reports any files skipped because a symlink among them resolved
    outside the mod's own folder (see tf2_core.resolved_path_under()) —
    this is a security-relevant refusal, not a routine "nothing found"
    case, so the user should actually see it rather than have it pass
    silently.

    Returns (model_files, material_files) where both are dicts of
    {path/extension: bytes}.
    """
    model_files, material_files, meta = core.source_from_disk(mdl_path)
    if meta.get("skipped_symlinks"):
        print(f"\n  Skipped {len(meta['skipped_symlinks'])} file(s) — a symlink among them")
        print("  pointed somewhere outside this mod's own folder, so it was refused")
        print("  rather than read (this guards against a downloaded mod secretly")
        print("  reading an unrelated file elsewhere on your system):")
        for s in meta["skipped_symlinks"]:
            print(f"    - {s}")

    if material_files:
        if HAVE_MATERIAL:
            verdict = material.validate_material_set(material_files, target_class=target_class)
            if verdict.blocked:
                print(f"\n  {len(verdict.blocked)} material file(s) refused by the safety check:")
                for b in verdict.blocked:
                    print(f"    - {b}")
            if verdict.warnings:
                for w in verdict.warnings:
                    print(f"    (note: {w})")
            material_files = verdict.safe_files
        else:
            print(f"\n  Skipping {len(material_files)} material file(s) — tf2_material.py isn't")
            print("  available, so custom textures can't be safety-checked. The model will")
            print("  import without them rather than bundle them unchecked.")
            material_files = {}

    if meta["materials_dir"]:
        if material_files:
            print(f"  Bundling {len(material_files)} material file(s) from {meta['materials_dir']}")
        else:
            print(f"  Found a materials folder at {meta['materials_dir']}, but nothing from it passed the safety check.")
    else:
        print("  No materials/ folder found next to the model.")
        print("  (Fine if it reuses stock TF2 textures; otherwise it may look untextured.)")
    return model_files, material_files


# ---------- interactive: shared pickers ----------

def choose(prompt, options, labels):
    """
    Display a numbered list of options and return the user's chosen value.

    'options' and 'labels' are parallel lists: options[i] is the internal value
    returned when the user selects labels[i] (the displayed text). This separation
    allows menu labels to be human-readable while return values are machine-usable.

    'q' always exits the tool cleanly. Invalid inputs loop back to the prompt.
    """
    for i, label in enumerate(labels, 1):
        print(f"  {i}. {label}")
    while True:
        raw = input(f"{prompt} (1-{len(options)}, q to quit): ").strip().lower()
        if raw == "q":
            sys.exit("Cancelled.")
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        print("  Invalid choice, try again.")


def choose_paginated(prompt, options, labels, page_size=15):
    """
    Same contract as choose() — numbered list in, chosen option out — but
    shown a page at a time instead of dumping the whole list at once.

    Built for own-inventory mode: a player's backpack can easily run to
    several hundred matched items once class/slot filtering still leaves a
    broad category (e.g. "all misc items for all classes"), and printing
    that in one block is hard to actually read or scroll back through.

    Numbers stay absolute across pages (item 47 is always item 47, on
    whichever page it falls on) — so there's only one number to track
    instead of a page-relative one that changes meaning each page.

    Navigation, typed at the same prompt as a normal selection:
        n        next page
        p        previous page
        <number> select that item directly, from any page
        q        quit

    Falls through to a plain, unpaginated choose() if the list already fits
    in one page — no point adding navigation prompts for a dozen items.
    """
    total = len(options)
    if total <= page_size:
        return choose(prompt, options, labels)

    page = 0
    last_page = (total - 1) // page_size

    while True:
        start = page * page_size
        end = min(start + page_size, total)
        print(f"\n  Page {page + 1} of {last_page + 1}  (items {start + 1}-{end} of {total})")
        for i in range(start, end):
            print(f"  {i + 1}. {labels[i]}")

        nav = []
        if page > 0:
            nav.append("p=prev")
        if page < last_page:
            nav.append("n=next")
        nav_hint = f", {', '.join(nav)}" if nav else ""

        raw = input(f"{prompt} (1-{total}{nav_hint}, q to quit): ").strip().lower()
        if raw == "q":
            sys.exit("Cancelled.")
        if raw == "n" and page < last_page:
            page += 1
            continue
        if raw == "p" and page > 0:
            page -= 1
            continue
        if raw.isdigit() and 1 <= int(raw) <= total:
            return options[int(raw) - 1]
        print("  Invalid choice, try again.")


def search_and_pick(pak, what, class_filter, index):
    """
    Interactive search loop for cosmetic items. Returns the archive path of
    the item the user selects.

    Two-phase search strategy for robust name matching:
    1. Search archive paths directly using the normalised keyword
    2. If phase 1 finds nothing, search the schema's friendly names and retry
       phase 1 with the matching internal filename stems — this handles users
       typing display names like 'Head Full of Hot Air' instead of archive
       path fragments like 'balloon_hat'

    If exactly one result is found, it is auto-selected without showing a menu.
    If no results are found after both phases, typo suggestions are shown.
    Loops until the user selects an item or types 'q'.
    """
    stems = core.all_stems(pak)  # Used for typo suggestions if search finds nothing
    while True:
        kw_raw = input(f"\nSearch for {what} (keyword, q to quit): ").strip()
        if kw_raw.lower() == "q":
            sys.exit("Cancelled.")
        if not kw_raw:
            print("  Please enter a keyword.")
            continue
        kw = normalize_keyword(kw_raw)
        models = core.find_models(pak, kw, class_filter)

        # Phase 2: search friendly names if archive path search found nothing
        if not models and index and HAVE_SCHEMA:
            name_stems = reverse_name_lookup(index, kw)
            for ns in name_stems:
                models.extend(core.find_models(pak, ns, class_filter))
            models = sorted(set(models))
            if models:
                print(f"  Found by item name:")

        if not models:
            print(f"  No matches for '{kw_raw}'.")
            hint = _did_you_mean(kw, stems)
            if hint:
                print(f"  Did you mean: {', '.join(hint)}")
            continue

        # Auto-select single result rather than showing a one-item menu
        if len(models) == 1:
            print(f"  Auto-selected: {label_for(models[0], index)}")
            return models[0]

        labels = [label_for(m, index) for m in models]
        print(f"\n  Matches for '{kw_raw}':")
        return choose(f"  Pick {what}", models, labels)


def search_and_pick_weapons(pak, what, class_filter, slot_filter, index):
    """
    Interactive search loop for weapon items. Returns the archive path of the
    weapon's viewmodel (first-person model) the user selects.

    Mirrors search_and_pick() but targets weapon-specific archive paths and
    applies character class and loadout slot filtering.

    Non-weapon filtering uses two mechanisms to keep results clean:
    1. Schema-based: if the schema can positively identify a result as a
       non-weapon (e.g. a cosmetic that happens to match the keyword), it is
       excluded. Items with no schema entry pass through rather than being
       silently dropped — it is better to show an unexpected result than to
       hide a valid weapon.
    2. Path-based blocklist: some non-weapon models in the game archive (such
       as decorative ornaments placed as props) have no schema entry but should
       not appear in weapon searches. These are excluded by known path fragments.
    """
    while True:
        kw_raw = input(f"\nSearch for {what} (keyword, q to quit): ").strip()
        if kw_raw.lower() == "q":
            sys.exit("Cancelled.")
        if not kw_raw:
            print("  Please enter a keyword.")
            continue
        kw = normalize_keyword(kw_raw)
        models = core.find_weapons(pak, kw)

        # Exclude items the schema positively identifies as non-weapons
        # (items with no schema entry pass through — better to show than to hide)
        if index and HAVE_SCHEMA:
            models = [
                m for m in models
                if not (
                    tf2_schema.lookup(index, m) and
                    tf2_schema.lookup(index, m).item_type not in ("weapon", "unknown")
                )
            ]
        # Exclude known non-weapon models by archive path fragment
        # (e.g. festive ornament props that appear in festive weapon searches)
        NON_WEAPON_PATH_FRAGMENTS = ["ornament"]
        models = [
            m for m in models
            if not any(fragment in m.lower() for fragment in NON_WEAPON_PATH_FRAGMENTS)
        ]

        # Phase 2: search friendly names if archive path search found nothing
        if not models and index and HAVE_SCHEMA:
            name_stems = reverse_name_lookup_weapon(index, kw)
            for ns in name_stems:
                models.extend(core.find_weapons(pak, ns))
            models = sorted(set(models))
            if models:
                print(f"  Found by item name:")

        # Apply class and slot filters if either is active
        needs_filter = (
            (class_filter and class_filter != "all") or
            (slot_filter and slot_filter != "all")
        )
        if index and HAVE_SCHEMA and needs_filter:
            filtered = []
            for mdl in models:
                info = tf2_schema.lookup(index, mdl)
                if info is None:
                    # No schema entry — include rather than silently discard
                    filtered.append(mdl)
                    continue
                if class_filter and class_filter != "all":
                    if class_filter.lower() not in [c.lower() for c in info.classes]:
                        continue
                if slot_filter and slot_filter != "all":
                    effective_slot = tf2_schema.resolve_class_slot(
                        info.item_slot, info.per_class_slot, class_filter
                    )
                    if effective_slot.lower() != slot_filter.lower():
                        continue
                filtered.append(mdl)
            models = filtered

        if not models:
            print(f"  No matches for '{kw_raw}'.")
            hint = _did_you_mean(kw, core.all_weapon_stems(pak))
            if hint:
                print(f"  Did you mean: {', '.join(hint)}")
            continue

        if len(models) == 1:
            print(f"  Auto-selected: {label_for_weapon(models[0], index)}")
            return models[0]

        labels = [label_for_weapon(m, index) for m in models]
        print(f"\n  Matches for '{kw_raw}':")
        return choose(f"  Pick {what}", models, labels)


def ask_disk_model():
    """
    Prompt the user for the path to a locally stored .mdl model file.

    Strips surrounding quote characters (commonly added when dragging files
    from file browsers on Windows and macOS). Expands ~ to the user's home
    directory. Validates that the path points to an existing .mdl file.
    Loops until a valid path is provided or the user quits.
    """
    while True:
        path = input("\nPath to the .mdl file (q to quit): ").strip().strip("'\"")
        if path.lower() == "q":
            sys.exit("Cancelled.")
        path = os.path.expanduser(path)
        if os.path.isfile(path) and path.endswith(".mdl"):
            return path
        print("  Not a valid .mdl file path, try again.")


# ---------- interactive: own-inventory mode ----------
# Lets a swap's REPLACEMENT source be picked from items the user actually
# owns on Steam, instead of searching the whole game catalog.
#
# Deliberately JSON-file-only: no live network fetch, no SteamID64 prompt,
# no cookie/session handling, and the tool never fetches-then-caches
# inventory data on its own initiative. (The --debug-inventory report file
# is the one thing in this section that does write to disk — a report the
# user explicitly asked for, not something quietly cached in the background.)
# See tf2_core.py's own-inventory section header for the full reasoning —
# in short, anything resembling "paste your Steam session here" is
# indistinguishable from a credential-stealing tool from the outside,
# regardless of how trustworthy the code actually is, so that whole
# surface is cut rather than guarded.

def list_inventory_json_files():
    """
    List .json files sitting in the inventory drop folder (imports/inventory/),
    so a previously exported inventory file can be picked without retyping
    a full path every time.

    Returns a sorted list of full paths. Empty if the folder is missing or
    has no .json files in it (the bundled how-to guide is a .txt file, so
    it never matches here).
    """
    if not os.path.isdir(INVENTORY_IMPORT_DIR):
        return []
    return sorted(
        os.path.join(INVENTORY_IMPORT_DIR, fn)
        for fn in os.listdir(INVENTORY_IMPORT_DIR)
        if fn.lower().endswith(".json")
    )


def load_owned_items_interactive():
    """
    Get the user's inventory data. Checks the inventory drop folder
    (imports/inventory/) for a previously exported .json file first; if one
    or more are found, offers to pick from them instead of retyping a path.
    Falls back to a manual path prompt if the folder is empty or the user
    wants a different file. This is the only way own-inventory mode gets
    data — see tf2_core.load_inventory_file()'s docstring, and
    imports/inventory/HOW_TO_GET_YOUR_INVENTORY.txt, for how to obtain that
    file in the first place.

    Nothing is cached to disk by the tool itself — any file found here was
    placed there by the user, not written by this function. The loaded
    list only lives in memory for the current run (see owned_items_cache
    in interactive()).

    Returns a list of owned items (the shape tf2_core.load_inventory_file()
    returns), or None if the user gives up without success.
    """
    found = list_inventory_json_files()
    path = None

    if found:
        opts = found + ["manual"]
        labels = [os.path.basename(p) for p in found] + ["Enter a different file path"]
        if len(found) == 1:
            labels[0] += "  (found in imports/inventory/)"
        choice = choose("\n  Pick an inventory file", opts, labels)
        if choice != "manual":
            path = choice

    if path is None:
        raw = input(
            "\n  Path to your saved inventory JSON file "
            "(see imports/inventory/HOW_TO_GET_YOUR_INVENTORY.txt for how "
            "to get one; q to quit): "
        ).strip().strip("'\"")
        if raw.lower() == "q":
            return None
        path = os.path.expanduser(raw)

    try:
        items = core.load_inventory_file(path)
        print(f"  Loaded {len(items)} items from file.")
        return items
    except core.InventoryError as e:
        print(f"  {e}")
        return None


def pick_from_inventory(pak, defindex_index, item_type, what, owned_items=None, cls=None, slot=None):
    """
    Let the user pick an item from their own owned TF2 items — usable at
    either the TARGET step (item to replace) or the SOURCE step (replacement)
    of a swap flow, since both just need an archive .mdl path in the end.

    item_type ("cosmetic" or "weapon") filters to matches relevant to the
    swap flow currently in progress. Returns an archive .mdl path in the
    exact same shape search_and_pick() / search_and_pick_weapons() return,
    so it works as a drop-in alternative — everything downstream (label_for,
    display_name, source_from_vpk) works on it identically without further
    changes.

    cls, if given, narrows multi-class items down to that one class's model
    variant — the same class filter already chosen at Step 1 of the swap
    flow. Without this, an all-class item with per-class model variants
    (most all-class cosmetics work this way) would show up once per class
    it supports, which looks like duplicate ownership in the picker but is
    really just every class variant of the one item actually owned.

    owned_items, if provided, is used directly instead of prompting for the
    inventory file path again — this is what lets "Load inventory from
    file" (the main menu option) be done once and then reused at both the
    target and source steps in the same swap, rather than asking twice.
    If not provided, this falls back to the original on-demand prompt, so
    the picker still works standalone if the user skips the load-once step.

    Returns a tuple: (picked_path_or_None, owned_items_or_None). The second
    value is whatever item list actually ended up being used — either the
    owned_items passed in, or a freshly loaded one if owned_items was None.
    Callers should store it and pass it back in on the next call within the
    same swap (target step, then source step), so a fresh load only ever
    happens once per swap rather than once per call. Without this, going
    straight into a swap without using "Load inventory from file" on the
    main menu first would silently reload (and re-prompt for the file) at
    every step that uses the inventory option, which is wasteful and, if
    the second prompt is missed or mishandled, can look like own-inventory
    mode "not working" when it's really just re-asking unnecessarily.

    The first value is None if the inventory couldn't be loaded, or had no
    usable items of the requested type — callers should offer a fallback to
    another source option in that case rather than treating it as fatal.
    Reasons an owned item might not show up here: it has no schema entry
    (some tools/currency items, and anything without a genuine loadout slot
    — see build_defindex_index()'s docstring), or the schema lists a model
    path that isn't actually present in this VPK (rare, but possible after
    a game update that hasn't propagated to all archive copies yet).
    """
    if defindex_index is None:
        print("  Own-inventory mode isn't available right now (schema index missing).")
        return None, owned_items

    if owned_items is None:
        owned_items = load_owned_items_interactive()
        if owned_items is None:
            return None, None

    matched = core.match_owned_items(owned_items, defindex_index, pak, class_filter=cls, slot_filter=slot)
    matched = [m for m in matched if m["item_type"] == item_type]

    if not matched:
        print(f"  No owned {item_type}s with usable model data were found in that inventory.")
        return None, owned_items

    options = [m["model_path"] for m in matched]
    labels = [m["name"] for m in matched]
    print(f"\n  Your owned {item_type}s ({len(matched)}):")
    picked = choose_paginated(f"  Pick {what}", options, labels)
    return picked, owned_items


# ---------- interactive: swap flow ----------

def interactive_swap(pak, index, defindex_index, preloader_dir, owned_items_cache=None):
    """
    Guided five-step cosmetic item swap flow.

    Step 1 — Character class filter: optionally narrows search results to items
             usable by a specific character class
    Step 2 — Target selection: the existing in-game item to be replaced — from
             the game archive, or an item from the user's own inventory file
    Step 3 — Source selection: the replacement item, from the game archive, a
             locally stored mod file, or an item from the user's own inventory file
    Step 4 — Confirmation: shows what will be built, warns about potential visual
             issues (head clipping, equip region mismatches), and requires approval
    Step 5 — Output: saves the result as a VPK archive file (portable, can be
             shared) or directly to the Casual Preloader's native addon folder
             format (immediately available in the preloader without manual import)

    owned_items_cache, if provided (via "Load inventory from file" on the
    main menu), is reused at both Step 2 and Step 3 so the inventory option
    works at either step without asking for the file path twice in one
    swap. If not provided, picking the inventory option at either step
    still works — it just prompts on the spot instead.

    All actual file operations are handled by the emit_* functions, which call
    tf2_core build functions and report results.
    """
    print("\n--- New swap ---\n")

    print("Step 1 - Which class?")
    class_opts = core.CLASSES + ["all (no filter)"]
    cls = choose("Select class", class_opts, class_opts)
    # Extract just the class name from "all (no filter)" if that was selected
    cls = cls.split()[0] if cls.startswith("all") else cls

    print("\nStep 2 - Cosmetic to REPLACE")
    target_opts, target_labels = ["search"], ["Search TF2's full catalog"]
    if defindex_index is not None:
        target_opts.append("inventory")
        target_labels.append("Pick from my inventory file")
    target_how = ("search" if len(target_opts) == 1 else
                  choose("Where from?", target_opts, target_labels))

    target = None
    if target_how == "inventory":
        target, loaded = pick_from_inventory(pak, defindex_index, "cosmetic",
                                              "the cosmetic to replace", owned_items_cache, cls=cls)
        if loaded is not None:
            owned_items_cache = loaded
        if target is None:
            print("  Falling back to full catalog search.")
    if target is None:
        target = search_and_pick(pak, "the cosmetic to replace", cls, index)
    dst_base = target[:-4]  # Strip .mdl to get the base archive path for building
    target_label = label_for(target, index)

    print("\nStep 3 - REPLACEMENT source")
    how = choose("Where from?",
                 ["builtin", "disk", "inventory"],
                 ["TF2's built-in cosmetics",
                  "Import a model from disk (Gamebanana / custom)",
                  "My inventory file"])

    material_files = None
    src_base = None
    if how == "builtin":
        # Source from the game archive — no external materials needed since
        # TF2 already has all the textures for its own items
        source = search_and_pick(pak, "the replacement cosmetic", cls, index)
        src_base = source[:-4]
        model_files = core.source_from_vpk(pak, src_base)
        src_label = label_for(source, index)
        source_clean = display_name(source, index)
    elif how == "inventory":
        source, loaded = pick_from_inventory(pak, defindex_index, "cosmetic",
                                              "the replacement cosmetic", owned_items_cache, cls=cls)
        if loaded is not None:
            owned_items_cache = loaded
        if source is None:
            print("  Falling back to TF2's built-in cosmetics search.")
            source = search_and_pick(pak, "the replacement cosmetic", cls, index)
        src_base = source[:-4]
        model_files = core.source_from_vpk(pak, src_base)
        src_label = label_for(source, index)
        source_clean = display_name(source, index)
    else:
        # Source from local disk — may include a materials folder with custom textures
        mdl_path = ask_disk_model()
        model_files, material_files = get_disk_source(mdl_path, target_class="cosmetic")
        src_label = os.path.basename(mdl_path)[:-4]
        source_clean = src_label

    print("\nStep 4 - Confirm")
    print(f"  Replace : {target_label}")
    print(f"  With    : {src_label}")
    # Safety warnings are only available when both items have schema entries
    if src_base:
        warn = clip_warning(index, src_base, dst_base)
        if warn:
            print(f"\n  Heads-up: {warn}")
    preview = core.preview_build(model_files, dst_base, material_files)
    summary = f"{preview['model_count']} model file(s), {fmt_size(preview['total_size'])}"
    if preview["material_count"]:
        summary += f" + {preview['material_count']} material(s)"
    print(f"\n  Preview: {summary}")
    if input("Proceed? (y/n): ").strip().lower() not in ("y", "yes"):
        sys.exit("Cancelled.")

    print("\nStep 5 - Output location")
    fname = output_filename(target, source_clean, index)
    addon_name = fname[:-4]  # Preloader addon folders do not have a .vpk extension
    opts, labels = ["default"], [f"Output folder as a VPK  ({OUTPUT_DIR})"]
    if os.path.isdir(preloader_dir):
        opts.append("preloader")
        labels.append("Preloader addons folder  (installed format, ready to use)")
    opts.append("custom")
    labels.append("Custom path")

    where = choose("Save to", opts, labels)
    if where == "preloader":
        if confirm_preloader_write(preloader_dir):
            emit_addon(model_files, dst_base, preloader_dir, addon_name, material_files, src_label, target_label)
    elif where == "custom":
        raw = input("Enter a path (file or folder): ").strip().strip("'\"")
        if not raw:
            # Empty input — fall back to default output folder
            emit_vpk(model_files, dst_base, os.path.join(OUTPUT_DIR, fname), material_files, src_label, target_label)
        elif is_in_preloader(raw, preloader_dir):
            # Path is inside the Casual Preloader folder — use native addon format
            if confirm_preloader_write(preloader_dir):
                emit_addon(model_files, dst_base, preloader_dir, addon_name, material_files, src_label, target_label)
        elif has_invalid_path_chars(raw):
            print("  That path contains invalid characters — saving to output folder instead.")
            emit_vpk(model_files, dst_base, os.path.join(OUTPUT_DIR, fname), material_files, src_label, target_label)
        else:
            out_path = resolve_out_path(raw, fname)
            valid, reason = validate_output_path(out_path)
            if not valid:
                print(f"  That path isn't writable: {reason}")
                print(f"  Saving to output folder instead.")
                out_path = os.path.join(OUTPUT_DIR, fname)
            emit_vpk(model_files, dst_base, out_path, material_files, src_label, target_label)
    else:
        emit_vpk(model_files, dst_base, os.path.join(OUTPUT_DIR, fname), material_files, src_label, target_label)


# ---------- interactive: weapon swap flow ----------

def interactive_weapon_swap(pak, index, defindex_index, preloader_dir, owned_items_cache=None):
    """
    Guided five-step weapon swap flow.

    Weapons require both the first-person viewmodel and the third-person worldmodel
    to be swapped together (see tf2_core.py module docstring for background on
    viewmodel vs worldmodel). This flow handles both automatically.

    Step 1 — Character class filter (optional)
    Step 2 — Loadout slot filter (optional — primary, secondary, melee, etc.)
    Step 3 — Target weapon: the existing weapon to replace — from the game
             archive, or an item from the user's own inventory file
    Step 4 — Source weapon: the replacement weapon, from the game archive or
             an item from the user's own inventory file
    Step 5 — Confirmation and output

    owned_items_cache, if provided (via "Load inventory from file" on the main
    menu), is reused at both Step 3 and Step 4 — same reasoning as
    interactive_swap()'s equivalent parameter.

    The actual worldmodel destination path is looked up from the game archive
    rather than guessed, because the archive path must be exact for the swap
    to take effect correctly (two possible folder structures exist — see
    _world_base_candidates in tf2_core.py).

    If no worldmodel is found for the source weapon, the swap is completed with
    the first-person viewmodel only. For melee weapons (knives, bats, wrenches
    etc.) this is the normal and expected outcome — most melee weapons in TF2
    do not have a separate third-person worldmodel.
    """
    print("\n--- New weapon swap ---\n")

    print("Step 1 - Which class?")
    class_opts = core.CLASSES + ["all (no filter)"]
    cls = choose("Select class", class_opts, class_opts)
    cls = cls.split()[0] if cls.startswith("all") else cls

    print("\nStep 2 - Which loadout slot?")
    slot_opts = slots_for_class(index, cls)
    slot_display = slot_opts + ["all (no filter)"]
    slot = choose("Select slot", slot_display, slot_display)
    slot = slot.split()[0] if slot.startswith("all") else slot

    print("\nStep 3 - Weapon to REPLACE")
    target_opts, target_labels = ["search"], ["Search TF2's full catalog"]
    if defindex_index is not None:
        target_opts.append("inventory")
        target_labels.append("Pick from my inventory file")
    target_how = ("search" if len(target_opts) == 1 else
                  choose("Where from?", target_opts, target_labels))

    target = None
    if target_how == "inventory":
        target, loaded = pick_from_inventory(pak, defindex_index, "weapon",
                                              "the weapon to replace", owned_items_cache, cls=cls, slot=slot)
        if loaded is not None:
            owned_items_cache = loaded
        if target is None:
            print("  Falling back to full catalog search.")
    if target is None:
        target = search_and_pick_weapons(pak, "the weapon to replace", cls, slot, index)
    dst_view_base = target[:-4]
    # Look up the actual worldmodel destination path from the game archive
    dst_world_base = core.resolve_world_base_from_vpk(pak, dst_view_base)
    target_label = label_for_weapon(target, index)

    print("\nStep 4 - REPLACEMENT source")
    how = choose("Where from?",
                 ["builtin", "disk", "inventory"],
                 ["TF2's built-in weapons",
                  "Import a model from disk (Gamebanana / custom)",
                  "My inventory file"])

    material_files = None
    if how == "inventory":
        source, loaded = pick_from_inventory(pak, defindex_index, "weapon",
                                              "the replacement weapon", owned_items_cache, cls=cls, slot=slot)
        if loaded is not None:
            owned_items_cache = loaded
        if source is None:
            print("  Falling back to TF2's built-in weapons search.")
            source = search_and_pick_weapons(pak, "the replacement weapon", cls, slot, index)
        src_view_base = source[:-4]
        src_label = label_for_weapon(source, index)
        source_clean = display_name(source, index)
        view_files, world_files, src_world_base = core.source_from_vpk_weapon(pak, src_view_base)
    elif how == "disk":
        # Weapons need BOTH a viewmodel and a worldmodel — the user picks
        # the viewmodel .mdl, and find_disk_weapon_worldmodel() tries to
        # auto-locate a matching worldmodel in the same downloaded mod
        # folder, using the same naming convention TF2 itself uses (see
        # that function's docstring). Materials for both, if any, are read
        # and safety-checked the same way a cosmetic disk-import already
        # is — get_disk_source() handles that internally.
        view_mdl_path = ask_disk_model()
        view_files, material_files = get_disk_source(view_mdl_path, target_class="weapon")
        src_label = os.path.basename(view_mdl_path)[:-4]
        source_clean = src_label

        world_files = {}
        world_mdl_path = core.find_disk_weapon_worldmodel(view_mdl_path)
        if world_mdl_path:
            print(f"  Found matching worldmodel: {os.path.basename(world_mdl_path)}")
            world_files, world_material_files = get_disk_source(world_mdl_path, target_class="weapon")
            material_files.update(world_material_files)
        else:
            print("  No matching worldmodel found alongside the viewmodel.")
            print("  (Normal for melee weapons — those typically have no worldmodel at all.)")
    else:
        source = search_and_pick_weapons(pak, "the replacement weapon", cls, slot, index)
        src_view_base = source[:-4]
        src_label = label_for_weapon(source, index)
        source_clean = display_name(source, index)
        view_files, world_files, src_world_base = core.source_from_vpk_weapon(pak, src_view_base)

    print("\nStep 5 - Confirm & output")
    print(f"  Replace : {target_label}")
    print(f"  With    : {src_label}")
    if how != "disk":
        warn = weapon_warning(index, src_view_base, dst_view_base)
        if warn:
            print(f"\n  Heads-up: {warn}")

    # Explain why no worldmodel was found, distinguishing expected cases from
    # unexpected ones to avoid confusing the user
    world_note = None
    if not world_files:
        dst_info = tf2_schema.lookup(index, dst_view_base) if (index and HAVE_SCHEMA) else None
        if dst_info and dst_info.item_slot == "melee":
            world_note = "melee weapons typically don't have separate world models — viewmodel only is expected"
        else:
            world_note = "no world model found — viewmodel only"
        print(f"  Note: {world_note.capitalize()}.")

    preview = core.preview_build_weapon(view_files, world_files, dst_view_base, dst_world_base or "")
    summary = f"{preview['view_count']} viewmodel file(s)"
    if preview["world_count"]:
        summary += f" + {preview['world_count']} worldmodel file(s)"
    summary += f", {fmt_size(preview['total_size'])}"
    if material_files:
        summary += f" + {len(material_files)} material(s)"
    print(f"\n  Preview: {summary}")

    if input("\nProceed? (y/n): ").strip().lower() not in ("y", "yes"):
        sys.exit("Cancelled.")

    print()
    fname = output_filename(target, source_clean, index)
    addon_name = fname[:-4]
    opts, labels = ["default"], [f"Output folder as a VPK  ({OUTPUT_DIR})"]
    if os.path.isdir(preloader_dir):
        opts.append("preloader")
        labels.append("Preloader addons folder  (installed format, ready to use)")
    opts.append("custom")
    labels.append("Custom path")

    # Output routing is identical to the cosmetic swap, using weapon build functions
    where = choose("Save to", opts, labels)
    if where == "preloader":
        if confirm_preloader_write(preloader_dir):
            emit_weapon_addon(view_files, world_files, dst_view_base, dst_world_base, preloader_dir, addon_name, src_label, target_label, world_note, material_files)
    elif where == "custom":
        raw = input("Enter a path (file or folder): ").strip().strip("'\"")
        if not raw:
            emit_weapon_vpk(view_files, world_files, dst_view_base, dst_world_base, os.path.join(OUTPUT_DIR, fname), src_label, target_label, world_note, material_files)
        elif is_in_preloader(raw, preloader_dir):
            if confirm_preloader_write(preloader_dir):
                emit_weapon_addon(view_files, world_files, dst_view_base, dst_world_base, preloader_dir, addon_name, src_label, target_label, world_note, material_files)
        elif has_invalid_path_chars(raw):
            print("  That path contains invalid characters — saving to output folder instead.")
            emit_weapon_vpk(view_files, world_files, dst_view_base, dst_world_base, os.path.join(OUTPUT_DIR, fname), src_label, target_label, world_note, material_files)
        else:
            out_path = resolve_out_path(raw, fname)
            valid, reason = validate_output_path(out_path)
            if not valid:
                print(f"  That path isn't writable: {reason}")
                print(f"  Saving to output folder instead.")
                out_path = os.path.join(OUTPUT_DIR, fname)
            emit_weapon_vpk(view_files, world_files, dst_view_base, dst_world_base, out_path, src_label, target_label, world_note, material_files)
    else:
        emit_weapon_vpk(view_files, world_files, dst_view_base, dst_world_base, os.path.join(OUTPUT_DIR, fname), src_label, target_label, world_note, material_files)


# ---------- interactive: skin (material) swap ----------
# See tf2_material.py's module docstring for the full safety reasoning. In
# short: this is the one swap type that could be turned into a cheat if it
# weren't deliberately scoped and filtered, so every material set produced
# here is run through tf2_material.validate_material_set() before anything
# is written, with no way to bypass that check from the interface.

def _ask_folder(prompt):
    """Prompt for an existing folder path. 'q' quits."""
    while True:
        p = input(f"{prompt} (q to quit): ").strip().strip("'\"")
        if p.lower() == "q":
            sys.exit("Cancelled.")
        p = os.path.expanduser(p)
        if os.path.isdir(p):
            return p
        print("  Not a folder, try again.")


def _report_verdict(verdict):
    """
    Print the safety verdict from tf2_material.validate_material_set().
    Returns True if it is safe to proceed, False if the set was refused.
    """
    if verdict.blocked:
        print("\n  BLOCKED - this material set was refused:")
        for b in verdict.blocked:
            print(f"    - {b}")
        print("\n  TF2autoswap only reskins weapon and cosmetic materials, and")
        print("  refuses world/map/base-player materials and any render flags")
        print("  that could create see-through or ESP effects. Nothing was written.")
        return False
    if verdict.warnings:
        print("\n  Notes:")
        for w in verdict.warnings:
            print(f"    - {w}")
    print(f"\n  {len(verdict.safe_files)} material file(s) passed the safety check.")
    return True


def interactive_skin_swap(pak, index, preloader_dir, tf2_path):
    """
    Skin / material swap: apply a reskin (custom .vmt/.vtf materials) to a
    weapon or cosmetic. Every material set is run through the safety layer
    in tf2_material before anything is written. World, map and base-player
    materials, and wallhack render flags (including ones hidden behind a
    runtime Proxies block — see tf2_material.has_proxies_block()), are
    refused outright; there's no setting to turn this off.

    tf2_path is the already-resolved TF2 installation directory (resolved
    once in run() at startup) — passed in here rather than re-resolving it,
    since the "copy another item's textures" source mode needs to open
    tf2_textures_dir.vpk separately from the main archive.
    """
    print("\n--- New skin / material swap ---\n")
    print("Applies a reskin (custom materials) to a weapon or cosmetic.")
    print("World, map and base-player materials are out of scope and refused.\n")
    print("Heads-up for WEAPON reskins specifically: war-painted weapon")
    print("skins are NOT a finished texture file anywhere in the game — TF2 composites")
    print("them at runtime on the GPU from four separate layers (bare metal, a colour")
    print("mask, a wear map, and ambient occlusion), reading the paint pattern from an")
    print("attached item attribute this tool has no access to. 'Copy another item's")
    print("textures' will pull that weapon's plain, unpainted stock material — not")
    print("any war paint pattern — even if you pick a war-painted weapon as the source.")

    kind = choose("What are you reskinning?",
                  ["weapon", "cosmetic"],
                  ["A weapon", "A cosmetic (hat / misc)"])
    target_class = kind

    if kind == "weapon":
        target = search_and_pick_weapons(pak, "the weapon to reskin", "all", "all", index)
    else:
        target = search_and_pick(pak, "the cosmetic to reskin", "all", index)
    target_label = display_name(target, index)

    src_mode = choose("Where do the new materials come from?",
                      ["disk", "ingame"],
                      ["Import a reskin folder from disk (Gamebanana / custom)",
                       "Copy another in-game item's textures (best effort)"])
    try:
        if src_mode == "disk":
            folder = _ask_folder("Path to the reskin folder (the one containing 'materials')")
            mats = material.read_disk_material_set(folder)
            source_clean = os.path.basename(os.path.normpath(folder))
        else:
            if kind == "weapon":
                src_item = search_and_pick_weapons(pak, "the item whose textures to copy", "all", "all", index)
            else:
                src_item = search_and_pick(pak, "the item whose textures to copy", "all", index)
            tex_pak = material.open_textures_pak(tf2_path)
            src_model = core.source_from_vpk(pak, src_item[:-4])
            mats = material.resolve_item_materials(tex_pak, pak, src_model.get(".mdl", b""))
            source_clean = display_name(src_item, index)
            if not mats:
                print("\n  Could not resolve that item's materials from the VPKs.")
                print("  This path is best-effort and needs validation against the")
                print("  real game archive. Try the disk import option instead.")
                return
    except core.SwapError as e:
        print(f"  {e}")
        return

    verdict = material.validate_material_set(mats, target_class=target_class)
    if not _report_verdict(verdict):
        return

    preview = material.preview_material_swap(verdict.safe_files)
    print(f"\n  Preview: {preview['vmt_count']} material(s), "
          f"{preview['vtf_count']} texture(s), {fmt_size(preview['total_size'])}")
    if input("\nProceed? (y/n): ").strip().lower() not in ("y", "yes"):
        sys.exit("Cancelled.")

    fname = sanitize_filename(f"{target_label} reskin ({source_clean}){SIGNATURE}.vpk")
    where = choose("Save to",
                   ["default", "custom"],
                   [f"Output folder as a VPK  ({OUTPUT_DIR})", "Custom path"])
    out_path = os.path.join(OUTPUT_DIR, fname)
    if where == "custom":
        raw = input("Enter a path (file or folder): ").strip().strip("'\"")
        if raw and not has_invalid_path_chars(raw):
            cand = resolve_out_path(raw, fname)
            valid, reason = validate_output_path(cand)
            if valid:
                out_path = cand
            else:
                print(f"  That path isn't writable ({reason}); using the output folder.")
        elif raw:
            print("  Invalid characters in path; using the output folder.")

    result = material.build_material_only(verdict.safe_files, out_path)
    print(f"\nSaved VPK: {result['out_path']}")
    print("Drag it onto the Casual Preloader, tick it, hit Install.")
    log.info(f"Built material swap '{out_path}' ({source_clean} reskin on {target_label})")


# ---------- interactive: map prop swap ----------

def search_and_pick_props(pak, what):
    """Search world props by keyword and pick one. Mirrors the other pickers."""
    while True:
        kw_raw = input(f"\nSearch for {what} (keyword, q to quit): ").strip()
        if kw_raw.lower() == "q":
            sys.exit("Cancelled.")
        if not kw_raw:
            print("  Please enter a keyword.")
            continue
        kw = normalize_keyword(kw_raw)
        hits = core.find_props(pak, kw)
        if not hits:
            print(f"  No props found for '{kw_raw}'.")
            continue
        labels = [h[7:-4] if h.startswith("models/") else h[:-4] for h in hits]
        if len(hits) == 1:
            print(f"  Auto-selected: {labels[0]}")
            return hits[0]
        if len(hits) > 40:
            print(f"  ({len(hits)} matches - showing first 40, refine your keyword for fewer)")
            hits, labels = hits[:40], labels[:40]
        print(f"\n  Matches for '{kw_raw}':")
        return choose("  Pick prop", hits, labels)


def interactive_prop_swap(pak, index, preloader_dir):
    """
    Map prop swap: replace one world prop MODEL with another, either from
    TF2's own catalog or imported from disk (e.g. a custom prop download).
    This reuses the model-swap pipeline; only the search/source differs.

    Disk-imported materials go through the exact same safety check as a
    disk-imported cosmetic or weapon (see get_disk_source()) — passing
    target_class="prop" tells validate_material_set() this is a complete
    new asset being imported, not a retexture of something already placed
    in a map, so its own bundled materials are scanned and allowed rather
    than skipped outright (see tf2_material.validate_material_set()'s
    docstring for the prop-specific reasoning). A malicious $ignorez/etc.
    material bundled with a custom prop download is still refused exactly
    like it would be for a cosmetic or weapon.

    Prop material swaps of an EXISTING in-game prop are still intentionally
    not offered anywhere in this tool — that's the actual see-through-prop
    wallhack vector (retexturing something already placed in a map), kept
    out of scope project-wide. This is a different thing: importing a
    whole new prop model (and its own materials, if it has any) to use as
    a replacement.
    """
    print("\n--- New map prop swap ---\n")
    print("Swaps one world prop model for another (e.g. a crate for a barrel).")
    print("Notes:")
    print("  - sv_pure rejects non-whitelisted prop models in matchmaking.")
    print("  - Replacing a large prop with a much smaller or empty one can open")
    print("    a sightline. Keep replacements similar in size to play fair.\n")

    target = search_and_pick_props(pak, "the prop to replace")
    dst_base = target[:-4]
    target_label = os.path.basename(target)[:-4]

    how = choose("Where's the replacement prop from?",
                 ["builtin", "disk"],
                 ["TF2's built-in props", "Import a model from disk (custom)"])

    material_files = None
    if how == "builtin":
        source = search_and_pick_props(pak, "the replacement prop model")
        src_base = source[:-4]
        model_files = core.source_from_vpk(pak, src_base)
        src_label = os.path.basename(source)[:-4]
    else:
        mdl_path = ask_disk_model()
        model_files, material_files = get_disk_source(mdl_path, target_class="prop")
        src_label = os.path.basename(mdl_path)[:-4]

    if ".mdl" not in model_files:
        print("  That source prop has no usable model files.")
        return

    # Read the target's own .mdl bytes purely for the size comparison below —
    # the swap itself only needs the target's archive path (dst_base), but
    # checking whether this is a substantial size change needs its actual
    # geometry. See core.prop_size_warning() for the fairness reasoning.
    target_model_files = core.source_from_vpk(pak, dst_base)
    size_warn = core.prop_size_warning(
        model_files.get(".mdl"), target_model_files.get(".mdl"))
    if size_warn:
        print(f"\n  Heads-up: {size_warn}")

    preview = core.preview_build(model_files, dst_base, material_files)
    summary = f"{preview['model_count']} model file(s), {fmt_size(preview['total_size'])}"
    if preview["material_count"]:
        summary += f" + {preview['material_count']} material(s)"
    print(f"\n  Replace : {target_label}")
    print(f"  With    : {src_label}")
    print(f"  Preview : {summary}")
    if input("\nProceed? (y/n): ").strip().lower() not in ("y", "yes"):
        sys.exit("Cancelled.")

    fname = sanitize_filename(f"{target_label} prop swap ({src_label}){SIGNATURE}.vpk")
    addon_name = fname[:-4]
    opts, labels = ["default"], [f"Output folder as a VPK  ({OUTPUT_DIR})"]
    if os.path.isdir(preloader_dir):
        opts.append("preloader")
        labels.append("Preloader addons folder (installed format)")
    opts.append("custom")
    labels.append("Custom path")

    where = choose("Save to", opts, labels)
    if where == "preloader":
        if confirm_preloader_write(preloader_dir):
            emit_addon(model_files, dst_base, preloader_dir, addon_name, material_files, src_label, target_label)
    elif where == "custom":
        raw = input("Enter a path (file or folder): ").strip().strip("'\"")
        if not raw:
            emit_vpk(model_files, dst_base, os.path.join(OUTPUT_DIR, fname), material_files, src_label, target_label)
        elif is_in_preloader(raw, preloader_dir):
            if confirm_preloader_write(preloader_dir):
                emit_addon(model_files, dst_base, preloader_dir, addon_name, material_files, src_label, target_label)
        elif has_invalid_path_chars(raw):
            print("  That path contains invalid characters — saving to output folder instead.")
            emit_vpk(model_files, dst_base, os.path.join(OUTPUT_DIR, fname), material_files, src_label, target_label)
        else:
            out_path = resolve_out_path(raw, fname)
            valid, reason = validate_output_path(out_path)
            if not valid:
                print(f"  That path isn't writable: {reason}")
                print(f"  Saving to output folder instead.")
                out_path = os.path.join(OUTPUT_DIR, fname)
            emit_vpk(model_files, dst_base, out_path, material_files, src_label, target_label)
    else:
        emit_vpk(model_files, dst_base, os.path.join(OUTPUT_DIR, fname), material_files, src_label, target_label)


# ---------- interactive: manage made mods ----------

def manage_mods(index):
    """
    Interactive loop for listing and deleting previously built mod archives.

    Re-scans the output directory on each iteration so the list updates
    immediately after a deletion rather than showing stale numbers.

    Root-level mods and mods in subdirectories are displayed in separate
    groups but share a single continuous numbering so the user can select
    either by number. The loop continues until the user types 'q'.
    """
    while True:
        mods = core.list_output_mods(OUTPUT_DIR)
        if not mods:
            print(f"\nNo mods found in {OUTPUT_DIR}")
            return

        root_mods = [m for m in mods if not m["in_subfolder"]]
        sub_mods = [m for m in mods if m["in_subfolder"]]
        all_displayed = []  # Single combined list for number-based selection

        print(f"\nMods you've built ({OUTPUT_DIR}):")
        for m in root_mods:
            all_displayed.append(m)
            tgt = display_name(m["target_stem"], index) if m["target_stem"] else "unknown target"
            print(f"  {len(all_displayed)}. {m['name']}")
            print(f"       replaces: {tgt}")

        if sub_mods:
            print(f"\n  In subfolders:")
            for m in sub_mods:
                all_displayed.append(m)
                tgt = display_name(m["target_stem"], index) if m["target_stem"] else "unknown target"
                print(f"  {len(all_displayed)}. {m['rel']}")
                print(f"       replaces: {tgt}")

        raw = input("\nEnter a number to remove, or q to go back: ").strip().lower()
        if raw == "q":
            return
        if raw.isdigit() and 1 <= int(raw) <= len(all_displayed):
            chosen = all_displayed[int(raw) - 1]
            if input(f"Delete '{chosen['name']}'? (y/n): ").strip().lower() in ("y", "yes"):
                core.remove_file(chosen["path"])
                print("Removed.")
                log.info(f"Removed mod: {chosen['path']}")
        else:
            print("Invalid choice.")


# ---------- interactive: list installed addons ----------

def show_installed(preloader_dir):
    """
    Display a list of TF2autoswap addons present in the Casual Preloader folder.

    Separates native addon folders (the preloader's own format, used when we
    write directly to the preloader) from loose VPK archive files (placed
    manually and potentially not yet imported by the preloader).

    Ends with a reminder that this reflects disk contents, not the preloader's
    internal enabled/disabled state — a mod being listed here does not mean it
    is currently active in the game.
    """
    try:
        entries = core.list_preloader_addons(preloader_dir, SIGNATURE)
    except core.SwapError as e:
        print(f"\n{e}")
        print("Set the folder with --preloader, or check the preloader is installed.")
        return
    if not entries:
        print(f"\nNothing found in {preloader_dir}")
        return

    ours = [e for e in entries if e["kind"] == "addon" and e["is_ours"]]
    vpks = [e for e in entries if e["kind"] == "vpk"]

    if not ours and not vpks:
        print(f"\nNo {PROJECT} addons or loose .vpk files found.")
        return

    if ours:
        print(f"\n{PROJECT} addons installed ({len(ours)}):")
        for a in ours:
            print(f"  {a['rel']}")
    if vpks:
        print(f"\nLoose .vpk files (not imported by the preloader):")
        for v in vpks:
            mark = f"   <- {PROJECT}" if v["is_ours"] else ""
            print(f"  {v['rel']}{mark}")

    print("\n(Note: this shows what's present in the folder, not which are")
    print(" enabled or disabled inside the preloader.)")


INVENTORY_DEBUG_REPORT_PATH = os.path.join(_SCRIPT_DIR, "inventory_debug_report.txt")


def show_inventory_diagnosis(tf2_path, pak, inventory_path):
    """
    CLI troubleshooting helper for --debug-inventory: loads an inventory
    JSON file and reports, per owned item, exactly why it does or doesn't
    show up as a usable swap source/target. See core.diagnose_owned_items()
    for what each status means and the likely cause for weapons (
    / War Paint items not carrying resolvable model data).

    Needs the defindex schema index — built/cached the same way as
    load_index(), via load_defindex_index().

    Output goes three places: the terminal (as before), a standalone report
    file (INVENTORY_DEBUG_REPORT_PATH, overwritten each run — easy to open,
    copy, or attach when asking for help), and a one-line summary in the
    main log file alongside the tool's other logged operations.
    """
    defindex_index = load_defindex_index(tf2_path)
    if defindex_index is None:
        print("Schema unavailable — can't diagnose without it.")
        return

    try:
        items = core.load_inventory_file(os.path.expanduser(inventory_path))
    except core.InventoryError as e:
        print(f"Couldn't load inventory file: {e}")
        return

    rows = core.diagnose_owned_items(items, defindex_index, pak)
    usable = sum(1 for r in rows if r["usable"])
    not_in_schema = sum(1 for r in rows if not r["in_schema"])
    no_model = sum(1 for r in rows if r["in_schema"] and not r["stems"])

    lines = [f"{len(rows)} owned items in file, {usable} usable as a swap source/target.", ""]
    for r in rows:
        if r["usable"]:
            status = "OK"
        elif not r["in_schema"]:
            status = "NOT IN SCHEMA"
        elif not r["stems"]:
            status = "NO MODEL DATA IN SCHEMA"
        else:
            status = "SCHEMA STEM(S) NOT IN VPK"
        if r["name_hint"] and r["schema_name"]:
            label = core.display_name_with_actual(r["name_hint"], r["schema_name"])
        else:
            label = r["name_hint"] or r["schema_name"] or f"defindex {r['defindex']}"
        lines.append(f"  [{status:24s}] {label}  (defindex {r['defindex']}, "
                      f"quality {r['quality']}, slot={r['item_slot']})")
        if status == "SCHEMA STEM(S) NOT IN VPK":
            lines.append(f"      schema stems: {r['stems']}")

    if not_in_schema or no_model:
        lines.append("")
        lines.append(f"  {not_in_schema} item(s) not found in the schema at all, "
                      f"{no_model} found but with no model data listed.")
        lines.append("  If most of your weapons fall in one of those two buckets, that's "
                      "consistent with War Paint weapons not carrying resolvable "
                      "model data the same way stock-model weapons do (see the v4.75 "
                      "war paint roadmap note) — not a bug in the matching logic itself.")

    print()
    for line in lines:
        print(line)

    try:
        with open(INVENTORY_DEBUG_REPORT_PATH, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print(f"\n(Full report also written to {INVENTORY_DEBUG_REPORT_PATH})")
    except Exception as e:
        print(f"\n(Couldn't write report file: {e})")

    log.info(
        f"Inventory diagnosis run on '{inventory_path}': "
        f"{len(rows)} items, {usable} usable, {not_in_schema} not in schema, "
        f"{no_model} in schema with no model data. Full report: {INVENTORY_DEBUG_REPORT_PATH}"
    )


# ---------- interactive: changelog viewer ----------

CHANGELOG_PATH = os.path.join(_SCRIPT_DIR, "CHANGELOG.md")


def _split_changelog_entries(text):
    """
    Parse CHANGELOG.md text into a list of (version_header, body) tuples.

    The changelog uses Markdown heading level 2 (lines starting with '## ')
    to mark the start of each version entry. This function splits on those
    headings, collecting the body text between them.

    Returns entries in the order they appear in the file (newest first, by
    convention in this project's changelog).
    """
    entries = []
    current_header, current_lines = None, []
    for line in text.splitlines():
        if line.startswith("## "):
            # A new version heading — save the previous entry if one exists
            if current_header:
                entries.append((current_header, "\n".join(current_lines).strip()))
            current_header, current_lines = line[3:].strip(), []
        elif current_header:
            current_lines.append(line)
    # Append the final entry after the loop ends (no trailing heading to trigger it)
    if current_header:
        entries.append((current_header, "\n".join(current_lines).strip()))
    return entries


def show_changelog():
    """
    Display the changelog in a paginated terminal format.

    Inspired by Arch Linux's package manager (pacman), which shows news relevant
    to the current update immediately on upgrade, then offers to show older history.

    Behaviour:
    - Shows the current version's entry immediately
    - Offers to page through older entries one at a time if more exist
    - Falls back gracefully if CHANGELOG.md is missing, unreadable, or empty

    This approach means routine users see a quick summary of what changed in
    the version they are running, without being overwhelmed by the full history.
    """
    if not os.path.isfile(CHANGELOG_PATH):
        print("\nCHANGELOG.md not found beside the tool — see the GitHub wiki instead.")
        return
    try:
        with open(CHANGELOG_PATH, encoding="utf-8", errors="replace") as f:
            entries = _split_changelog_entries(f.read())
    except Exception as e:
        print(f"\nCouldn't read the changelog: {e}")
        return
    if not entries:
        print("\nThe changelog appears to be empty.")
        return

    # Find this version's entry; fall back to the first (newest) entry if not found
    current = next((e for e in entries if VERSION in e[0]), entries[0])
    print(f"\n--- {current[0]} ---\n")
    print(current[1])

    if len(entries) > 1:
        raw = input("\nShow full version history? (y/n): ").strip().lower()
        if raw in ("y", "yes"):
            for header, body in entries:
                if header == current[0]:
                    continue  # Already shown above — skip it in the history loop
                print(f"\n--- {header} ---\n")
                print(body)
                nxt = input("\n(Enter for next, q to stop): ").strip().lower()
                if nxt == "q":
                    break


# ---------- interactive entry ----------

def interactive(pak, index, defindex_index, preloader_dir, tf2_path):
    """
    Main interactive menu, shown when the tool is run with no command-line arguments.

    Displays the current version number and a one-line summary of what is new
    in this release before the option list, so returning users can see at a
    glance what changed without needing to check separately.

    This loops rather than running once, specifically so "Load inventory
    from file" can cache the result in memory and return to the menu —
    letting a swap started afterward use that cache at both the TARGET and
    SOURCE steps without asking for the file path twice. Every other action
    still exits after completing, same as before; the loop only continues
    automatically after a successful inventory load. Nothing here is ever
    written to disk — the cache is a plain in-memory variable for the
    current run only.

    defindex_index supports own-inventory mode generally — see
    load_defindex_index() and pick_from_inventory(). It may be None if the
    schema could not be loaded; own-inventory mode is simply skipped in that
    case, same as friendly names are skipped elsewhere.

    The skin/material and prop swap options only appear when tf2_material
    is available (HAVE_MATERIAL) — see that module's docstring. tf2_path is
    threaded through from run()'s already-resolved TF2 path, needed by
    interactive_skin_swap()'s "copy another item's textures" source mode.
    """
    owned_items_cache = None

    while True:
        print(f"\n=== {PROJECT} v{VERSION} ===")
        print(f"  What's new: {WHATS_NEW}")
        if owned_items_cache is not None:
            print(f"  Inventory loaded: {len(owned_items_cache)} items "
                  f"(available for target/source picks this session)")

        opts = ["swap", "weapon"]
        labels = ["Create a cosmetic swap", "Create a weapon swap"]
        if HAVE_MATERIAL:
            opts += ["skin", "prop"]
            labels += [
                      "Create a skin / material swap",
                      "Create a map prop swap"]
        opts += ["mods", "installed", "loadinv", "changelog"]
        labels += ["List / remove mods I've made",
                   "List addons in the preloader folder",
                   "Load inventory from file" + (" (reload)" if owned_items_cache else ""),
                   "What's changed in this version"]
        action = choose("\nWhat would you like to do?", opts, labels)

        if action == "swap":
            print("\nSelected: Cosmetic swap")
            interactive_swap(pak, index, defindex_index, preloader_dir, owned_items_cache)
            return
        elif action == "weapon":
            print("\nSelected: Weapon swap")
            interactive_weapon_swap(pak, index, defindex_index, preloader_dir, owned_items_cache)
            return
        elif action == "skin":
            print("\nSelected: Skin / material swap")
            interactive_skin_swap(pak, index, preloader_dir, tf2_path)
            return
        elif action == "prop":
            print("\nSelected: Map prop swap")
            interactive_prop_swap(pak, index, preloader_dir)
            return
        elif action == "mods":
            manage_mods(index)
            return
        elif action == "loadinv":
            items = load_owned_items_interactive()
            if items is not None:
                owned_items_cache = items
            # Loop back to the menu either way — a failed load just means
            # the inventory option stays unavailable, not a hard exit.
            continue
        elif action == "changelog":
            show_changelog()
            return
        else:
            show_installed(preloader_dir)
            return


# ---------- CLI mode ----------

def cli(pak, index, args):
    """
    Non-interactive cosmetic swap, triggered by passing source and target keywords
    as command-line arguments.

    The character class filter (--filter) is applied to the target item search as
    well as the source, for consistency. If the filter narrows the target search
    to zero results, a second unfiltered search is attempted — a very specific
    keyword should not silently fail just because a filter is active.

    Supports --dry-run to preview the output without writing any files, and routes
    to either VPK or native addon folder output based on the --out and
    --to-preloader flags.
    """
    # Apply class filter to target with unfiltered fallback
    dst = core.find_models(pak, args.target, args.cls)
    if not dst:
        dst = core.find_models(pak, args.target)
    if not dst:
        raise core.ModelNotFound(f"Nothing found for target '{args.target}' (try --list)")
    target_mdl = dst[0]
    dst_base = target_mdl[:-4]

    if args.import_path:
        # Source is a locally stored mod file (e.g. downloaded from Gamebanana)
        model_files, material_files = get_disk_source(os.path.expanduser(args.import_path), target_class="cosmetic")
        src_label = os.path.basename(args.import_path)[:-4]
        source_clean = src_label
        src_base = None  # No archive path, so no schema-based warnings available
    else:
        # Source is a built-in game item from the archive
        src = core.find_models(pak, args.source, args.cls)
        if not src:
            raise core.ModelNotFound(f"Nothing found for source '{args.source}' (try --list)")
        src_base = src[0][:-4]
        model_files = core.source_from_vpk(pak, src_base)
        material_files = None
        src_label = args.source
        source_clean = display_name(src[0], index)

    print(f"Source : {src_label}\nTarget : {dst_base}")
    if src_base:
        warn = clip_warning(index, src_base, dst_base)
        if warn:
            print(f"\n  Heads-up: {warn}")
    print()

    if args.dry_run:
        # Preview mode: show what would be built without writing any files
        preview = core.preview_build(model_files, dst_base, material_files)
        print("DRY RUN — nothing will be written.\n")
        for e in preview["entries"]:
            print(f"  {e['ext']:12s}  {e['size']:>10,} bytes")
        print(f"\n  Total: {len(preview['entries'])} file(s), {fmt_size(preview['total_size'])}")
        fname = output_filename(target_mdl, source_clean, index)
        if args.to_preloader:
            dest = os.path.join(args.preloader_dir, fname[:-4])
            print(f"  Would install as addon to: {dest}")
        elif args.out:
            if has_invalid_path_chars(args.out):
                print(f"  Would save VPK to: {os.path.join(OUTPUT_DIR, fname)}  (invalid chars in path — using output folder)")
            else:
                print(f"  Would save VPK to: {resolve_out_path(args.out, fname)}")
        else:
            print(f"  Would save VPK to: {os.path.join(OUTPUT_DIR, fname)}")
        return

    fname = output_filename(target_mdl, source_clean, index)
    addon_name = fname[:-4]
    if args.to_preloader:
        if confirm_preloader_write(args.preloader_dir):
            emit_addon(model_files, dst_base, args.preloader_dir, addon_name, material_files, src_label, args.target)
    elif args.out and is_in_preloader(args.out, args.preloader_dir):
        if confirm_preloader_write(args.preloader_dir):
            emit_addon(model_files, dst_base, args.preloader_dir, addon_name, material_files, src_label, args.target)
    elif args.out:
        if has_invalid_path_chars(args.out):
            print("  That path contains invalid characters — saving to output folder instead.")
            emit_vpk(model_files, dst_base, os.path.join(OUTPUT_DIR, fname), material_files, src_label, args.target)
        else:
            emit_vpk(model_files, dst_base, resolve_out_path(args.out, fname), material_files, src_label, args.target)
    else:
        emit_vpk(model_files, dst_base, os.path.join(OUTPUT_DIR, fname), material_files, src_label, args.target)


# ---------- CLI: weapon mode ----------

def cli_weapon(pak, index, args):
    """
    Non-interactive weapon swap, triggered by source/target keywords plus --weapon,
    or tf2autoswap.py --import path/to/c_thing.mdl <target> --weapon for a
    disk-imported source (worldmodel auto-detected via
    core.find_disk_weapon_worldmodel() — see that function's docstring).

    Mirrors cli() but uses weapon-specific search and build functions. Reads both
    the first-person viewmodel and the third-person worldmodel for the source weapon,
    and resolves the correct destination archive paths for both before building.

    See interactive_weapon_swap() for a full explanation of viewmodel vs worldmodel
    and why both must be swapped together.
    """
    dst = core.find_weapons(pak, args.target)
    if not dst:
        raise core.ModelNotFound(f"Nothing found for target weapon '{args.target}' (try --list --weapon)")
    target_mdl = dst[0]
    dst_view_base = target_mdl[:-4]
    dst_world_base = core.resolve_world_base_from_vpk(pak, dst_view_base)

    material_files = None
    if args.import_path:
        view_mdl_path = os.path.expanduser(args.import_path)
        view_files, material_files = get_disk_source(view_mdl_path, target_class="weapon")
        src_label = os.path.basename(view_mdl_path)[:-4]
        source_clean = src_label
        src_view_base = None  # no archive path, so no schema-based slot-mismatch warning available

        world_files = {}
        world_mdl_path = core.find_disk_weapon_worldmodel(view_mdl_path)
        if world_mdl_path:
            print(f"Found matching worldmodel: {os.path.basename(world_mdl_path)}")
            world_files, world_material_files = get_disk_source(world_mdl_path, target_class="weapon")
            material_files.update(world_material_files)
        else:
            print("No matching worldmodel found alongside the viewmodel (normal for melee weapons).")
    else:
        src = core.find_weapons(pak, args.source)
        if not src:
            raise core.ModelNotFound(f"Nothing found for source weapon '{args.source}' (try --list --weapon)")
        src_view_base = src[0][:-4]
        view_files, world_files, src_world_base = core.source_from_vpk_weapon(pak, src_view_base)
        src_label = args.source
        source_clean = display_name(src[0], index)

    print(f"Source : {src_label}\nTarget : {dst_view_base}")
    if src_view_base:
        warn = weapon_warning(index, src_view_base, dst_view_base)
        if warn:
            print(f"\n  Heads-up: {warn}")
    print()

    if args.dry_run:
        preview = core.preview_build_weapon(view_files, world_files, dst_view_base, dst_world_base or "")
        print("DRY RUN — nothing will be written.\n")
        for e in preview["entries"]:
            print(f"  {e['ext']:20s}  {e['size']:>10,} bytes")
        print(f"\n  Total: {len(preview['entries'])} file(s), {fmt_size(preview['total_size'])}")
        if material_files:
            print(f"  + {len(material_files)} material(s)")
        fname = output_filename(target_mdl, source_clean, index)
        if args.to_preloader:
            print(f"  Would install as addon to: {os.path.join(args.preloader_dir, fname[:-4])}")
        elif args.out:
            if has_invalid_path_chars(args.out):
                print(f"  Would save VPK to: {os.path.join(OUTPUT_DIR, fname)}  (invalid chars in path — using output folder)")
            else:
                print(f"  Would save VPK to: {resolve_out_path(args.out, fname)}")
        else:
            print(f"  Would save VPK to: {os.path.join(OUTPUT_DIR, fname)}")
        return

    fname = output_filename(target_mdl, source_clean, index)
    addon_name = fname[:-4]

    world_note = None
    if not world_files:
        dst_info = tf2_schema.lookup(index, dst_view_base) if (index and HAVE_SCHEMA) else None
        if dst_info and dst_info.item_slot == "melee":
            world_note = "melee weapons typically don't have separate world models — viewmodel only is expected"
        else:
            world_note = "no world model found — viewmodel only"

    if args.to_preloader:
        if confirm_preloader_write(args.preloader_dir):
            emit_weapon_addon(view_files, world_files, dst_view_base, dst_world_base, args.preloader_dir, addon_name, src_label, args.target, world_note, material_files)
    elif args.out and is_in_preloader(args.out, args.preloader_dir):
        if confirm_preloader_write(args.preloader_dir):
            emit_weapon_addon(view_files, world_files, dst_view_base, dst_world_base, args.preloader_dir, addon_name, src_label, args.target, world_note, material_files)
    elif args.out:
        if has_invalid_path_chars(args.out):
            print("  That path contains invalid characters — saving to output folder instead.")
            emit_weapon_vpk(view_files, world_files, dst_view_base, dst_world_base, os.path.join(OUTPUT_DIR, fname), src_label, args.target, world_note, material_files)
        else:
            emit_weapon_vpk(view_files, world_files, dst_view_base, dst_world_base, resolve_out_path(args.out, fname), src_label, args.target, world_note, material_files)
    else:
        emit_weapon_vpk(view_files, world_files, dst_view_base, dst_world_base, os.path.join(OUTPUT_DIR, fname), src_label, args.target, world_note, material_files)


# ---------- CLI: prop mode ----------

def cli_prop(pak, index, args):
    """
    Scripted map prop swap: tf2autoswap.py <source> <target> --prop, or
    tf2autoswap.py --import path/to/thing.mdl <target> --prop for a
    disk-imported source. Reuses the model-swap build path; only the
    search/source is prop-scoped. See interactive_prop_swap()'s docstring
    for why disk-imported prop materials use target_class="prop".
    """
    dst = core.find_props(pak, args.target)
    if not dst:
        raise core.ModelNotFound(f"No prop found for target '{args.target}'")
    dst_base = dst[0][:-4]
    target_label = os.path.basename(dst[0])[:-4]

    material_files = None
    if args.import_path:
        model_files, material_files = get_disk_source(os.path.expanduser(args.import_path), target_class="prop")
        src_label = os.path.basename(args.import_path)[:-4]
    else:
        src = core.find_props(pak, args.source)
        if not src:
            raise core.ModelNotFound(f"No prop found for source '{args.source}'")
        src_base = src[0][:-4]
        model_files = core.source_from_vpk(pak, src_base)
        src_label = os.path.basename(src[0])[:-4]

    if ".mdl" not in model_files:
        raise core.BuildError("That source prop has no usable model files.")

    print(f"Source : {src_label}\nTarget : {target_label}")
    print("  Note: sv_pure rejects non-whitelisted prop models in matchmaking.")
    target_model_files = core.source_from_vpk(pak, dst_base)
    size_warn = core.prop_size_warning(model_files.get(".mdl"), target_model_files.get(".mdl"))
    if size_warn:
        print(f"  Heads-up: {size_warn}")

    fname = sanitize_filename(f"{target_label} prop swap ({src_label}){SIGNATURE}.vpk")
    if args.dry_run:
        preview = core.preview_build(model_files, dst_base, material_files)
        summary = f"{preview['model_count']} file(s), {fmt_size(preview['total_size'])}"
        if preview["material_count"]:
            summary += f" + {preview['material_count']} material(s)"
        print(f"\nDRY RUN - {summary}")
        print(f"  Would save VPK to: {os.path.join(OUTPUT_DIR, fname)}")
        return

    if args.to_preloader and confirm_preloader_write(args.preloader_dir):
        emit_addon(model_files, dst_base, args.preloader_dir, fname[:-4], material_files, src_label, target_label)
    elif args.out and not has_invalid_path_chars(args.out):
        emit_vpk(model_files, dst_base, resolve_out_path(args.out, fname), material_files, src_label, target_label)
    else:
        emit_vpk(model_files, dst_base, os.path.join(OUTPUT_DIR, fname), material_files, src_label, target_label)


# ---------- entry ----------

def run():
    """
    Parse command-line arguments and route to the appropriate function.

    If source and target keywords are present (or --import and a target), routes
    to the non-interactive CLI swap functions. Otherwise opens the interactive menu.

    Routing priority:
    1. --list-installed: list Casual Preloader addons — does not need the game archive
    2. --list-mods: list built output files — needs schema for names, not the archive
    3. --list: search items without building — needs the archive open
    4. source + target (or --import + target): non-interactive swap
    5. No arguments: interactive menu
    """
    ap = argparse.ArgumentParser(description=f"{PROJECT} — swap TF2 cosmetics, client-side")
    ap.add_argument("--version", action="version", version=f"{PROJECT} {VERSION}")
    ap.add_argument("source", nargs="?", help="keyword of the item to use as the replacement")
    ap.add_argument("target", nargs="?", help="keyword of the item to replace")
    ap.add_argument("--weapon", action="store_true", help="swap weapons instead of cosmetics")
    ap.add_argument("--prop", action="store_true", help="map prop model swap mode")
    ap.add_argument("--skin", action="store_true", help="skin / material swap mode (interactive only)")
    ap.add_argument("--filter", dest="cls", help="restrict to items for a specific class (e.g. pyro)")
    ap.add_argument("--import", dest="import_path", help="use a local .mdl file as the replacement source")
    ap.add_argument("--out", help="custom output path (file or folder)")
    ap.add_argument("--to-preloader", action="store_true", help="write directly to the Casual Preloader addons folder")
    ap.add_argument("--dry-run", action="store_true", help="show what would be built without writing any files")
    ap.add_argument("--list", action="store_true", help="search for items without building anything")
    ap.add_argument("--list-mods", action="store_true", help="list previously built mods")
    ap.add_argument("--list-installed", action="store_true", help="list addons in the Casual Preloader folder")
    ap.add_argument("--debug-inventory", metavar="JSONFILE",
                     help="diagnose why items in an inventory JSON file aren't matching as swap sources")
    ap.add_argument("--preloader", help="override the Casual Preloader addons folder path")
    ap.add_argument("--tf2", help="override the TF2 installation tf/ directory path")
    ap.add_argument("--cake", action="store_true", help=argparse.SUPPRESS)  # Hidden easter egg
    args = ap.parse_args()

    if args.cake:
        print("""
               i
              (|)
         ..--""|""--..
      .'   (@) | (@)    '.
     (  (@)    '    (@)   )
      '..   (@)   (@)  ..'
      |  ''--......--''  |
      | ~  ~  ~  ~  ~  ~ |
      |__________________|
       '-..__________..-'

  The cake is a lie.
  ~ Cake - Powered by OpenRouter ~
""")
        sys.exit("Cancelled.")

    preloader_dir = os.path.expanduser(args.preloader) if args.preloader else PRELOADER_ADDONS
    # Attach the resolved preloader path to args so sub-functions can access it
    args.preloader_dir = preloader_dir

    # --list-installed does not need TF2 or the game archive — run immediately
    if args.list_installed:
        show_installed(preloader_dir)
        return

    tf2 = core.resolve_tf2(args.tf2)
    print(f"TF2 found: {tf2}")

    # --list-mods needs the schema for friendly names but not the game archive
    if args.list_mods:
        index = load_index(tf2)
        manage_mods_readonly(index)
        return

    # Open the game archive — needed for all remaining operations
    pak = core.open_pak(tf2)

    if args.debug_inventory:
        show_inventory_diagnosis(tf2, pak, args.debug_inventory)
        return

    if args.list:
        # Search and display items without building any output files
        index = load_index(tf2)
        for kw_raw in (args.source, args.target):
            if not kw_raw:
                continue
            kw = normalize_keyword(kw_raw)
            print(f"\n{kw_raw}:")
            if args.weapon:
                hits = core.find_weapons(pak, kw)
                for h in hits:
                    print(f"  {label_for_weapon(h, index)}")
            else:
                hits = core.find_models(pak, kw, args.cls)
                for h in hits:
                    print(f"  {label_for(h, index)}")
            if not hits:
                print("  (nothing found)")
        return

    # Handle the --import shorthand: 'tf2autoswap.py --import file.mdl keyword'
    # The argument parser sees source=keyword, target=None — swap them here
    if args.import_path and args.source and not args.target:
        args.target = args.source
        args.source = None

    index = load_index(tf2)

    # --skin and --prop modes. --skin is interactive-only (it needs folder
    # browsing and the safety verdict displayed step by step), so it always
    # routes to the interactive flow regardless of other arguments. --prop
    # accepts source and target keywords for scripted use, falling through
    # to the interactive picker if either is missing.
    if args.skin:
        if not HAVE_MATERIAL:
            print("Skin / material swap needs tf2_material.py beside this script.")
            return
        interactive_skin_swap(pak, index, preloader_dir, tf2)
        return
    if args.prop:
        if not HAVE_MATERIAL:
            print("Prop swap needs tf2_material.py beside this script.")
            return
        if args.target and (args.source or args.import_path):
            cli_prop(pak, index, args)
        else:
            interactive_prop_swap(pak, index, preloader_dir)
        return

    if (args.import_path and args.target) or (args.source and args.target):
        # Enough arguments for a non-interactive swap
        if args.weapon:
            cli_weapon(pak, index, args)
        else:
            cli(pak, index, args)
    else:
        # Not enough arguments — open the interactive menu.
        # The defindex index (for own-inventory mode) is only built here,
        # not for CLI-arg swaps, since CLI mode has no own-inventory option yet.
        defindex_index = load_defindex_index(tf2)
        interactive(pak, index, defindex_index, preloader_dir, tf2)


def manage_mods_readonly(index):
    """
    CLI version of the mod list: displays built mods without the interactive
    delete loop. Used by the --list-mods flag.

    Separate from manage_mods() because the CLI version should print and exit
    without waiting for user input. Points the user to interactive mode if
    they want to delete any listed mods.
    """
    mods = core.list_output_mods(OUTPUT_DIR)
    if not mods:
        print(f"\nNo mods found in {OUTPUT_DIR}")
        return

    root_mods = [m for m in mods if not m["in_subfolder"]]
    sub_mods = [m for m in mods if m["in_subfolder"]]

    print(f"\nMods you've built ({OUTPUT_DIR}):")
    i = 1
    for m in root_mods:
        tgt = display_name(m["target_stem"], index) if m["target_stem"] else "unknown target"
        print(f"  {i}. {m['name']}")
        print(f"       replaces: {tgt}")
        i += 1
    if sub_mods:
        print(f"\n  In subfolders:")
        for m in sub_mods:
            tgt = display_name(m["target_stem"], index) if m["target_stem"] else "unknown target"
            print(f"  {i}. {m['rel']}")
            print(f"       replaces: {tgt}")
            i += 1
    print("\n(Run interactively — option 3 — to remove any of these.)")


# ---------- acknowledgement system ----------
# This block handles the first-run risk disclosure that users must accept before
# the tool proceeds. The accepted state is stored as a hashed flag file.

# Imported here rather than at the top of the file because it is used only in
# this section — keeping the import close to its usage makes the dependency clear.
import hashlib as _hashlib

# Path for the acknowledgement flag file in the hidden state directory
ACKNOWLEDGED_FLAG = os.path.join(STATE_DIR, ".acknowledged")

# The flag file stores a SHA256 cryptographic hash of a known string rather than
# plain text. This is NOT to conceal anything — the source code is publicly
# available and the string being hashed is documented here. The purpose is light
# tamper-resistance: a user cannot bypass the first-run prompt simply by creating
# a blank file or writing arbitrary text into the flag file location.
# The hash is deterministic and verifiable: hashlib.sha256(b"tf2autoswap_acknowledged").hexdigest()
_ACK_HASH = _hashlib.sha256(b"tf2autoswap_acknowledged").hexdigest()


def _hide_on_windows(path):
    """
    Set the Windows 'hidden' file attribute on a folder or file.

    On Linux and macOS, files and folders whose names begin with a dot are
    hidden by operating system convention and no further action is needed.
    On Windows, the hidden attribute must be set explicitly via the 'attrib'
    command-line utility.

    The CREATE_NO_WINDOW flag (integer value 0x08000000) prevents a brief
    console window from appearing when the subprocess is spawned.

    Failures are silently ignored — a visible state folder is inconvenient
    but does not affect any tool functionality.
    """
    if os.name == "nt":
        try:
            subprocess.run(["attrib", "+h", path], check=False,
                           creationflags=0x08000000)  # CREATE_NO_WINDOW
        except Exception:
            pass


INVENTORY_GUIDE_TEXT = """\
How to get your TF2 inventory file
===================================

This lets you pick swap sources/targets from items you actually own,
instead of searching TF2's whole catalog. The tool never contacts Steam
itself — you export the file yourself, and the tool only reads it locally.

1. Make sure your Steam inventory privacy is set to Public.
   (Steam > Settings > Privacy Settings > Inventory — this is separate
   from your overall profile privacy setting.)

2. Find your SteamID64 if you don't already know it:
   https://steamid.io  (paste your profile URL there)

3. While logged into Steam in your browser, visit this URL with your own
   SteamID64 in place of <steamid64>:

   https://steamcommunity.com/inventory/<steamid64>/440/2?l=english&count=5000

4. Save the page as a .json file:
   - Most browsers: Ctrl+S (Cmd+S on Mac). If asked, choose a "Page
     Source" / raw save option rather than "Webpage, Complete".
   - Alternative: select all the text on the page (Ctrl+A), copy it,
     paste into a plain text editor, and save it with a .json extension.

5. Drop the saved .json file in this folder (imports/inventory/).
   Next time you choose "Load inventory from file" in the tool, it'll
   offer this file automatically instead of asking for a path.

What this file contains, for your own peace of mind:
   Just your TF2 item list — names, qualities, and item IDs. It does NOT
   contain your Steam password, login session, or anything that could be
   used to access your account. It's safe to keep, delete, or share for
   troubleshooting without any account-security risk.

If you place more than one .json file here, the tool will ask you which
one to use.
"""


def write_inventory_guide():
    """
    Write the bundled how-to guide into imports/inventory/ if it isn't
    there already. Called from setup_folders() on every run; only writes
    when missing so a user's own notes added to the file aren't overwritten.
    Failure is silently ignored — same non-fatal approach as the rest of
    folder setup, the guide is a convenience, not a requirement.
    """
    try:
        if not os.path.isfile(INVENTORY_GUIDE_PATH):
            with open(INVENTORY_GUIDE_PATH, "w", encoding="utf-8") as f:
                f.write(INVENTORY_GUIDE_TEXT)
    except Exception:
        pass


def setup_folders():
    """
    Create the tool's working folder structure after the risk acknowledgement.
    Called once per run immediately after check_acknowledgement().

    Folders created:
    - STATE_DIR (.tf2autoswap/): hidden folder for internal tool state files
      (acknowledgement flag, item schema cache). Marked hidden on Windows.
    - IMPORTS_DIR subdirectories: organised drop zones where users place mod
      files before importing them. Created with descriptive subdirectory names
      so users immediately understand where each type of file belongs.
    - imports/inventory/ additionally gets a bundled how-to guide on first
      run (write_inventory_guide()), explaining how to export an inventory
      JSON file from Steam and drop it there for own-inventory mode.

    Folders NOT created here:
    - OUTPUT_DIR: created only on the first actual build, so a fresh installation
      has a clean folder structure with no empty placeholder folders.

    This function is idempotent (safe to call multiple times) — exist_ok=True
    means existing folders are left unchanged. This also makes the folder
    structure self-healing: if a user accidentally deletes a folder, it is
    recreated automatically on next run.

    Legacy cleanup: removes state files left in OUTPUT_DIR by versions before
    4.8 (when state was moved to the hidden STATE_DIR). Leaving them would
    cause the acknowledgement prompt to appear again on first run after updating.
    """
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        _hide_on_windows(STATE_DIR)
        for sub in IMPORT_SUBDIRS:
            os.makedirs(os.path.join(IMPORTS_DIR, sub), exist_ok=True)
        write_inventory_guide()
        # Remove pre-4.8 state files from the old location if they exist
        for legacy in (".acknowledged", "schema_cache.json"):
            p = os.path.join(OUTPUT_DIR, legacy)
            if os.path.isfile(p):
                os.remove(p)
                log.info(f"Removed legacy state file: {p}")
    except Exception as e:
        log.warning(f"Folder setup issue (non-fatal): {e}")


def check_acknowledgement():
    """
    First-run risk disclosure gate. Must complete before any other tool action.

    Background: TF2autoswap modifies how game assets appear to the local player
    by loading replacement files at game launch. While this is a common and
    accepted practice in the TF2 community, there are risks users should be
    aware of:

    - VAC (Valve Anti-Cheat): Valve's anti-cheat system monitors running game
      processes for software that modifies game behaviour. Client-side cosmetic
      mods are generally tolerated, but there is a non-zero risk of a VAC ban.
      A VAC ban permanently restricts the account from playing on VAC-secured
      servers across all Steam games.

    - Competitive league rules: RGL and ETF2L are organised competitive leagues
      for TF2. Some leagues prohibit client-side modifications. Players who
      participate in these leagues must check the relevant rules before using
      this tool.

    Behaviour:
    - First run: displays the full warning, requires the user to type 'agree'
    - Subsequent runs: shows a one-line reminder only
    - If the flag file exists but the hash does not match: re-prompts
      (handles tampered files and version changes that require re-acknowledgement)

    The STATE_DIR must already exist before this function runs (it creates it
    if needed) because the flag file is stored inside it.

    Note: this function is CLI-only. Any future graphical interface should
    implement its own equivalent disclosure rather than calling this directly.
    """
    os.makedirs(STATE_DIR, exist_ok=True)
    if os.path.isfile(ACKNOWLEDGED_FLAG):
        try:
            stored = open(ACKNOWLEDGED_FLAG).read().strip()
        except Exception:
            stored = ""
        if stored == _ACK_HASH:
            # Previously acknowledged — show brief reminder and continue
            print("(Reminder: use this tool while TF2 is closed.)")
            print()
            return
        # File exists but hash does not match — re-prompt
        os.remove(ACKNOWLEDGED_FLAG)

    # Display the full first-run disclosure
    print("=" * 56)
    print("  IMPORTANT — please read before continuing")
    print("=" * 56)
    print("  - Use this tool while TF2 is CLOSED.")
    print("  - Client-side mods may violate competitive")
    print("    league rules (RGL, ETF2L, etc).")
    print("    Check your league's policy before using.")
    print("  - VAC bans for client mods are rare but")
    print("    possible. Use at your own risk.")
    print("=" * 56)
    print()
    while True:
        try:
            resp = input("  Type 'agree' to accept, or 'q' to quit: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            # Handle Ctrl+C or end-of-file input (e.g. piped input in scripts)
            print("\nCancelled.")
            sys.exit(0)
        if resp == "agree":
            break
        if resp in ("q", "quit", "exit"):
            print("Cancelled.")
            sys.exit(0)
        print("  Please type 'agree' to continue, or 'q' to quit.")

    # Store the hash to record that the user has accepted the disclosure
    open(ACKNOWLEDGED_FLAG, "w").write(_ACK_HASH + "\n")
    log.info("User acknowledged risk warning.")
    print()


def main():
    """
    Top-level entry point. Runs in sequence:
    1. Initialise logging
    2. Show the risk acknowledgement prompt (first run) or reminder (subsequent runs)
    3. Create the tool's folder structure
    4. Parse arguments and run the tool

    Error handling layers:
    - KeyboardInterrupt (user pressed Ctrl+C): exits cleanly with no traceback
    - SwapError and subclasses (expected tool errors): shows a clean message and
      the log file path for reference
    - All other exceptions (unexpected errors): logs the full traceback to file
      and shows a brief message with the log file path

    The 'global log' assignment is necessary because setup_logging() creates and
    returns a configured logger instance — the module-level 'log' variable must
    be updated to point at this configured instance rather than the unconfigured
    placeholder created at import time.
    """
    global log
    log = setup_logging()
    check_acknowledgement()
    setup_folders()
    try:
        run()
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(0)
    except core.SwapError as e:
        log.error(str(e))
        print(f"\nERROR: {e}")
        print(f"(logged to {LOG_PATH})")
        sys.exit(1)
    except Exception as e:
        log.exception("Unexpected error")
        print(f"\nUnexpected error: {e}")
        print(f"Full details logged to {LOG_PATH}")
        sys.exit(1)


# Standard Python entry point guard. Ensures main() only runs when this file
# is executed directly ('python3 tf2autoswap.py') and not when it is imported
# as a module by another Python script (e.g. a future backend or test suite).
# Without this guard, importing this module would immediately trigger the
# acknowledgement prompt and attempt to run the full tool — a breaking behaviour
# that was fixed in version 4.7.1.
if __name__ == "__main__":
    main()
