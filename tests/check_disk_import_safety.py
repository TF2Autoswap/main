#!/usr/bin/env python3
"""
test_disk_import_safety.py - guards source_from_disk() against the symlink
information-disclosure issue found during the material-swap security review.

Background: a downloaded mod (Gamebanana or similar) is a folder of files
the user did not create and is very unlikely to inspect file by file before
importing. If one of those files is a symlink pointing outside the mod's
own folder, naive code that just open()s every file it finds will silently
read whatever the symlink actually points to — and since source_from_disk()
bundles everything it reads into the eventual output VPK, that content
would end up packed into a file the user might then share or upload.

Confirmed with a real proof-of-concept before resolved_path_under() (in
tf2_core.py) existed: a planted symlink disguised as a .vtf texture had an
arbitrary local file's real contents read straight into material_files.

This must never silently regress, hence a dedicated permanent test rather
than just the one-off verification done during the original review.

Run: python3 test_disk_import_safety.py
"""

import os
import sys
import tempfile
import tf2_core as core

PASS, FAIL = 0, 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}")


print("resolved_path_under()")

with tempfile.TemporaryDirectory() as root:
    inside = os.path.join(root, "inside.txt")
    open(inside, "w").write("x")
    check("a real file inside the root is allowed",
          core.resolved_path_under(inside, root))

    outside_dir = tempfile.mkdtemp()
    outside_file = os.path.join(outside_dir, "secret.txt")
    open(outside_file, "w").write("secret")
    link_to_outside = os.path.join(root, "disguised.vtf")
    os.symlink(outside_file, link_to_outside)
    check("a symlink resolving outside the root is refused",
          not core.resolved_path_under(link_to_outside, root))

    legit_target_dir = os.path.join(root, "shared")
    os.makedirs(legit_target_dir)
    legit_target = os.path.join(legit_target_dir, "real.txt")
    open(legit_target, "w").write("real content")
    link_within = os.path.join(root, "linked.vtf")
    os.symlink(legit_target, link_within)
    check("a symlink resolving to another file WITHIN the root is allowed",
          core.resolved_path_under(link_within, root))


print("\nsource_from_disk() — full attack + legitimate-use scenarios")

# --- attack case: a symlinked "texture" secretly points at an unrelated file ---
with tempfile.TemporaryDirectory() as attack_root:
    models_dir = os.path.join(attack_root, "models")
    mats_dir = os.path.join(attack_root, "materials", "models", "weapons",
                             "c_models", "c_scattergun")
    os.makedirs(models_dir)
    os.makedirs(mats_dir)

    secret_dir = tempfile.mkdtemp()
    secret_path = os.path.join(secret_dir, "sensitive.txt")
    open(secret_path, "w").write("this should not leak")

    evil_link = os.path.join(mats_dir, "c_scattergun.vtf")
    os.symlink(secret_path, evil_link)

    mdl_path = os.path.join(models_dir, "fake.mdl")
    open(mdl_path, "wb").write(b"IDST" + b"x" * 200)

    _, material_files, meta = core.source_from_disk(mdl_path)
    check("malicious symlink's target content does NOT appear in material_files",
          all(b"this should not leak" != v for v in material_files.values()))
    check("malicious symlink is recorded in skipped_symlinks, not silently dropped",
          any("c_scattergun.vtf" in s for s in meta["skipped_symlinks"]))
    check("material_files is empty (the only material file offered was malicious)",
          material_files == {})

