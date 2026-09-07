# TF2autoswap

[![Netlify Status](https://api.netlify.com/api/v1/badges/9791a194-65b5-40e0-aafc-62aa37204772/deploy-status)](https://app.netlify.com/sites/tf2autoswap/deploys)

A guided Python pipeline for client-side TF2 cosmetic and weapon model swapping. Handles asset lookup, safety checks, and VPK or native addon output automatically. Free to use — requires Python 3.8+.

Changes are visible only to you. No game files are permanently modified.
TF2 AutoSwap is a fan-made project and is not affiliated with Valve or Team Fortress 2.


---

## Important notice

- **VAC risk** — client-side model swaps are a grey area. Use at your own risk and only while TF2 is closed.
- **Competitive leagues** — most leagues prohibit visual modifications. Check the rules for any league you play in before using this tool.
- This tool has no affiliation with Valve or the TF2 team.

---

## What it does

- Swap any cosmetic or weapon model for another
- Apply custom material reskins to weapons or cosmetics via a safety-filtered pipeline
- Swap map props with size-mismatch warnings to keep play fair
- Load your Steam inventory to pick items as swap sources or targets
- Outputs a file ready for use with the [Casual Preloader](https://cueki.github.io/casual-pre-loader/) by cukei
- Guided step-by-step menu, or run from the command line
- Warns you before any swap that may cause visual clipping or animation issues

---

## Requirements

- Python 3.8 or later
- Windows, Linux, or macOS
- Dependencies install automatically on first run

---

## Getting started

Download the latest release, extract the folder, then run:

```
python3 tf2autoswap.py
```

Full documentation is included with each release.

---

## Development process

All releases follow a structured pipeline:

**Research & evaluation → Scope check & feasibility → Implementation → Local testing → Robust evaluation → Release**

See the [Development Process](https://github.com/TF2Autoswap/main/wiki/Development-Process) wiki page for full details.

---

## License

**GNU GENERAL PUBLIC LICENSE v3** — Free to use, modify, and distribute. See `LICENSE` for full terms.

---

## Credits

- Tool by **Sky (TF2Autoswap)** with AI assistance via OpenRouter
- Casual Preloader by **cukei** — [gamebanana.com/tools/19049](https://gamebanana.com/tools/19049)
