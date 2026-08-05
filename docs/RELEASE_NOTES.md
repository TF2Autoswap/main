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

### Decorated Weapon Swaps (Gun Mettle / Tough Break Skins)
Apply collection skins (Brick House, War Room, Treadplate, etc.) to any supported weapon client-side:

**Two Targeting Modes:**
- **Per-variant** mode: Replace only one specific painted variant (e.g., War Room Minigun → Brick House)
- **Weapon-wide** mode: Replace all variants of that weapon type

**Three Source Options:**
- SFM Workshop library auto-detection
- Built-in catalog (158 variants across 14 weapons, 8 collections)
- Manual VTF path input

**Guided Flow:** class → weapon → mode → [variant selection] → skin → build

**Supported Collections:**
- Concealed Killer, Craftsmann, Teufort, Powerhouse
- Harvest, Pyroland, Gentlemanne, Warbird

Credit attribution required for shared mods (gabrielwoj / Baldurs Tod).  
War paint skins (System 2, procedural) are out of scope.

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

**82 tests total:**
- 70 pytest unit/integration tests
- 12 security regression tests

**Coverage:**
- tf2_schema.py: 70% (security-critical module)
- Overall: 24%
- 100% pass rate

**New Test Files:**
- `tests/test_security_schema.py` — Schema/cache size validation
- `tests/test_tf2_core_paths.py` — Path handling
- `tests/test_tf2_core_logic.py` — Schema logic
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
git clone https://github.com/TF2Autoswap/autoswap.git
cd autoswap
python3 tf2autoswap.py
```

Dependencies (`vpk`, `vdf`) auto-install on first run.

### Upgrade from 4.7
1. Backup `output/` directory (your built mods)
2. Pull latest code: `git pull`
3. State files migrate automatically to `.tf2autoswap/`
4. No cache reset required (format unchanged)

---

## ⚠️ Known Issues

- War paint skins (System 2, procedural patterns) not supported — out of scope for v4.8
- Decorated weapon catalog limited to Gun Mettle / Tough Break collections
- Material-only swaps (pure retextures with no model change) not yet exposed in UI

---

## 🐛 Bug Reports

Report issues at: https://github.com/TF2Autoswap/autoswap/issues

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
- **Coding Assistance:** Claude (Anthropic)
- **SFM Workshop Mods:** gabrielwoj / Baldurs Tod
- **Security Audit:** Oz (Warp AI Agent)

---

## 🔗 Links

- **Repository:** https://github.com/TF2Autoswap/autoswap
- **Security Audit:** SECURITY_AUDIT_V48.md
- **Changelog:** CHANGELOG.md
- **Development Guide:** DEVELOPMENT.md
- **Testing Guide:** TESTING.md

---

**Co-Authored-By: Oz <oz-agent@warp.dev>**
