# TF2autoswap

[![Netlify Status](https://api.netlify.com/api/v1/badges/9791a194-65b5-40e0-aafc-62aa37204772/deploy-status)](https://app.netlify.com/sites/tf2autoswap/deploys)

A guided Python pipeline for client-side TF2 cosmetic and weapon model swapping. Handles asset lookup, safety checks, and VPK or native addon output automatically. Free to use — requires Python 3.8+.

Changes are visible only to you. No game files are permanently modified.
TF2 AutoSwap is a fan-made project and is not affiliated with Valve or Team Fortress 2.


---

## What it does

- Swap any cosmetic or weapon model for another
- Outputs a file ready for use with the [Casual Preloader](https://cueki.github.io/casual-pre-loader/) by cukei
- Guided step-by-step menu, or run from the command line
- Warns you before any swap that may cause visual clipping or animation issues

---

## Requirements

- Python 3.8 or later
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

**GNU GENERAL PUBLIC LICENSE** — Free to use and modify with credit.

---

## Credits

- Tool by **Sky (TF2Autoswap)** with coding assistance from Claude (Anthropic)
- Casual Preloader by **cukei** — [gamebanana.com/tools/19049](https://gamebanana.com/tools/19049)
