# TF2autoswap v4.8 — Testing Checklist

Thanks for testing! Work through the steps below and report anything unexpected as a GitHub issue.

---

## Setup

- [ ] Extract the zip and run `python3 tf2autoswap.py`
- [ ] On first run, the risk warning appears and requires typing `agree` to continue
- [ ] On second run, a one-line reminder appears instead of the full warning
- [ ] The `imports/` folder structure is created with organised subdirectories (cosmetics, weapons/viewmodel, weapons/worldmodel, weapons/materials, props, inventory)

---

## Basic

- [ ] Interactive menu loads with multiple swap options (cosmetic, weapon, **decorated weapon**, skin, prop, inventory, manage mods, list installed)
- [ ] A cosmetic swap completes and produces a `.vpk` in the `output/` folder
- [ ] A weapon swap completes and the output is larger than the cosmetic swap (world model included)

---

## Decorated Weapon Swap

**Requires:** Baldurs Tod's per-collection SFM Workshop mods installed, OR use the test VTFs in
`imports/weapons/materials/decorated_test_skins/`.

- [ ] Decorated weapon swap option appears in the main menu (between weapon swap and skin swap)
- [ ] Step 1 prompts for class selection (Scout, Soldier, Pyro, etc.)
- [ ] Step 2 lists correct weapons for that class (Heavy shows Minigun + Shotgun, Engineer shows Pistol + Shotgun + Wrench)
- [ ] Step 3 auto-detects SFM library skins (or falls back to manual VTF path if not installed)
- [ ] Library mode: skin names display correctly (e.g. "Brick House (Powerhouse)", not raw slugs)
- [ ] Selecting a skin generates the VMT, reads the VTF, and bundles both
- [ ] Output VPK contains 1 VMT + 1 VTF (∼2 MB typical)
- [ ] Manual VTF path: point at `imports/weapons/materials/decorated_test_skins/powerhouse_minigun_brickhouse.vtf`
- [ ] In-game: load the VPK via Casual Preloader and verify the minigun shows the Brick House skin

---

## Disk Import (Material Transport)

- [ ] Import a cosmetic model from disk with a sibling `materials/` folder — materials are bundled
- [ ] Import a weapon viewmodel from disk — worldmodel is auto-detected if present alongside it
- [ ] Import a model with materials containing suspicious flags (e.g. `$ignorez`) — materials are refused by the safety check

---

## Prop Swap

- [ ] Prop swap mode opens (interactive or via `--prop` CLI flag)
- [ ] Search for a prop (e.g. `barrel`) and pick a replacement
- [ ] Swap a large prop for a much smaller one — a size warning appears at the confirm step
- [ ] Swap props of similar size — no size warning appears

---

## Search

- [ ] Searching `festive` in weapon swap mode does **not** return ornament models
- [ ] Searching for an all-class item (e.g. `bills_hat`) with a class filter returns a result

---

## Output paths

- [ ] Custom path with no `.vpk` extension — filename is appended automatically
- [ ] Custom path containing `|` — rejected and falls back to `output/` folder

---

## Notes

- Report issues at: https://github.com/TF2Autoswap/releases/issues
- Include your OS, Python version, and the exact error or unexpected behaviour
