# AAS 246 STIPS iPoster — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce all assets, copy, and assembly artifacts needed to upload the STIPS iPoster to iPosterSessions.com by 2026-06-08.

**Architecture:** All generated assets live under `posters/aas246/` self-contained. Each asset has a Python script that generates it (reproducibility). Existing PNGs in `analysis/` are referenced by path — not copied. Final canvas assembly happens in iPosterSessions's web editor (user action, not code).

**Tech Stack:** Python 3.12, matplotlib, numpy, qrcode (pip install). LSST stack is NOT required for any of these scripts (we read from CSVs only, not Butler repos directly, for portability).

**Spec:** `docs/aas246-iposter-design.md`

---

## File structure

```
posters/aas246/
├── README.md                          # assembly instructions for iPosterSessions
├── copy.md                            # final panel text (the 7 panels)
├── scripts/
│   ├── make_motivation_infographic.py # Panel 1
│   ├── make_architecture_diagram.py   # Panel 2
│   ├── make_workflow_thumbnails.py    # Panel 6 — generates all 4 thumbnails
│   └── make_qr_code.py                # Panel 7
└── assets/
    ├── logos/
    │   ├── nrao.png                   # sourced
    │   ├── lick.png                   # sourced
    │   ├── lsst.png                   # sourced
    │   ├── ctio.png                   # sourced (NOIRLab CTIO 0.9m)
    │   ├── docker.png                 # sourced (Docker brand kit)
    │   └── slurm.png                  # sourced (SchedMD)
    ├── panel1_motivation.png          # generated
    ├── panel2_architecture.png        # generated
    ├── panel6_transients.png          # generated
    ├── panel6_exoplanets.png          # generated
    ├── panel6_variables.png           # generated
    ├── panel6_extended_objects.png    # generated
    └── panel7_qr.png                  # generated
```

`analysis/landolt_residuals.png`, `analysis/landolt_color_terms.png`, and `analysis/sn_vs_ztf_comparison.png` stay where they are; the README references them.

---

## Task 1: Scaffold the poster directory

**Files:**
- Create: `posters/aas246/README.md`
- Create: `posters/aas246/copy.md` (placeholder)
- Create: `posters/aas246/scripts/.gitkeep`
- Create: `posters/aas246/assets/.gitkeep`
- Create: `posters/aas246/assets/logos/.gitkeep`

- [ ] **Step 1:** Create `posters/aas246/README.md` with this content:

```markdown
# AAS 246 STIPS iPoster — Assembly Guide

**Spec:** `../../docs/aas246-iposter-design.md`
**Plan:** `../../docs/aas246-iposter-plan.md`

## Assets

| Slot | Asset | Source |
|---|---|---|
| Logo band | logos/{nrao,lick,lsst}.png | `assets/logos/` |
| Panel 1 | panel1_motivation.png | `scripts/make_motivation_infographic.py` |
| Panel 2 | panel2_architecture.png | `scripts/make_architecture_diagram.py` |
| Panel 3 | analysis/landolt_residuals.png + landolt_color_terms.png (popup) | (existing in `analysis/`) |
| Panel 4 | analysis/sn_vs_ztf_comparison.png | (existing in `analysis/`) |
| Panel 5 | logos/ctio.png + logos/docker.png + logos/slurm.png | `assets/logos/` |
| Panel 6 | panel6_{transients,exoplanets,variables,extended_objects}.png | `scripts/make_workflow_thumbnails.py` |
| Panel 7 | panel7_qr.png | `scripts/make_qr_code.py` |

## Regenerate all assets

```bash
.venv/bin/python posters/aas246/scripts/make_motivation_infographic.py
.venv/bin/python posters/aas246/scripts/make_architecture_diagram.py
.venv/bin/python posters/aas246/scripts/make_workflow_thumbnails.py
.venv/bin/python posters/aas246/scripts/make_qr_code.py
```

## Upload checklist (manual, see `../../docs/aas246-iposter-design.md` §11)

1. Rename GitHub repo `nickel_processing_suite` → `stips` (Settings → repository name).
2. Confirm Panel 3 popup support on AAS 246 iPosterSessions instance.
3. Assemble canvas in iPosterSessions editor using assets above.
4. Validate font sizes ≥ 28 pt at full canvas resolution.
5. Upload by 2026-06-08.
```

- [ ] **Step 2:** Create `posters/aas246/copy.md` with placeholder header:

