# Logging System for `stips run`

## Overview

The `stips run` command implements comprehensive logging that captures all pipeline steps in both individual step logs and a unified pipeline log file.

## Architecture

### Log Directory Structure

When you run `stips -c config.yaml run`, all logs are stored under `logs/RUN_ID/` in the monorepo root, organized by pipeline step:

```
logs/
└── 20260211_143022_12345/          # RUN_ID: timestamp_pid
    ├── run_info.txt                # Run metadata
    ├── pipeline.log                # Unified log for all Python code
    ├── summary.txt                 # Final run summary
    ├── bootstrap/
    │   └── bootstrap.log           # Repository initialization
    ├── templates/
    │   ├── ps1_template_r.log      # PS1 template for r-band
    │   ├── ps1_template_i.log      # PS1 template for i-band
    │   └── coadd_template_r.log    # Coadd template for r-band (if used)
    ├── calibs_template/            # Template night calibrations (for coadd templates)
    │   ├── 20230101.log
    │   └── 20230102.log
    ├── science_template/           # Template night science (for coadd templates)
    │   ├── 20230101.log
    │   └── 20230102.log
    ├── calibs/                     # Nightly calibrations
    │   ├── 20230519.log
    │   ├── 20230521.log
    │   └── 20230523.log
    ├── science/                    # Science processing per night
    │   ├── 20230519.log
    │   ├── 20230521.log
    │   └── 20230523.log
    ├── dia/                        # Difference imaging per night/band
    │   ├── 20230519_r.log
    │   ├── 20230519_i.log
    │   ├── 20230521_r.log
    │   └── 20230521_i.log
    ├── fphot/                      # Forced photometry per night
    │   ├── 20230519.log
    │   ├── 20230521.log
    │   └── 20230523.log
    └── lightcurve/                 # Lightcurve extraction
        ├── forced_phot.log         # From forced photometry
        └── dia_sources.log         # From DIA sources
```

### Unified Logging

- **`pipeline.log`**: Contains all Python-level logs from the orchestrator and core modules
- **Step logs**: Each step (calibs, science, dia, etc.) gets its own log file containing:
  - LSST pipetask output (qgraph generation, quantum execution)
  - Butler command output (ingest, certify, collection management)
  - All subprocess stdout/stderr

## LSST Pipeline Logging Options

The system now properly utilizes LSST's built-in logging capabilities:

### Pipetask Logging

All `pipetask` commands are run with:
- `--log-file <path>`: Writes LSST logs to the step-specific file (appends if exists)
- `--log-level INFO`: Sets logging threshold (CRITICAL|ERROR|WARNING|INFO|VERBOSE|DEBUG|TRACE)
- `--long-log`: Uses detailed log format with timestamps and component names

### Butler Logging

All `butler` commands are run with:
- `--log-file <path>`: Writes butler logs to the step-specific file (appends if exists)
- `--log-level INFO`: Sets logging threshold
- `--long-log`: Uses detailed log format

### Example Log Entry

```
2026-02-11T14:30:22.123Z INFO  lsst.pipe.tasks.calibrate Processing CCD 0
2026-02-11T14:30:23.456Z INFO  lsst.meas.algorithms.psf Fitting PSF with 234 stars
```

## Implementation Details

### Core Changes

1. **`stack.py`** - Enhanced `run_pipetask()` and `run_butler()`:
   ```python
   def run_pipetask(
       args: list[str],
       config: Config,
       *,
       capture_output: bool = False,
       check: bool = True,
       log_file: Path | None = None,      # NEW
       log_level: str = "INFO",            # NEW
   ) -> subprocess.CompletedProcess:
   ```

2. **`run.py`** - Pipeline orchestrator:
   - `_setup_run_logging()`: Creates log directory, sets `RUN_LOG_DIR` env var
   - `_get_step_log_file()`: Generates step-specific log paths
   - Passes log files to each pipeline step

3. **All pipeline modules** - Updated to accept `log_file` parameter:
   - `bootstrap.py`
   - `calibs.py`
   - `science.py`
   - `dia.py`
   - `fphot.py`
   - `coadd.py`
   - `ps1_template.py`
   - `lightcurve.py`

### Environment Variables

- **`RUN_ID`**: Unique run identifier (timestamp_pid), inherited by shell scripts
- **`RUN_LOG_DIR`**: Path to log directory, used by `_get_step_log_file()`

## Usage

### Running the Pipeline

```bash
stips -c scripts/config/2023ixf/pipeline_ps1_template.yaml run
```

Output shows log location:
```
[INFO] Logs: /path/to/stips/logs/20260211_143022_12345
[INFO] Pipeline run for 2023ixf
...
✓ Pipeline complete
  Logs: /path/to/stips/logs/20260211_143022_12345
```

### Inspecting Logs

View the unified pipeline log:
```bash
less logs/20260211_143022_12345/pipeline.log
```

View a specific step for a night:
```bash
less logs/20260211_143022_12345/calibs/20230519.log
less logs/20260211_143022_12345/science/20230519.log
```

View DIA logs for a specific night and band:
```bash
less logs/20260211_143022_12345/dia/20230519_r.log
less logs/20260211_143022_12345/dia/20230519_i.log
```

