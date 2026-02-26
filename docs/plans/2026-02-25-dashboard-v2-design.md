# Dashboard v2 Design

## Goal

Enhance the NPS pipeline dashboard from a run overview + live log viewer into a comprehensive monitoring and analysis tool with per-exposure drill-down, full log browsing, interactive lightcurve charts, and Butler dataset visibility.

## Current State

The dashboard (FastAPI + Jinja2 + HTMX + SSE) provides:
- Run list page with status/duration/phase counts
- Run detail page with phase progress bar, night status grid, live pipeline.log tailing, and optional Slurm job table
- No access to per-phase logs, no analysis/plot viewing, no Butler data insight

## Design

### Navigation: 4-Level Drill-Down

```
Run List → Run Detail (tabbed) → Night Detail → Exposure Detail
```

Run detail gains four tabs, switched via HTMX without page reloads:
- **Overview** — enhanced night grid with summary cards
- **Logs** — browsable log file tree with viewer
- **Analysis** — lightcurve plots (static PNG + interactive Plotly.js) and output files
- **Data** — Butler dataset counts per night/band (on-demand)

### Routes

| Route | Purpose |
|-------|---------|
| `GET /` | Run list (existing) |
| `GET /run/{id}` | Run detail with tabs (default: Overview) |
| `GET /run/{id}/tab/{name}` | HTMX partial for tab content |
| `GET /run/{id}/night/{night}` | Night drill-down: per-exposure breakdown |
| `GET /run/{id}/night/{night}/exposure/{exp}` | Single exposure log viewer |
| `GET /api/log/{id}/{path:path}` | Serve any log file from run directory |
| `GET /api/log-tree/{id}` | JSON log directory tree |
| `GET /api/lightcurve-data/{id}` | Lightcurve CSV as JSON for Plotly |
| `GET /api/butler-counts/{id}` | Butler dataset counts (on-demand) |
| `GET /api/events/{id}` | SSE stream (existing, enhanced) |

### Tab 1: Overview (Enhanced)

Enhancements to existing run detail content:
- **Summary cards** at top: calibs/science/DIA/fphot progress bars with counts
- **Duration per phase** in the progress bar
- **Clickable night grid cells** → navigate to night detail page
- **Hover tooltips** on cells with quick stats (quanta counts, error summary)

### Tab 2: Log Browser

Split-pane layout:
- **Left sidebar**: file tree of `logs/{run_id}/` showing all subdirectories and log files
- **Right panel**: log viewer with syntax highlighting (ERROR=red, WARNING=yellow, DEBUG=gray)
- For active runs, selected log auto-tails via SSE
- Client-side text search within the displayed log
- Per-exposure file listing when viewing split log directories

Implementation:
- `GET /api/log-tree/{id}` returns the directory tree as JSON
- HTMX loads log content into the viewer panel on tree node click
- Log viewer reuses the existing colorized log rendering

### Tab 3: Analysis

**Lightcurve section:**
- Static PNG preview (existing pipeline output)
- Interactive Plotly.js chart from CSV data:
  - Scatter with error bars, one trace per band (color-coded)
  - Hover: MJD, magnitude, error, band, night
  - Band toggle via legend clicks
  - Zoom/pan
  - Axis labels from lightcurve config (apparent mag, days since explosion, etc.)
- CSV data table with sortable columns

**Output files section:**
- Gallery of all output files (PNGs, CSVs) from `lightcurves/` directory
- Inline image preview for PNGs, download links for CSVs

Implementation:
- `GET /api/lightcurve-data/{id}` reads the CSV, returns JSON with columns and metadata
- Plotly.js loaded from CDN, chart rendered client-side
- No new Python dependencies

### Tab 4: Data (Butler)

On-demand Butler dataset counts per night per band:
- Dataset types: `calexp`, `initial_pvi`, `goodSeeingDiff_differenceExp`, `forced_diff_radec`
- Table format: rows=nights, columns=dataset types, cells=counts
- "Load data" button triggers the query (avoids slow startup)
- Requires LSST stack to be available on the dashboard host

Implementation:
- `butler_query.py` module uses `run_with_stack()` to execute Butler queries
- Queries `butler query-datasets` for each dataset type, grouped by night/band
- Results cached in memory for the session (Butler queries are slow)

### Night Detail Page

Accessed by clicking a night in the overview grid:
- **Header**: night date, overall status
- **Per-phase status**: calibs, science, DIA(per-band), fphot(per-band)
- **Exposure list**: table of all exposures for the night with individual pass/fail status
- **Per-exposure logs**: click an exposure to view its split log
- **Error summary**: extracted error messages from failed exposures

### New Templates

| Template | Content |
|----------|---------|
| `run_detail.html` | Enhanced with tab navigation |
| `tabs/overview.html` | Summary cards + enhanced night grid |
| `tabs/logs.html` | Split-pane log browser |
| `tabs/analysis.html` | Lightcurve plots + output gallery |
| `tabs/data.html` | Butler dataset count tables |
| `night_detail.html` | Per-exposure breakdown |
| `partials/summary_cards.html` | Progress bar cards |
| `partials/log_viewer.html` | Reusable log viewer component |
| `partials/log_tree.html` | File tree sidebar |

### New Backend Modules

| Module | Purpose |
|--------|---------|
| `collector.py` (enhanced) | Log tree discovery, per-exposure status |
| `butler_query.py` (new) | Butler dataset count queries |
| `analysis.py` (new) | Lightcurve CSV parsing, output file discovery |

### Technology

- Keep existing: FastAPI, Jinja2, HTMX, SSE-Starlette, uvicorn
- Add client-side only: Plotly.js (CDN, no Python dependency)
- No new Python dependencies
- No JavaScript build step

### CSS Additions

- Tab navigation styling
- Split-pane layout for log browser
- File tree styling (collapsible, icons for dirs/files)
- Summary card styling with inline progress bars
- Plotly chart container styling
- Image gallery grid
- Table sorting indicators
