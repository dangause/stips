# Lightcurve Configuration System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `lightcurve:` YAML config section and `LightcurveConfig` dataclass to control lightcurve data selection and display (y-axis mode, x-axis mode, distance modulus, explosion date).

**Architecture:** New `LightcurveConfig` dataclass in `core/lightcurve.py` parsed from a top-level `lightcurve:` YAML section (with backwards-compatible fallback to `options:` keys). The config flows through `run.py` orchestrator → `lightcurve.run()` → `extract_lightcurve.py` script args. Plotting helpers in `plotting.py` gain axis-mode-aware formatting. CLI gets matching flags.

**Tech Stack:** Python dataclasses, Click CLI, matplotlib, pandas, YAML

**IMPORTANT:** A pipeline is currently running. Do NOT modify any files under `scripts/config/` until all other tasks are complete, and do NOT modify any running pipeline code paths (calibs, science, dia, fphot). The lightcurve changes are additive and only affect the final extraction/plotting step.

---

### Task 1: Add LightcurveConfig dataclass to core/lightcurve.py

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/core/lightcurve.py:1-24`

**Step 1: Add the LightcurveConfig dataclass**

Add after the existing imports and before `LightcurveResult`:

```python
@dataclass
class LightcurveConfig:
    """Configuration for lightcurve extraction and plotting."""

    enabled: bool = True

    # Data selection
    dataset_type: str = "dia_source_unfiltered"
    min_snr: float = 3.0
    radius: float = 1.0
    band: str | None = None

    # Y-axis display
    y_axis: str = "apparent_mag"  # apparent_mag | absolute_mag | flux_nJy | flux_adu
    distance_modulus: float | None = None

    # X-axis display
    x_axis: str = "mjd"  # mjd | days_since_explosion
    explosion_mjd: float | None = None

    _VALID_Y_AXES = ("apparent_mag", "absolute_mag", "flux_nJy", "flux_adu")
    _VALID_X_AXES = ("mjd", "days_since_explosion")

    def validate(self):
        """Raise ValueError if config is inconsistent."""
        if self.y_axis not in self._VALID_Y_AXES:
            raise ValueError(
                f"Invalid y_axis '{self.y_axis}', must be one of: {self._VALID_Y_AXES}"
            )
        if self.x_axis not in self._VALID_X_AXES:
            raise ValueError(
                f"Invalid x_axis '{self.x_axis}', must be one of: {self._VALID_X_AXES}"
            )
        if self.y_axis == "absolute_mag" and self.distance_modulus is None:
            raise ValueError(
                "y_axis='absolute_mag' requires distance_modulus to be set"
            )
        if self.x_axis == "days_since_explosion" and self.explosion_mjd is None:
            raise ValueError(
                "x_axis='days_since_explosion' requires explosion_mjd to be set"
            )

    @classmethod
    def from_yaml(cls, lc_section: dict | None, options: dict | None = None) -> "LightcurveConfig":
        """Parse from YAML lightcurve: section with fallback to options: block.

        Args:
            lc_section: The 'lightcurve:' top-level YAML dict (may be None).
            options: The 'options:' YAML dict for backwards compat (may be None).

        Returns:
            Validated LightcurveConfig instance.
        """
        lc = lc_section or {}
        opts = options or {}

        config = cls(
            enabled=lc.get("enabled", opts.get("lightcurve", True)),
            dataset_type=lc.get(
                "dataset_type",
                opts.get("lightcurve_dataset_type", "dia_source_unfiltered"),
            ),
            min_snr=float(lc.get("min_snr", opts.get("lightcurve_min_snr", 3.0))),
            radius=float(lc.get("radius", 1.0)),
            band=lc.get("band"),
            y_axis=lc.get("y_axis", "apparent_mag"),
            distance_modulus=(
                float(lc["distance_modulus"])
                if lc.get("distance_modulus") is not None
                else None
            ),
            x_axis=lc.get("x_axis", "mjd"),
            explosion_mjd=(
                float(lc["explosion_mjd"])
                if lc.get("explosion_mjd") is not None
                else None
            ),
        )
        config.validate()
        return config
