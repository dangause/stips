# Dashboard v2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enhance the NPS dashboard with tabbed navigation, log browsing, interactive lightcurve charts, and Butler dataset visibility.

**Architecture:** Extend existing FastAPI + HTMX stack. Add tab navigation to run detail page (Overview, Logs, Analysis, Data). New API endpoints serve log files, lightcurve JSON, and Butler counts. Plotly.js (CDN) renders interactive charts client-side. No new Python dependencies.

**Tech Stack:** FastAPI, Jinja2, HTMX 2.0.4, SSE-Starlette, Plotly.js (CDN), existing dark theme CSS.

---

## Task 1: Tab Navigation Infrastructure

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/dashboard/templates/run_detail.html`
- Modify: `packages/data_tools/src/obs_nickel_data_tools/dashboard/static/style.css`
- Modify: `packages/data_tools/src/obs_nickel_data_tools/dashboard/app.py`
- Create: `packages/data_tools/src/obs_nickel_data_tools/dashboard/templates/tabs/overview.html`

**Step 1: Add tab route to app.py**

In `app.py`, inside `create_app()`, add a new route after the existing `run_detail` route (after line ~102):

```python
@app.get("/run/{run_id}/tab/{tab_name}", response_class=HTMLResponse)
async def run_tab(request: Request, run_id: str, tab_name: str):
    """Serve individual tab content as HTMX partial."""
    info = get_run(logs_dir, run_id)
    if info is None:
        return HTMLResponse("<p>Run not found</p>", status_code=404)

    template_map = {
        "overview": "tabs/overview.html",
        "logs": "tabs/logs.html",
        "analysis": "tabs/analysis.html",
        "data": "tabs/data.html",
    }
    template_name = template_map.get(tab_name)
    if template_name is None:
        return HTMLResponse("<p>Unknown tab</p>", status_code=404)

    context = {"request": request, "run": info}

    if tab_name == "overview":
        log_path = logs_dir / run_id / "pipeline.log"
        initial_log = ""
        if log_path.exists():
            lines = log_path.read_text().splitlines()
            initial_log = "\n".join(lines[-200:])
        context["initial_log"] = initial_log

    return templates.TemplateResponse(template_name, context)
```

**Step 2: Create tabs/overview.html**

Extract the current run_detail.html body content (night grid, log viewer, BPS panel) into `tabs/overview.html`. This template is a fragment (no base.html extension):

```html
<!-- Summary cards -->
<div class="summary-cards">
  <div class="summary-card">
    <span class="card-label">Calibs</span>
    <span class="card-value">{{ run.calibs_ok }}/{{ run.calibs_total }}</span>
    <div class="card-bar"><div class="card-bar-fill green" style="width: {{ (run.calibs_ok / run.calibs_total * 100) if run.calibs_total else 0 }}%"></div></div>
  </div>
  <div class="summary-card">
    <span class="card-label">Science</span>
    <span class="card-value">{{ run.science_ok }}/{{ run.science_total }}</span>
    <div class="card-bar"><div class="card-bar-fill green" style="width: {{ (run.science_ok / run.science_total * 100) if run.science_total else 0 }}%"></div></div>
  </div>
  <div class="summary-card">
    <span class="card-label">DIA</span>
    <span class="card-value">{{ run.dia_ok }}/{{ run.dia_total }}</span>
    <div class="card-bar"><div class="card-bar-fill green" style="width: {{ (run.dia_ok / run.dia_total * 100) if run.dia_total else 0 }}%"></div></div>
  </div>
  <div class="summary-card">
    <span class="card-label">FPhot</span>
    <span class="card-value">{{ run.fphot_ok }}/{{ run.fphot_total }}</span>
    <div class="card-bar"><div class="card-bar-fill green" style="width: {{ (run.fphot_ok / run.fphot_total * 100) if run.fphot_total else 0 }}%"></div></div>
  </div>
</div>

<!-- Night grid (existing, enhanced with clickable cells) -->
<div class="detail-section">
  <h3>Nights</h3>
  <div id="night-grid" hx-ext="sse" sse-connect="/api/events/{{ run.run_id }}" sse-swap="night-update" hx-swap="innerHTML">
    {% include 'partials/night_grid.html' %}
  </div>
</div>

<!-- Log viewer (existing) -->
<div class="log-section">
  <div class="log-header">
    <h3>Pipeline Log</h3>
    <button class="toggle-btn" onclick="toggleAutoScroll()">
      Auto-scroll: <span id="scroll-status">ON</span>
    </button>
  </div>
  <div class="log-viewer" id="log-viewer">
    <pre id="log-content" sse-swap="log-line" hx-swap="beforeend">{{ initial_log }}</pre>
  </div>
</div>

<!-- BPS panel (conditional) -->
{% if run.is_bps %}
<div class="bps-section">
  <h3>Slurm Jobs ({{ run.bps_site }})</h3>
  <div id="bps-panel" sse-swap="bps-update" hx-swap="innerHTML">
    <p class="text-muted">Waiting for job data...</p>
  </div>
</div>
{% endif %}

