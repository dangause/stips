# Logging Improvements Summary

## Changes Made

### Organized Directory Structure

Logs are now organized into subdirectories by pipeline step, making it much easier to navigate and find specific logs:

**Before:**
```
logs/RUN_ID/
├── pipeline.log
├── calibs_20230519.log
├── calibs_20230521.log
├── calibs_20230523.log
├── science_20230519.log
├── science_20230521.log
├── science_20230523.log
├── dia_20230519_r.log
├── dia_20230519_i.log
... (30+ files in flat structure)
```

**After:**
```
logs/RUN_ID/
├── pipeline.log
├── summary.txt
├── bootstrap/
│   └── bootstrap.log
├── templates/
│   ├── ps1_template_r.log
│   └── ps1_template_i.log
├── calibs/
│   ├── 20230519.log
│   ├── 20230521.log
│   └── 20230523.log
├── science/
│   ├── 20230519.log
│   ├── 20230521.log
│   └── 20230523.log
├── dia/
│   ├── 20230519_r.log
│   ├── 20230519_i.log
│   └── ...
├── fphot/
│   ├── 20230519.log
│   └── ...
└── lightcurve/
    ├── forced_phot.log
    └── dia_sources.log
```

### Benefits

1. **Easier Navigation**: Logs grouped by step type
2. **Clear Organization**: Each step has its own directory
3. **Scalability**: Handles campaigns with many nights better
4. **Quick Debugging**: Easy to find all logs for a specific step
5. **Parallel Review**: Multiple people can review different steps simultaneously

### Directory Mapping

| Step | Directory | Files |
|------|-----------|-------|
| Bootstrap | `bootstrap/` | `bootstrap.log` |
| PS1 Templates | `templates/` | `ps1_template_{band}.log` |
| Coadd Templates | `templates/` | `coadd_template_{band}.log` |
| Template Calibs | `calibs_template/` | `{night}.log` |
| Template Science | `science_template/` | `{night}.log` |
| Calibrations | `calibs/` | `{night}.log` |
| Science | `science/` | `{night}.log` |
| DIA | `dia/` | `{night}_{band}.log` |
| Forced Photometry | `fphot/` | `{night}.log` |
| Lightcurve | `lightcurve/` | `forced_phot.log` or `dia_sources.log` |

## Usage Examples

### View all calibration logs
```bash
cd logs/20260211_143022_12345/calibs/
ls -lh
```

### Check if any DIA runs failed
```bash
grep -l "ERROR" logs/20260211_143022_12345/dia/*.log
```

### Compare science processing for different nights
```bash
diff logs/20260211_143022_12345/science/20230519.log \
     logs/20260211_143022_12345/science/20230521.log
```

### View all template-related logs
```bash
ls -lh logs/20260211_143022_12345/templates/
ls -lh logs/20260211_143022_12345/calibs_template/
ls -lh logs/20260211_143022_12345/science_template/
```

### Archive logs by step
```bash
RUN_ID=20260211_143022_12345
tar czf calibs_logs.tar.gz logs/$RUN_ID/calibs/
tar czf dia_logs.tar.gz logs/$RUN_ID/dia/
```

## Implementation Details

The reorganization is handled by the `_get_step_log_file()` function in [run.py](../packages/data_tools/src/obs_nickel_data_tools/core/run.py), which:

1. Takes step name, night, and band as parameters
2. Creates appropriate subdirectory based on step type
3. Generates filename based on identifiers
4. Ensures directory exists before returning path

All subdirectories are created automatically as needed, so no manual setup is required.

## Backward Compatibility

This is a new feature with no backward compatibility concerns since:
- Each run creates a fresh log directory
- Old log directories (if any existed) remain unchanged
- The new structure is only used for new runs

## Testing

To test the new structure:
```bash
nickel run scripts/config/2023ixf/pipeline_ps1_template.yaml

# Verify directory structure
tree logs/$(ls -t logs/ | head -1)

# Check that logs exist in subdirectories
find logs/$(ls -t logs/ | head -1) -name "*.log" -type f
```