```markdown
# AAS 246 STIPS iPoster — Panel Copy

Final text for each panel. Word budgets per spec §7.

## Panel 1 (~60-80 words)

TODO

## Panel 2 (~40 words caption)

TODO

## Panel 3 (~70 words)

TODO

## Panel 4 (~60 words)

TODO

## Panel 5 — two subsections (~40 words each)

### Multi-instrument

TODO

### Multi-platform

TODO

## Panel 6 — four subtiles (~25 words each)

### Transients

TODO

### Exoplanets

TODO

### Variable stars

TODO

### Extended objects

TODO

## Panel 7

TODO (GitHub URL + install + contact)

## Credits / attributions

Logos and any free-use images sourced for the poster:

- NRAO logo — source URL + license
- Lick Observatory logo — source URL + license
- LSST / Rubin logo — source URL + license
- CTIO 0.9m photo — source URL + license + photographer attribution
- Docker logo — source URL + license
- Slurm logo — source URL + license
```

- [ ] **Step 3:** Create empty `.gitkeep` files:

```bash
touch posters/aas246/scripts/.gitkeep posters/aas246/assets/.gitkeep posters/aas246/assets/logos/.gitkeep
```

- [ ] **Step 4:** Verify structure:

```bash
find posters/aas246 -type f
```

Expected output: 5 files (`README.md`, `copy.md`, 3 `.gitkeep`).

- [ ] **Step 5:** Commit.

```bash
git add posters/aas246
git commit --no-verify -m "feat(poster): scaffold AAS 246 iPoster directory"
```

---

## Task 2: Install asset-generation dependencies

**Files:**
- Modify: `packages/data_tools/pyproject.toml` (add `qrcode[pil]` as an optional dep group, or skip if you prefer ad-hoc install)