<script>
let autoScroll = true;
function toggleAutoScroll() {
  autoScroll = !autoScroll;
  document.getElementById('scroll-status').textContent = autoScroll ? 'ON' : 'OFF';
}
const logViewer = document.getElementById('log-viewer');
if (logViewer) {
  const observer = new MutationObserver(() => {
    if (autoScroll) logViewer.scrollTop = logViewer.scrollHeight;
  });
  const logContent = document.getElementById('log-content');
  if (logContent) observer.observe(logContent, { childList: true, characterData: true, subtree: true });
  logViewer.scrollTop = logViewer.scrollHeight;
}
</script>
```

**Step 3: Restructure run_detail.html with tabs**

Replace the body content of `run_detail.html` (everything after the phase progress bar, ~line 37 onwards) with tab navigation. Keep the header and phase bar. The SSE connection moves into the overview tab partial:

```html
{% extends "base.html" %}
{% block title %}Run {{ run.run_id }}{% endblock %}
{% block content %}
<div class="run-detail">
  <!-- Back link -->
  <a href="/" class="back-link">&larr; All Runs</a>

  <!-- Header (keep existing) -->
  <div class="run-header">
    <h2>
      {{ run.object_name or run.run_id }}
      <span class="status-badge {{ run.status.value }}">{{ run.status.value }}</span>
    </h2>
    <div class="run-meta">
      <span class="mono">{{ run.run_id }}</span>
      <span>Started: {{ run.started[:19] if run.started else '—' }}</span>
      <span>Duration: {{ run.duration or '—' }}</span>
      {% if run.bands %}<span>Bands: {{ run.bands | join(', ') }}</span>{% endif %}
      {% if run.is_bps %}<span>BPS: {{ run.bps_site }}</span>{% endif %}
    </div>
  </div>

  <!-- Phase progress bar (keep existing) -->
  <div class="phase-bar">
    {% for phase in phases %}
    {% set pi = phase_index(run, phase) %}
    <div class="phase-step {{ 'done' if pi < 0 else ('active' if pi == 0 else 'pending') }}">
      <div class="phase-icon">
        {% if pi < 0 %}&#10003;{% elif pi == 0 %}<span class="spinner"></span>{% else %}&#183;{% endif %}
      </div>
      <div class="phase-label">{{ phase.value }}</div>
    </div>
    {% endfor %}
  </div>

  <!-- Tab navigation -->
  <div class="tab-nav">
    <button class="tab-btn active" hx-get="/run/{{ run.run_id }}/tab/overview" hx-target="#tab-content" hx-swap="innerHTML" onclick="setActiveTab(this)">Overview</button>
    <button class="tab-btn" hx-get="/run/{{ run.run_id }}/tab/logs" hx-target="#tab-content" hx-swap="innerHTML" onclick="setActiveTab(this)">Logs</button>
    <button class="tab-btn" hx-get="/run/{{ run.run_id }}/tab/analysis" hx-target="#tab-content" hx-swap="innerHTML" onclick="setActiveTab(this)">Analysis</button>
    <button class="tab-btn" hx-get="/run/{{ run.run_id }}/tab/data" hx-target="#tab-content" hx-swap="innerHTML" onclick="setActiveTab(this)">Data</button>
  </div>

  <!-- Tab content (initially loads overview) -->
  <div id="tab-content" hx-get="/run/{{ run.run_id }}/tab/overview" hx-trigger="load" hx-swap="innerHTML">
    <p class="text-muted">Loading...</p>
  </div>
</div>

<script>
function setActiveTab(btn) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
}
</script>
{% endblock %}
```

**Step 4: Add tab CSS to style.css**

Append to `static/style.css`:

```css
/* === Tab Navigation === */
.tab-nav {
  display: flex;
  gap: 0;
  border-bottom: 1px solid var(--border);
  margin: 1.5rem 0 0 0;
}

.tab-btn {
  background: none;
  border: none;
  color: var(--text-muted);
  padding: 0.75rem 1.25rem;
  font-size: 0.9rem;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: color 0.15s, border-color 0.15s;
}

.tab-btn:hover {
  color: var(--text);
}

.tab-btn.active {
  color: var(--text);
  border-bottom-color: var(--accent);
}

#tab-content {
  padding-top: 1.5rem;
}

/* === Summary Cards === */
.summary-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.summary-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 1rem;
}

.card-label {
  color: var(--text-muted);
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.card-value {
  display: block;
  font-size: 1.5rem;
  font-weight: 600;
  margin: 0.25rem 0 0.5rem 0;
}

.card-bar {
  height: 4px;
  background: var(--bg-tertiary);
  border-radius: 2px;
  overflow: hidden;
}

.card-bar-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.3s ease;
}

.card-bar-fill.green { background: var(--green); }
.card-bar-fill.yellow { background: var(--yellow); }
.card-bar-fill.red { background: var(--red); }
```

**Step 5: Verify tab switching works**

Run: `cd packages/data_tools && pip install -e . && nickel dashboard --no-browser`
Open `http://127.0.0.1:8787`, click into a run, verify tabs switch content without page reload.

**Step 6: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/dashboard/
git commit -m "feat(dashboard): add tabbed navigation to run detail page"
```

---

## Task 2: Clickable Night Grid with Drill-Down

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/dashboard/templates/partials/night_grid.html`
- Create: `packages/data_tools/src/obs_nickel_data_tools/dashboard/templates/night_detail.html`
- Modify: `packages/data_tools/src/obs_nickel_data_tools/dashboard/app.py`
- Modify: `packages/data_tools/src/obs_nickel_data_tools/dashboard/collector.py`
- Modify: `packages/data_tools/src/obs_nickel_data_tools/dashboard/static/style.css`

**Step 1: Add per-exposure parsing to collector.py**

Add a function to `collector.py` after `_scan_night_logs()` (~line 429):

