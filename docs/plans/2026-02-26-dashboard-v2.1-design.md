# Dashboard v2.1 Design

**Goal:** Enhance NPS dashboard with FITS image viewing, interactive lightcurves, source catalog browsing, pipeline quality metrics, and general polish.

**Depends on:** Dashboard v2 (tabbed navigation, log browser, analysis tab, data tab — already implemented).

**Tech stack:** FastAPI, Jinja2, HTMX 2.0.4, SSE-Starlette, Plotly.js (CDN), astropy 7.1.0, matplotlib 3.10.8. No new pip dependencies.

---

## 1. Fix Duration Bug

**Problem:** `collector.py` computes `datetime.now() - start` for ALL runs, including completed ones. A run that finished 3 days ago shows "3d 2h" instead of its actual 45-minute duration.

**Solution:** For completed runs (where `summary.txt` exists), use the file's mtime as the end timestamp. This requires zero changes to `run.py` — the mtime of `summary.txt` is the moment the pipeline wrote its final status.

**Implementation:**
- In `_parse_run()` in `collector.py`, after detecting that `summary_path.exists()`, use `summary_path.stat().st_mtime` as the end time
- Format: `end - start` for completed runs, `now - start` for running runs

---

## 2. Enhanced Interactive Lightcurve

**Current:** Basic Plotly scatter with markers only, no range control, plain tooltips.

**Improvements:**
- **Range slider** on x-axis (`rangeslider: {visible: true}`) for temporal zoom
- **Crosshair hover** (`hovermode: 'x unified'`) showing all bands at a given epoch
- **Lines + markers** mode connecting points chronologically per band
- **Mag/flux toggle** via Plotly `updatemenus` button — switches y-axis between magnitude (reversed) and flux (nJy)
- **Rich tooltips** showing: night, band, MJD, mag +/- err, flux, S/N
- **Band toggle** buttons in legend (already works with Plotly click-to-hide)

**Files:** `tabs/analysis.html` (Plotly config), `style.css` (plotly container sizing)

---

## 3. FITS Image Viewer

**Architecture:** New `image_renderer.py` module that uses subprocess to run a Butler query + astropy rendering script. Results cached as PNGs in a temp directory keyed by `{run_id}/{dataset_type}/{night}_{band}.png`.

**Dataset types to render:**
- `calexp` — calibrated science exposure
- `goodSeeingDiff_templateExp` or `template_detector` — warped template
- `goodSeeingDiff_differenceExp` or `difference_image` — subtraction result

**Rendering approach:**
- Use astropy's `ZScaleInterval` + `AsinhStretch` for display stretch
- matplotlib figure with dark background matching dashboard theme
- Render to PNG bytes, serve via API, cache on disk

**API endpoints:**
- `GET /api/fits-image/{run_id}?type={dataset_type}&night={night}&band={band}` — returns cached PNG or renders on demand
- `GET /api/fits-list/{run_id}` — returns available (night, band, dataset_type) combinations

**UI: Side-by-side comparison panel**
- Night selector dropdown
- Band selector (r/i/etc.)
- Three-panel layout: Science | Template | Difference
- Click to expand any panel
- Located in the Analysis tab or as a new "Images" sub-section

**Caching:** PNGs stored in `/tmp/nps-dashboard-cache/{run_id}/` with TTL managed by file age. Cache cleared on server restart.

---

## 4. Source Catalog Viewer

**Architecture:** Subprocess Butler query (like `butler_query.py`) returns catalog data as JSON. Rendered as sortable tables client-side.

**Catalogs to display:**
- `dia_source_unfiltered` — DIA detection catalog
  - Key columns: coord_ra, coord_dec, ip_diffim_forced_PsfFlux_instFlux, ip_diffim_forced_PsfFlux_instFluxErr, band, visit, SNR, flags
- `forced_phot_diffim_radec` — forced photometry catalog
  - Key columns: coord_ra, coord_dec, psfDiffFlux, psfDiffFluxErr, band, visit

**API endpoints:**
- `GET /api/catalog/{run_id}/{catalog_type}?night={night}&band={band}&limit=200` — returns paginated catalog rows as JSON

**UI:**
- Located in the Data tab (extends existing Butler counts section)
- Catalog type selector dropdown
- Night/band filters
- Sortable columns (click header to sort)
- Pagination controls (prev/next, 200 rows per page)
- Export to CSV button (downloads filtered data)

---

## 5. Pipeline Quality Metrics

**Architecture:** Subprocess Butler query retrieves metric values per night. Displayed as a color-coded per-night table.

**Metric groups:**

### Science Calibration Metrics (from `calibrateImage_metadata_metrics`)
| Metric | Good | Warning | Bad |
|--------|------|---------|-----|
| psf_good_star_count | >= 10 | 5-9 | < 5 |
| astrometry_matches_count | >= 20 | 10-19 | < 10 |
| photometry_matches_count | >= 20 | 10-19 | < 10 |
| bad_mask_fraction | < 0.05 | 0.05-0.15 | > 0.15 |
| cr_mask_fraction | < 0.03 | 0.03-0.10 | > 0.10 |

### DIA Quality Metrics (from `diffimMetadata_metrics`)
| Metric | Good | Warning | Bad |
|--------|------|---------|-----|
| spatialKernelSum | 0.8-1.2 | 0.5-0.8 or 1.2-1.5 | < 0.5 or > 1.5 |
| templateCoveragePercent | > 90% | 70-90% | < 70% |
| spatialConditionNum | < 100 | 100-1000 | > 1000 |

### Detection Metrics (from `detectAndMeasureDiaSource_metadata_metrics`)
| Metric | Display |
|--------|---------|
| nMergedDiaSources | Count |
| nPixelsDetectedPositive | Count |
| nPixelsDetectedNegative | Count |

**API endpoint:**
- `GET /api/metrics/{run_id}` — returns all metrics grouped by night

**UI:**
- New "Metrics" section in the Data tab or a dedicated sub-tab
- Per-night rows with color-coded cells (green/yellow/red)
- Expandable rows showing all metrics for a night
- Tooltip showing threshold definitions

---

## 6. General Polish

### HTMX View Transitions
- Add `transition:true` to tab `hx-swap` attributes
- CSS `view-transition-name` on `#tab-content` for fade animation
- `::view-transition-old` / `::view-transition-new` keyframes

### Loading Skeletons
- Replace "Loading..." with animated skeleton blocks (pulsing gray rectangles)
- Skeleton for: tab content, chart area, data tables

### Micro-animations
- Summary cards: fade-in on load with staggered delay
- Night grid cells: subtle hover scale effect
- Phase bar: smooth transition when phase changes

### CSS cleanup
- Consistent spacing variables
- Better mobile breakpoints for new components (image viewer, catalog tables)

---

## File Summary

### New Files
- `dashboard/image_renderer.py` — FITS to PNG rendering via Butler + astropy
- `dashboard/catalog_query.py` — Butler catalog queries for source tables and metrics

### Modified Files
- `dashboard/collector.py` — fix duration calculation
- `dashboard/app.py` — new API routes (fits-image, fits-list, catalog, metrics)
- `dashboard/templates/tabs/analysis.html` — enhanced Plotly config, image viewer panel
- `dashboard/templates/tabs/data.html` — source catalog viewer, metrics table
- `dashboard/templates/run_detail.html` — view transition attributes
- `dashboard/templates/base.html` — skeleton CSS
- `dashboard/static/style.css` — transitions, skeletons, image viewer, catalog table, metrics styles