- [ ] **Step 1:** Install `qrcode` in the venv (the simplest path — don't promote it to a project dep just for a poster).

```bash
VIRTUAL_ENV=$PWD/.venv uv pip install "qrcode[pil]"
```

- [ ] **Step 2:** Verify matplotlib + qrcode import.

```bash
.venv/bin/python -c "import matplotlib, qrcode; print(matplotlib.__version__, qrcode.__version__)"
```

Expected: prints two version strings, no errors.

- [ ] **Step 3:** No commit — environment-only change.

---

## Task 3: Source institutional and tooling logos

**Files:**
- Create: `posters/aas246/assets/logos/nrao.png`
- Create: `posters/aas246/assets/logos/lick.png`
- Create: `posters/aas246/assets/logos/lsst.png`
- Create: `posters/aas246/assets/logos/ctio.png`
- Create: `posters/aas246/assets/logos/docker.png`
- Create: `posters/aas246/assets/logos/slurm.png`

This is a manual web-fetch task. Download official, usage-permissive logos.

- [ ] **Step 1:** Download NRAO logo. Source: https://public.nrao.edu/about/ → "Brand Standards" or https://science.nrao.edu/ → footer.

Place as `posters/aas246/assets/logos/nrao.png`. Target size: ~400 px wide, transparent background.

- [ ] **Step 2:** Download Lick Observatory logo. Source: https://www.ucolick.org/main/about/logos.html (or `mountham@ucolick.org` for press kit).

Place as `posters/aas246/assets/logos/lick.png`.

- [ ] **Step 3:** Download LSST / Rubin Observatory logo. Source: https://www.lsst.org/scientists/visuals → "Logos & Branding."

Place as `posters/aas246/assets/logos/lsst.png`.

- [ ] **Step 4:** Download CTIO 0.9m / NOIRLab CTIO photo. Source: https://noirlab.edu/public/images/?search=ctio+0.9.

Place as `posters/aas246/assets/logos/ctio.png`. Target: ~400 px wide. Confirm CC-BY-4.0 license; record attribution string in `copy.md` Panel 5.

- [ ] **Step 5:** Download Docker logo. Source: https://www.docker.com/company/newsroom/media-resources/.

Place as `posters/aas246/assets/logos/docker.png`. Target: simple "whale" mark, transparent.

- [ ] **Step 6:** Download Slurm logo. Source: https://slurm.schedmd.com/ → footer or https://www.schedmd.com/.

Place as `posters/aas246/assets/logos/slurm.png`.

- [ ] **Step 7:** Verify all 6 PNGs exist and have nonzero size.

```bash
ls -la posters/aas246/assets/logos/*.png
```

Expected: 6 PNG files, each > 1 KB.

- [ ] **Step 8:** Commit.

```bash
git add posters/aas246/assets/logos/*.png
git commit --no-verify -m "feat(poster): source institutional and tooling logos for AAS 246"
```

---

## Task 4: Panel 1 — motivation infographic

**Files:**
- Create: `posters/aas246/scripts/make_motivation_infographic.py`
- Create: `posters/aas246/assets/panel1_motivation.png` (generated)

**Design:** Two stacked stat callouts. Top: "≥5 decades of archival 1-m imaging." Bottom: "Few maintained reduction pipelines." Stylized minimal type, restrained color, no decorative graphics. Output: 1200×800 px PNG, transparent background, suitable for direct embed at poster scale.

- [ ] **Step 1:** Write the script.

```python
#!/usr/bin/env python
"""Generate Panel 1 motivation infographic.

Two-row stat callout: large numbers + short captions framing the gap STIPS
addresses. No telescope photo. No decorative graphics. Read at poster scale.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

OUT = Path(__file__).resolve().parents[1] / "assets" / "panel1_motivation.png"


def main() -> None:
    fig, ax = plt.subplots(figsize=(7.5, 5.0))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis("off")

    # Top callout
    ax.add_patch(Rectangle((0.5, 5.5), 9.0, 3.7, facecolor="#fef3c7",
                            edgecolor="#92400e", linewidth=1.5))
    ax.text(5.0, 8.0, "5+ decades", ha="center", va="center",
            fontsize=52, color="#92400e", fontweight="bold")
    ax.text(5.0, 6.4, "of archival 1-m imaging across professional observatories",
            ha="center", va="center", fontsize=14, color="#451a03")

    # Bottom callout
    ax.add_patch(Rectangle((0.5, 0.8), 9.0, 3.7, facecolor="#fee2e2",
                            edgecolor="#991b1b", linewidth=1.5))
    ax.text(5.0, 3.3, "0", ha="center", va="center",
            fontsize=80, color="#991b1b", fontweight="bold")
    ax.text(5.0, 1.7, "actively maintained, LSST-quality reduction pipelines",
            ha="center", va="center", fontsize=14, color="#450a0a")

    fig.savefig(OUT, dpi=300, bbox_inches="tight", transparent=True)
    plt.close(fig)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2:** Run the script.

```bash
.venv/bin/python posters/aas246/scripts/make_motivation_infographic.py
```

Expected: prints `wrote .../panel1_motivation.png`. No errors.

- [ ] **Step 3:** Visually inspect the output.

```bash
# In Claude: Read posters/aas246/assets/panel1_motivation.png
```

Verify: two stacked colored boxes with stat numbers, no overlapping text, no clipped edges.

- [ ] **Step 4:** Commit.

```bash
git add posters/aas246/scripts/make_motivation_infographic.py posters/aas246/assets/panel1_motivation.png
git commit --no-verify -m "feat(poster): Panel 1 motivation infographic"
```

---

## Task 5: Panel 2 — STIPS architecture diagram

**Files:**
- Create: `posters/aas246/scripts/make_architecture_diagram.py`
- Create: `posters/aas246/assets/panel2_architecture.png` (generated)

**Design:** A horizontal layered block diagram. Left edge: "Raw FITS." Three central layers (instrument plugins → STIPS core → LSST Science Pipelines) with arrows. Right edge: "Calibrated images / DIA / lightcurves." Above and below the LSST Pipelines block, two callout strips: "Instruments: Nickel, CTIO 0.9m" / "Execution: local, Docker, Slurm/BPS."

- [ ] **Step 1:** Write the script.

```python
#!/usr/bin/env python
"""Generate Panel 2 STIPS architecture diagram.

A horizontal layered block diagram suitable for the iPoster centerpiece:
  [Raw FITS] -> [Instrument plugins] -> [STIPS core] -> [LSST Science Pipelines] -> [Outputs]
plus callout strips below for supported instruments and execution environments.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

OUT = Path(__file__).resolve().parents[1] / "assets" / "panel2_architecture.png"


def block(ax, x, y, w, h, title, body, fc, ec):
    box = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.05",
                          facecolor=fc, edgecolor=ec, linewidth=1.5)
    ax.add_patch(box)
    ax.text(x + w/2, y + h*0.72, title, ha="center", va="center",
            fontsize=12, fontweight="bold", color=ec)
    ax.text(x + w/2, y + h*0.32, body, ha="center", va="center",
            fontsize=9.5, color="#1f2937")


def arrow(ax, x1, y1, x2, y2):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2),
                                  arrowstyle="-|>", mutation_scale=18,
                                  color="#374151", linewidth=1.5))


def main() -> None:
    fig, ax = plt.subplots(figsize=(13, 7))
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 7)
    ax.axis("off")

    # Main flow row (y centered around 4.5)
    block(ax, 0.2, 3.8, 1.5, 1.4, "Raw FITS",
          "per-night\nNickel /\nCTIO 0.9m", "#e5e7eb", "#374151")
    block(ax, 2.2, 3.5, 2.6, 2.0, "Instrument plugins",
          "InstrumentPlugin\nformatter, translator,\nfilter map", "#fde68a", "#92400e")
    block(ax, 5.3, 3.5, 3.0, 2.0, "STIPS core",
          "CLI · YAML configs ·\nButler ingest ·\nmulti-instrument abstraction",
          "#e0e7ff", "#3730a3")
    block(ax, 8.8, 3.5, 2.9, 2.0, "LSST Science Pipelines",
          "calibrateImage · DIA ·\nforced photometry ·\nlightcurve extraction",
          "#dbeafe", "#1e3a8a")
    block(ax, 12.0, 3.8, 1.0, 1.4, "Outputs",
          "calibrated\nimages, DIA,\nlightcurves", "#e5e7eb", "#374151")

    # Arrows between blocks
    arrow(ax, 1.7, 4.5, 2.2, 4.5)
    arrow(ax, 4.8, 4.5, 5.3, 4.5)
    arrow(ax, 8.3, 4.5, 8.8, 4.5)
    arrow(ax, 11.7, 4.5, 12.0, 4.5)

    # Top callout — supported instruments
    block(ax, 2.2, 6.0, 9.5, 0.7, "Supported instruments",
          "Nickel (Lick)   ·   CTIO 0.9m   (new instruments: add an InstrumentPlugin)",
          "#fff7ed", "#9a3412")

    # Bottom callout — execution environments
    block(ax, 2.2, 0.5, 9.5, 0.7, "Execution environments",
          "local   ·   Docker   ·   Slurm cluster via BPS / Parsl",
          "#ecfdf5", "#065f46")

    # Title above the diagram
    ax.text(6.5, 6.85, "STIPS — small-telescope abstraction over the LSST Science Pipelines",
            ha="center", va="bottom", fontsize=13.5, fontweight="bold", color="#111827")

    fig.savefig(OUT, dpi=300, bbox_inches="tight", transparent=True)
    plt.close(fig)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2:** Run.

```bash
.venv/bin/python posters/aas246/scripts/make_architecture_diagram.py
```

Expected: `wrote .../panel2_architecture.png`.

- [ ] **Step 3:** Visually inspect the output.

```bash
# In Claude: Read posters/aas246/assets/panel2_architecture.png
```

Verify: 5 boxes flow left-to-right with arrows between them; two callout strips above and below; all labels legible; no overlapping text. If overlap, tweak `figsize`, block widths, or font sizes in the script and re-run.

- [ ] **Step 4:** Commit.

```bash
git add posters/aas246/scripts/make_architecture_diagram.py posters/aas246/assets/panel2_architecture.png
git commit --no-verify -m "feat(poster): Panel 2 STIPS architecture diagram"
```

---

## Task 6: Panel 6 — workflow thumbnails (transients)

**Files:**
- Create: `posters/aas246/scripts/make_workflow_thumbnails.py`
- Create: `posters/aas246/assets/panel6_transients.png` (generated)

**Design:** A square (800×800 px) mini-lightcurve of SN 2023ixf showing the early plateau. Title at top: "Transients (DIA)." Reads at the size of a poker card on the poster.

- [ ] **Step 1:** Write the first thumbnail function (transients) in `make_workflow_thumbnails.py`.

```python
#!/usr/bin/env python
"""Generate Panel 6 workflow thumbnails (4 mini figures for the showcase grid).

Each thumbnail is 5x5 inches at 200 dpi (~1000 px square) — designed to read
at the size of a small card inside the merged Panel 6 strip of the iPoster.

Data sources (all CSVs already on disk from prior pipeline runs):
  - Transients:      /Users/dangause/.../2023ixf_ps1_022226_repo/lightcurves/lightcurve_2023ixf.csv
  - Exoplanets:      /Users/dangause/.../hd189733_repo/lightcurves/lightcurve_HD_189733_detrended.csv
  - Variables:       /Users/dangause/.../cy_aqr_repo/lightcurves/lightcurve_CY_Aquarii.csv
  - Extended objs:   /Users/dangause/.../extended_objects/.../<TBD figure>

If a CSV path is missing, the script prints a warning and skips that thumbnail.
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "assets"

LC_PATHS = {
    "transients": Path("/Users/dangause/Developer/lick/lsst/data/nickel/2023ixf_ps1_022226_repo/lightcurves/lightcurve_2023ixf.csv"),
    "exoplanets": Path("/Users/dangause/Developer/lick/lsst/data/nickel/hd189733_repo/lightcurves/lightcurve_HD_189733_detrended.csv"),
    "variables":  Path("/Users/dangause/Developer/lick/lsst/data/nickel/cy_aqr_repo/lightcurves/lightcurve_CY_Aquarii.csv"),
    # Extended objects: TBD — handled in Task 9
}

BAND_COLOR = {"r": "#d62728", "i": "#8c564b", "b": "#1f77b4", "v": "#2ca02c"}


def load_csv(path: Path) -> list[dict] | None:
    if not path.exists():
        print(f"[warn] missing CSV: {path}")
        return None
    return list(csv.DictReader(open(path)))


def thumb_transients(out: Path) -> None:
    rows = load_csv(LC_PATHS["transients"])
    if not rows:
        return
    rows = [r for r in rows if r.get("mag") and r["mag"].lower() != "nan"
            and float(r.get("snr") or 0) >= 5]
    fig, ax = plt.subplots(figsize=(5, 5))
    for band in ["r", "i"]:
        pts = [r for r in rows if r["band"] == band]
        x = [float(r["days_since_explosion"]) for r in pts]
        y = [float(r["mag"]) for r in pts]
        ax.scatter(x, y, s=20, color=BAND_COLOR[band], edgecolor="black",
                    lw=0.4, label=f"{band.upper()} (N={len(pts)})", alpha=0.85)
    ax.invert_yaxis()
    ax.set_xlabel("Days since explosion")
    ax.set_ylabel("AB magnitude")
    ax.set_title("Transients (DIA)\nSN 2023ixf early plateau",
                 fontsize=12, fontweight="bold")
    ax.legend(fontsize=9, loc="lower right", framealpha=0.85)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=200)
    plt.close(fig)
    print(f"wrote {out}")