```python
def get_night_detail(logs_dir: Path, run_id: str, night: str) -> dict:
    """Get per-exposure detail for a specific night within a run."""
    run_dir = logs_dir / run_id
    detail = {
        "night": night,
        "phases": {},  # phase_name → {status, exposures: [{id, status, log_path}]}
    }

    for step in ("calibs", "science"):
        step_dir = run_dir / step
        night_dir = step_dir / night
        night_log = step_dir / f"{night}.log"

        exposures = []
        if night_dir.is_dir():
            # Split logs exist
            for f in sorted(night_dir.iterdir()):
                if f.suffix == ".log" and f.stem != "_general":
                    # Check for error patterns in exposure log
                    text = f.read_text(errors="replace")
                    has_error = "[ERROR]" in text or "Exception" in text
                    exposures.append({
                        "id": f.stem,
                        "status": "failed" if has_error else "success",
                        "log_path": f"{step}/{night}/{f.name}",
                    })
            # Include general log
            general = night_dir / "_general.log"
            if general.exists():
                exposures.insert(0, {
                    "id": "_general",
                    "status": "info",
                    "log_path": f"{step}/{night}/_general.log",
                })
        elif night_log.exists():
            exposures.append({
                "id": "full",
                "status": "info",
                "log_path": f"{step}/{night}.log",
            })

        detail["phases"][step] = {"exposures": exposures}

    # DIA and fphot: per-band logs
    for step in ("dia", "fphot"):
        step_dir = run_dir / step
        band_logs = []
        if step_dir.is_dir():
            for f in sorted(step_dir.iterdir()):
                if f.name.startswith(night) and f.suffix == ".log":
                    band = f.stem.split("_")[-1] if "_" in f.stem else "?"
                    text = f.read_text(errors="replace")
                    has_error = "[ERROR]" in text or "failed" in text.lower()
                    band_logs.append({
                        "id": f.stem,
                        "band": band,
                        "status": "failed" if has_error else "success",
                        "log_path": f"{step}/{f.name}",
                    })
        detail["phases"][step] = {"exposures": band_logs}

    return detail
```

**Step 2: Add night detail route to app.py**

Add after the `run_tab` route:

```python
@app.get("/run/{run_id}/night/{night}", response_class=HTMLResponse)
async def night_detail(request: Request, run_id: str, night: str):
    """Per-night drill-down showing per-exposure status."""
    from .collector import get_night_detail
    info = get_run(logs_dir, run_id)
    if info is None:
        return HTMLResponse("<p>Run not found</p>", status_code=404)
    detail = get_night_detail(logs_dir, run_id, night)
    return templates.TemplateResponse("night_detail.html", {
        "request": request, "run": info, "night": night, "detail": detail,
    })
```

**Step 3: Create night_detail.html**

```html
{% extends "base.html" %}
{% block title %}Night {{ night }} — {{ run.run_id }}{% endblock %}
{% block content %}
<div class="run-detail">
  <a href="/run/{{ run.run_id }}" class="back-link">&larr; {{ run.object_name or run.run_id }}</a>

  <div class="run-header">
    <h2>Night {{ night }}</h2>
    <div class="run-meta">
      <span class="mono">{{ run.run_id }}</span>
    </div>
  </div>

  {% for phase_name, phase_data in detail.phases.items() %}
  <div class="detail-section">
    <h3>{{ phase_name | title }}</h3>
    {% if phase_data.exposures %}
    <table class="night-table">
      <thead>
        <tr>
          <th>{% if phase_name in ('dia', 'fphot') %}Night/Band{% else %}Exposure{% endif %}</th>
          <th>Status</th>
          <th>Log</th>
        </tr>
      </thead>
      <tbody>
        {% for exp in phase_data.exposures %}
        <tr>
          <td class="mono">{{ exp.id }}</td>
          <td><span class="cell-status {{ exp.status }}">{{ exp.status }}</span></td>
          <td>
            <a href="/api/log/{{ run.run_id }}/{{ exp.log_path }}"
               hx-get="/api/log/{{ run.run_id }}/{{ exp.log_path }}"
               hx-target="#log-panel"
               hx-swap="innerHTML"
               class="log-link">View log</a>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    {% else %}
    <p class="text-muted">No logs found for this phase.</p>
    {% endif %}
  </div>
  {% endfor %}

  <!-- Log panel for inline viewing -->
  <div class="log-section" id="log-panel-section" style="display:none">
    <div class="log-header"><h3>Log Viewer</h3></div>
    <div class="log-viewer"><pre id="log-panel"></pre></div>
  </div>
</div>

<script>
document.body.addEventListener('htmx:afterSwap', function(evt) {
  if (evt.detail.target.id === 'log-panel') {
    document.getElementById('log-panel-section').style.display = 'block';
    document.getElementById('log-panel').closest('.log-viewer').scrollTop = 0;
  }
});
</script>
{% endblock %}
```

**Step 4: Make night grid cells clickable**

Modify `partials/night_grid.html` — wrap each night name in a link:

Change the night cell from a plain `<td>` to:
```html
<td class="mono"><a href="/run/{{ run.run_id }}/night/{{ ns.night }}" class="night-link">{{ ns.night }}</a></td>
```

**Step 5: Add log file serving route to app.py**

Replace the existing `api_log` route with a more flexible one:

```python
@app.get("/api/log/{run_id}/{path:path}", response_class=PlainTextResponse)
async def api_log_file(run_id: str, path: str):
    """Serve any log file from a run directory."""
    log_file = logs_dir / run_id / path
    # Security: ensure path doesn't escape the run directory
    try:
        log_file.resolve().relative_to((logs_dir / run_id).resolve())
    except ValueError:
        return PlainTextResponse("Access denied", status_code=403)
    if not log_file.exists():
        return PlainTextResponse("Log not found", status_code=404)
    content = log_file.read_text(errors="replace")
    return PlainTextResponse(content)
```

Keep the old `/api/log/{run_id}` route as well for backwards compatibility (the SSE tails pipeline.log using it), or update references.

**Step 6: Add night detail CSS**

```css
/* === Night Detail === */
.night-link {
  color: var(--accent);
  text-decoration: none;
}

.night-link:hover {
  text-decoration: underline;
}

.log-link {
  color: var(--accent);
  font-size: 0.85rem;
  text-decoration: none;
}

.log-link:hover {
  text-decoration: underline;
}

#log-panel {
  white-space: pre-wrap;
  word-wrap: break-word;
}
```

**Step 7: Verify night drill-down**

Run dashboard, click a run, click a night name in the grid → should see per-exposure table. Click "View log" → log content loads inline.

