# Changelog
 
All notable changes to TF2autoswap are recorded here.
Versions follow the project's own numbering. Dates are when each cut was made.
 
## [4.8] - 2026-07-02
### Security
- **CRITICAL: Schema file size validation** — `load_schema()` now enforces a 200MB limit on
  `items_game.txt` to prevent memory exhaustion DoS attacks from maliciously crafted schema files.
  Real schema is ~20MB; this provides 10x headroom while protecting against multi-gigabyte payloads.
  See SECURITY_AUDIT_V48.md for details.
- **CRITICAL: Cache file size validation** — `load_schema_cache()` and `load_defindex_cache()`
  enforce a 100MB limit to prevent cache poisoning attacks. Oversized cache files are automatically
  deleted and regenerated. Real caches are ~5MB; this provides 20x headroom.
- **Comprehensive security regression tests** — 12 new tests in `tests/test_security_schema.py`
  validate both file size enforcement mechanisms, including adversarial inputs, cache recovery,
  and boundary conditions.
### Added
- **Skin / material swaps** — apply a custom reskin (replacement .vmt/.vtf materials) to any
  weapon or cosmetic. Two source modes:
  - **Import a reskin folder from disk** — point the tool at a Gamebanana download or custom
    material pack; all .vmt/.vtf files are collected, run through the non-optional safety layer
    (`validate_material_set()` in `tf2_material.py`), and bundled into a VPK ready to use.
  - **Copy another in-game item's textures** — select any weapon or cosmetic from TF2's archive
    as the material source; the tool resolves its materials from `tf2_textures_dir.vpk` and
    applies them to the target. Best-effort — some items have complex multi-material setups that
    may require the disk import path instead.
  - The safety layer is non-optional and refuses: world/map/brush materials, base player body
    materials, and any VMT flags or runtime proxies that could enable wallhack or ESP effects.
    There is no way to bypass this check.
  - Available in both the interactive menu and via `--skin` on the command line.
  - Decorated weapon skins (official Gun Mettle/Tough Break collection patterns) were
    attempted during v4.8 development but are **not included** — they render at launch via the
    game's HUD and composite on the GPU from per-defindex item attributes the tool has no access
    to, making a VMT-based intercept non-viable. War paint skins (System 2) are out of scope
    for the same fundamental reason.
- **Prop size checking** — prop swaps now compare the hull bounding boxes (overall
  collision dimensions) of source and replacement models. If the size difference is
  substantial (2.5x or more on the longest axis), a warning appears at the confirm
  step explaining the fairness concern: swapping a large prop for a much smaller one
  can open a sightline that everyone else expects to be blocked, while your own
  collision stays governed by the server's original data. The swap can still proceed
  — this is guidance, not enforcement — but the user now knows the size mismatch
  up front rather than discovering it in-game. See `prop_size_warning()` and
  `read_mdl_hull_dimensions()` in `tf2_core.py` for the implementation and reasoning.
- **Material transport for disk imports** — custom models imported from disk
  (cosmetics, weapons, props) now automatically bundle any sibling `materials/` folder
  found next to the .mdl file. All bundled materials are run through the same safety
  layer as the dedicated skin-swap feature (refuses wallhack/ESP render flags) before
  being packed, closing a gap where disk-imported materials previously bypassed the
  safety check entirely.
- **Organised import folders** — the `imports/` directory is now created with a clear
  subfolder structure: `cosmetics/`, `weapons/viewmodel/`, `weapons/worldmodel/`,
  `weapons/materials/`, `props/`, and `inventory/`. Makes the intended locations for
  user-dropped mod files visible from the start and reduces clutter.
### Changed
- State directory (caches, acknowledgement flag) moved from `output/.tf2autoswap/` to
  `.tf2autoswap/` at the project root. Keeps internal tool state separate from
  user-created mod files and matches the dotfolder convention more cleanly.
 
## [4.7] - 2026-06-10
### Fixed
- **World model flat path generation** — the flat candidate in `_world_base_candidates()`
  now correctly drops the `c_<name>` subfolder when building the `w_models/` path.
  Previously generated `w_models/c_<name>/w_<name>` (wrong); now correctly generates
  `w_models/w_<name>`. World models for flat-structure weapons like the minigun now
  pack correctly.
- **Windows pip PATH warning** — pip auto-installs now pass `--no-warn-script-location`
  so the harmless but alarming PATH warning no longer appears on first run.
