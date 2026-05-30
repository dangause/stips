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
| Panel 5 | logos/ctio.png + logos/docker.png + styled-text "Slurm" | `assets/logos/` |
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