View all logs for a specific step:
```bash
ls -lh logs/20260211_143022_12345/calibs/
ls -lh logs/20260211_143022_12345/science/
```

View LSST quantum graph details for a specific night:
```bash
grep "qgraph" logs/20260211_143022_12345/science/20230519.log
```

Check for failures across all steps:
```bash
grep -r "ERROR" logs/20260211_143022_12345/
```

Check failures in a specific step:
```bash
grep "ERROR" logs/20260211_143022_12345/dia/*.log
```

### Log Levels

To enable more verbose LSST logging, you can modify the `log_level` parameter in the code:

```python
# In core modules, change default from "INFO" to "VERBOSE" or "DEBUG"
run_pipetask(..., log_file=log_file, log_level="VERBOSE")
```

Common levels:
- **INFO**: Standard pipeline progress messages (default)
- **VERBOSE**: Detailed processing information
- **DEBUG**: Full debugging output
- **TRACE**: Maximum verbosity for troubleshooting

## Log File Rotation

Log files are created fresh for each run. Old runs are preserved in the `logs/` directory with unique RUN_IDs. To clean old logs:

```bash
# Keep only logs from last 7 days
find logs/ -name "2026*" -type d -mtime +7 -exec rm -rf {} +
```

## Parallel Execution and Log Ordering

### Understanding Parallel Logging

When using parallel jobs (`-j 8`), multiple LSST workers write to the same log file simultaneously. The logging system handles this well:

1. **Timestamps are preserved**: Each log entry includes a precise timestamp
2. **Entries are mostly ordered**: Due to LSST's logging implementation, entries are generally chronological
3. **Minor interleaving possible**: Occasionally, entries may appear slightly out of order

### Log Format with Timestamps

LSST `--long-log` format includes ISO 8601 timestamps:
```
INFO 2026-02-12T09:13:38.146-08:00 lsst.pipe.base ()(executor.py:826) - Message
```

This format allows:
- Easy chronological reading
- Precise timing analysis
- Post-processing if needed

### Sorting Logs (If Needed)

If you need perfectly chronological logs, use the sort utility:

```bash
# Sort a log file in place
python scripts/utilities/sort_lsst_log.py logs/RUN_ID/science/20230519.log

# Sort to a new file
python scripts/utilities/sort_lsst_log.py logs/RUN_ID/science/20230519.log sorted.log
```

The script:
- Preserves multi-line log entries
- Sorts by ISO 8601 timestamps
- Handles continuation lines correctly

### Reducing Interleaving

To minimize log interleaving:

1. **Use fewer jobs** for critical runs:
   ```bash
   # Edit run YAML:
   options:
     jobs: 1  # Serial execution, perfect ordering
   ```

2. **Post-process logs** after completion using the sort utility

3. **Trust timestamps** - the `--long-log` format makes it easy to follow execution order

## Organizing Logs by Quantum/Detector

When using parallel execution (`-j > 1`), multiple workers process different quanta (detector/exposure combinations) simultaneously, writing to the same log file. This interleaves log entries from different detectors/exposures, making it harder to debug individual quantum failures.

### Option 1: Split Logs Post-Execution

Use the `split_log_by_quantum.py` utility to reorganize existing log files by quantum identifiers:

```bash
# Split by detector
python scripts/utilities/split_log_by_quantum.py \\
    logs/RUN_ID/calibs/20230519.log \\
    --output-dir logs/RUN_ID/calibs/20230519_by_detector \\
    --split-by detector

# Split by exposure (useful for science processing)
python scripts/utilities/split_log_by_quantum.py \\
    logs/RUN_ID/science/20230519.log \\
    --output-dir logs/RUN_ID/science/20230519_by_exposure \\
    --split-by exposure

# Split by detector+exposure (full quantum separation)
python scripts/utilities/split_log_by_quantum.py \\
    logs/RUN_ID/science/20230519.log \\
    --output-dir logs/RUN_ID/science/20230519_by_quantum \\
    --split-by detector,exposure

# Split by detector+band (useful for DIA)
python scripts/utilities/split_log_by_quantum.py \\
    logs/RUN_ID/dia/20230519_r.log \\
    --output-dir logs/RUN_ID/dia/20230519_r_by_detector \\
    --split-by detector,band
```

This creates separate log files like:
```
logs/RUN_ID/calibs/20230519_by_detector/
├── detector0.log
├── detector1.log
└── unknown.log  # Lines without dataId info
```

### Option 2: Extract Per-Quantum Logs from Butler

LSST stores quantum execution logs in the Butler repository as `tasklabel_log` dataset types. You can extract these after pipeline completion:

```bash
# Extract all logs from a run collection
python scripts/utilities/extract_butler_logs.py \\
    /path/to/repo \\
    --collection "Nickel/runs/20230519/calibs/*" \\
    --output-dir logs/20230519_from_butler/calibs

# Extract logs for specific task
python scripts/utilities/extract_butler_logs.py \\
    /path/to/repo \\
    --collection "Nickel/runs/20230519/science/*" \\
    --task-label isr \\
    --output-dir logs/20230519_from_butler/science_isr
```