```

**Step 2: Update `run()` to accept LightcurveConfig**

Change the `run()` function signature and body to accept an optional `LightcurveConfig` and pass its display parameters through to the extraction script as new CLI args.

Current signature (line 26-39):
```python
def run(
    ra: float,
    dec: float,
    collections: str,
    config: Config,
    *,
    radius: float = 1.0,
    min_snr: float = 3.0,
    band: str | None = None,
    name: str | None = None,
    output: Path | None = None,
    plot: bool = True,
    dataset_type: str = "dia_source_unfiltered",
    log_file: Path | None = None,
) -> LightcurveResult:
```

New signature:
```python
def run(
    ra: float,
    dec: float,
    collections: str,
    config: Config,
    *,
    radius: float = 1.0,
    min_snr: float = 3.0,
    band: str | None = None,
    name: str | None = None,
    output: Path | None = None,
    plot: bool = True,
    dataset_type: str = "dia_source_unfiltered",
    log_file: Path | None = None,
    lc_config: LightcurveConfig | None = None,
) -> LightcurveResult:
```

In the args-building section (after line 109, before `if plot:`), add:

```python
    # Display configuration (new lightcurve config options)
    if lc_config:
        args.extend(["--y-axis", lc_config.y_axis])
        args.extend(["--x-axis", lc_config.x_axis])
        if lc_config.explosion_mjd is not None:
            args.extend(["--explosion-mjd", str(lc_config.explosion_mjd)])
        if lc_config.distance_modulus is not None:
            args.extend(["--distance-modulus", str(lc_config.distance_modulus)])
```

**Step 3: Verify no syntax errors**

Run: `python -c "from obs_nickel_data_tools.core.lightcurve import LightcurveConfig; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/core/lightcurve.py
git commit -m "feat: add LightcurveConfig dataclass with YAML parsing and validation"
```

---

### Task 2: Add new CLI args to extract_lightcurve.py

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/pipeline_tools/extract_lightcurve.py:38-100` (parse_args)

**Step 1: Add new argparse arguments**

After the `--name` argument (line 92), add:

```python
    parser.add_argument(
        "--y-axis",
        default="apparent_mag",
        choices=["apparent_mag", "absolute_mag", "flux_nJy", "flux_adu"],
        help="Y-axis display mode (default: apparent_mag)",
    )
    parser.add_argument(
        "--x-axis",
        default="mjd",
        choices=["mjd", "days_since_explosion"],
        help="X-axis display mode (default: mjd)",
    )
    parser.add_argument(
        "--explosion-mjd",
        type=float,
        default=None,
        help="Explosion MJD (required when --x-axis=days_since_explosion)",
    )
    parser.add_argument(
        "--distance-modulus",
        type=float,
        default=None,
        help="Distance modulus (required when --y-axis=absolute_mag)",
    )
```

Add validation after line 98 (`if args.ra is not None and args.dec is None:`):

```python
    if args.x_axis == "days_since_explosion" and args.explosion_mjd is None:
        parser.error("--explosion-mjd required when using --x-axis=days_since_explosion")
    if args.y_axis == "absolute_mag" and args.distance_modulus is None:
        parser.error("--distance-modulus required when using --y-axis=absolute_mag")
```

**Step 2: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/pipeline_tools/extract_lightcurve.py
git commit -m "feat: add y-axis/x-axis display args to extract_lightcurve.py"
```

---

### Task 3: Implement y-axis and x-axis logic in extract_lightcurve.py

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/pipeline_tools/extract_lightcurve.py`

**Step 1: Add days_since_explosion column to DataFrame**

After the DataFrame is created and sorted (line 564-565: `df = pd.DataFrame(all_detections); df = df.sort_values("mjd")`), add:

```python
    # Add days_since_explosion column if explosion_mjd is provided
    if args.explosion_mjd is not None:
        df["days_since_explosion"] = df["mjd"] - args.explosion_mjd
```

**Step 2: Add absolute magnitude column**

After the days_since_explosion block, add:

