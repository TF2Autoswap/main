# TF2autoswap — Project Context

This file exists so a new AI session (Warp Agent, or any AI assistant in
your current coding environment) has the background that isn't written
anywhere else in the repo. The README and CHANGELOG cover *what* the tool does. This covers the *why*
behind decisions that aren't obvious from the code alone.

If you're an AI assistant reading this to help with the project: the
human (Sky) directs all development decisions, testing, and version
bumps. You implement and review — you don't decide scope, priorities,
or when to ship. When in doubt, ask rather than assume.

---

## What this project is

A free, GPL v3 Python tool that swaps TF2 cosmetic and weapon models
client-side. Outputs a VPK file or a Casual Preloader addon folder.
Solo project, genuinely a passion project — not aiming for wide
community adoption right now (see "Distribution posture" below).

## Project ethos (read this before suggesting anything)

- **Transparency-first.** AI assistance in building this tool is
  openly documented, not hidden. Don't suggest scrubbing AI involvement
  from commits, comments, or docs.
- **Safety/safeguards are first-class features**, not afterthoughts.
  Things like the risk acknowledgement prompt, clip warnings, and
  slot-mismatch warnings are deliberate design, not boilerplate to trim.
- **"Vibe coding" does not describe this project.** Sky directs,
  reviews, and iterates on every change. Don't write code that wouldn't
  survive a real review pass.
- **Documentation is part of the deliverable**, not cleanup done after.
  Comments should explain *why*, not just *what* — assume a
  non-specialist auditor is reading them.

## Distribution posture

Deliberately low-profile and GitHub-first. There was real community
friction historically around AI-assisted TF2 tools, so there's no
active promotion. A small group of warm contacts playtest informally
before anything wider happens. Don't suggest "let's announce this on
Reddit/the TF2 subreddit" type actions — that's explicitly not the plan.

---

## Architecture (non-negotiable rules)

- **`tf2_core.py`** — pure logic. Zero `print()` or `input()` calls,
  ever. Any interface (current CLI, future GUI) sits on top of this.
- **`tf2_schema.py`** — parses `items_game.txt` into a lookup index.
  Optional dependency at runtime — the tool must degrade gracefully
  (no friendly names, no warnings) if this or `vdf` isn't available.
- **`tf2autoswap.py`** — the CLI interface layer. All `print`/`input`
  lives here.

This split exists specifically so a future GUI (see `v5_gui_design_transfer.md`)
can replace only the interface layer without touching core or schema.

## Domain knowledge that's easy to get wrong

- **Two weapon worldmodel folder structures exist** in TF2's archive,
  and there's no way to know which one a given weapon uses without
  checking the archive directly (see `_world_base_candidates()` in
  `tf2_core.py`). Always resolve from the actual VPK, never guess-only,
  when building real output.
- **`used_by_classes` in `items_game.txt` encodes per-class loadout
  slot overrides as slot-name values** — e.g. Shotgun is Engineer's
  primary but Heavy's secondary. This bit a previous version (silently
  excluded weapons from class filtering). Any code touching class/slot
  filtering needs to handle this correctly.
- **Cache format versioning matters.** Schema and other caches must
  carry a format-version guard. A cache written by an older field
  layout loading silently into newer code is a real bug class here,
  not theoretical.
- **Never surface cookie/session concepts to end users.** Cookie
  support for any future live-fetch feature exists only via environment
  variable, with a `*** DO NOT surface to end users ***` warning in the
  docstring. This mirrors a known TF2 scam pattern (fake tools asking
  for session cookies). A live Steam session credential was once caught
  in AI-generated draft code and had to be rotated — this rule exists
  because of that, not hypothetically.

## Roadmap (current order — don't reorder without Sky's say)

1. **v4.8** (dev branch, NOT shipped) — security hardening (schema/cache size
   validation), prop size fairness warnings (hull bounding box checks, 2.5x
   threshold), material transport for disk imports, organised import folders.
   Decorated weapon swaps was attempted but **blocked**: decorated weapons target
   specific base skins and render at launch via the game's HUD, making the VMT
   proxy redirect approach non-viable. The ~500 lines of non-functional decorated
   weapon code were removed during the pre-release cleanup pass (commit bb4bcb1).
   Skin/material swaps via `interactive_skin_swap()` / `--skin` (custom user-provided
   reskin folders, routed through the tf2_material.py safety layer) are a separate
   working feature and remain in the release. The prop swap feature was also held
   back due to concerns about sightline misuse but now includes `prop_size_warning()`
   as a fairness safeguard.
2. **v4.85** — backend/API prep for mods.tf integration
3. **v4.9** — cleanup + licence formalisation (PyPI, signed releases, pip packaging)
4. **v4.95** — backend polish
5. **v5** — GUI (see `v5_gui_design_transfer.md` for full design spec)

War paint support (System 2) has been investigated and deferred indefinitely. The core
blocker is that war paints require material pre-registration via `vguipreload.res` inside
the Casual Preloader's own VPK — either creating a dependency on the preloader's internals
(fragile) or shipping a competing precache VPK (scope creep). Revisit only if the preloader
falls out of active development or a cleaner integration path emerges.

**Skin/material swaps** are a working v4.8 feature via `tf2_material.py` and the
`interactive_skin_swap()` / `--skin` CLI path (custom user-provided reskin
folders, not official decorated weapon skins — those are blocked by engine,
see the Roadmap section above). The safety layer is non-optional and enforces
two hard boundaries:
- **Allowed:** weapon viewmodel and cosmetic item materials, gated behind
  `validate_material_set()` which refuses wallhack render flags.
- **Permanently blocked:** world/map/brush materials, base player body
  materials, and any VMT content that enables depth-test bypass or ESP
  (enforced in code, not by documentation).

Do not propose removing or bypassing the safety layer. Extending the
allowed scope (e.g. to world materials or base player textures) is
permanently off the roadmap — that is the actual wallhack vector.

## Version bumps are Sky's call

Don't bump `VERSION` or rewrite `WHATS_NEW` in `tf2autoswap.py` unless
explicitly asked to. Flagging a changelog or version string as "stale"
is fine; changing it yourself isn't.

---

## If you're being asked to write code for this project

- Match the existing docstring style — plain-language explanations of
  TF2/Valve concepts for non-specialist readers, not just API docs.
- Functional smoke-test before calling something done, not just
  "it compiles."
- If something touches safety logic (warnings, the acknowledgement
  system, anything that could mislead a user about risk), treat it as
  needing the same care as the existing safety code — that logic is
  kept deliberately auditable.