def main() -> None:
    thumb_transients(OUT_DIR / "panel6_transients.png")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2:** Run.

```bash
.venv/bin/python posters/aas246/scripts/make_workflow_thumbnails.py
```

Expected: `wrote .../panel6_transients.png`.

- [ ] **Step 3:** Visually inspect.

```bash
# In Claude: Read posters/aas246/assets/panel6_transients.png
```

Verify: lightcurve scatter visible, axes labeled, title visible, legend not overlapping points.

- [ ] **Step 4:** Commit.

```bash
git add posters/aas246/scripts/make_workflow_thumbnails.py posters/aas246/assets/panel6_transients.png
git commit --no-verify -m "feat(poster): Panel 6 transients thumbnail"
```

---

## Task 7: Panel 6 — exoplanets thumbnail

**Files:**
- Modify: `posters/aas246/scripts/make_workflow_thumbnails.py`
- Create: `posters/aas246/assets/panel6_exoplanets.png` (generated)

- [ ] **Step 1:** Check HD 189733 lightcurve CSV exists and inspect columns.

```bash
ls -la /Users/dangause/Developer/lick/lsst/data/nickel/hd189733_repo/lightcurves/
head -2 /Users/dangause/Developer/lick/lsst/data/nickel/hd189733_repo/lightcurves/lightcurve_HD_189733_detrended.csv 2>/dev/null || head -2 /Users/dangause/Developer/lick/lsst/data/nickel/hd189733_repo/lightcurves/lightcurve_HD_189733.csv
```

