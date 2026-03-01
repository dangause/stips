# Dashboard v2.1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enhance the NPS dashboard with a duration bug fix, interactive lightcurves, FITS image viewing, source catalog browsing, pipeline quality metrics, and UI polish.

**Architecture:** Server-side rendering with FastAPI + Jinja2 + HTMX. New Butler queries run as subprocess calls (same pattern as `butler_query.py`). FITS images rendered to PNG via astropy/matplotlib and cached on disk. All new features integrate into existing tab structure (Analysis and Data tabs).

**Tech Stack:** FastAPI, Jinja2, HTMX 2.0.4, SSE-Starlette, Plotly.js 2.35.0 (CDN), astropy 7.1.0, matplotlib 3.10.8. No new pip dependencies.

---

## Task 1: Fix Duration Bug

The duration calculation in `collector.py:156-170` uses `datetime.now()` for ALL runs. Completed runs should use `summary.txt` mtime as end time.

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/dashboard/collector.py:146-170`

**Step 1: Fix the duration calculation**

In `collector.py`, replace the duration block (lines 156-170) so that completed runs use `summary_path.stat().st_mtime` as the end time:

```python
    # Calculate duration
    if info.started:
        try:
            start = datetime.fromisoformat(info.started)
            # For completed runs, use summary.txt mtime as end time
            if summary_path.exists():
                end_ts = summary_path.stat().st_mtime
                end = datetime.fromtimestamp(end_ts, tz=timezone.utc)
            else:
                end = datetime.now(timezone.utc)
            elapsed = end - start
            hours, remainder = divmod(int(elapsed.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)
            if hours >= 24:
                days = hours // 24
                hours = hours % 24
                info.duration = f"{days}d {hours}h {minutes}m"
            elif hours > 0:
                info.duration = f"{hours}h {minutes}m"
            elif minutes > 0:
                info.duration = f"{minutes}m {seconds}s"
            else:
                info.duration = f"{seconds}s"
        except (ValueError, TypeError):
            pass
```

Note: `summary_path` is already defined on line 146 (`summary_path = run_dir / "summary.txt"`), so this variable is in scope. Also adds day-level formatting for runs > 24h.

**Step 2: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('packages/data_tools/src/obs_nickel_data_tools/dashboard/collector.py').read()); print('OK')"`
Expected: OK

**Step 3: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/dashboard/collector.py
git commit -m "fix: use summary.txt mtime for completed run duration calculation"
```

---

## Task 2: Enhanced Interactive Lightcurve

Upgrade the Plotly chart in the Analysis tab with range slider, crosshair hover, lines+markers, mag/flux toggle, and rich tooltips.

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/dashboard/templates/tabs/analysis.html`

**Step 1: Replace the Plotly rendering code**

Replace the entire `renderPlotlyChart` function (and add a helper) in `analysis.html` with the enhanced version. The new code goes between the `renderPlotlyChart(data);` call and the `renderDataTable` function:

```javascript
function renderPlotlyChart(data) {
  const traces = [];
  const cols = data.columns;
  const xCol = cols.find(c => c.match(/mjd|MJD|days/i)) || cols[0];
  const magCol = cols.find(c => c.match(/^mag$|magnitude/i));
  const fluxCol = cols.find(c => c.match(/flux_nJy|flux/i));
  const errCol = cols.find(c => c.match(/mag_err|err|error|sigma/i));
  const fluxErrCol = cols.find(c => c.match(/flux.*err/i)) || errCol;
  const bandCol = cols.find(c => c.match(/band|filter/i));
  const snrCol = cols.find(c => c.match(/snr|s_n|signal/i));
  const nightCol = cols.find(c => c.match(/night|day_obs/i));
  const yCol = magCol || cols.find(c => c.match(/mag|flux/i)) || cols[1];
  const isMag = yCol && yCol.toLowerCase().includes('mag');

  // Build traces per band — magnitude view
  const magTraces = [];
  const fluxTraces = [];

  for (const band of data.bands) {
    const points = data.data
      .filter(r => r[bandCol] === band)
      .sort((a, b) => a[xCol] - b[xCol]);

    // Build tooltip text
    const hoverTexts = points.map(r => {
      let text = '';
      if (nightCol) text += `Night: ${r[nightCol]}<br>`;
      text += `Band: ${band}<br>`;
      text += `${xCol}: ${typeof r[xCol] === 'number' ? r[xCol].toFixed(4) : r[xCol]}<br>`;
      if (magCol && r[magCol] != null) {
        text += `Mag: ${r[magCol].toFixed(3)}`;
        if (errCol && r[errCol] != null) text += ` &plusmn; ${r[errCol].toFixed(3)}`;
        text += '<br>';
      }
      if (fluxCol && r[fluxCol] != null) {
        text += `Flux: ${r[fluxCol].toFixed(2)} nJy`;
        if (fluxErrCol && r[fluxErrCol] != null) text += ` &plusmn; ${r[fluxErrCol].toFixed(2)}`;
        text += '<br>';
      }
      if (snrCol && r[snrCol] != null) text += `S/N: ${r[snrCol].toFixed(1)}`;
      return text;
    });

    const color = BAND_COLORS[band] || '#8b949e';

    // Magnitude trace
    if (magCol) {
      const magTrace = {
        x: points.map(r => r[xCol]),
        y: points.map(r => r[magCol]),
        mode: 'lines+markers',
        type: 'scatter',
        name: band,
        marker: { color: color, size: 7 },
        line: { color: color, width: 1.5 },
        hovertext: hoverTexts,
        hoverinfo: 'text',
      };
      if (errCol) {
        magTrace.error_y = {
          type: 'data',
          array: points.map(r => r[errCol]),
          visible: true,
          color: color,
          thickness: 1,
        };
      }
      magTraces.push(magTrace);
    }

    // Flux trace (hidden initially if mag is primary)
    if (fluxCol) {
      const fluxTrace = {
        x: points.map(r => r[xCol]),
        y: points.map(r => r[fluxCol]),
        mode: 'lines+markers',
        type: 'scatter',
        name: band + ' (flux)',
        visible: magCol ? false : true,
        marker: { color: color, size: 7 },
        line: { color: color, width: 1.5 },
        hovertext: hoverTexts,
        hoverinfo: 'text',
        showlegend: !magCol,
      };
      if (fluxErrCol) {
        fluxTrace.error_y = {
          type: 'data',
          array: points.map(r => r[fluxErrCol]),
          visible: true,
          color: color,
          thickness: 1,
        };
      }
      fluxTraces.push(fluxTrace);
    }
  }

  // Use mag traces if available, else flux
  const allTraces = magCol ? [...magTraces, ...fluxTraces] : fluxTraces.length ? fluxTraces : magTraces;

  // If no mag or flux columns detected, fall back to generic y column
  if (allTraces.length === 0) {
    for (const band of data.bands) {
      const points = data.data
        .filter(r => r[bandCol] === band)
        .sort((a, b) => a[xCol] - b[xCol]);
      const color = BAND_COLORS[band] || '#8b949e';
      allTraces.push({
        x: points.map(r => r[xCol]),
        y: points.map(r => r[yCol]),
        mode: 'lines+markers',
        type: 'scatter',
        name: band,
        marker: { color: color, size: 7 },
        line: { color: color, width: 1.5 },
      });
    }
  }

  const layout = {
    paper_bgcolor: '#0d1117',
    plot_bgcolor: '#161b22',
    font: { color: '#e6edf3', family: 'system-ui, sans-serif' },
    xaxis: {
      title: xCol,
      gridcolor: '#30363d',
      zerolinecolor: '#30363d',
      rangeslider: { visible: true, bgcolor: '#161b22', bordercolor: '#30363d', thickness: 0.08 },
    },
    yaxis: {
      title: magCol ? 'Magnitude' : (fluxCol ? 'Flux (nJy)' : yCol),
      autorange: (magCol && !fluxCol) ? 'reversed' : true,
      gridcolor: '#30363d',
      zerolinecolor: '#30363d',
    },
    legend: { orientation: 'h', y: -0.25 },
    margin: { t: 40, r: 20, b: 80, l: 60 },
    hovermode: 'x unified',
  };

  // Add mag/flux toggle button if both columns exist
  if (magCol && fluxCol) {
    const nBands = data.bands.length;
    layout.updatemenus = [{
      type: 'buttons',
      direction: 'left',
      x: 0,
      y: 1.12,
      xanchor: 'left',
      bgcolor: '#21262d',
      font: { color: '#e6edf3', size: 11 },
      buttons: [
        {
          label: 'Magnitude',
          method: 'update',
          args: [
            { visible: [...Array(nBands).fill(true), ...Array(nBands).fill(false)] },
            { 'yaxis.title': 'Magnitude', 'yaxis.autorange': 'reversed' },
          ],
        },
        {
          label: 'Flux (nJy)',
          method: 'update',
          args: [
            { visible: [...Array(nBands).fill(false), ...Array(nBands).fill(true)] },
            { 'yaxis.title': 'Flux (nJy)', 'yaxis.autorange': true },
          ],
        },
      ],
    }];
  }

  Plotly.newPlot('plotly-chart', allTraces, layout, {
    responsive: true,
    displayModeBar: true,
    modeBarButtonsToRemove: ['lasso2d', 'select2d'],
  });
}
```

**Step 2: Verify the template renders without syntax errors**

Run: `python3 -c "from jinja2 import Environment; env = Environment(); env.parse(open('packages/data_tools/src/obs_nickel_data_tools/dashboard/templates/tabs/analysis.html').read()); print('OK')"`
Expected: OK

**Step 3: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/dashboard/templates/tabs/analysis.html
git commit -m "feat: enhance lightcurve with range slider, crosshair, mag/flux toggle"
```

---

## Task 3: FITS Image Viewer

New module to render FITS images as PNGs via astropy/matplotlib, with API endpoints and a side-by-side comparison UI in the Analysis tab.

**Files:**
- Create: `packages/data_tools/src/obs_nickel_data_tools/dashboard/image_renderer.py`
- Modify: `packages/data_tools/src/obs_nickel_data_tools/dashboard/app.py` (add 2 routes)
- Modify: `packages/data_tools/src/obs_nickel_data_tools/dashboard/templates/tabs/analysis.html` (add image viewer section)
- Modify: `packages/data_tools/src/obs_nickel_data_tools/dashboard/static/style.css` (image viewer styles)

### Step 1: Create `image_renderer.py`

Create `packages/data_tools/src/obs_nickel_data_tools/dashboard/image_renderer.py`:

```python
"""FITS image rendering for the dashboard.

Renders FITS images to PNG via Butler + astropy/matplotlib subprocess.
Results cached as PNGs in a temp directory.
"""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Cache directory for rendered PNGs
_CACHE_DIR = Path(tempfile.gettempdir()) / "nps-dashboard-cache"


def get_cache_dir() -> Path:
    """Return the cache directory, creating it if needed."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR


def get_cached_png(run_id: str, dataset_type: str, night: str, band: str) -> Path | None:
    """Return path to cached PNG if it exists."""
    png_path = _png_path(run_id, dataset_type, night, band)
    return png_path if png_path.exists() else None


def render_fits_image(
    repo_path: str,
    run_id: str,
    dataset_type: str,
    night: str,
    band: str,
) -> Path | None:
    """Render a FITS image from Butler to a cached PNG file.

    Returns path to the PNG file, or None if rendering failed.
    """
    png_path = _png_path(run_id, dataset_type, night, band)
    if png_path.exists():
        return png_path

    png_path.parent.mkdir(parents=True, exist_ok=True)

    script = _build_render_script(repo_path, dataset_type, night, band, str(png_path))

    try:
        result = subprocess.run(
            ["python3", "-c", script],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            logger.warning(
                "FITS render failed for %s/%s/%s: %s",
                night, band, dataset_type, result.stderr[:500],
            )
            return None

        if png_path.exists():
            return png_path
        return None

    except subprocess.TimeoutExpired:
        logger.warning("FITS render timed out for %s/%s/%s", night, band, dataset_type)
        return None
    except Exception as e:
        logger.warning("FITS render error: %s", e)
        return None


def list_available_images(repo_path: str) -> list[dict]:
    """Query Butler for available (night, band, dataset_type) combinations.

    Returns list of dicts with keys: night, band, dataset_type.
    """
    script = _build_list_script(repo_path)

    try:
        result = subprocess.run(
            ["python3", "-c", script],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            logger.warning("FITS list query failed: %s", result.stderr[:500])
            return []

        return json.loads(result.stdout)

    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as e:
        logger.warning("FITS list error: %s", e)
        return []


def _png_path(run_id: str, dataset_type: str, night: str, band: str) -> Path:
    """Construct the cache path for a rendered PNG."""
    safe_dt = dataset_type.replace("/", "_")
    return get_cache_dir() / run_id / f"{night}_{band}_{safe_dt}.png"


def _build_render_script(
    repo_path: str, dataset_type: str, night: str, band: str, output_path: str
) -> str:
    """Build Python script that loads FITS via Butler and renders to PNG."""
    return f'''
import sys
try:
    from lsst.daf.butler import Butler
    import numpy as np
    from astropy.visualization import ZScaleInterval, AsinhStretch, ImageNormalize
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError as e:
    print(f"Missing dependency: {{e}}", file=sys.stderr)
    sys.exit(1)

repo = "{repo_path}"
dataset_type = "{dataset_type}"
night = "{night}"
band = "{band}"
output = "{output_path}"

try:
    butler = Butler(repo)
    # Find matching datasets
    refs = list(butler.registry.queryDatasets(
        dataset_type,
        where="instrument=\\'Nickel\\' AND day_obs={night_int} AND band=\\'{band_val}\\'".format(
            night_int=int(night), band_val=band
        ),
    ))

    if not refs:
        # Try without band constraint for template types
        refs = list(butler.registry.queryDatasets(
            dataset_type,
            where="instrument=\\'Nickel\\' AND day_obs={night_int}".format(night_int=int(night)),
        ))

    if not refs:
        print(f"No {{dataset_type}} found for {{night}}/{{band}}", file=sys.stderr)
        sys.exit(1)

    # Use first matching ref
    exposure = butler.get(refs[0])

    # Get the image array
    if hasattr(exposure, "image"):
        img_data = exposure.image.array
    elif hasattr(exposure, "getImage"):
        img_data = exposure.getImage().array
    else:
        img_data = np.asarray(exposure)

    # Apply ZScale + Asinh stretch
    interval = ZScaleInterval()
    stretch = AsinhStretch(a=0.1)
    norm = ImageNormalize(img_data, interval=interval, stretch=stretch)

    fig, ax = plt.subplots(1, 1, figsize=(8, 8), facecolor="#0d1117")
    ax.set_facecolor("#0d1117")
    ax.imshow(img_data, norm=norm, cmap="gray", origin="lower")
    ax.set_title(f"{{dataset_type}} | {{night}} | {{band}}", color="#e6edf3", fontsize=10)
    ax.tick_params(colors="#8b949e", labelsize=7)
    for spine in ax.spines.values():
        spine.set_color("#30363d")
    fig.tight_layout(pad=1.0)
    fig.savefig(output, dpi=100, bbox_inches="tight", facecolor="#0d1117")
    plt.close(fig)
    print("OK")

except Exception as e:
    print(f"Error: {{e}}", file=sys.stderr)
    sys.exit(1)
'''


def _build_list_script(repo_path: str) -> str:
    """Build Python script that lists available image datasets."""
    return f'''
import json, sys
try:
    from lsst.daf.butler import Butler
except ImportError:
    print("[]")
    sys.exit(0)

repo = "{repo_path}"
dataset_types = ["calexp", "goodSeeingDiff_differenceExp", "goodSeeingDiff_templateExp"]

try:
    butler = Butler(repo)
    results = []
    seen = set()

    for dt in dataset_types:
        try:
            refs = list(butler.registry.queryDatasets(dt))
            for ref in refs:
                did = ref.dataId
                night = str(did.get("day_obs", ""))[:8]
                band = did.get("band", did.get("physical_filter", "?"))
                key = f"{{night}}_{{band}}_{{dt}}"
                if key not in seen:
                    seen.add(key)
                    results.append({{"night": night, "band": band, "dataset_type": dt}})
        except Exception:
            pass

    print(json.dumps(results))
except Exception as e:
    print("[]")
    sys.exit(0)
'''
```

### Step 2: Add API routes to `app.py`

Add two new routes and their imports to `app.py`. After the existing `api_butler_counts` route (line 209), add:

```python
    @app.get("/api/fits-image/{run_id}")
    async def api_fits_image(run_id: str, type: str, night: str, band: str):
        """Render and serve a FITS image as PNG."""
        from fastapi.responses import FileResponse

        from .image_renderer import get_cached_png, render_fits_image

        # Check cache first
        cached = get_cached_png(run_id, type, night, band)
        if cached:
            return FileResponse(cached, media_type="image/png")

        # Find repo path
        run_info_path = logs_dir / run_id / "run_info.txt"
        if not run_info_path.exists():
            return PlainTextResponse("Run info not found", status_code=404)

        repo_path = None
        for line in run_info_path.read_text().splitlines():
            if line.startswith("Repository:"):
                repo_path = line.split(":", 1)[1].strip()
                break

        if not repo_path:
            return PlainTextResponse("Repository not found", status_code=404)

        png_path = render_fits_image(repo_path, run_id, type, night, band)
        if png_path is None:
            return PlainTextResponse("Failed to render image", status_code=500)

        return FileResponse(png_path, media_type="image/png")

    @app.get("/api/fits-list/{run_id}", response_class=JSONResponse)
    async def api_fits_list(run_id: str):
        """List available FITS images for a run."""
        from .image_renderer import list_available_images

        run_info_path = logs_dir / run_id / "run_info.txt"
        if not run_info_path.exists():
            return JSONResponse({"images": [], "error": "Run info not found"})

        repo_path = None
        for line in run_info_path.read_text().splitlines():
            if line.startswith("Repository:"):
                repo_path = line.split(":", 1)[1].strip()
                break

        if not repo_path:
            return JSONResponse({"images": [], "error": "Repository not found"})

        images = list_available_images(repo_path)
        return JSONResponse({"images": images, "error": None})
```

### Step 3: Add image viewer UI to analysis.html

Insert the FITS image viewer section before the `{% else %}` block (before line 31 of analysis.html), after the CSV Data Table section:

```html
  <!-- FITS Image Viewer -->
  <div class="detail-section">
    <h3>FITS Image Viewer</h3>
    <div class="fits-viewer">
      <div class="fits-controls">
        <button class="action-btn" id="load-fits-btn" onclick="loadFitsList()">Load Available Images</button>
        <span id="fits-spinner" class="spinner-inline" style="display:none"></span>
        <select id="fits-night" class="fits-select" onchange="updateFitsViewer()" disabled>
          <option value="">Select Night</option>
        </select>
        <select id="fits-band" class="fits-select" onchange="updateFitsViewer()" disabled>
          <option value="">Select Band</option>
        </select>
      </div>
      <div id="fits-panels" class="fits-panels" style="display:none">
        <div class="fits-panel">
          <h4>Science (calexp)</h4>
          <div class="fits-img-container" id="fits-calexp">
            <p class="text-muted">Select night & band</p>
          </div>
        </div>
        <div class="fits-panel">
          <h4>Template</h4>
          <div class="fits-img-container" id="fits-template">
            <p class="text-muted">Select night & band</p>
          </div>
        </div>
        <div class="fits-panel">
          <h4>Difference</h4>
          <div class="fits-img-container" id="fits-difference">
            <p class="text-muted">Select night & band</p>
          </div>
        </div>
      </div>
    </div>
  </div>
```

And add the FITS viewer JavaScript at the end of the existing `<script>` block (before `</script>`):

```javascript
// === FITS Image Viewer ===
let fitsData = [];

function loadFitsList() {
  const btn = document.getElementById('load-fits-btn');
  const spinner = document.getElementById('fits-spinner');
  btn.disabled = true;
  spinner.style.display = 'inline-block';

  fetch('/api/fits-list/{{ run.run_id }}')
    .then(r => r.json())
    .then(data => {
      fitsData = data.images || [];
      spinner.style.display = 'none';
      if (fitsData.length === 0) {
        btn.textContent = 'No FITS images available';
        return;
      }
      btn.style.display = 'none';

      // Populate night dropdown
      const nights = [...new Set(fitsData.map(d => d.night))].sort();
      const nightSel = document.getElementById('fits-night');
      nightSel.innerHTML = '<option value="">Select Night</option>';
      nights.forEach(n => {
        nightSel.innerHTML += `<option value="${n}">${n}</option>`;
      });
      nightSel.disabled = false;

      document.getElementById('fits-panels').style.display = 'grid';
    })
    .catch(err => {
      spinner.style.display = 'none';
      btn.textContent = 'Failed to load';
    });
}

function updateFitsViewer() {
  const night = document.getElementById('fits-night').value;
  const band = document.getElementById('fits-band').value;

  // Update band selector when night changes
  if (night && !band) {
    const bands = [...new Set(fitsData.filter(d => d.night === night).map(d => d.band))].sort();
    const bandSel = document.getElementById('fits-band');
    bandSel.innerHTML = '<option value="">Select Band</option>';
    bands.forEach(b => {
      bandSel.innerHTML += `<option value="${b}">${b}</option>`;
    });
    bandSel.disabled = false;
    return;
  }

  if (!night || !band) return;

  // Load images for each panel
  const panels = {
    'fits-calexp': 'calexp',
    'fits-template': 'goodSeeingDiff_templateExp',
    'fits-difference': 'goodSeeingDiff_differenceExp',
  };

  for (const [panelId, dtype] of Object.entries(panels)) {
    const container = document.getElementById(panelId);
    const available = fitsData.some(d => d.night === night && d.band === band && d.dataset_type === dtype);
    if (available) {
      container.innerHTML = '<p class="text-muted">Rendering...</p>';
      const img = new Image();
      img.onload = () => { container.innerHTML = ''; container.appendChild(img); };
      img.onerror = () => { container.innerHTML = '<p class="text-muted">Render failed</p>'; };
      img.src = `/api/fits-image/{{ run.run_id }}?type=${encodeURIComponent(dtype)}&night=${night}&band=${band}`;
      img.className = 'fits-image';
      img.onclick = function() { this.classList.toggle('expanded'); };
    } else {
      container.innerHTML = '<p class="text-muted">Not available</p>';
    }
  }
}
```

### Step 4: Add FITS viewer CSS to `style.css`

Append to `packages/data_tools/src/obs_nickel_data_tools/dashboard/static/style.css`, before the responsive section:

```css
/* === FITS Image Viewer === */
.fits-viewer {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.fits-controls {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.fits-select {
  background: var(--bg-tertiary);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 0.4rem 0.75rem;
  border-radius: 4px;
  font-size: 0.85rem;
}

.fits-select:disabled {
  opacity: 0.5;
}

.fits-panels {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1rem;
}

.fits-panel {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.75rem;
}

.fits-panel h4 {
  font-size: 0.8rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 0.5rem;
}

.fits-img-container {
  min-height: 200px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.fits-image {
  max-width: 100%;
  border-radius: 4px;
  cursor: pointer;
  transition: transform 0.2s;
}

.fits-image.expanded {
  transform: scale(2);
  position: relative;
  z-index: 20;
}
```

### Step 5: Verify all files parse**

Run:
```bash
python3 -c "import ast; ast.parse(open('packages/data_tools/src/obs_nickel_data_tools/dashboard/image_renderer.py').read()); print('image_renderer OK')"
python3 -c "import ast; ast.parse(open('packages/data_tools/src/obs_nickel_data_tools/dashboard/app.py').read()); print('app OK')"
```
Expected: Both print OK

### Step 6: Commit

```bash
git add packages/data_tools/src/obs_nickel_data_tools/dashboard/image_renderer.py \
      packages/data_tools/src/obs_nickel_data_tools/dashboard/app.py \
      packages/data_tools/src/obs_nickel_data_tools/dashboard/templates/tabs/analysis.html \
      packages/data_tools/src/obs_nickel_data_tools/dashboard/static/style.css
git commit -m "feat: add FITS image viewer with side-by-side science/template/difference"
```

---

## Task 4: Source Catalog Viewer

New module for Butler catalog queries. Adds sortable source tables to the Data tab.

**Files:**
- Create: `packages/data_tools/src/obs_nickel_data_tools/dashboard/catalog_query.py`
- Modify: `packages/data_tools/src/obs_nickel_data_tools/dashboard/app.py` (add catalog route)
- Modify: `packages/data_tools/src/obs_nickel_data_tools/dashboard/templates/tabs/data.html` (add catalog UI)
- Modify: `packages/data_tools/src/obs_nickel_data_tools/dashboard/static/style.css` (catalog styles)

### Step 1: Create `catalog_query.py`

Create `packages/data_tools/src/obs_nickel_data_tools/dashboard/catalog_query.py`:

```python
"""Butler catalog and metric queries for the dashboard.

Queries source catalogs and pipeline metrics via subprocess.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Source catalog types
CATALOG_TYPES = {
    "dia_source_unfiltered": {
        "label": "DIA Sources",
        "columns": [
            "coord_ra", "coord_dec", "band", "visit",
            "ip_diffim_forced_PsfFlux_instFlux",
            "ip_diffim_forced_PsfFlux_instFluxErr",
        ],
    },
    "forced_phot_diffim_radec": {
        "label": "Forced Photometry",
        "columns": [
            "coord_ra", "coord_dec", "band", "visit",
            "psfDiffFlux", "psfDiffFluxErr",
        ],
    },
}

# Metric dataset types and their key fields
METRIC_TYPES = {
    "calibrateImage_metadata_metrics": {
        "label": "Science Calibration",
        "metrics": {
            "psf_good_star_count": {"good": (10, None), "warn": (5, 10), "bad": (None, 5)},
            "astrometry_matches_count": {"good": (20, None), "warn": (10, 20), "bad": (None, 10)},
            "photometry_matches_count": {"good": (20, None), "warn": (10, 20), "bad": (None, 10)},
            "bad_mask_fraction": {"good": (None, 0.05), "warn": (0.05, 0.15), "bad": (0.15, None)},
            "cr_mask_fraction": {"good": (None, 0.03), "warn": (0.03, 0.10), "bad": (0.10, None)},
        },
    },
    "diffimMetadata_metrics": {
        "label": "DIA Quality",
        "metrics": {
            "spatialKernelSum": {"good": (0.8, 1.2), "warn_low": (0.5, 0.8), "warn_high": (1.2, 1.5)},
            "templateCoveragePercent": {"good": (90, None), "warn": (70, 90), "bad": (None, 70)},
            "spatialConditionNum": {"good": (None, 100), "warn": (100, 1000), "bad": (1000, None)},
        },
    },
    "detectAndMeasureDiaSource_metadata_metrics": {
        "label": "Detection Counts",
        "metrics": {
            "nMergedDiaSources": {},
            "nPixelsDetectedPositive": {},
            "nPixelsDetectedNegative": {},
        },
    },
}


def query_catalog(
    repo_path: str,
    catalog_type: str,
    night: str | None = None,
    band: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> dict:
    """Query a Butler catalog and return rows as JSON.

    Returns:
        {
            "available": bool,
            "error": str | None,
            "columns": [...],
            "rows": [{...}, ...],
            "total": int,
        }
    """
    if catalog_type not in CATALOG_TYPES:
        return {"available": False, "error": f"Unknown catalog: {catalog_type}", "columns": [], "rows": [], "total": 0}

    script = _build_catalog_script(repo_path, catalog_type, night, band, limit, offset)

    try:
        result = subprocess.run(
            ["python3", "-c", script],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            return {"available": False, "error": result.stderr[:300], "columns": [], "rows": [], "total": 0}

        data = json.loads(result.stdout)
        data["available"] = True
        data["error"] = None
        return data

    except subprocess.TimeoutExpired:
        return {"available": False, "error": "Query timed out", "columns": [], "rows": [], "total": 0}
    except (json.JSONDecodeError, Exception) as e:
        return {"available": False, "error": str(e), "columns": [], "rows": [], "total": 0}


def query_metrics(repo_path: str) -> dict:
    """Query pipeline quality metrics grouped by night.

    Returns:
        {
            "available": bool,
            "error": str | None,
            "metric_groups": { group_label: { night: { metric: value } } },
            "thresholds": { ... },
        }
    """
    script = _build_metrics_script(repo_path)

    try:
        result = subprocess.run(
            ["python3", "-c", script],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            return {"available": False, "error": result.stderr[:300], "metric_groups": {}, "thresholds": {}}

        data = json.loads(result.stdout)
        data["available"] = True
        data["error"] = None
        # Attach threshold definitions for client-side color coding
        data["thresholds"] = {
            dt: info["metrics"]
            for dt, info in METRIC_TYPES.items()
        }
        return data

    except subprocess.TimeoutExpired:
        return {"available": False, "error": "Query timed out", "metric_groups": {}, "thresholds": {}}
    except (json.JSONDecodeError, Exception) as e:
        return {"available": False, "error": str(e), "metric_groups": {}, "thresholds": {}}


def _build_catalog_script(
    repo_path: str, catalog_type: str, night: str | None, band: str | None, limit: int, offset: int
) -> str:
    """Build Python script to query a source catalog."""
    cols = json.dumps(CATALOG_TYPES[catalog_type]["columns"])
    where_parts = ["instrument='Nickel'"]
    if night:
        where_parts.append(f"day_obs={int(night)}")
    if band:
        where_parts.append(f"band='{band}'")
    where_clause = " AND ".join(where_parts)

    return f'''
import json, sys
try:
    from lsst.daf.butler import Butler
except ImportError:
    print(json.dumps({{"columns": [], "rows": [], "total": 0}}))
    sys.exit(0)

repo = "{repo_path}"
catalog_type = "{catalog_type}"
desired_cols = {cols}
limit = {limit}
offset = {offset}

try:
    butler = Butler(repo)
    refs = list(butler.registry.queryDatasets(catalog_type, where="{where_clause}"))
    total = len(refs)

    rows = []
    for ref in refs[offset:offset + limit]:
        try:
            cat = butler.get(ref)
            did = ref.dataId
            night = str(did.get("day_obs", ""))
            band = did.get("band", "?")

            # Extract columns from catalog
            if hasattr(cat, "columns"):
                available_cols = list(cat.columns)
            else:
                available_cols = []

            for i, record in enumerate(cat):
                if i >= 50:  # Limit rows per dataset ref
                    break
                row = {{"night": night, "band": band}}
                for col in desired_cols:
                    if col in available_cols:
                        val = record[col]
                        try:
                            row[col] = float(val)
                        except (TypeError, ValueError):
                            row[col] = str(val)
                rows.append(row)

        except Exception as e:
            pass

    columns = ["night", "band"] + desired_cols
    print(json.dumps({{"columns": columns, "rows": rows[:limit], "total": total}}))

except Exception as e:
    print(json.dumps({{"columns": [], "rows": [], "total": 0, "error": str(e)}}))
    sys.exit(0)
'''


def _build_metrics_script(repo_path: str) -> str:
    """Build Python script to query pipeline metrics."""
    metric_types = json.dumps(list(METRIC_TYPES.keys()))
    metric_fields = json.dumps({
        dt: list(info["metrics"].keys())
        for dt, info in METRIC_TYPES.items()
    })

    return f'''
import json, sys
try:
    from lsst.daf.butler import Butler
except ImportError:
    print(json.dumps({{"metric_groups": {{}}}}))
    sys.exit(0)

repo = "{repo_path}"
metric_types = {metric_types}
metric_fields = {metric_fields}

try:
    butler = Butler(repo)
    groups = {{}}

    for dt in metric_types:
        group_data = {{}}
        try:
            refs = list(butler.registry.queryDatasets(dt))
            for ref in refs:
                did = ref.dataId
                night = str(did.get("day_obs", ""))[:8]
                band = did.get("band", "?")
                key = f"{{night}}/{{band}}"

                try:
                    metrics = butler.get(ref)
                    row = {{}}
                    desired = metric_fields.get(dt, [])
                    for field in desired:
                        if hasattr(metrics, field):
                            val = getattr(metrics, field)
                            try:
                                row[field] = float(val)
                            except (TypeError, ValueError):
                                row[field] = str(val)
                        elif isinstance(metrics, dict) and field in metrics:
                            val = metrics[field]
                            try:
                                row[field] = float(val)
                            except (TypeError, ValueError):
                                row[field] = str(val)
                    if row:
                        group_data[key] = row
                except Exception:
                    pass

        except Exception:
            pass

        if group_data:
            groups[dt] = group_data

    print(json.dumps({{"metric_groups": groups}}))

except Exception as e:
    print(json.dumps({{"metric_groups": {{}}, "error": str(e)}}))
    sys.exit(0)
'''
```

### Step 2: Add catalog and metrics API routes to `app.py`

After the `api_fits_list` route added in Task 3, add:

```python
    @app.get("/api/catalog/{run_id}/{catalog_type}", response_class=JSONResponse)
    async def api_catalog(
        run_id: str,
        catalog_type: str,
        night: str | None = None,
        band: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ):
        """Query a Butler source catalog."""
        from .catalog_query import query_catalog

        run_info_path = logs_dir / run_id / "run_info.txt"
        if not run_info_path.exists():
            return JSONResponse({"available": False, "error": "Run info not found"})

        repo_path = None
        for line in run_info_path.read_text().splitlines():
            if line.startswith("Repository:"):
                repo_path = line.split(":", 1)[1].strip()
                break

        if not repo_path:
            return JSONResponse({"available": False, "error": "Repository not found"})

        data = query_catalog(repo_path, catalog_type, night, band, limit, offset)
        return JSONResponse(data)

    @app.get("/api/metrics/{run_id}", response_class=JSONResponse)
    async def api_metrics(run_id: str):
        """Query pipeline quality metrics."""
        from .catalog_query import query_metrics

        run_info_path = logs_dir / run_id / "run_info.txt"
        if not run_info_path.exists():
            return JSONResponse({"available": False, "error": "Run info not found"})

        repo_path = None
        for line in run_info_path.read_text().splitlines():
            if line.startswith("Repository:"):
                repo_path = line.split(":", 1)[1].strip()
                break

        if not repo_path:
            return JSONResponse({"available": False, "error": "Repository not found"})

        data = query_metrics(repo_path)
        return JSONResponse(data)
```

### Step 3: Update data.html with catalog viewer

Replace the full content of `packages/data_tools/src/obs_nickel_data_tools/dashboard/templates/tabs/data.html`:

```html
<div class="data-tab">
  <!-- Butler Dataset Counts (existing) -->
  <div class="detail-section">
    <h3>Butler Dataset Counts</h3>
    <p class="text-muted">Query the Butler repository for actual dataset counts per night and band.</p>
    <button class="action-btn" id="load-butler-btn"
            hx-get="/api/butler-counts/{{ run.run_id }}"
            hx-target="#butler-results"
            hx-swap="innerHTML"
            hx-indicator="#butler-spinner">
      Load Dataset Counts
    </button>
    <span id="butler-spinner" class="htmx-indicator spinner-inline"></span>
    <div id="butler-results" class="butler-results"></div>
  </div>

  <!-- Source Catalog Viewer -->
  <div class="detail-section">
    <h3>Source Catalogs</h3>
    <div class="catalog-controls">
      <select id="catalog-type" class="fits-select" onchange="resetCatalogFilters()">
        <option value="dia_source_unfiltered">DIA Sources</option>
        <option value="forced_phot_diffim_radec">Forced Photometry</option>
      </select>
      <input type="text" id="catalog-night" class="fits-select" placeholder="Night (e.g. 20230527)" style="width:160px">
      <input type="text" id="catalog-band" class="fits-select" placeholder="Band (e.g. r)" style="width:80px">
      <button class="action-btn" onclick="loadCatalog(0)">Query</button>
      <span id="catalog-spinner" class="spinner-inline" style="display:none"></span>
    </div>
    <div id="catalog-results" class="catalog-results"></div>
    <div id="catalog-pagination" class="catalog-pagination"></div>
  </div>

  <!-- Pipeline Quality Metrics -->
  <div class="detail-section">
    <h3>Pipeline Quality Metrics</h3>
    <p class="text-muted">Color-coded quality indicators per night: calibration, DIA, and detection metrics.</p>
    <button class="action-btn" id="load-metrics-btn" onclick="loadMetrics()">
      Load Metrics
    </button>
    <span id="metrics-spinner" class="spinner-inline" style="display:none"></span>
    <div id="metrics-results"></div>
  </div>
</div>

<script>
// === Butler Counts (existing) ===
document.body.addEventListener('htmx:afterSwap', function(evt) {
  if (evt.detail.target.id === 'butler-results') {
    try {
      const data = JSON.parse(evt.detail.target.textContent);
      evt.detail.target.innerHTML = renderButlerTable(data);
    } catch(e) {}
  }
});

function renderButlerTable(data) {
  if (!data.available) {
    return '<p class="text-muted">Butler not available: ' + (data.error || 'unknown error') + '</p>';
  }
  const nights = Object.keys(data.nights).sort();
  const dtypes = data.dataset_types;
  if (nights.length === 0) {
    return '<p class="text-muted">No datasets found in repository.</p>';
  }
  let html = '<table class="night-table butler-table"><thead><tr><th>Night</th>';
  for (const dt of dtypes) {
    const short = dt.replace('goodSeeingDiff_', '').replace('forced_diff_', 'fphot_');
    html += '<th>' + short + '</th>';
  }
  html += '</tr></thead><tbody>';
  for (const night of nights) {
    html += '<tr><td class="mono">' + night + '</td>';
    for (const dt of dtypes) {
      const bands = data.nights[night][dt] || {};
      const parts = Object.entries(bands)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([band, count]) => '<span class="band-count">' + band + ':' + count + '</span>');
      html += '<td>' + (parts.length ? parts.join(' ') : '<span class="text-muted">&mdash;</span>') + '</td>';
    }
    html += '</tr>';
  }
  html += '</tbody></table>';
  return html;
}

// === Source Catalog ===
let catalogCurrentOffset = 0;
const CATALOG_LIMIT = 200;

function resetCatalogFilters() {
  document.getElementById('catalog-results').innerHTML = '';
  document.getElementById('catalog-pagination').innerHTML = '';
}

function loadCatalog(offset) {
  catalogCurrentOffset = offset;
  const type = document.getElementById('catalog-type').value;
  const night = document.getElementById('catalog-night').value.trim();
  const band = document.getElementById('catalog-band').value.trim();
  const spinner = document.getElementById('catalog-spinner');
  spinner.style.display = 'inline-block';

  let url = `/api/catalog/{{ run.run_id }}/${type}?limit=${CATALOG_LIMIT}&offset=${offset}`;
  if (night) url += `&night=${night}`;
  if (band) url += `&band=${band}`;

  fetch(url)
    .then(r => r.json())
    .then(data => {
      spinner.style.display = 'none';
      if (!data.available) {
        document.getElementById('catalog-results').innerHTML =
          '<p class="text-muted">' + (data.error || 'Not available') + '</p>';
        return;
      }
      renderCatalogTable(data);
      renderCatalogPagination(data.total, offset);
    })
    .catch(err => {
      spinner.style.display = 'none';
      document.getElementById('catalog-results').innerHTML =
        '<p class="text-muted">Query failed</p>';
    });
}

let catalogSortCol = null;
let catalogSortAsc = true;
let catalogRows = [];
let catalogColumns = [];

function renderCatalogTable(data) {
  catalogRows = data.rows;
  catalogColumns = data.columns;
  catalogSortCol = null;
  catalogSortAsc = true;
  _renderCatalogRows();
}

function _renderCatalogRows() {
  const rows = [...catalogRows];
  if (catalogSortCol !== null) {
    rows.sort((a, b) => {
      const va = a[catalogSortCol], vb = b[catalogSortCol];
      if (typeof va === 'number' && typeof vb === 'number') {
        return catalogSortAsc ? va - vb : vb - va;
      }
      return catalogSortAsc ? String(va).localeCompare(String(vb)) : String(vb).localeCompare(String(va));
    });
  }

  let html = '<table class="night-table catalog-table"><thead><tr>';
  for (const col of catalogColumns) {
    const arrow = catalogSortCol === col ? (catalogSortAsc ? ' &uarr;' : ' &darr;') : '';
    html += `<th class="sortable" onclick="sortCatalog('${col}')">${col}${arrow}</th>`;
  }
  html += '</tr></thead><tbody>';
  for (const row of rows) {
    html += '<tr>';
    for (const col of catalogColumns) {
      const val = row[col];
      const display = typeof val === 'number' ? val.toFixed(4) : (val || '');
      html += '<td class="mono">' + display + '</td>';
    }
    html += '</tr>';
  }
  html += '</tbody></table>';
  if (rows.length === 0) {
    html = '<p class="text-muted">No results found for this query.</p>';
  }
  document.getElementById('catalog-results').innerHTML = html;
}

function sortCatalog(col) {
  if (catalogSortCol === col) {
    catalogSortAsc = !catalogSortAsc;
  } else {
    catalogSortCol = col;
    catalogSortAsc = true;
  }
  _renderCatalogRows();
}

function renderCatalogPagination(total, offset) {
  let html = '<div class="pagination-controls">';
  html += `<span class="text-muted">Showing ${offset + 1}-${Math.min(offset + CATALOG_LIMIT, total)} of ${total} dataset refs</span>`;
  if (offset > 0) {
    html += ` <button class="action-btn" onclick="loadCatalog(${offset - CATALOG_LIMIT})">Prev</button>`;
  }
  if (offset + CATALOG_LIMIT < total) {
    html += ` <button class="action-btn" onclick="loadCatalog(${offset + CATALOG_LIMIT})">Next</button>`;
  }
  html += '</div>';
  document.getElementById('catalog-pagination').innerHTML = html;
}

// === Pipeline Quality Metrics ===
function loadMetrics() {
  const btn = document.getElementById('load-metrics-btn');
  const spinner = document.getElementById('metrics-spinner');
  btn.disabled = true;
  spinner.style.display = 'inline-block';

  fetch('/api/metrics/{{ run.run_id }}')
    .then(r => r.json())
    .then(data => {
      spinner.style.display = 'none';
      btn.style.display = 'none';
      if (!data.available) {
        document.getElementById('metrics-results').innerHTML =
          '<p class="text-muted">' + (data.error || 'Metrics not available') + '</p>';
        return;
      }
      renderMetrics(data);
    })
    .catch(err => {
      spinner.style.display = 'none';
      btn.disabled = false;
      document.getElementById('metrics-results').innerHTML =
        '<p class="text-muted">Failed to load metrics</p>';
    });
}

function renderMetrics(data) {
  const groups = data.metric_groups;
  const thresholds = data.thresholds;
  let html = '';

  const groupLabels = {
    'calibrateImage_metadata_metrics': 'Science Calibration',
    'diffimMetadata_metrics': 'DIA Quality',
    'detectAndMeasureDiaSource_metadata_metrics': 'Detection Counts',
  };

  for (const [dt, nightData] of Object.entries(groups)) {
    const label = groupLabels[dt] || dt;
    const thresh = thresholds[dt] || {};
    const metrics = Object.keys(thresh);
    const nightKeys = Object.keys(nightData).sort();

    if (nightKeys.length === 0) continue;

    html += `<div class="metrics-group"><h4>${label}</h4>`;
    html += '<div class="table-scroll"><table class="night-table metrics-table"><thead><tr><th>Night/Band</th>';
    for (const m of metrics) {
      html += `<th title="${m}">${m.replace(/_/g, ' ')}</th>`;
    }
    html += '</tr></thead><tbody>';

    for (const key of nightKeys) {
      const row = nightData[key];
      html += `<tr><td class="mono">${key}</td>`;
      for (const m of metrics) {
        const val = row[m];
        if (val === undefined || val === null) {
          html += '<td><span class="text-muted">&mdash;</span></td>';
          continue;
        }
        const cls = getMetricClass(m, val, thresh[m] || {});
        const display = typeof val === 'number' ? val.toFixed(3) : val;
        html += `<td><span class="metric-cell ${cls}" title="${m}: ${display}">${display}</span></td>`;
      }
      html += '</tr>';
    }
    html += '</tbody></table></div></div>';
  }

  if (!html) {
    html = '<p class="text-muted">No metrics data available.</p>';
  }
  document.getElementById('metrics-results').innerHTML = html;
}

function getMetricClass(name, value, thresh) {
  if (typeof value !== 'number' || !thresh || Object.keys(thresh).length === 0) return '';

  // Handle metrics where lower is better (fractions)
  if (thresh.good) {
    const [lo, hi] = thresh.good;
    if ((lo === null || value >= lo) && (hi === null || value <= hi)) return 'metric-good';
  }
  if (thresh.warn) {
    const [lo, hi] = thresh.warn;
    if ((lo === null || value >= lo) && (hi === null || value <= hi)) return 'metric-warn';
  }
  if (thresh.warn_low) {
    const [lo, hi] = thresh.warn_low;
    if ((lo === null || value >= lo) && (hi === null || value <= hi)) return 'metric-warn';
  }
  if (thresh.warn_high) {
    const [lo, hi] = thresh.warn_high;
    if ((lo === null || value >= lo) && (hi === null || value <= hi)) return 'metric-warn';
  }
  if (thresh.bad) {
    const [lo, hi] = thresh.bad;
    if ((lo === null || value >= lo) && (hi === null || value <= hi)) return 'metric-bad';
  }

  // If none matched explicitly, check if value is outside good range
  if (thresh.good) return 'metric-bad';
  return '';
}
</script>
```

### Step 4: Add catalog and metrics CSS to `style.css`

Append before the responsive section:

```css
/* === Source Catalog === */
.catalog-controls {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
  margin-bottom: 1rem;
}

.catalog-results {
  margin-top: 0.5rem;
}

.catalog-table th.sortable {
  cursor: pointer;
  user-select: none;
}

.catalog-table th.sortable:hover {
  color: var(--accent);
}

.catalog-pagination {
  margin-top: 0.75rem;
}

.pagination-controls {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

/* === Pipeline Quality Metrics === */
.metrics-group {
  margin-top: 1rem;
}

.metrics-group h4 {
  font-size: 0.9rem;
  color: var(--text-muted);
  margin-bottom: 0.5rem;
}

.metrics-table th {
  font-size: 0.7rem;
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.metric-cell {
  display: inline-block;
  padding: 2px 6px;
  border-radius: 3px;
  font-family: var(--mono);
  font-size: 0.75rem;
}

.metric-good {
  background: rgba(63, 185, 80, 0.15);
  color: var(--green);
}

.metric-warn {
  background: rgba(210, 153, 34, 0.15);
  color: var(--yellow);
}

.metric-bad {
  background: rgba(248, 81, 73, 0.15);
  color: var(--red);
}
```

### Step 5: Verify all files parse

Run:
```bash
python3 -c "import ast; ast.parse(open('packages/data_tools/src/obs_nickel_data_tools/dashboard/catalog_query.py').read()); print('catalog_query OK')"
python3 -c "import ast; ast.parse(open('packages/data_tools/src/obs_nickel_data_tools/dashboard/app.py').read()); print('app OK')"
```
Expected: Both print OK

### Step 6: Commit

```bash
git add packages/data_tools/src/obs_nickel_data_tools/dashboard/catalog_query.py \
      packages/data_tools/src/obs_nickel_data_tools/dashboard/app.py \
      packages/data_tools/src/obs_nickel_data_tools/dashboard/templates/tabs/data.html \
      packages/data_tools/src/obs_nickel_data_tools/dashboard/static/style.css
git commit -m "feat: add source catalog viewer and pipeline quality metrics dashboard"
```

---

## Task 5: General Polish — View Transitions & Loading Skeletons

Add HTMX view transitions for smooth tab switching, loading skeleton animations, and micro-animations.

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/dashboard/templates/run_detail.html` (transition attributes)
- Modify: `packages/data_tools/src/obs_nickel_data_tools/dashboard/templates/base.html` (meta tag)
- Modify: `packages/data_tools/src/obs_nickel_data_tools/dashboard/static/style.css` (transitions, skeletons, animations)

### Step 1: Add view transition meta tag to `base.html`

In `base.html`, add the view transition meta tag inside `<head>`, after the stylesheet link (line 10):

```html
    <meta name="view-transition" content="same-origin">
```

### Step 2: Update `run_detail.html` with transition attributes

Update the tab buttons and content div to use HTMX view transitions. Change the `hx-swap` attribute from `innerHTML` to `innerHTML transition:true`:

Line 43: `hx-swap="innerHTML transition:true"`
Line 44: `hx-swap="innerHTML transition:true"`
Line 45: `hx-swap="innerHTML transition:true"`
Line 46: `hx-swap="innerHTML transition:true"`

Also add `style="view-transition-name: tab-content"` to the `#tab-content` div.

And replace the loading text with a skeleton:

```html
  <div id="tab-content" style="view-transition-name: tab-content"
       hx-get="/run/{{ run.run_id }}/tab/overview" hx-trigger="load" hx-swap="innerHTML transition:true">
    <div class="skeleton-container">
      <div class="skeleton skeleton-cards">
        <div class="skeleton-card"></div>
        <div class="skeleton-card"></div>
        <div class="skeleton-card"></div>
        <div class="skeleton-card"></div>
      </div>
      <div class="skeleton skeleton-block" style="height: 200px"></div>
      <div class="skeleton skeleton-block" style="height: 300px"></div>
    </div>
  </div>
```

### Step 3: Add transitions, skeletons, and micro-animation CSS

Append to `style.css`, before the responsive section:

```css
/* === View Transitions === */
::view-transition-old(tab-content) {
  animation: fade-out 0.15s ease-in;
}

::view-transition-new(tab-content) {
  animation: fade-in 0.2s ease-out;
}

@keyframes fade-out {
  from { opacity: 1; }
  to { opacity: 0; }
}

@keyframes fade-in {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: translateY(0); }
}

/* === Loading Skeletons === */
.skeleton-container {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.skeleton-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1rem;
}

.skeleton-card {
  height: 90px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 8px;
  animation: skeleton-pulse 1.5s ease-in-out infinite;
}

.skeleton-block {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 8px;
  animation: skeleton-pulse 1.5s ease-in-out infinite;
}

@keyframes skeleton-pulse {
  0%, 100% { opacity: 0.6; }
  50% { opacity: 0.3; }
}

/* === Micro-animations === */
.summary-card {
  animation: card-fade-in 0.3s ease-out backwards;
}

.summary-card:nth-child(1) { animation-delay: 0ms; }
.summary-card:nth-child(2) { animation-delay: 60ms; }
.summary-card:nth-child(3) { animation-delay: 120ms; }
.summary-card:nth-child(4) { animation-delay: 180ms; }

@keyframes card-fade-in {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.night-table td .cell-status {
  transition: transform 0.15s ease;
}

.night-table tr:hover .cell-status {
  transform: scale(1.05);
}

.phase-step {
  transition: opacity 0.3s ease;
}

.detail-section {
  animation: section-fade-in 0.25s ease-out backwards;
}

@keyframes section-fade-in {
  from { opacity: 0; }
  to { opacity: 1; }
}
```

### Step 4: Update responsive breakpoints for new components

Add to the existing `@media (max-width: 900px)` block:

```css
  .fits-panels {
    grid-template-columns: 1fr;
  }

  .skeleton-cards {
    grid-template-columns: repeat(2, 1fr);
  }

  .catalog-controls {
    flex-direction: column;
    align-items: stretch;
  }
```

### Step 5: Commit

```bash
git add packages/data_tools/src/obs_nickel_data_tools/dashboard/templates/run_detail.html \
      packages/data_tools/src/obs_nickel_data_tools/dashboard/templates/base.html \
      packages/data_tools/src/obs_nickel_data_tools/dashboard/static/style.css
git commit -m "feat: add view transitions, loading skeletons, and micro-animations"
```

---

## Task 6: Final Verification & Restart

Verify all files, restart the dev server, and test in browser.

### Step 1: Syntax check all Python files

```bash
for f in packages/data_tools/src/obs_nickel_data_tools/dashboard/{app,collector,analysis,butler_query,image_renderer,catalog_query}.py; do
  python3 -c "import ast; ast.parse(open('$f').read()); print('OK: $f')"
done
```

Expected: All print OK.

### Step 2: Verify Jinja2 templates parse

```bash
python3 -c "
from jinja2 import Environment
env = Environment()
for f in ['run_detail.html', 'base.html', 'tabs/overview.html', 'tabs/logs.html', 'tabs/analysis.html', 'tabs/data.html']:
    path = f'packages/data_tools/src/obs_nickel_data_tools/dashboard/templates/{f}'
    env.parse(open(path).read())
    print(f'OK: {f}')
"
```

### Step 3: Kill old server and restart

```bash
# Kill any existing dashboard server
pkill -f "uvicorn.*obs_nickel" || true
sleep 1

# Start fresh server
cd /Users/dangause/Developer/lick/lsst/lsst_stack/stack/nickel_processing_suite/.worktrees/bps-full
PYTHONPATH=packages/data_tools/src python3 -m uvicorn obs_nickel_data_tools.dashboard:app --host 0.0.0.0 --port 8000 --factory &
```

### Step 4: Manual browser verification

- [ ] Duration shows correct time for completed runs (not start-to-now)
- [ ] Tab transitions are smooth (fade animation)
- [ ] Loading skeletons show while tabs load
- [ ] Summary cards animate in with stagger
- [ ] Lightcurve has range slider under x-axis
- [ ] Crosshair hover shows all bands at an epoch
- [ ] Points connected with lines per band
- [ ] Mag/flux toggle button works (if both columns exist)
- [ ] FITS viewer: Load button queries available images
- [ ] Night/band dropdowns populate and update panels
- [ ] Three-panel science/template/difference layout
- [ ] Source catalog query button works
- [ ] Table columns sortable (click header)
- [ ] Pagination prev/next works
- [ ] Metrics load button shows color-coded table
- [ ] Green/yellow/red thresholds applied correctly
- [ ] Mobile: FITS panels stack vertically, catalog controls stack

### Step 5: Final commit (if any fixes needed)

```bash
git add -A
git commit -m "fix: address verification issues from dashboard v2.1"
```