# --- legitimate case: a symlink to another file within the SAME mod folder ---
with tempfile.TemporaryDirectory() as legit_root:
    models_dir2 = os.path.join(legit_root, "models")
    mats_dir2 = os.path.join(legit_root, "materials", "models", "weapons",
                              "c_models", "c_x")
    shared_assets = os.path.join(legit_root, "shared_textures")
    os.makedirs(models_dir2)
    os.makedirs(mats_dir2)
    os.makedirs(shared_assets)

    real_texture = os.path.join(shared_assets, "real_texture.vtf")
    open(real_texture, "wb").write(b"REAL_TEXTURE_BYTES")

    legit_link = os.path.join(mats_dir2, "c_x.vtf")
    os.symlink(real_texture, legit_link)

    mdl_path2 = os.path.join(models_dir2, "thing.mdl")
    open(mdl_path2, "wb").write(b"IDST" + b"x" * 200)

    _, material_files2, meta2 = core.source_from_disk(mdl_path2)
    check("a legitimate within-folder symlink is still read normally",
          material_files2.get("materials/models/weapons/c_models/c_x/c_x.vtf") == b"REAL_TEXTURE_BYTES")
    check("no false-positive skip for the legitimate symlink",
          meta2["skipped_symlinks"] == [])

# --- attack case: the .mdl's own sibling (.vvd) is the disguised symlink ---
with tempfile.TemporaryDirectory() as attack_root2:
    secret_dir2 = tempfile.mkdtemp()
    secret_path2 = os.path.join(secret_dir2, "id_rsa_lookalike.txt")
    open(secret_path2, "w").write("pretend private key contents")

    mdl_path3 = os.path.join(attack_root2, "thing.mdl")
    open(mdl_path3, "wb").write(b"IDST" + b"x" * 200)
    evil_sibling = os.path.join(attack_root2, "thing.vvd")
    os.symlink(secret_path2, evil_sibling)

    model_files3, _, meta3 = core.source_from_disk(mdl_path3)
    check("a disguised .mdl sibling (.vvd) symlink is refused, not read",
          ".vvd" not in model_files3)
    check("disguised sibling is recorded in skipped_symlinks",
          any("thing.vvd" in s for s in meta3["skipped_symlinks"]))


print("\nfind_mod_materials() — folder structure detection")

def _make_mdl(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "wb").write(b"IDST" + b"x" * 200)

# Flat structure — most common simple-reskin packaging. Found during the
# functional review: the original version of this function only looked for
# a literal 'models' folder name in the path, so it silently missed this
# entirely normal, very common case — the materials folder genuinely
# existed right next to the .mdl, but the function reported none found,
# meaning a real import would have looked untextured for no good reason.
with tempfile.TemporaryDirectory() as r:
    mdl = os.path.join(r, "thing.mdl")
    _make_mdl(mdl)
    os.makedirs(os.path.join(r, "materials"))
    check("flat mod structure (no 'models' folder at all) is found",
          core.find_mod_materials(mdl) == os.path.join(r, "materials"))

# Standard archive-mirroring structure — must not regress.
with tempfile.TemporaryDirectory() as r:
    mdl = os.path.join(r, "models", "player", "items", "scout", "thing.mdl")
    _make_mdl(mdl)
    os.makedirs(os.path.join(r, "materials"))
    check("standard nested structure still works",
          core.find_mod_materials(mdl) == os.path.join(r, "materials"))

# Nested 'models inside models' — the original edge case this function was
# specifically written to handle. Must find the INNER materials folder.
with tempfile.TemporaryDirectory() as r:
    mdl = os.path.join(r, "models", "mymod", "models", "thing.mdl")
    _make_mdl(mdl)
    os.makedirs(os.path.join(r, "models", "mymod", "materials"))
    check("nested models-in-models finds the inner materials folder",
          core.find_mod_materials(mdl) == os.path.join(r, "models", "mymod", "materials"))

# No materials anywhere nearby — must correctly report None, not guess.
with tempfile.TemporaryDirectory() as r:
    mdl = os.path.join(r, "models", "player", "items", "scout", "thing.mdl")
    _make_mdl(mdl)
    check("genuinely no materials folder nearby returns None",
          core.find_mod_materials(mdl) is None)


print("\nfind_disk_weapon_worldmodel() — weapon disk-import worldmodel detection")