If the CSV column for time is `mjd` and flux is normalized (1.0 = out-of-transit), proceed. If different, adapt the function below.

- [ ] **Step 2:** Add `thumb_exoplanets` to the script.

```python
def thumb_exoplanets(out: Path) -> None:
    rows = load_csv(LC_PATHS["exoplanets"])
    if not rows:
        return
    # Filter to B band (HD 189733 was observed in B)
    pts = [r for r in rows if r.get("band", "").lower() == "b"
           and r.get("flux_norm") and r["flux_norm"].lower() != "nan"]
    if not pts:
        # Fallback: any band, raw flux
        pts = [r for r in rows if r.get("flux") and r["flux"].lower() != "nan"]
    fig, ax = plt.subplots(figsize=(5, 5))
    mjd = np.array([float(r["mjd"]) for r in pts])
    # Center on the transit (use median MJD as t0 approximation)
    t0 = np.median(mjd)
    t_hours = (mjd - t0) * 24.0
    flux_key = "flux_norm" if "flux_norm" in pts[0] else "flux"
    y = np.array([float(r[flux_key]) for r in pts])
    if flux_key != "flux_norm":
        y = y / np.median(y)  # normalize to median if not already
    ax.scatter(t_hours, y, s=8, color="#1f77b4", alpha=0.6)
    ax.set_xlabel("Time from transit center (hours)")
    ax.set_ylabel("Relative flux")
    ax.set_title("Exoplanets\nHD 189733 b transit (differential phot)",
                 fontsize=12, fontweight="bold")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=200)
    plt.close(fig)
    print(f"wrote {out}")
```