- **Custom path filename** — custom output paths with no `.vpk` extension now have the
  generated filename appended automatically, consistent with folder path behaviour.
- **Invalid character check** — expanded to catch shell-special characters (`|`, `&`,
  `;`, etc.) in addition to null bytes and non-printable characters.
- **Ornament models in weapon search** — `c_xms_festive_ornament` and similar
  schema-less non-weapon models are now excluded via a path-based blocklist, preventing
  them appearing in festive weapon searches.
### Changed
- All-class items with no class-specific variants now appear in all class searches
  rather than being silently excluded.
### Added
- **Schema caching** — `items_game.txt` is parsed once and saved to
  `output/schema_cache.json`. Subsequent runs load the cache instead of
  re-parsing, significantly reducing startup time. Cache automatically
  refreshes if TF2 updates items_game.txt.
- **Startup risk warning** — shown on every run. First run requires typing
  `agree` before continuing. Covers VAC risk, competitive league policies,
  and using the tool while TF2 is closed.
- **Acknowledgement flag** — stored in `output/.acknowledged` as a SHA256
  hash rather than plain text. This is not to hide anything (the source is
  fully open); it provides light tamper-resistance for liability purposes.
  Verifiable with: `hashlib.sha256(b"tf2autoswap_acknowledged").hexdigest()`
  Agreement is also timestamped in the log.
### Documentation
- README updated with a note on the Windows PATH warning for users on older versions.
## [4.6] - 2026-06-08
### Fixed
- **World model detection** — `derive_world_base()` now correctly derives the flat
  `w_models/w_<name>.mdl` path structure TF2 uses, rather than the nested folder
  structure that was assumed. World models now pack correctly for standard weapons.
- **All-class cosmetic class filtering** — per-class variants of all-class items
  (e.g. the Demoman variant of the Cozy Camper) no longer appear in searches for
  other classes. Handles shortened path names (`_demo`, `_engi`, `_solly` etc).
- **Duplicate weapon search results** — weapons appearing from multiple VPK paths
  with the same basename are deduplicated before displaying the pick list.
- **Weapon search clutter** — animation rigs, arm models, festivized variants,
  and seasonal reskins are filtered from weapon search results by default.
  Searching for a variant term directly (e.g. `festivizer`) still shows them.
- **Path validation** — custom output paths are validated before building.
  If a path isn't writable, the tool falls back to the output folder and
  tells the user, rather than writing to an unknown location silently.
- **Subfolder mod scanning** — list/remove mods now scans subfolders within
  the output directory, displayed separately from root-level mods.
### Added
- **Keyword normalisation** — search keywords are lowercased, spaces converted
  to underscores, and punctuation (apostrophes etc) stripped before matching.
  `crusader's getup` now finds `hwn2015_firebug_suit` correctly.
- **Friendly name reverse search** — if a keyword returns no VPK hits, the tool
  searches schema friendly names and retries with the matching internal stem.
  Works for both cosmetics and weapons.
- **Auto-select single results** — if a search returns exactly one match it is
  selected automatically with a confirmation line, skipping the pick prompt.
- **Menu selection confirmation** — choosing cosmetic swap or weapon swap from
  the main menu prints a confirmation line before the first step, so a wrong
  choice is immediately obvious.
- **Smarter "did you mean"** — suggestions are pre-filtered to stems sharing
  the same starting characters before running difflib, reducing unrelated matches.
- **Melee world model note** — when no world model is found for a melee weapon,
  the message now clarifies this is expected behaviour rather than an error.
## [4.5] - 2026-06-08
### Added
- **Slot compatibility warnings** — `clip_warning()` now warns on any equip region
  mismatch between source and target cosmetics, not just head replacements. If two
  items cover different areas of the player model, a warning is shown at the confirm
  step so the user can make an informed choice before proceeding.
- **Preloader write warning** — writing directly to the Casual Preloader folder now
  shows a hard warning explaining the risk and requires typing `yes` to confirm.
  This applies in both interactive mode and CLI (`--to-preloader`, custom paths that
  point inside the preloader folder).
### Changed
- Output folder and log file are now **self-contained within the tool folder** rather
  than writing to `~/tf2_swaps/`. Built VPKs go to `output/` and the log file sits
  alongside the scripts. This makes the tool fully portable — zip the folder and
  everything moves with it.
