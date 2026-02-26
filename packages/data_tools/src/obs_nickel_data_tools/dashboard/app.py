"""FastAPI application for the NPS pipeline dashboard."""

from __future__ import annotations

import asyncio
import html
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sse_starlette.sse import EventSourceResponse

from obs_nickel_data_tools.dashboard.collector import (
    PHASE_ORDER,
    LogTailer,
    Phase,
    RunInfo,
    discover_runs,
    get_run,
    get_slurm_jobs,
)

_HERE = Path(__file__).parent


def create_app(logs_dir: Path) -> FastAPI:
    """Create the FastAPI dashboard application.

    Args:
        logs_dir: Path to the logs directory to monitor.

    Returns:
        Configured FastAPI application.
    """
    app = FastAPI(title="NPS Dashboard")

    # Mount static files
    app.mount("/static", StaticFiles(directory=_HERE / "static"), name="static")

    # Jinja2 templates
    templates = Jinja2Templates(directory=_HERE / "templates")

    def _phase_index(run: RunInfo, phase: Phase) -> int:
        """Return -1 if phase is complete, 0 if current, 1 if pending."""
        current_idx = PHASE_ORDER.index(run.current_phase)
        phase_idx = PHASE_ORDER.index(phase)
        if phase_idx < current_idx:
            return -1  # done
        elif phase_idx == current_idx:
            return 0  # active
        return 1  # pending

    # Register template globals
    templates.env.globals["phase_index"] = _phase_index
    templates.env.globals["phases"] = [p for p in Phase if p != Phase.COMPLETE]

    # ── Routes ────────────────────────────────────────────────────────

    @app.get("/", response_class=HTMLResponse)
    async def run_list(request: Request) -> HTMLResponse:
        """Show all pipeline runs."""
        runs = discover_runs(logs_dir)
        return templates.TemplateResponse(
            "run_list.html",
            {"request": request, "runs": runs, "logs_dir": str(logs_dir)},
        )

    @app.get("/run/{run_id}", response_class=HTMLResponse)
    async def run_detail(request: Request, run_id: str) -> HTMLResponse:
        """Show detail view for a single run."""
        run = get_run(logs_dir, run_id)
        if run is None:
            return HTMLResponse(
                content="<h1>Run not found</h1><a href='/'>Back</a>",
                status_code=404,
            )
        return templates.TemplateResponse(
            "run_detail.html",
            {"request": request, "run": run},
        )

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

        context: dict = {"request": request, "run": info}

        if tab_name == "overview":
            log_path = logs_dir / run_id / "pipeline.log"
            initial_log = ""
            if log_path.exists():
                try:
                    lines = log_path.read_text().splitlines()
                    initial_log = "\n".join(lines[-200:])
                except OSError:
                    initial_log = "[Could not read pipeline.log]"
            context["initial_log"] = initial_log

        if tab_name == "analysis":
            from .analysis import find_lightcurve_files, find_output_images

            context["lc_files"] = find_lightcurve_files(logs_dir, run_id)
            context["output_images"] = find_output_images(logs_dir, run_id)

        if tab_name == "logs":
            from .collector import get_log_tree

            context["log_tree"] = get_log_tree(logs_dir, run_id)

        return templates.TemplateResponse(template_name, context)

    @app.get("/run/{run_id}/night/{night}", response_class=HTMLResponse)
    async def night_detail(request: Request, run_id: str, night: str):
        """Per-night drill-down showing per-exposure status."""
        from .collector import get_night_detail

        info = get_run(logs_dir, run_id)
        if info is None:
            return HTMLResponse("<p>Run not found</p>", status_code=404)
        detail = get_night_detail(logs_dir, run_id, night)
        return templates.TemplateResponse(
            "night_detail.html",
            {
                "request": request,
                "run": info,
                "night": night,
                "detail": detail,
            },
        )

    @app.get("/api/log/{run_id}", response_class=PlainTextResponse)
    async def api_log(run_id: str) -> PlainTextResponse:
        """Return raw pipeline.log content."""
        pipeline_log = logs_dir / run_id / "pipeline.log"
        if not pipeline_log.exists():
            return PlainTextResponse("", status_code=404)
        try:
            with open(pipeline_log) as f:
                return PlainTextResponse(f.read())
        except OSError:
            return PlainTextResponse("", status_code=500)

    @app.get("/api/log/{run_id}/{path:path}", response_class=PlainTextResponse)
    async def api_log_file(run_id: str, path: str):
        """Serve any log file from a run directory."""
        log_file = logs_dir / run_id / path
        try:
            log_file.resolve().relative_to((logs_dir / run_id).resolve())
        except ValueError:
            return PlainTextResponse("Access denied", status_code=403)
        if not log_file.exists():
            return PlainTextResponse("Log not found", status_code=404)
        content = log_file.read_text(errors="replace")
        return PlainTextResponse(content)

    @app.get("/api/log-tree/{run_id}", response_class=JSONResponse)
    async def api_log_tree(run_id: str):
        """Return the log directory tree as JSON."""
        from .collector import get_log_tree

        tree = get_log_tree(logs_dir, run_id)
        return JSONResponse(tree)

    @app.get("/api/lightcurve-data/{run_id}", response_class=JSONResponse)
    async def api_lightcurve_data(run_id: str):
        """Return lightcurve CSV data as JSON for Plotly rendering."""
        from .analysis import find_lightcurve_files, parse_lightcurve_csv

        lc = find_lightcurve_files(logs_dir, run_id)
        if not lc.get("csv_path"):
            return JSONResponse(
                {"error": "No lightcurve CSV found", "data": [], "bands": []}
            )
        data = parse_lightcurve_csv(lc["csv_path"])
        return JSONResponse(data)

    @app.get("/api/image/{run_id}")
    async def api_image(run_id: str, path: str):
        """Serve an output image file."""
        from fastapi.responses import FileResponse

        img_path = Path(path)
        if not img_path.exists() or img_path.suffix not in (".png", ".jpg", ".jpeg"):
            return PlainTextResponse("Image not found", status_code=404)
        return FileResponse(img_path, media_type="image/png")

    @app.get("/api/butler-counts/{run_id}", response_class=JSONResponse)
    async def api_butler_counts(run_id: str):
        """Query Butler for dataset counts (on-demand, cached)."""
        from .butler_query import query_butler_counts

        data = query_butler_counts(run_id, logs_dir)
        return JSONResponse(data)

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

    @app.get("/api/events/{run_id}")
    async def api_events(run_id: str) -> EventSourceResponse:
        """SSE stream for live run updates."""
        return EventSourceResponse(
            _event_generator(logs_dir, run_id),
            media_type="text/event-stream",
        )

    return app