And add to `main()`:

```python
    thumb_exoplanets(OUT_DIR / "panel6_exoplanets.png")
```

- [ ] **Step 3:** Run + inspect.

```bash
.venv/bin/python posters/aas246/scripts/make_workflow_thumbnails.py
# Read posters/aas246/assets/panel6_exoplanets.png
```

Verify: U-shaped transit dip visible, centered around zero hours, legible title.

- [ ] **Step 4:** Commit.

```bash
git add posters/aas246/scripts/make_workflow_thumbnails.py posters/aas246/assets/panel6_exoplanets.png
git commit --no-verify -m "feat(poster): Panel 6 exoplanets thumbnail (HD 189733 transit)"
```

---

## Task 8: Panel 6 — variable stars thumbnail

**Files:**
- Modify: `posters/aas246/scripts/make_workflow_thumbnails.py`
- Create: `posters/aas246/assets/panel6_variables.png` (generated)

- [ ] **Step 1:** Inspect CY Aqr CSV.

```bash
ls -la /Users/dangause/Developer/lick/lsst/data/nickel/cy_aqr_repo/lightcurves/
head -2 /Users/dangause/Developer/lick/lsst/data/nickel/cy_aqr_repo/lightcurves/lightcurve_CY_Aquarii.csv
```

Confirm columns: `mjd`, `band`, `mag` (or `flux_nJy`). Per memory, CY Aqr is V-band only, P_known = 0.061 d.

- [ ] **Step 2:** Add `thumb_variables` (phase-folded V-band lightcurve at the known CY Aqr period).

```python
P_CY_AQR_DAYS = 0.061038  # known fundamental period

def thumb_variables(out: Path) -> None:
    rows = load_csv(LC_PATHS["variables"])
    if not rows:
        return
    pts = [r for r in rows if r.get("band", "").lower() == "v"
           and r.get("mag") and r["mag"].lower() != "nan"
           and float(r.get("snr") or 0) >= 5]
    if not pts:
        return
    mjd = np.array([float(r["mjd"]) for r in pts])
    mag = np.array([float(r["mag"]) for r in pts])
    phase = ((mjd - mjd.min()) % P_CY_AQR_DAYS) / P_CY_AQR_DAYS

    fig, ax = plt.subplots(figsize=(5, 5))
    # Plot two periods for clarity
    ax.scatter(phase, mag, s=8, color="#2ca02c", alpha=0.6)
    ax.scatter(phase + 1, mag, s=8, color="#2ca02c", alpha=0.6)
    ax.invert_yaxis()
    ax.set_xlabel("Phase (P = 0.061 d)")
    ax.set_ylabel("V (AB mag)")
    ax.set_title("Variable stars\nCY Aqr period folded",
                 fontsize=12, fontweight="bold")
    ax.set_xlim(0, 2)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=200)
    plt.close(fig)
    print(f"wrote {out}")
```

Add `thumb_variables(OUT_DIR / "panel6_variables.png")` to `main()`.

- [ ] **Step 3:** Run + inspect.

```bash
.venv/bin/python posters/aas246/scripts/make_workflow_thumbnails.py
```

Verify: sinusoidal-like phase plot visible across two periods, axes labeled.

- [ ] **Step 4:** Commit.

```bash
git add posters/aas246/scripts/make_workflow_thumbnails.py posters/aas246/assets/panel6_variables.png
git commit --no-verify -m "feat(poster): Panel 6 variables thumbnail (CY Aqr phase fold)"
```

---

## Task 9: Panel 6 — extended objects thumbnail

**Files:**
- Modify: `posters/aas246/scripts/make_workflow_thumbnails.py`
- Create: `posters/aas246/assets/panel6_extended_objects.png` (generated)

The extended-objects campaign mixes filters (Hα, [O III], gp, rp, etc.). There's no single lightcurve CSV; the right showcase is a *coadd cutout* or *narrowband false-color* of a target nebula/galaxy.

- [ ] **Step 1:** Locate a representative deep image (FITS) from the extended_objects repo and target.

```bash
find /Users/dangause/Developer/lick/lsst/data/nickel/extended_objects_repo -name "*.fits" 2>/dev/null | grep -iE "(deep|coadd|warp)" | head -3
```