```python
    # Add absolute magnitude column if distance_modulus is provided
    if args.distance_modulus is not None:
        df["abs_mag"] = df["mag"] - args.distance_modulus
        df["abs_mag_err"] = df["mag_err"]  # Error propagation: same error
```

**Step 3: Update the summary output**

In the summary section (lines 567-597), after printing MJD range, add days range if applicable:

```python
    if "days_since_explosion" in df.columns:
        print(
            f"Days since explosion: {df['days_since_explosion'].min():.1f} - "
            f"{df['days_since_explosion'].max():.1f}"
        )
```

**Step 4: Update plot_light_curves to accept display config**

Change the `plot_light_curves` function signature from:
```python
def plot_light_curves(df: pd.DataFrame, output_path: Path, target_name: str):
```
to:
```python
def plot_light_curves(
    df: pd.DataFrame,
    output_path: Path,
    target_name: str,
    y_axis: str = "apparent_mag",
    x_axis: str = "mjd",
):
```

**Step 5: Determine x/y column names and labels based on config**

At the top of `plot_light_curves`, after the import block, add logic to determine which columns and labels to use:

```python
    # Determine which columns to plot based on display config
    if y_axis == "apparent_mag":
        y_col, y_err_col = "mag", "mag_err"
        ylabel = "Apparent Magnitude (AB)"
        invert_y = True
    elif y_axis == "absolute_mag":
        y_col, y_err_col = "abs_mag", "abs_mag_err"
        ylabel = "Absolute Magnitude"
        invert_y = True
    elif y_axis == "flux_nJy":
        y_col, y_err_col = "flux_nJy", "flux_nJy_err"
        ylabel = "Flux (nJy)"
        invert_y = False
    elif y_axis == "flux_adu":
        y_col, y_err_col = "flux", "flux_err"
        ylabel = "Flux (ADU)"
        invert_y = False
    else:
        y_col, y_err_col = "mag", "mag_err"
        ylabel = "Apparent Magnitude (AB)"
        invert_y = True

    if x_axis == "days_since_explosion" and "days_since_explosion" in df.columns:
        x_col = "days_since_explosion"
        xlabel = "Days Since Explosion"
    else:
        x_col = "mjd"
        xlabel = "Modified Julian Date (MJD)"
```

**Step 6: Update both plot code paths to use dynamic columns**

In the publication-style path, replace hardcoded `band_data["mjd"]`, `band_data["mag"]`, `band_data["mag_err"]` with:
```python
        for band in bands:
            band_data = df[df["band"] == band]
            plot_lightcurve_band(
                ax,
                band_data[x_col].values,
                band_data[y_col].values,
                band_data[y_err_col].values,
                band,
                count=len(band_data),
            )

        format_lightcurve_axes(ax, ylabel=ylabel, xlabel=xlabel, invert_y=invert_y)
```

In the fallback path, replace similarly:
```python
            ax.errorbar(
                band_data[x_col],
                band_data[y_col],
                yerr=band_data[y_err_col],
                ...
            )

        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ...
        if invert_y:
            ax.invert_yaxis()
```

Replace the `_clamp_ylim` calls to use the dynamic y_col:
```python
        # Clamp ylim for magnitude modes only
        if invert_y:
            _clamp_ylim(ax, df, y_col=y_col)
```

Update `_clamp_ylim` signature to accept `y_col`:
```python
def _clamp_ylim(ax, df: pd.DataFrame, y_col: str = "mag"):
    finite_vals = df[y_col][np.isfinite(df[y_col])]
    ...
```

**Step 7: Update the main() call to pass display config to plotting**

Change the plot call at line 609 from:
```python
        plot_light_curves(df, output_path, plot_title)
```
to:
```python
        plot_light_curves(
            df, output_path, plot_title,
            y_axis=args.y_axis, x_axis=args.x_axis,
        )
```

**Step 8: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/pipeline_tools/extract_lightcurve.py
git commit -m "feat: implement y-axis/x-axis display modes in lightcurve extraction"
```

---

### Task 4: Wire LightcurveConfig into run.py orchestrator

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/core/run.py:343-490` (RunConfig) and `977-1028` (_run_lightcurve_step)

