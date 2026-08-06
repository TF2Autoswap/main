# SECURITY.md — threat model and controls

**Trust boundary:** the operator is trusted; agents and any file they read
(VPK archives, user-provided mod files, schema data) are the untrusted
component we confine. We do not defend against a malicious operator.

This document governs agent-safety *boundaries* for the TF2autoswap
codebase. The *coordination rules* (how agents coordinate, verify, and
hand off) live in `HARMONY.md`. Cross-link, don't duplicate.

## Threat model

| Threat | Source | Impact |
|--------|--------|--------|
| Wallhack/ESP via material injection | User-provided VMT files with depth-test bypass, unlit shaders, or runtime proxy animation of `$ignorez`/`$alpha` | Player receives unfair visibility advantage; tool's safety claim broken |
| Memory exhaustion DoS | Maliciously oversized `items_game.txt` or poisoned cache files | Tool crashes or hangs with OOM |
| Path traversal / symlink escape | User-controlled import paths with `../` sequences or symlinks | Writes outside intended output directory; possible system file overwrite |
| Accidental live dispatch | Operator typo / default-on mode | Unintended file mutations via agent-issued shell commands |
| Audit blindness | Silent logging failure | No record of what was built, when, or by whom |
| Session credential exposure | AI-generated code surfacing cookie/session concepts to end users | Phishing-adjacent trust damage in the TF2 community; real Steam credential once caught in draft code |
| Prop swap sightline manipulation | Swapping a large prop model for a much smaller one | Player gets unobstructed sightline through geometry other players expect to be blocked |
| Unfair advantage via cosmetic swap | Swapping differently-shaped cosmetics between equip regions | Player model hitbox mismatch vs visible model (source engine server-authoritative on collision, but visual mismatch is unfair) |

## Controls

Each control is numbered and anchored to the function or constant that
enforces it. A control with no code anchor is a wish.

### C1. Material safety layer (hard-refuse)

**Anchor:** `tf2_material.py::validate_material_set()` (line 399),
`tf2_material.py::scan_vmt_safety()`, `classify_material_path()`,
`find_risky_proxy_targets()` (line 250), `has_proxies_block()` (line 275)

All user-provided material files pass through a non-optional safety gate
that enforces three hard boundaries:

1. **Path classification** — `classify_material_path()` uses
   `posixpath.normpath()` BEFORE allow-list checks, preventing `../`
   traversal from reclassifying a blocked path (`materials/maps/`) as an
   allowed one (`materials/models/weapons/`). Only cosmetic item
   materials and weapon viewmodel materials pass; world, map, brush,
   base player body materials are permanently refused.

2. **Shader-based refusal** — unlit shaders (`UnlitGeneric`,
   `UnlitTwoTexture`) on player-visible materials are blocked. These
   remove lighting calculations, producing fullbright rendering
   (soft ESP).

3. **VMT proxy detection** — `find_risky_proxy_targets()` inspects
   `Proxies` blocks for `resultVar` targeting `$alpha`, `$ignorez`,
   or `$cloakFactor` — parameters that can enable wallhack or
   partial invisibility at runtime. Any hit is hard-refused.
   Legitimate proxies (`weapon_invis`, `BurnLevel`, `weapon_glow`)
   that target cosmetic parameters are informational, not blocked.

**Severity:** hard-refuse. A violation stops the build.

### C2. Schema file size validation (hard-refuse)

**Anchor:** `tf2_schema.py::MAX_SCHEMA_SIZE` = 200MB (line 93),
`tf2_schema.py::load_schema()` (line 212)

Before parsing `items_game.txt`, `os.path.getsize()` checks against
a 200MB limit (real schema is ~20MB; 10x headroom). Oversized files
raise `SwapError` — no bytes are read. Prevents memory exhaustion
DoS from maliciously crafted schema files.

### C3. Cache file size validation (silent-recover)

**Anchor:** `tf2_schema.py::MAX_CACHE_SIZE` = 100MB (line 98),
`tf2_schema.py::load_schema_cache()`, `load_defindex_cache()`

Before loading cached schema/defindex data, `os.path.getsize()` checks
against a 100MB limit (real cache ~5MB; 20x headroom). Poisoned caches
are deleted and regenerated, not loaded. Non-fatal: the tool rebuilds
from the real schema file on the next run.

### C4. Risk acknowledgement prompt (hard-refuse)

**Anchor:** `tf2autoswap.py` — startup acknowledgement flow