def _colorize_log_line(line: str) -> str:
    """Add color span based on log level."""
    escaped = html.escape(line.rstrip())
    if "[ERROR]" in line:
        return f'<span style="color:#f85149">{escaped}</span>\n'
    if "[WARNING]" in line:
        return f'<span style="color:#d29922">{escaped}</span>\n'
    if "[DEBUG]" in line:
        return f'<span style="color:#8b949e">{escaped}</span>\n'
    return escaped + "\n"


async def _event_generator(
    logs_dir: Path, run_id: str
) -> AsyncGenerator[dict[str, str], None]:
    """Generate SSE events for a running pipeline.

    Emits:
    - log-line: New log content (colorized HTML)
    - night-update: Updated night grid HTML
    - bps-update: Updated BPS panel HTML
    """
    pipeline_log = logs_dir / run_id / "pipeline.log"
    tailer = LogTailer(pipeline_log)
    # Start from current end so we don't re-send initial content
    tailer.read_tail(0)

    poll_count = 0
    while True:
        await asyncio.sleep(2)

        # Check if run is still active
        summary = logs_dir / run_id / "summary.txt"
        run_complete = summary.exists()

        # Send new log lines
        new_text = tailer.read_new()
        if new_text:
            colorized = "".join(
                _colorize_log_line(line) for line in new_text.splitlines()
            )
            yield {"event": "log-line", "data": colorized}

        # Every 5th poll (~10s), send full night grid update
        poll_count += 1
        if poll_count % 5 == 0:
            run = get_run(logs_dir, run_id)
            if run is not None:
                night_html = _render_night_grid(run)
                yield {"event": "night-update", "data": night_html}

                # BPS update if applicable
                if run.is_bps:
                    jobs = get_slurm_jobs()
                    bps_html = _render_bps_panel(jobs)
                    yield {"event": "bps-update", "data": bps_html}

        if run_complete:
            # Send final update and close
            run = get_run(logs_dir, run_id)
            if run is not None:
                night_html = _render_night_grid(run)
                yield {"event": "night-update", "data": night_html}
            break


def _render_night_grid(run: RunInfo) -> str:
    """Render the night grid table as HTML string."""
    if not run.nights:
        return '<p class="empty-state">No night data found</p>'

    bands = run.bands or ["r", "i"]
    rows = []
    for ns in run.nights:
        cells = [
            f'<td class="mono"><a href="/run/{run.run_id}/night/{ns.night}" class="night-link">{html.escape(ns.night)}</a></td>',
            f'<td><span class="cell-status {ns.calibs}">{ns.calibs}</span></td>',
            f'<td><span class="cell-status {ns.science}">{ns.science}</span></td>',
        ]
        for band in bands:
            st = ns.dia.get(band, "pending")
            cells.append(f'<td><span class="cell-status {st}">{st}</span></td>')
        for band in bands:
            st = ns.fphot.get(band, "pending")
            cells.append(f'<td><span class="cell-status {st}">{st}</span></td>')
        rows.append(f'<tr>{"".join(cells)}</tr>')

    headers = ["Night", "Calibs", "Science"]
    headers.extend(f"DIA({b})" for b in bands)
    headers.extend(f"FPhot({b})" for b in bands)
    th = "".join(f"<th>{h}</th>" for h in headers)

    return (
        f'<table class="night-table"><thead><tr>{th}</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>'
    )


def _render_bps_panel(jobs: list[dict[str, str]]) -> str:
    """Render the BPS/Slurm jobs table as HTML string."""
    if not jobs:
        return '<p class="empty-state">No active Slurm jobs</p>'

    rows = []
    for job in jobs:
        state_cls = job.get("state", "").lower()
        rows.append(
            f"<tr>"
            f'<td class="mono">{html.escape(job.get("job_id", ""))}</td>'
            f'<td>{html.escape(job.get("name", ""))}</td>'
            f'<td><span class="slurm-state {state_cls}">{html.escape(job.get("state", ""))}</span></td>'
            f'<td>{html.escape(job.get("time", ""))}</td>'
            f'<td>{html.escape(job.get("nodes", ""))}</td>'
            f"</tr>"
        )

    return (
        '<table class="slurm-table">'
        "<thead><tr><th>Job ID</th><th>Name</th><th>State</th><th>Time</th><th>Nodes</th></tr></thead>"
        f'<tbody>{"".join(rows)}</tbody></table>'
    )