This creates a directory structure like:
```
logs/20230519_from_butler/calibs/
├── cpBiasIsr/
│   ├── det0_exp86008005_day20230520.log
│   ├── det0_exp86008006_day20230520.log
│   └── det0_exp86008007_day20230520.log
├── cpBiasCombine/
│   └── day20230520.log
└── cpFlatIsr/
    ├── det0_exp86008010_day20230520.log
    └── det0_exp86008011_day20230520.log
```

### Which Approach to Use?

**Use `split_log_by_quantum.py` when:**
- You want to analyze logs immediately after a run without waiting for Butler ingestion
- You're debugging a currently running pipeline
- You have the pipeline log files but not Butler access

**Use `extract_butler_logs.py` when:**
- You want the "official" per-quantum logs as LSST intended
- You're analyzing historical runs
- You need logs that are guaranteed to match quantum boundaries exactly
- You want to query logs programmatically via Butler

**Comparison:**

| Feature | split_log_by_quantum.py | extract_butler_logs.py |
|---------|-------------------------|------------------------|
| **Source** | Pipeline log files | Butler repository |
| **Availability** | Immediate during/after run | After Butler ingestion |
| **Accuracy** | Heuristic (parses dataId from logs) | Exact (LSST's native quantum logs) |
| **Organization** | By dataId fields you specify | By task + full dataId |
| **Use case** | Quick debugging, real-time analysis | Historical analysis, programmatic queries |

## Troubleshooting

### No logs appearing

1. Check that `RUN_LOG_DIR` is set:
   ```bash
   echo $RUN_LOG_DIR
   ```

2. Verify log directory was created:
   ```bash
   ls -la logs/
   ```

3. Check file permissions on the log directory

### Incomplete logs

- LSST logs are appended, so if a command fails early, partial logs will exist
- Check the exit code in `pipeline.log`
- Look for ERROR or FATAL messages in step logs

### Large log files

LSST pipelines can generate verbose logs. For production runs:
- Use `log_level="INFO"` (default)
- Consider compressing old logs: `gzip logs/20260211_*/*.log`

### Logs appear out of order

This is normal with parallel execution (`-j > 1`). The timestamps show the actual chronological order. Options:
- **Sort by timestamp**: `python scripts/utilities/sort_lsst_log.py <logfile>`
- **Split by quantum**: `python scripts/utilities/split_log_by_quantum.py <logfile> --output-dir <dir> --split-by detector`
- **Extract from Butler**: `python scripts/utilities/extract_butler_logs.py <repo> --collection <coll> --output-dir <dir>`
- **Reduce parallelism**: Set `jobs: 1` in your run YAML

### Debugging specific detector/quantum failures

If a specific detector or exposure fails:

1. **Find the quantum** in the interleaved log:
   ```bash
   grep "detector: 0" logs/RUN_ID/calibs/20230519.log | grep ERROR
   ```

2. **Split by quantum** for focused analysis:
   ```bash
   python scripts/utilities/split_log_by_quantum.py \\
       logs/RUN_ID/calibs/20230519.log \\
       --output-dir logs/RUN_ID/calibs/20230519_by_detector \\
       --split-by detector

   # Now read just the failing detector's log
   less logs/RUN_ID/calibs/20230519_by_detector/detector0.log
   ```

3. **Extract from Butler** for exact quantum logs:
   ```bash
   python scripts/utilities/extract_butler_logs.py \\
       $REPO \\
       --collection "Nickel/runs/20230519/calibs/*" \\
       --output-dir logs/20230519_butler_logs
   ```

## Utilities

The following utilities are provided in `scripts/utilities/` for log management:

- **`sort_lsst_log.py`** - Sort log files by timestamp
  - Handles multi-line log entries
  - Preserves ISO 8601 timestamps
  - Useful for perfectly chronological output from parallel runs

- **`split_log_by_quantum.py`** - Split interleaved logs by quantum/detector
  - Parses dataId from LSST long-log format
  - Splits by detector, exposure, band, or combinations
  - Enables per-quantum debugging without Butler access

- **`extract_butler_logs.py`** - Extract per-quantum logs from Butler repository
  - Retrieves `tasklabel_log` datasets
  - Organizes by task and full dataId
  - Provides LSST's native per-quantum logging

All utilities are executable and include built-in help:
```bash
python scripts/utilities/sort_lsst_log.py --help
python scripts/utilities/split_log_by_quantum.py --help
python scripts/utilities/extract_butler_logs.py --help
```

## References

- [LSST pipetask documentation](https://pipelines.lsst.io/modules/lsst.ctrl.mpexec/pipetask.html)
- [LSST Logging Guide](https://developer.lsst.io/stack/logging.html)
- [Butler command reference](https://pipelines.lsst.io/v/weekly/modules/lsst.daf.butler/scripts/butler.html)
- [LSST Quantum Graph documentation](https://pipelines.lsst.io/v/weekly/modules/lsst.pipe.base/quantum-graph-overview.html)
- [LSST BPS (Batch Production Service)](https://pipelines.lsst.io/modules/lsst.ctrl.bps/quickstart.html)