On first launch, the user must type `agree` after reading a warning
covering VAC risk, competitive league policies, and the requirement to
close TF2 before using the tool. Acknowledgement is stored as a SHA256
hash (not plaintext) and timestamped in the log. Refusal exits.

### C5. Dry-run / confirm gate (warn-only until confirm)

**Anchor:** `tf2autoswap.py` — interactive confirm step;
`--dry-run` CLI flag

Every build shows a compact preview (file count, size, destination)
before writing. The `--dry-run` flag shows the exact output without
writing anything. No files are created without explicit confirmation
in interactive mode.

### C6. Prop size fairness warning (warn-only)

**Anchor:** `tf2_core.py::read_mdl_hull_dimensions()` (line 1008),
`tf2_core.py::prop_size_warning()` (line 1052)

Prop swaps compare source and replacement model hull bounding boxes.
If the size difference exceeds 2.5x on the longest axis, a warning
appears explaining the sightline fairness concern. The swap proceeds
(the warning is guidance, not enforcement) because prop collision is
server-authoritative — the real risk is visual, not mechanical. The
user makes an informed choice.

### C7. Cosmetic equip-region and weapon slot warnings (warn-only)

**Anchor:** `tf2_schema.py::clip_warning()` (line 583),
`tf2_schema.py::weapon_swap_warning()` (line 629)

Mismatched equip regions or weapon slots show a warning at the confirm
step. The swap can still proceed — this is guidance, not enforcement —
but the user is informed of possible animation or visual issues.

### C8. No cookie/session surface to end users (hard-refuse in review)

**Anchor:** `docs/PROJECT_CONTEXT.md` — "Never surface cookie/session
concepts to end users"

Any future live-fetch feature must access session credentials only via
environment variable with a `*** DO NOT surface to end users ***`
guard in the docstring. Cookie/session concepts must never appear in
user-facing prompts, docs, or error messages. This rule exists because
a live Steam session credential was once caught in AI-generated draft
code and had to be rotated.

### C9. No shell injection (design invariant)

**Anchor:** `tf2_core.py` — all subprocess calls use argument lists,
not shell strings. `tf2autoswap.py` — all `os.path` functions for
path construction.

Verified: zero subprocess calls with string interpolation. The
auto-install path for `vpk`/`vdf` uses `[sys.executable, "-m", "pip",
"install", ...]` with hardcoded package names — no user-controlled
strings in the command.

### C10. Lazy imports gated by availability (degrade-gracefully)

**Anchor:** `tf2_core.py::get_vpk()`, `tf2autoswap.py` lines 63-83

Optional dependencies (`vpk`, `vdf`, `Pillow`) are imported lazily.
If unavailable, the tool degrades with clear messaging rather than
crashing. The schema system gracefully handles missing `vdf` (no
friendly names, no class filtering — but core swap operations still
work).

## Enforcement modes

- **active** — controls enforced in-process by code in this repo
  (material safety, schema size, cache size, shell injection).
- **advisory** — controls communicated in agent prompts but not
  actively brokered (HARMONY.md coordination rules for subagent
  behavior).

Controls C1–C10 are active. Agent coordination rules in `HARMONY.md`
are advisory (they govern agent behavior, which the orchestrator
re-verifies on disk per HARMONY §4).

## Known limitations

- **Material safety is code-enforced, not runtime-monitored.**
  `validate_material_set()` gates at build time. If a future TF2
  update changes how VMT proxies or shader parameters work, the
  allow/deny tables may need updating.
- **Prop size warning is guidance, not enforcement.** The check
  uses hull bounding boxes as a proxy for visual obstruction, which
  is a reasonable heuristic but not exact. Server-side collision
  is authoritative regardless.
- **No material file size limit.** Material files (VTF/VMT) are
  user-selected from their own TF2 install or local disk, bounded
  by TF2's engine constraints. A limit has been discussed but
  deferred as low-priority (user controls the input).
- **TOCTOU (residual).** File existence/size checks are
  point-in-time. This is inherent to filesystem operations.
- **Cache structure validation is implicit.** Corrupted cache
  files are caught by broad try/except, not explicit key checks.
  Effective but less auditable than explicit validation.
- **Agent self-reports are not trusted.** Per HARMONY §4, all
  agent claims are re-verified on disk by the orchestrator.

## Reporting

Security issues: contact MelancholySky via
[Steam](https://steamcommunity.com/id/MelancholySky) or
melancholysky@outlook.com. Do not open a public GitHub issue.

## Supported versions

Only the latest release receives security updates. v4.7 (latest
shipped) is supported; versions before 4.6 are not.