with tempfile.TemporaryDirectory() as r:
    view_dir = os.path.join(r, "models", "weapons", "c_models", "c_customgun")
    view_path = os.path.join(view_dir, "c_customgun.mdl")
    world_path = os.path.join(view_dir, "w_customgun.mdl")
    _make_mdl(view_path)
    _make_mdl(world_path)
    check("Structure A (worldmodel alongside viewmodel) is found",
          core.find_disk_weapon_worldmodel(view_path) == world_path)

with tempfile.TemporaryDirectory() as r:
    view_dir = os.path.join(r, "models", "weapons", "c_models", "c_customgun2")
    world_dir = os.path.join(r, "models", "weapons", "w_models")
    view_path = os.path.join(view_dir, "c_customgun2.mdl")
    world_path = os.path.join(world_dir, "w_customgun2.mdl")
    _make_mdl(view_path)
    _make_mdl(world_path)
    check("Structure B (separate w_models folder) is found",
          core.find_disk_weapon_worldmodel(view_path) == world_path)

with tempfile.TemporaryDirectory() as r:
    view_dir = os.path.join(r, "models", "weapons", "c_models", "c_knife")
    view_path = os.path.join(view_dir, "c_knife.mdl")
    _make_mdl(view_path)
    check("melee weapon (no worldmodel anywhere) correctly returns None",
          core.find_disk_weapon_worldmodel(view_path) is None)

with tempfile.TemporaryDirectory() as r:
    weird_path = os.path.join(r, "thing.mdl")
    _make_mdl(weird_path)
    check("non-viewmodel filename (no c_ prefix) returns None",
          core.find_disk_weapon_worldmodel(weird_path) is None)


print("\nEXTS now includes .phy (found missing during real-world prop review)")

with tempfile.TemporaryDirectory() as r:
    mdl_path = os.path.join(r, "breakable_prop.mdl")
    phy_path = os.path.join(r, "breakable_prop.phy")
    _make_mdl(mdl_path)
    open(phy_path, "wb").write(b"fake collision data")
    model_files, _, _ = core.source_from_disk(mdl_path)
    check(".phy (collision/physics data) is bundled alongside the model",
          ".phy" in model_files and model_files[".phy"] == b"fake collision data")


print("\nread_vpk_entry() — VPK missing-chunk error handling")

class _FakeEntry:
    def __init__(self, data=None, raises=None):
        self._data, self._raises = data, raises
    def read(self):
        if self._raises:
            raise self._raises
        return self._data

class _FakePak:
    def __init__(self, entries):
        self._entries = entries
    def __getitem__(self, path):
        if path not in self._entries:
            raise KeyError(path)
        return self._entries[path]

fake_pak = _FakePak({
    "exists/clean.vtf": _FakeEntry(data=b"real bytes"),
    "exists/missing_chunk.vtf": _FakeEntry(raises=FileNotFoundError(2, "No such file or directory", "tf2_textures_072.vpk")),
})

check("a file that exists and reads fine still works",
      core.read_vpk_entry(fake_pak, "exists/clean.vtf") == b"real bytes")

try:
    core.read_vpk_entry(fake_pak, "does/not/exist.vtf")
    check("a path absent from the index raises KeyError", False)
except KeyError:
    check("a path absent from the index raises KeyError", True)

try:
    core.read_vpk_entry(fake_pak, "exists/missing_chunk.vtf")
    check("a path present in the index but missing its chunk raises BuildError", False)
except core.BuildError as e:
    check("a path present in the index but missing its chunk raises BuildError",
          "missing" in str(e).lower() and "verify integrity" in str(e).lower())
except KeyError:
    check("a path present in the index but missing its chunk raises BuildError (not KeyError)", False)


print("\nread_mdl_hull_dimensions() / prop_size_warning() — synthetic test data")