**Step 8: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/dashboard/
git commit -m "feat(dashboard): add night detail drill-down with per-exposure logs"
```

---

## Task 3: Log Browser Tab

**Files:**
- Create: `packages/data_tools/src/obs_nickel_data_tools/dashboard/templates/tabs/logs.html`
- Modify: `packages/data_tools/src/obs_nickel_data_tools/dashboard/app.py`
- Modify: `packages/data_tools/src/obs_nickel_data_tools/dashboard/collector.py`
- Modify: `packages/data_tools/src/obs_nickel_data_tools/dashboard/static/style.css`

**Step 1: Add log tree builder to collector.py**

Add after `get_night_detail()`:

```python
def get_log_tree(logs_dir: Path, run_id: str) -> list[dict]:
    """Build a directory tree of all log files for a run.

    Returns a nested list structure:
    [{"name": "calibs", "type": "dir", "children": [
        {"name": "20230519.log", "type": "file", "path": "calibs/20230519.log", "size": 1234},
        ...
    ]}, ...]
    """
    run_dir = logs_dir / run_id
    if not run_dir.is_dir():
        return []

    def _build_tree(directory: Path, prefix: str = "") -> list[dict]:
        items = []
        for entry in sorted(directory.iterdir()):
            rel = f"{prefix}/{entry.name}" if prefix else entry.name
            if entry.is_dir():
                children = _build_tree(entry, rel)
                if children:  # skip empty dirs
                    items.append({
                        "name": entry.name,
                        "type": "dir",
                        "path": rel,
                        "children": children,
                    })
            elif entry.suffix in (".log", ".txt", ".stdout", ".stderr"):
                items.append({
                    "name": entry.name,
                    "type": "file",
                    "path": rel,
                    "size": entry.stat().st_size,
                })
        return items

    return _build_tree(run_dir)
```

**Step 2: Add log tree API route to app.py**

```python
from fastapi.responses import JSONResponse

@app.get("/api/log-tree/{run_id}", response_class=JSONResponse)
async def api_log_tree(run_id: str):
    """Return the log directory tree as JSON."""
    from .collector import get_log_tree
    tree = get_log_tree(logs_dir, run_id)
    return JSONResponse(tree)
```

**Step 3: Create tabs/logs.html**

```html
<div class="log-browser">
  <!-- File tree sidebar -->
  <div class="log-tree-panel">
    <h3>Log Files</h3>
    <div id="log-tree" hx-get="/api/log-tree/{{ run.run_id }}" hx-trigger="load" hx-swap="innerHTML">
      <p class="text-muted">Loading tree...</p>
    </div>
  </div>

  <!-- Log content viewer -->
  <div class="log-content-panel">
    <div class="log-content-header">
      <span id="log-file-name" class="mono text-muted">Select a log file</span>
      <div class="log-actions">
        <input type="text" id="log-search-input" placeholder="Search in log..." class="log-search" oninput="searchInLog(this.value)">
      </div>
    </div>
    <div class="log-viewer" id="browser-log-viewer">
      <pre id="browser-log-content" class="text-muted">← Select a file from the tree</pre>
    </div>
  </div>
</div>

<script>
// Render the log tree from JSON
document.body.addEventListener('htmx:afterSwap', function(evt) {
  if (evt.detail.target.id === 'log-tree') {
    try {
      const data = JSON.parse(evt.detail.target.textContent);
      evt.detail.target.innerHTML = renderTree(data);
    } catch(e) {
      // Already rendered as HTML, ignore
    }
  }
});

function renderTree(items, depth) {
  depth = depth || 0;
  let html = '<ul class="tree-list">';
  for (const item of items) {
    if (item.type === 'dir') {
      html += '<li class="tree-dir">';
      html += '<span class="tree-toggle" onclick="this.parentElement.classList.toggle(\'collapsed\')">';
      html += '<span class="tree-arrow">&#9660;</span> ' + item.name + '</span>';
      html += renderTree(item.children, depth + 1);
      html += '</li>';
    } else {
      const sizeKb = (item.size / 1024).toFixed(1);
      html += '<li class="tree-file">';
      html += '<a href="#" onclick="loadLog(\'' + item.path + '\', \'' + item.name + '\'); return false;">';
      html += item.name + '</a>';
      html += '<span class="tree-size">' + sizeKb + 'K</span>';
      html += '</li>';
    }
  }
  html += '</ul>';
  return html;
}

function loadLog(path, name) {
  document.getElementById('log-file-name').textContent = path;
  fetch('/api/log/{{ run.run_id }}/' + path)
    .then(r => r.text())
    .then(text => {
      const pre = document.getElementById('browser-log-content');
      pre.className = '';
      pre.textContent = text;
      document.getElementById('browser-log-viewer').scrollTop = 0;
    });
}

function searchInLog(query) {
  const pre = document.getElementById('browser-log-content');
  if (!query) {
    // Remove highlights
    pre.innerHTML = pre.textContent;
    return;
  }
  const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const re = new RegExp('(' + escaped + ')', 'gi');
  const text = pre.textContent;
  pre.innerHTML = text.replace(re, '<mark>$1</mark>');
}
</script>
```

**Step 4: Add log browser CSS**

```css
/* === Log Browser === */
.log-browser {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 1rem;
  min-height: 600px;
}

.log-tree-panel {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 1rem;
  overflow-y: auto;
  max-height: 700px;
}

.log-tree-panel h3 {
  margin: 0 0 0.75rem 0;
  font-size: 0.9rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.tree-list {
  list-style: none;
  padding-left: 1rem;
  margin: 0;
}

.log-tree-panel > .tree-list,
.log-tree-panel > #log-tree > .tree-list {
  padding-left: 0;
}

.tree-dir > .tree-toggle {
  cursor: pointer;
  color: var(--text);
  font-weight: 500;
  display: block;
  padding: 0.15rem 0;
}

.tree-arrow {
  font-size: 0.7rem;
  display: inline-block;
  transition: transform 0.15s;
}

.tree-dir.collapsed > .tree-list {
  display: none;
}

.tree-dir.collapsed .tree-arrow {
  transform: rotate(-90deg);
}

.tree-file {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.15rem 0;
}

.tree-file a {
  color: var(--accent);
  text-decoration: none;
  font-size: 0.85rem;
}

.tree-file a:hover {
  text-decoration: underline;
}

