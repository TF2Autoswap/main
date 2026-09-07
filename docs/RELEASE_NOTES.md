# TF2autoswap v4.8 Release Notes
**Release Date:** 2026-07-02  
**Type:** Major feature release + critical security fixes

---

## 🛡️ Critical Security Updates

This release addresses **two critical security vulnerabilities** discovered during comprehensive security audit:

### CRITICAL-001: Schema File Size Validation
- **Issue:** Memory exhaustion DoS via oversized `items_game.txt`
- **Fix:** Enforced 200MB limit in `load_schema()` (real schema ~20MB, 10x safety margin)
- **Impact:** Prevents multi-gigabyte malicious schema files from causing OOM crashes

### CRITICAL-002: Cache File Size Validation  
- **Issue:** Cache poisoning via oversized cache files
- **Fix:** Enforced 100MB limit with automatic deletion of poisoned caches
- **Impact:** Prevents persistent DoS via malicious cache replacement

**All users are strongly recommended to upgrade immediately.**

Full security audit available in `SECURITY_AUDIT_V48.md`.

---

## ✨ New Features

### Skin / Material Swaps
Apply a custom reskin (replacement .vmt/.vtf materials) to any weapon or cosmetic client-side:

**Two Source Modes:**
- **Import a reskin folder from disk** — point the tool at a Gamebanana download or custom
  material pack; all .vmt/.vtf files are collected, run through the non-optional safety layer
  (`validate_material_set()` in `tf2_material.py`), and bundled into a VPK.
- **Copy another in-game item's textures** — select any weapon or cosmetic from TF2's archive
  as the material source; the tool resolves its materials from `tf2_textures_dir.vpk` and
  applies them to the target.

**Safety Layer:** The safety check is non-optional and refuses: world/map/brush materials,
base player body materials, and any VMT flags or runtime proxies that could enable wallhack
or ESP effects. There is no way to bypass this check.

**Decorated weapon skins** (official Gun Mettle/Tough Break collection patterns) were
attempted during v4.8 development but are not included — they render at launch via the
game's HUD and composite on the GPU from per-defindex item attributes the tool has no access
to, making a VMT-based intercept non-viable. War paint skins (System 2) are out of scope
for the same reason.

---

### Prop Size Checking
Warns when swapping props with 2.5x+ size difference:
- Compares hull bounding boxes (collision dimensions)
- Warns at confirmation step about fairness concerns
- Swap can still proceed (guidance, not enforcement)
- Explains sightline / collision implications

See `prop_size_warning()` and `read_mdl_hull_dimensions()` in `tf2_core.py`.

---

### Material Transport for Disk Imports
Custom models imported from disk now automatically bundle sibling `materials/` folders:
- All bundled materials run through safety layer
- Refuses wallhack/ESP render flags (`$ignorez`, etc.)
- Closes gap where disk imports bypassed safety checks

---

### Organised Import Folders
`imports/` directory now has clear subfolder structure:
- `cosmetics/`
- `weapons/viewmodel/`
- `weapons/worldmodel/`
- `weapons/materials/`
- `props/`
- `inventory/`

Makes intended drop locations visible from the start.

---

## 🔧 Changes

### State Directory Relocation
- **Old:** `output/.tf2autoswap/`
- **New:** `.tf2autoswap/` (project root)
- Separates internal state from user-created mod files
- Matches dotfolder convention

---

## 📊 Test Coverage

**722 tests passing** (1 skipped), verified at release.

**Test Files:**
- `tests/test_tf2_material_safety.py` — Material safety layer (47 tests)
- `tests/test_tf2_material_extended.py` — Material engine (80+ tests)
- `tests/test_security_schema.py` — Schema/cache size validation (12 tests)
- `tests/test_tf2_core_paths.py` — Path handling
- `tests/test_tf2_core_logic.py` — Schema logic
- `tests/test_tf2_core_models.py` — MDL/model operations
- `tests/test_tf2autoswap.py` — CLI and integration flows
- `tests/test_tf2autoswap_errors.py` — Error handling
- `tests/test_tf2autoswap_import_modes.py` — Import paths
- `tests/test_tf2autoswap_menus.py` — Menu/interactive flows
- `tests/test_tf2autoswap_swap_flows.py` — Swap workflows
- `tests/test_integration_workflows.py` — End-to-end flows

---

## 🔐 Security Strengths (tf2_material.py)

The v4.8 material safety layer demonstrates exemplary security design:

### Path Traversal Protection
- Uses `posixpath.normpath()` BEFORE classification checks
- Prevents `../` exploits in MDL cdmaterials directory strings
- Example: `materials/models/weapons/../../../maps/x.vmt` → correctly classified as "world" (BLOCKED)

### VMT Runtime Proxy Detection
- Detects `Proxies` blocks that animate risky parameters at runtime
- Catches animated transparency, dynamic depth-test disabling, fresnel self-illum
- Static scans can't detect these — dynamic proxy analysis required

### Shader Classification
- Blocks unlit shaders (`UnlitGeneric`, `UnlitTwoTexture`) on player-visible materials
- Prevents fullbright / always-visible surfaces (soft ESP)

**No wallhack/ESP features are user-configurable. Safety layer cannot be disabled.**

---

## 📦 Installation

### New Installation
```bash
git clone https://github.com/TF2Autoswap/main.git
cd autoswap
python3 tf2autoswap.py
```

Dependencies (`vpk`, `vdf`) auto-install on first run — there is no
requirements file to install from.

### Upgrade from 4.7
1. Backup `output/` directory (your built mods)
2. Pull latest code: `git pull`
3. **Pre-4.8 state files are removed, not migrated.** The old `output/.tf2autoswap/`
   state (`.acknowledged`, `schema_cache.json`) is deleted on first run, so the
   risk acknowledgement prompt appears once again. Your built mods in `output/`
   are untouched.
4. No cache reset required (format unchanged)

---

## ⚠️ Known Issues

- War paint skins (System 2, procedural patterns) not supported — out of scope (rendered
  by TF2's GPU compositor from per-item attributes, same fundamental limitation as
  decorated weapon skins)
- Decorated weapon skins (Gun Mettle/Tough Break collections) not supported — blocked by
  engine; see CHANGELOG for details
- Some items with complex multi-material setups may require the disk import path rather
  than the in-game copy-textures option (best-effort)

---

## 🐛 Bug Reports

Report issues at: https://github.com/TF2Autoswap/main/issues

**Include:**
- OS and Python version
- Full command or interactive flow
- Error message (if any)
- `tf2autoswap.log` (last 100 lines)

---

## 📜 License

GPL v3 — see LICENSE file

---

## 🙏 Credits

- **Core Development:** Melancholy Sky

---

## 🔗 Links

- **Repository:** https://github.com/TF2Autoswap/main
- **Security Audit:** docs/SECURITY_AUDIT_V48.md
- **Changelog:** CHANGELOG.md
- **Project Context:** docs/PROJECT_CONTEXT.md
- **Contributing:** docs/CONTRIBUTING.md
- **Testing Guide:** docs/TESTING.md

---