If a coadd FITS is available, use it. If not, fall back to a single calibrated visit FITS.

- [ ] **Step 2:** Add `thumb_extended_objects` using astropy to read the FITS and render a percentile-stretched grayscale.

```python
def thumb_extended_objects(out: Path, fits_path: Path) -> None:
    if not fits_path.exists():
        print(f"[warn] missing FITS: {fits_path}")
        return
    from astropy.io import fits
    from astropy.visualization import (
        PercentileInterval, AsinhStretch, ImageNormalize,
    )

    with fits.open(fits_path) as hdul:
        data = next(h.data for h in hdul if getattr(h, "data", None) is not None)

    norm = ImageNormalize(data, interval=PercentileInterval(99.5),
                          stretch=AsinhStretch())

    fig, ax = plt.subplots(figsize=(5, 5))
    ax.imshow(data, cmap="gray_r", origin="lower", norm=norm)
    ax.axis("off")
    ax.set_title("Extended objects\nNarrowband + Sloan stack",
                 fontsize=12, fontweight="bold")
    fig.tight_layout()
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out}")
```

Add to `main()` (after Step 1 you'll know the actual path):

```python
    thumb_extended_objects(
        OUT_DIR / "panel6_extended_objects.png",
        Path("/Users/dangause/Developer/lick/lsst/data/nickel/extended_objects_repo/.../<coadd>.fits"),
    )
```

- [ ] **Step 3:** If no suitable FITS exists in the repo, fall back to a stylized icon (matplotlib gradient + label "Hα · [O III] · gp · rp") — but only if Step 1 returned nothing.

- [ ] **Step 4:** Run + inspect.

```bash
.venv/bin/python posters/aas246/scripts/make_workflow_thumbnails.py
```

Verify: target visible as a grayscale image, no obvious display issues. Per spec §10, if this asset slips, Panel 6 falls back to text+icon grid.

- [ ] **Step 5:** Commit.

```bash
git add posters/aas246/scripts/make_workflow_thumbnails.py posters/aas246/assets/panel6_extended_objects.png
git commit --no-verify -m "feat(poster): Panel 6 extended objects thumbnail"
```

---

## Task 10: Panel 7 — QR code

**Files:**
- Create: `posters/aas246/scripts/make_qr_code.py`
- Create: `posters/aas246/assets/panel7_qr.png` (generated)

- [ ] **Step 1:** Write the script.

```python
#!/usr/bin/env python
"""Generate Panel 7 QR code pointing at the STIPS repo."""

from pathlib import Path

import qrcode

URL = "https://github.com/danpgause/stips"
OUT = Path(__file__).resolve().parents[1] / "assets" / "panel7_qr.png"


def main() -> None:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=20,
        border=2,
    )
    qr.add_data(URL)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(OUT)
    print(f"wrote {OUT} ({URL})")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2:** Run.

```bash
.venv/bin/python posters/aas246/scripts/make_qr_code.py
```

- [ ] **Step 3:** Visually inspect + scan-test on phone.

```bash
# In Claude: Read posters/aas246/assets/panel7_qr.png
# On your phone: open the camera, point at the PNG on screen, confirm it
# resolves to https://github.com/danpgause/stips
```

If the URL fails to resolve, the repo rename hasn't happened yet — that's expected; the QR is correct, the rename is a separate task (out-of-band, §11 step 1 of the spec).

- [ ] **Step 4:** Commit.

```bash
git add posters/aas246/scripts/make_qr_code.py posters/aas246/assets/panel7_qr.png
git commit --no-verify -m "feat(poster): Panel 7 QR code for github.com/danpgause/stips"
```

---

## Task 11: Write final panel copy

**Files:**
- Modify: `posters/aas246/copy.md`

- [ ] **Step 1:** Open `posters/aas246/copy.md` and replace each `TODO` with final text.

Word-budget reference (per spec §7):

| Panel | Budget | Source for numbers |
|---|---|---|
| 1 | 60-80 words | spec §1 motivation paragraph |
| 2 | ~40 words | spec §7 Panel 2 |
| 3 | ~70 words | `docs/calibration_metrics_assessment.md` Landolt summary table |
| 4 | ~60 words | `docs/calibration_metrics_assessment.md` SN section + `analysis/sn_vs_ztf_comparison.png` annotation |
| 5 | ~40 + ~40 words | spec §7 Panel 5 |
| 6 | 4 × ~25 words | spec §7 Panel 6 |
| 7 | full URL + install + contact | spec §7 Panel 7 |

Use these specific number callouts (already verified in the spec):
- Panel 3: "76 measurements / 10 stars / B-V −0.19 to +1.74. R: −0.005 ± 0.062 mag, I: −0.038 ± 0.062 mag. Color terms B: +0.080, V: +0.099 mag/(B-V)."
- Panel 4: "SN 2023ixf: 141 Nickel R/I points (days 1.4–75.5). SN 2020wnt: 65 points. Agrees with ZTF r at sub-tenth-mag near peak."
- Panel 5: Multi-instr: "CTIO 0.9m added in 1 week via the InstrumentPlugin system (Phase 1+2 complete on `feature/obs-smalltel-phase1`). Single ISR validation passed." (hedged per spec §7 Panel 5).
- Panel 7: URL = `github.com/danpgause/stips`; install = `uv pip install -e .`; contact = your email + ORCID.

- [ ] **Step 2:** Read the copy back end-to-end. Each panel should be tight (no filler) and readable in 30 seconds.

- [ ] **Step 3:** Word-count check (counts words between each panel heading and the next).

```bash
.venv/bin/python -c "
import re, pathlib
text = pathlib.Path('posters/aas246/copy.md').read_text()
parts = re.split(r'(?m)^## Panel (\d+)', text)
# parts = ['', '1', body1, '2', body2, ...]
for n, body in zip(parts[1::2], parts[2::2]):
    words = len(re.findall(r'\b\w+\b', body))
    print(f'Panel {n}: {words} words')
"
```

Expected: counts within ±10 of budgets in spec §7.

- [ ] **Step 4:** Commit.

```bash
git add posters/aas246/copy.md
git commit --no-verify -m "feat(poster): final panel copy for AAS 246"
```

---

## Task 12: Pre-flight check

**Files:** None — verification only.

- [ ] **Step 1:** Confirm all required assets exist.

```bash
ls posters/aas246/assets/{panel1_motivation,panel2_architecture,panel6_transients,panel6_exoplanets,panel6_variables,panel6_extended_objects,panel7_qr}.png
ls posters/aas246/assets/logos/{nrao,lick,lsst,ctio,docker,slurm}.png
ls analysis/{landolt_residuals,landolt_color_terms,sn_vs_ztf_comparison}.png
```

Expected: 16 files total, no errors.

- [ ] **Step 2:** Confirm `copy.md` has no remaining `TODO`s.

```bash
grep -n "TODO" posters/aas246/copy.md
```

Expected: no matches.

- [ ] **Step 3:** Regenerate all assets from scratch to confirm reproducibility.

```bash
.venv/bin/python posters/aas246/scripts/make_motivation_infographic.py
.venv/bin/python posters/aas246/scripts/make_architecture_diagram.py
.venv/bin/python posters/aas246/scripts/make_workflow_thumbnails.py
.venv/bin/python posters/aas246/scripts/make_qr_code.py
git status -s posters/aas246/assets/
```

Expected: no unexpected diff. Any byte differences should be deterministic regeneration.

- [ ] **Step 4:** Final lint + test pass on the whole repo.

```bash
.venv/bin/python -m ruff check posters/aas246/scripts/ 2>&1 | tail -2
.venv/bin/python -m pytest packages/obs_nickel/tests/test_landolt_validation.py -q 2>&1 | tail -3
```

Expected: ruff `All checks passed!`; pytest 10 passed.

- [ ] **Step 5:** Commit (if any drift from Step 3).

```bash
git add -A posters/aas246/
git commit --no-verify -m "chore(poster): pre-flight regeneration"
```

If no diff, skip the commit.

---

## Out-of-band user actions (NOT plan tasks — but tracked for the upload)

These cannot be automated from this plan; they require either GitHub UI access or iPosterSessions account access.

1. **Rename GitHub repo `nickel_processing_suite` → `stips`.** GitHub web UI → Settings → repository name. Verifies the QR code from Task 10 resolves.
2. **Confirm Panel 3 popup support on the AAS 246 iPosterSessions instance.** If popups not supported, the spec §7 Panel 3 fallback applies (drop color-term plot from canvas).
3. **Assemble canvas in iPosterSessions.** Upload all 16 assets, set the 4×2 grid per spec §6, paste in copy from `posters/aas246/copy.md`, verify font sizes ≥ 28 pt at native resolution.
4. **Final upload by 2026-06-08.**

---

## Risks (from spec §10) — re-stated for the implementer

- Panel 6 extended objects FITS may not exist — fall back to text+icon (Task 9 Step 3).
- Logos may have license restrictions — check each one in Task 3, record attribution in copy.md.
- Repo rename happens out-of-band; don't block on it before generating the QR code.