## [4.4] - 2026-06-07
### Added
- **Weapon swaps** — swap any TF2 weapon model for another, client-side.
  - Guided 5-step flow: class → loadout slot → weapon to replace → replacement → confirm & output.
  - Swaps both viewmodel (`c_models`) and worldmodel (`w_models`) in one operation. If no
    worldmodel is found for a weapon, the swap completes with the viewmodel only.
  - Slot mismatch warnings — warns if source and target are different loadout slots
    (e.g. primary into melee), which can cause animation or behaviour issues in-game.
  - Output to VPK or preloader addon folder (native installed format), identical to cosmetic swaps.
    Addon folder writes both model sets at their correct `models/weapons/c_models/...` and
    `models/weapons/w_models/...` paths, ready for the preloader with no manual import step.
  - `--weapon` CLI flag — routes `python3 tf2autoswap.py <source> <target> --weapon` to weapon mode.
  - `--list --weapon` lists weapon matches with slot labels.
### Changed
- Interactive menu expanded from 3 to 4 options: cosmetic swap / weapon swap / mods / installed.
- `ItemInfo` in `tf2_schema.py` gains three new fields: `item_slot` (e.g. "primary"),
  `item_type` ("cosmetic", "weapon", "unknown"), and `animation_risk` (True for melee weapons).
- `weapon_swap_warning()` added to `tf2_schema.py` (parallel to `clip_warning()`).
## [4.3] - 2026-06-07
### Added
- Output to the preloader now writes the preloader's native **installed addon
  format** (a folder with the extracted files plus a `mod.json` manifest),
  matching what the preloader creates when a VPK is dragged in. Mods sent to
  the preloader appear ready to enable, with no manual import step.
- Custom paths and `--out` that point inside the preloader folder are detected
  and written in addon format automatically.
### Changed
- Outputting elsewhere (the output folder, or any path outside the preloader)
  still produces a single `.vpk` — the portable form for sharing.
- `--list-installed` now lists native addon folders (detected via their
  `mod.json`) as well as loose `.vpk` files, flagging each from TF2autoswap.
  Only TF2autoswap addons are shown (reducing clutter); loose `.vpk` files
  are still flagged to the user.
- **Dry run / preview**: `--dry-run` on the command line shows exactly what
  would be built (file-by-file sizes, destination path) without writing
  anything. In interactive mode, a compact preview line (file count and size)
  shows at the confirm step.
## [4.2] - 2026-06-07
### Added
- Output directly to the preloader addons folder, removing the manual move step:
  - a "Preloader addons folder" choice at the output step in interactive mode
  - a `--to-preloader` command-line flag
  - passing a folder to `--out` now works (the filename is added for you)
- `--version` flag, and the version now shows in the interactive header.
### Fixed
- Giving a folder as the output path no longer crashes; the tool appends the
  generated filename instead of trying to write the VPK as a directory.
## [4.1] - 2026-06-07
### Changed
- Renamed the project to **TF2autoswap**.
- New output filename format using friendly names:
  `<Target> replacement mod (<Source>)_TF2autoswap.vpk`.
### Added
- List / remove mods you've built (interactive menu option and `--list-mods`).
- List `.vpk` addons present in the preloader folder (`--list-installed`),
  with your own files flagged via the `_TF2autoswap` signature.
- Interactive mode now opens to a menu: swap / manage mods / list installed.
## [4.0-beta] - 2026-06-07
### Changed
- Split the code into a clean core (`tf2_core.py`) and interface
  (`tf2autoswap.py`), so future frontends (TUI/GUI) sit on top without a rewrite.
### Added
- Error logging and build history written to `~/tf2_swaps/tf2autoswap.log`.
## Earlier development (pre-versioning)
### Added
- Friendly item names and head-clip warnings, read from TF2's item schema
  (`items_game.txt`) via `tf2_schema.py`. Warns when a head-replacement model
  is swapped onto a slot that doesn't hide the default head.
- Import custom models from disk (Gamebanana / custom work), automatically
  bundling a sibling `materials/` folder.
- "Did you mean" suggestions for typos, and search that treats spaces and
  underscores the same.
- Guided interactive mode and a scriptable command-line mode.
- Cross-platform TF2 path detection (Linux / Windows / macOS).
- Core swap engine: relocate one cosmetic's model onto another's path, patch
  the MDL header, and output a preloader-ready VPK.