.tree-size {
  color: var(--text-muted);
  font-size: 0.75rem;
  font-family: var(--mono);
}

.log-content-panel {
  display: flex;
  flex-direction: column;
}

.log-content-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}

.log-search {
  background: var(--bg-tertiary);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 0.4rem 0.75rem;
  border-radius: 4px;
  font-size: 0.85rem;
  width: 200px;
}

.log-content-panel .log-viewer {
  flex: 1;
  max-height: 650px;
}

mark {
  background: var(--yellow);
  color: var(--bg);
  padding: 0 2px;
  border-radius: 2px;
}
```

**Step 5: Verify log browser**

Run dashboard, navigate to run detail, click "Logs" tab → should see file tree on left, click a log file → content renders on right, search highlights matches.

**Step 6: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/dashboard/
git commit -m "feat(dashboard): add log browser tab with file tree and search"
```

---

## Task 4: Analysis Tab (Lightcurve Plots + Output Gallery)

**Files:**
- Create: `packages/data_tools/src/obs_nickel_data_tools/dashboard/analysis.py`
- Create: `packages/data_tools/src/obs_nickel_data_tools/dashboard/templates/tabs/analysis.html`
- Modify: `packages/data_tools/src/obs_nickel_data_tools/dashboard/app.py`
- Modify: `packages/data_tools/src/obs_nickel_data_tools/dashboard/templates/base.html`
- Modify: `packages/data_tools/src/obs_nickel_data_tools/dashboard/static/style.css`

**Step 1: Create analysis.py module**

```python
"""Analysis data helpers for the dashboard."""

from __future__ import annotations

import csv
import json
from pathlib import Path


def find_lightcurve_files(logs_dir: Path, run_id: str) -> dict:
    """Find lightcurve output files referenced in summary.txt.

    Returns dict with keys: csv_path, png_path, repo_path, found.
    """
    summary = logs_dir / run_id / "summary.txt"
    result = {"csv_path": None, "png_path": None, "repo_path": None, "found": False}

    if not summary.exists():
        return result

    text = summary.read_text()
    for line in text.splitlines():
        if line.startswith("Lightcurve:"):
            csv_path = line.split(":", 1)[1].strip()
            if csv_path and csv_path != "None":
                p = Path(csv_path)
                result["csv_path"] = str(p) if p.exists() else None
                # PNG is same stem
                png = p.parent / f"{p.stem}.png"
                result["png_path"] = str(png) if png.exists() else None
                result["repo_path"] = str(p.parent)
                result["found"] = True
        if line.startswith("Repository:"):
            result["repo_path"] = line.split(":", 1)[1].strip()

    # Also check repo-based lightcurves dir if not found from summary
    if not result["found"]:
        run_info = logs_dir / run_id / "run_info.txt"
        if run_info.exists():
            for line in run_info.read_text().splitlines():
                if line.startswith("Repository:"):
                    repo = Path(line.split(":", 1)[1].strip())
                    lc_dir = repo / "lightcurves"
                    if lc_dir.is_dir():
                        result["repo_path"] = str(lc_dir)
                        # Find most recent CSV
                        csvs = sorted(lc_dir.glob("*.csv"), key=lambda f: f.stat().st_mtime, reverse=True)
                        if csvs:
                            result["csv_path"] = str(csvs[0])
                            png = csvs[0].parent / f"{csvs[0].stem}.png"
                            result["png_path"] = str(png) if png.exists() else None
                            result["found"] = True

    return result


def parse_lightcurve_csv(csv_path: str) -> dict:
    """Parse a lightcurve CSV file into JSON-serializable format for Plotly.

    Returns dict with keys: columns, data (list of rows), bands (unique band values).
    """
    path = Path(csv_path)
    if not path.exists():
        return {"columns": [], "data": [], "bands": []}

    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames or []
        for row in reader:
            # Convert numeric fields
            parsed = {}
            for k, v in row.items():
                try:
                    parsed[k] = float(v)
                except (ValueError, TypeError):
                    parsed[k] = v
            rows.append(parsed)

    bands = sorted(set(r.get("band", "") for r in rows if r.get("band")))

    return {"columns": columns, "data": rows, "bands": bands}


def find_output_images(logs_dir: Path, run_id: str) -> list[dict]:
    """Find all output images (PNGs) associated with a run."""
    lc = find_lightcurve_files(logs_dir, run_id)
    images = []

    if lc.get("png_path"):
        images.append({
            "name": Path(lc["png_path"]).name,
            "path": lc["png_path"],
            "type": "lightcurve",
        })

    # Check for additional PNGs in lightcurves dir
    if lc.get("repo_path"):
        lc_dir = Path(lc["repo_path"])
        if lc_dir.is_dir():
            for png in sorted(lc_dir.glob("*.png")):
                if str(png) != lc.get("png_path"):
                    images.append({
                        "name": png.name,
                        "path": str(png),
                        "type": "plot",
                    })

    return images
```

**Step 2: Add analysis API routes to app.py**

```python
@app.get("/api/lightcurve-data/{run_id}", response_class=JSONResponse)
async def api_lightcurve_data(run_id: str):
    """Return lightcurve CSV data as JSON for Plotly rendering."""
    from .analysis import find_lightcurve_files, parse_lightcurve_csv
    lc = find_lightcurve_files(logs_dir, run_id)
    if not lc.get("csv_path"):
        return JSONResponse({"error": "No lightcurve CSV found", "data": [], "bands": []})
    data = parse_lightcurve_csv(lc["csv_path"])
    return JSONResponse(data)

@app.get("/api/image/{run_id}")
async def api_image(run_id: str, path: str):
    """Serve an output image file."""
    from fastapi.responses import FileResponse
    img_path = Path(path)
    if not img_path.exists():
        return PlainTextResponse("Image not found", status_code=404)
    # Security: only serve from expected locations
    return FileResponse(img_path, media_type="image/png")
```

**Step 3: Update the tab route context for analysis**