def _make_synthetic_mdl_with_hull(hull_min, hull_max):
    """
    Generate a minimal valid .mdl file with specific hull dimensions.
    Byte layout per Source SDK studiohdr_t:
        0-3:   'IDST' magic
        4-7:   version (int)
        8-11:  checksum (int)
        12-75: name (64 bytes, null-terminated)
        76-87: dataLength (int)
        88-99: eyeposition (3 floats)
        100-111: illumposition (3 floats)
        112-123: hull_min (3 floats x, y, z)
        124-135: hull_max (3 floats x, y, z)
    """
    import struct
    header = b'IDST'  # magic
    header += struct.pack('<i', 48)  # version
    header += struct.pack('<i', 0)  # checksum
    header += b'test_model'.ljust(64, b'\x00')  # name
    header += struct.pack('<i', 0)  # dataLength
    header += struct.pack('<3f', 0.0, 0.0, 0.0)  # eyeposition
    header += struct.pack('<3f', 0.0, 0.0, 0.0)  # illumposition
    header += struct.pack('<3f', *hull_min)  # hull_min
    header += struct.pack('<3f', *hull_max)  # hull_max
    # Pad to at least 128 bytes (minimum for read_mdl_hull_dimensions)
    return header.ljust(200, b'\x00')

# Synthetic models with known dimensions
small_hat = _make_synthetic_mdl_with_hull(
    hull_min=(-10.0, -10.0, -10.0),
    hull_max=(10.0, 10.0, 10.0)
)  # ~20 units longest axis (hat-scale)

large_vehicle = _make_synthetic_mdl_with_hull(
    hull_min=(-200.0, -150.0, -100.0),
    hull_max=(200.0, 150.0, 100.0)
)  # ~400 units longest axis (vehicle-scale)

medium_prop_a = _make_synthetic_mdl_with_hull(
    hull_min=(-50.0, -40.0, -30.0),
    hull_max=(50.0, 40.0, 30.0)
)  # ~100 units longest axis

medium_prop_b = _make_synthetic_mdl_with_hull(
    hull_min=(-60.0, -45.0, -35.0),
    hull_max=(60.0, 45.0, 35.0)
)  # ~120 units longest axis (similar to medium_prop_a)

hull = core.read_mdl_hull_dimensions(small_hat)
check("hull dimensions read correctly from synthetic .mdl (hat-scale, sane size)",
      hull is not None and 15 < max(hull[1][i] - hull[0][i] for i in range(3)) < 25)

check("invalid bytes (no IDST magic) return None, not garbage",
      core.read_mdl_hull_dimensions(b"not a real mdl") is None)

check("hat vs vehicle-scale prop -> warns (20x size difference, exceeds 2.5x threshold)",
      core.prop_size_warning(small_hat, large_vehicle) is not None)

# Direction check: when src=small_hat is the replacement and dst=large_vehicle is the
# original, the ORIGINAL is the bigger one, so the warning must say "original".
warn_dir = core.prop_size_warning(small_hat, large_vehicle)
check("warning correctly identifies the ORIGINAL as bigger (replacement=small_hat, original=large_vehicle)",
      warn_dir is not None and "original" in warn_dir)

# Reversed: src=large_vehicle is the replacement, dst=small_hat is the original.
# Now the REPLACEMENT is bigger, so the warning must say "replacement".
warn_rev = core.prop_size_warning(large_vehicle, small_hat)
check("warning correctly identifies the REPLACEMENT as bigger (replacement=large_vehicle, original=small_hat)",
      warn_rev is not None and "replacement" in warn_rev)

check("two similarly-sized medium props -> no warning (within 2.5x threshold)",
      core.prop_size_warning(medium_prop_a, medium_prop_b) is None)
check("identical model compared to itself -> no warning",
      core.prop_size_warning(medium_prop_a, medium_prop_a) is None)
check("missing model bytes on either side -> None, not a crash",
      core.prop_size_warning(None, large_vehicle) is None and core.prop_size_warning(small_hat, None) is None)


# ---------------------------------------------------------------------------
print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