**Step 1: Add lc_config field to RunConfig**

In the `RunConfig` dataclass (line 343), replace the three lightcurve fields (lines 370-372):

```python
    lightcurve: bool = True
    lightcurve_dataset_type: str = "dia_source_unfiltered"
    lightcurve_min_snr: float = 3.0
```

with a single `LightcurveConfig` field:

```python
    lc_config: "LightcurveConfig" = field(default_factory=lambda: LightcurveConfig())
```

Add the import at the top of the file (inside the `TYPE_CHECKING` block, line 78-80):

```python
if TYPE_CHECKING:
    from obs_nickel_data_tools.core.config import Config
    from obs_nickel_data_tools.core.lightcurve import LightcurveConfig
    from obs_nickel_data_tools.core.science import ScienceConfig
```

**Step 2: Update RunConfig.from_yaml() to parse lightcurve section**

In `from_yaml()`, replace the three lightcurve lines (476-480):

```python
            lightcurve=options.get("lightcurve", True),
            lightcurve_dataset_type=options.get(
                "lightcurve_dataset_type", "dia_source_unfiltered"
            ),
            lightcurve_min_snr=float(options.get("lightcurve_min_snr", 3.0)),
```

with:

```python
            lc_config=LightcurveConfig.from_yaml(
                data.get("lightcurve"), options
            ),
```

Add the non-TYPE_CHECKING import inside `from_yaml`:
```python
        from obs_nickel_data_tools.core.lightcurve import LightcurveConfig
```

**Step 3: Update _run_lightcurve_step to use lc_config**

In `_run_lightcurve_step` (line 977-1028), replace references:
- `run_cfg.lightcurve_dataset_type` → `run_cfg.lc_config.dataset_type`
- `run_cfg.lightcurve_min_snr` → `run_cfg.lc_config.min_snr`

And pass `lc_config` to `lightcurve.run()`:

```python
        lc_result = lightcurve.run(
            ra=run_cfg.ra,
            dec=run_cfg.dec,
            collections=collections,
            config=config,
            name=run_cfg.object_name,
            plot=True,
            min_snr=run_cfg.lc_config.min_snr,
            dataset_type=run_cfg.lc_config.dataset_type,
            log_file=lc_log,
            lc_config=run_cfg.lc_config,
        )
```

**Step 4: Update the lightcurve gate in run()**

In the main `run()` function (line 1283), replace:
```python
    if run_cfg.lightcurve:
```
with:
```python
    if run_cfg.lc_config.enabled:
```

**Step 5: Verify no syntax errors**

Run: `python -c "from obs_nickel_data_tools.core.run import RunConfig; print('OK')"`
Expected: `OK`

**Step 6: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/core/run.py
git commit -m "feat: wire LightcurveConfig into pipeline orchestrator"
```

---

### Task 5: Add new CLI flags to nickel lightcurve command

**Files:**
- Modify: `packages/data_tools/src/obs_nickel_data_tools/cli.py:846-925`

**Step 1: Add new Click options**

After the `--dataset-type` option (line 866), add:

```python
@click.option(
    "--y-axis",
    type=click.Choice(["apparent_mag", "absolute_mag", "flux_nJy", "flux_adu"]),
    default="apparent_mag",
    help="Y-axis display mode (default: apparent_mag)",
)
@click.option(
    "--x-axis",
    type=click.Choice(["mjd", "days_since_explosion"]),
    default="mjd",
    help="X-axis display mode (default: mjd)",
)
@click.option(
    "--explosion-mjd",
    type=float,
    default=None,
    help="Explosion MJD (required with --x-axis=days_since_explosion)",
)
@click.option(
    "--distance-modulus",
    type=float,
    default=None,
    help="Distance modulus (required with --y-axis=absolute_mag)",
)
```

**Step 2: Update the function signature**

Add the new parameters to the `lightcurve()` function:

```python
def lightcurve(
    ctx: click.Context,
    ra: float,
    dec: float,
    collections: str,
    radius: float,
    min_snr: float,
    band: str | None,
    name: str | None,
    output: Path | None,
    plot: bool,
    dataset_type: str,
    y_axis: str,
    x_axis: str,
    explosion_mjd: float | None,
    distance_modulus: float | None,
) -> None:
```

**Step 3: Add validation and construct LightcurveConfig**

At the start of the function body, add:

```python
    # Validate dependent options
    if x_axis == "days_since_explosion" and explosion_mjd is None:
        raise click.UsageError("--explosion-mjd required with --x-axis=days_since_explosion")
    if y_axis == "absolute_mag" and distance_modulus is None:
        raise click.UsageError("--distance-modulus required with --y-axis=absolute_mag")

    from obs_nickel_data_tools.core.lightcurve import LightcurveConfig

    lc_config = LightcurveConfig(
        dataset_type=dataset_type,
        min_snr=min_snr,
        radius=radius,
        band=band,
        y_axis=y_axis,
        x_axis=x_axis,
        explosion_mjd=explosion_mjd,
        distance_modulus=distance_modulus,
    )