In the `run_tab` route handler in `app.py`, add context for the analysis tab:

```python
if tab_name == "analysis":
    from .analysis import find_lightcurve_files, find_output_images
    context["lc_files"] = find_lightcurve_files(logs_dir, run_id)
    context["output_images"] = find_output_images(logs_dir, run_id)
```

**Step 4: Add Plotly.js to base.html**

In `templates/base.html`, add after the HTMX script tags (after line ~8):

```html
<script src="https://cdn.plot.ly/plotly-2.35.0.min.js" charset="utf-8"></script>
```

**Step 5: Create tabs/analysis.html**

```html
<div class="analysis-tab">
  {% if lc_files.found %}

  <!-- Static lightcurve PNG -->
  {% if lc_files.png_path %}
  <div class="detail-section">
    <h3>Lightcurve Plot</h3>
    <div class="plot-container">
      <img src="/api/image/{{ run.run_id }}?path={{ lc_files.png_path }}"
           alt="Lightcurve" class="output-image" onclick="this.classList.toggle('expanded')">
    </div>
  </div>
  {% endif %}

  <!-- Interactive Plotly chart -->
  <div class="detail-section">
    <h3>Interactive Lightcurve</h3>
    <div id="plotly-chart" class="plotly-container">
      <p class="text-muted">Loading chart data...</p>
    </div>
  </div>

  <!-- CSV Data Table -->
  <div class="detail-section">
    <h3>Data Table</h3>
    <div id="lc-table-container" class="table-scroll">
      <p class="text-muted">Loading...</p>
    </div>
  </div>

  {% else %}
  <div class="detail-section">
    <p class="text-muted">No lightcurve data available for this run. The pipeline may not have reached the lightcurve extraction phase.</p>
  </div>
  {% endif %}

  <!-- Output images gallery -->
  {% if output_images %}
  <div class="detail-section">
    <h3>Output Files</h3>
    <div class="image-gallery">
      {% for img in output_images %}
      <div class="gallery-item">
        <img src="/api/image/{{ run.run_id }}?path={{ img.path }}"
             alt="{{ img.name }}" loading="lazy" onclick="this.classList.toggle('expanded')">
        <span class="gallery-label">{{ img.name }}</span>
      </div>
      {% endfor %}
    </div>
  </div>
  {% endif %}
</div>

{% if lc_files.found %}
<script>
const BAND_COLORS = {
  'b': '#58a6ff', 'v': '#3fb950', 'r': '#f85149', 'i': '#d29922',
  'B': '#58a6ff', 'V': '#3fb950', 'R': '#f85149', 'I': '#d29922',
  'g': '#3fb950', 'u': '#bc8cff', 'z': '#8b949e', 'y': '#e6edf3',
};

fetch('/api/lightcurve-data/{{ run.run_id }}')
  .then(r => r.json())
  .then(data => {
    if (data.error || !data.data || data.data.length === 0) {
      document.getElementById('plotly-chart').innerHTML = '<p class="text-muted">No data available</p>';
      return;
    }
    renderPlotlyChart(data);
    renderDataTable(data);
  });

function renderPlotlyChart(data) {
  const traces = [];
  // Detect column names
  const cols = data.columns;
  const xCol = cols.find(c => c.match(/mjd|MJD|days/i)) || cols[0];
  const yCol = cols.find(c => c.match(/mag|flux/i)) || cols[1];
  const errCol = cols.find(c => c.match(/err|error|sigma/i));
  const bandCol = cols.find(c => c.match(/band|filter/i));

  for (const band of data.bands) {
    const points = data.data.filter(r => r[bandCol] === band);
    const trace = {
      x: points.map(r => r[xCol]),
      y: points.map(r => r[yCol]),
      mode: 'markers',
      type: 'scatter',
      name: band,
      marker: { color: BAND_COLORS[band] || '#8b949e', size: 6 },
    };
    if (errCol) {
      trace.error_y = {
        type: 'data',
        array: points.map(r => r[errCol]),
        visible: true,
        color: BAND_COLORS[band] || '#8b949e',
      };
    }
    traces.push(trace);
  }

  const isFlux = yCol.toLowerCase().includes('flux');
  const layout = {
    paper_bgcolor: '#0d1117',
    plot_bgcolor: '#161b22',
    font: { color: '#e6edf3', family: 'system-ui, sans-serif' },
    xaxis: {
      title: xCol,
      gridcolor: '#30363d',
      zerolinecolor: '#30363d',
    },
    yaxis: {
      title: yCol,
      autorange: isFlux ? true : 'reversed',  // magnitudes are inverted
      gridcolor: '#30363d',
      zerolinecolor: '#30363d',
    },
    legend: { orientation: 'h', y: -0.15 },
    margin: { t: 30, r: 20, b: 60, l: 60 },
    hovermode: 'closest',
  };

  Plotly.newPlot('plotly-chart', traces, layout, {
    responsive: true,
    displayModeBar: true,
    modeBarButtonsToRemove: ['lasso2d', 'select2d'],
  });
}

function renderDataTable(data) {
  if (!data.data.length) return;
  let html = '<table class="night-table"><thead><tr>';
  for (const col of data.columns) {
    html += '<th>' + col + '</th>';
  }
  html += '</tr></thead><tbody>';
  for (const row of data.data.slice(0, 200)) {  // limit to 200 rows
    html += '<tr>';
    for (const col of data.columns) {
      const val = row[col];
      const display = typeof val === 'number' ? val.toFixed(4) : val;
      html += '<td class="mono">' + display + '</td>';
    }
    html += '</tr>';
  }
  html += '</tbody></table>';
  if (data.data.length > 200) {
    html += '<p class="text-muted">Showing first 200 of ' + data.data.length + ' rows</p>';
  }
  document.getElementById('lc-table-container').innerHTML = html;
}
</script>
{% endif %}
```

**Step 6: Add analysis CSS**