```

**Step 4: Pass lc_config to lightcurve.run()**

Update the `lc_module.run()` call to include `lc_config=lc_config`.

**Step 5: Commit**

```bash
git add packages/data_tools/src/obs_nickel_data_tools/cli.py
git commit -m "feat: add --y-axis, --x-axis, --explosion-mjd, --distance-modulus CLI flags"
```

---

### Task 6: Update YAML configs to use new lightcurve: section

**Files:**
- Modify: `scripts/config/2023ixf/pipeline_ps1_template.yaml:92-104`
- Modify: `scripts/config/2023ixf/pipeline_nickel_template.yaml:102-114`

**IMPORTANT:** Only do this task AFTER confirming the pipeline is no longer running. The user noted a PS1 pipe is currently running.

**Step 1: Update pipeline_ps1_template.yaml**

Replace the lightcurve keys in `options:` (lines 100-102):
```yaml
  lightcurve: true
  lightcurve_dataset_type: forced_phot_diffim_radec
  lightcurve_min_snr: 0
```

Remove those three lines from `options:` and add a new top-level section after `options:`:

```yaml
# Lightcurve configuration
lightcurve:
  enabled: true
  dataset_type: forced_phot_diffim_radec
  min_snr: 0
  y_axis: apparent_mag
  x_axis: days_since_explosion
  explosion_mjd: 60082.75       # 2023-05-19 (~discovery date)
```

**Step 2: Update pipeline_nickel_template.yaml**

Same pattern: remove lightcurve keys from `options:` and add:

```yaml
# Lightcurve configuration
lightcurve:
  enabled: true
  dataset_type: forced_phot_diffim_radec
  min_snr: 0
  y_axis: apparent_mag
  x_axis: days_since_explosion
  explosion_mjd: 60082.75       # 2023-05-19 (~discovery date)
```

**Step 3: Commit**

```bash
git add scripts/config/2023ixf/pipeline_ps1_template.yaml scripts/config/2023ixf/pipeline_nickel_template.yaml
git commit -m "feat: migrate 2023ixf configs to new lightcurve: section"
```

---

### Task 7: Verify end-to-end with dry run

**Step 1: Test YAML parsing with dry run**

Run: `nickel run scripts/config/2023ixf/pipeline_nickel_template.yaml --dry-run`

Expected: No errors. Should print pipeline plan including "Extracting lightcurve..." step.

**Step 2: Test CLI flags**

Run: `nickel lightcurve --help`

Expected: Should show new options `--y-axis`, `--x-axis`, `--explosion-mjd`, `--distance-modulus`.

**Step 3: Test validation**

Run: `nickel lightcurve --ra 210.91 --dec 54.32 --collections "Nickel/runs/*/diff/*/run" --y-axis absolute_mag`

Expected: Error message about `--distance-modulus required`.

Run: `nickel lightcurve --ra 210.91 --dec 54.32 --collections "Nickel/runs/*/diff/*/run" --x-axis days_since_explosion`

Expected: Error message about `--explosion-mjd required`.

**Step 4: Commit (if any fixes needed)**

```bash
git add -u
git commit -m "fix: address issues found during end-to-end verification"
```