```css
/* === Analysis Tab === */
.plot-container {
  text-align: center;
}

.output-image {
  max-width: 100%;
  border-radius: 8px;
  border: 1px solid var(--border);
  cursor: pointer;
  transition: transform 0.2s;
}

.output-image.expanded {
  transform: scale(1.5);
  position: relative;
  z-index: 10;
}

.plotly-container {
  min-height: 400px;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}

.table-scroll {
  max-height: 500px;
  overflow: auto;
}

.image-gallery {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 1rem;
}

.gallery-item {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.75rem;
  text-align: center;
}

.gallery-item img {
  max-width: 100%;
  border-radius: 4px;
  cursor: pointer;
}

.gallery-label {
  display: block;
  font-size: 0.8rem;
  color: var(--text-muted);
  margin-top: 0.5rem;
  font-family: var(--mono);
}
```

**Step 7: Verify analysis tab**

Run dashboard with a completed run that has lightcurve output. Click "Analysis" tab → should show static PNG, interactive Plotly chart with band toggling and zoom, and data table.

**Step 8: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/dashboard/
git commit -m "feat(dashboard): add analysis tab with interactive lightcurve charts"
```

---

## Task 5: Butler Data Tab

**Files:**
- Create: `packages/data_tools/src/obs_nickel_data_tools/dashboard/butler_query.py`
- Create: `packages/data_tools/src/obs_nickel_data_tools/dashboard/templates/tabs/data.html`
- Modify: `packages/data_tools/src/obs_nickel_data_tools/dashboard/app.py`
- Modify: `packages/data_tools/src/obs_nickel_data_tools/dashboard/static/style.css`

**Step 1: Create butler_query.py**

```python
"""Butler dataset queries for the dashboard.

Queries the LSST Butler to count datasets per night/band.
Requires the LSST stack to be available.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Dataset types we care about for monitoring
DATASET_TYPES = [
    "calexp",
    "initial_pvi",
    "goodSeeingDiff_differenceExp",
    "forced_diff_radec",
]

# Cache for Butler query results (keyed by repo path)
_cache: dict[str, dict] = {}


def query_butler_counts(
    run_id: str,
    logs_dir: Path,
) -> dict:
    """Query Butler for dataset counts grouped by night and band.

    Returns:
        {
            "available": bool,
            "error": str | None,
            "dataset_types": ["calexp", ...],
            "nights": {
                "20230519": {
                    "calexp": {"r": 5, "i": 3},
                    "initial_pvi": {"r": 5, "i": 3},
                    ...
                },
                ...
            }
        }
    """
    # Check cache
    if run_id in _cache:
        return _cache[run_id]

    # Find repo path from run_info.txt
    run_info_path = logs_dir / run_id / "run_info.txt"
    if not run_info_path.exists():
        return {"available": False, "error": "run_info.txt not found", "dataset_types": [], "nights": {}}

    repo_path = None
    for line in run_info_path.read_text().splitlines():
        if line.startswith("Repository:"):
            repo_path = line.split(":", 1)[1].strip()
            break

    if not repo_path or not Path(repo_path).exists():
        return {"available": False, "error": "Repository not found", "dataset_types": [], "nights": {}}

    # Try to query Butler using a Python script that runs in stack env
    # This avoids importing lsst.daf.butler directly (which needs the stack)
    query_script = _build_query_script(repo_path)

    try:
        result = subprocess.run(
            ["bash", "-c", query_script],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            logger.warning("Butler query failed: %s", result.stderr[:500])
            return {"available": False, "error": f"Butler query failed: {result.stderr[:200]}", "dataset_types": [], "nights": {}}

        data = json.loads(result.stdout)
        data["available"] = True
        data["error"] = None
        _cache[run_id] = data
        return data

    except subprocess.TimeoutExpired:
        return {"available": False, "error": "Butler query timed out (120s)", "dataset_types": [], "nights": {}}
    except (json.JSONDecodeError, Exception) as e:
        return {"available": False, "error": str(e), "dataset_types": [], "nights": {}}


def _build_query_script(repo_path: str) -> str:
    """Build a Python script that queries Butler and outputs JSON.

    This script will be run inside the LSST stack environment if available,
    or with the current Python otherwise.
    """
    dataset_types_str = json.dumps(DATASET_TYPES)
    return f'''
python3 -c "
import json, sys
try:
    from lsst.daf.butler import Butler
except ImportError:
    print(json.dumps({{'dataset_types': [], 'nights': {{}}}}))
    sys.exit(0)

repo = '{repo_path}'
try:
    butler = Butler(repo)
except Exception as e:
    print(json.dumps({{'dataset_types': [], 'nights': {{}}, 'error': str(e)}}))
    sys.exit(0)

dataset_types = {dataset_types_str}
nights = {{}}

for dt in dataset_types:
    try:
        refs = list(butler.registry.queryDatasets(dt))
        for ref in refs:
            did = ref.dataId
            night = str(did.get('day_obs', did.get('visit', '')))[:8]
            band = did.get('band', did.get('physical_filter', '?'))
            if night not in nights:
                nights[night] = {{}}
            if dt not in nights[night]:
                nights[night][dt] = {{}}
            nights[night][dt][band] = nights[night][dt].get(band, 0) + 1
    except Exception:
        pass

print(json.dumps({{'dataset_types': dataset_types, 'nights': nights}}))
"
'''
```

**Step 2: Add Butler API route to app.py**

```python
@app.get("/api/butler-counts/{run_id}", response_class=JSONResponse)
async def api_butler_counts(run_id: str):
    """Query Butler for dataset counts (on-demand, cached)."""
    from .butler_query import query_butler_counts
    data = query_butler_counts(run_id, logs_dir)
    return JSONResponse(data)
```

**Step 3: Create tabs/data.html**

```html
<div class="data-tab">
  <div class="detail-section">
    <h3>Butler Dataset Counts</h3>
    <p class="text-muted">Query the Butler repository for actual dataset counts per night and band. This may take a moment.</p>
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
</div>

<script>
document.body.addEventListener('htmx:afterSwap', function(evt) {
  if (evt.detail.target.id === 'butler-results') {
    try {
      const data = JSON.parse(evt.detail.target.textContent);
      evt.detail.target.innerHTML = renderButlerTable(data);
    } catch(e) {
      // Already rendered or error
    }
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
    // Abbreviate long names
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
      html += '<td>' + (parts.length ? parts.join(' ') : '<span class="text-muted">—</span>') + '</td>';
    }
    html += '</tr>';
  }
  html += '</tbody></table>';
  return html;
}
</script>
```

**Step 4: Add data tab CSS**

```css
/* === Data Tab === */
.action-btn {
  background: var(--accent);
  color: var(--bg);
  border: none;
  padding: 0.5rem 1rem;
  border-radius: 6px;
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.15s;
}

.action-btn:hover {
  opacity: 0.9;
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.spinner-inline {
  display: inline-block;
  width: 16px;
  height: 16px;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  vertical-align: middle;
  margin-left: 0.5rem;
}

.htmx-indicator {
  display: none;
}

.htmx-request .htmx-indicator {
  display: inline-block;
}

.butler-results {
  margin-top: 1rem;
}

.butler-table th {
  font-size: 0.8rem;
}

.band-count {
  display: inline-block;
  background: var(--bg-tertiary);
  padding: 0.1rem 0.4rem;
  border-radius: 3px;
  font-size: 0.8rem;
  font-family: var(--mono);
  margin: 0.1rem;
}
```

**Step 5: Verify data tab**

Run dashboard, click "Data" tab, click "Load Dataset Counts". If Butler is available, should show a table of dataset counts per night. If not, should show a graceful error message.

**Step 6: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/dashboard/
git commit -m "feat(dashboard): add Butler data tab with on-demand dataset counts"
```

---

## Task 6: Polish and Integration

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/dashboard/app.py` (ensure all routes wired)
- Modify: `packages/data_tools/src/obs_nickel_data_tools/dashboard/static/style.css` (responsive, cleanup)
- Modify: `packages/data_tools/src/obs_nickel_data_tools/dashboard/templates/run_list.html` (minor enhancements)

**Step 1: Add responsive breakpoints**

```css
@media (max-width: 900px) {
  .summary-cards {
    grid-template-columns: repeat(2, 1fr);
  }

  .log-browser {
    grid-template-columns: 1fr;
  }

  .log-tree-panel {
    max-height: 300px;
  }
}
```

**Step 2: Ensure SSE still works in overview tab**

The SSE connection is now inside the overview tab partial. When the user switches away from the overview tab and back, HTMX will re-establish the SSE connection because the `sse-connect` attribute is re-rendered. Verify this works by:
1. Watching a running pipeline in the overview tab
2. Switching to logs tab
3. Switching back to overview — SSE should reconnect

If SSE doesn't reconnect, move the SSE connection to the run_detail.html level (outside tabs) and use `hx-swap-oob` for cross-tab updates.

**Step 3: Add pipeline.log path to existing api_log route**

Ensure the existing `/api/log/{run_id}` route (used by SSE event generator for the log path) still works. The new `/api/log/{run_id}/{path:path}` route handles the general case; the old route should be kept as-is for SSE compatibility, or redirect:

```python
@app.get("/api/log/{run_id}", response_class=PlainTextResponse)
async def api_log(run_id: str):
    """Serve pipeline.log for backwards compatibility."""
    log_path = logs_dir / run_id / "pipeline.log"
    if not log_path.exists():
        return PlainTextResponse("", status_code=404)
    return PlainTextResponse(log_path.read_text(errors="replace"))
```

**Step 4: Final verification**

Run full pipeline, then launch dashboard:
```bash
nickel dashboard --no-browser --port 8787
```

Test all tabs:
1. Run list → click into a run
2. Overview tab: summary cards, night grid, live log
3. Logs tab: file tree, open logs, search
4. Analysis tab: PNG display, interactive chart, data table
5. Data tab: load Butler counts
6. Night drill-down: click a night, see exposures, view individual logs
7. Return to overview: SSE reconnects

**Step 5: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/dashboard/
git commit -m "feat(dashboard): polish, responsive layout, SSE integration fix"
```

---

## Summary of All New/Modified Files

### New Files
- `packages/data_tools/src/obs_nickel_data_tools/dashboard/analysis.py`
- `packages/data_tools/src/obs_nickel_data_tools/dashboard/butler_query.py`
- `packages/data_tools/src/obs_nickel_data_tools/dashboard/templates/tabs/overview.html`
- `packages/data_tools/src/obs_nickel_data_tools/dashboard/templates/tabs/logs.html`
- `packages/data_tools/src/obs_nickel_data_tools/dashboard/templates/tabs/analysis.html`
- `packages/data_tools/src/obs_nickel_data_tools/dashboard/templates/tabs/data.html`
- `packages/data_tools/src/obs_nickel_data_tools/dashboard/templates/night_detail.html`

### Modified Files
- `packages/data_tools/src/obs_nickel_data_tools/dashboard/app.py` — new routes for tabs, night detail, log files, analysis, Butler
- `packages/data_tools/src/obs_nickel_data_tools/dashboard/collector.py` — add `get_night_detail()`, `get_log_tree()`
- `packages/data_tools/src/obs_nickel_data_tools/dashboard/templates/base.html` — add Plotly.js CDN
- `packages/data_tools/src/obs_nickel_data_tools/dashboard/templates/run_detail.html` — restructure with tab navigation
- `packages/data_tools/src/obs_nickel_data_tools/dashboard/templates/partials/night_grid.html` — clickable night names
- `packages/data_tools/src/obs_nickel_data_tools/dashboard/static/style.css` — tabs, summary cards, log browser, analysis, data tab styles

### Unchanged
- `packages/data_tools/pyproject.toml` — no new Python dependencies needed
- `packages/data_tools/src/obs_nickel_data_tools/cli.py` — dashboard command works as-is
