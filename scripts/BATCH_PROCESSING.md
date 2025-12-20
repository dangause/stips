# Batch Processing Guide

This guide explains how to use `batch_process_nights.sh` to process multiple nights efficiently.

## Quick Start

### 1. Create a nights list file

Create a text file with one night per line (YYYYMMDD format):

```bash
cat > my_nights.txt <<EOF
20240625
20240626
20240627
EOF
```

### 2. Run the batch script

```bash
./scripts/batch_process_nights.sh --nights-file my_nights.txt
```

This will process each night through:
1. **fetch_archive_night.py** - Download raw data from Lick archive (automatic)
2. **10_calibs.sh** - Build bias, flats, and defects
3. **20_science.sh** - ISR and single-visit processing + per-night coadds

## Common Usage Examples

### Basic processing (download + process)
Download from archive and process all nights with default settings (8 parallel jobs):
```bash
./scripts/batch_process_nights.sh --nights-file nights.txt
```

### Process existing data (skip download)
If you already have the raw data downloaded:
```bash
./scripts/batch_process_nights.sh --nights-file nights.txt --skip-download
```

### Force re-download all files
Re-download even if files already exist locally:
```bash
./scripts/batch_process_nights.sh --nights-file nights.txt --download-overwrite
```

### High-performance processing
Use 16 parallel jobs for faster processing:
```bash
./scripts/batch_process_nights.sh --nights-file nights.txt -j 16
```

### Process specific nights from command line
```bash
./scripts/batch_process_nights.sh --nights "20240625,20240626,20240627"
```

### Skip calibrations (if already processed)
```bash
./scripts/batch_process_nights.sh --nights-file nights.txt --skip-download --skip-calibs
```

### Skip per-night coadds (only run ISR + single-visit)
```bash
./scripts/batch_process_nights.sh --nights-file nights.txt --skip-coadds
```

### Process specific object
Filter science exposures by OBJECT header:
```bash
./scripts/batch_process_nights.sh --nights-file nights.txt --object "2020wnt"
```

### Exclude bad exposures
Use a file with bad exposure/visit IDs:
```bash
./scripts/batch_process_nights.sh --nights-file nights.txt --bad-file bad_exposures.txt
```

### Build multi-night template after processing
Process all nights and build a deep coadd template:
```bash
./scripts/batch_process_nights.sh \
  --nights-file nights.txt \
  --build-template \
  --template-tract 1099 \
  --template-band r
```

### Continue on errors
Keep processing remaining nights even if one fails:
```bash
./scripts/batch_process_nights.sh \
  --nights-file nights.txt \
  --continue-on-error
```

### Dry run
See what would be executed without running:
```bash
./scripts/batch_process_nights.sh --nights-file nights.txt --dry-run
```

## Advanced Examples

### Full production run with template
Process all nights, build template for difference imaging:
```bash
./scripts/batch_process_nights.sh \
  --nights-file good_nights.txt \
  -j 16 \
  --build-template \
  --template-tract 1099 \
  --template-band r \
  --continue-on-error
```

### Reprocess science only (calibs already done)
```bash
./scripts/batch_process_nights.sh \
  --nights-file nights.txt \
  --skip-calibs \
  -j 16
```

### Process transient target with bad exposure filtering
```bash
./scripts/batch_process_nights.sh \
  --nights-file sn_nights.txt \
  --object "SN2024abc" \
  --bad-file bad_exposures.txt \
  -j 12
```

## Nights File Format

The nights file should contain one night per line in `YYYYMMDD` format:

```
# Nights for processing
# Lines starting with # are comments

20240625  # Good seeing night
20240626
20240627

# 20240628  # Commented out - bad weather

20240629
20240630
```

## Bad Exposures File Format

The bad exposures file should contain exposure or visit IDs to exclude:

```
# Bad exposures/visits to exclude
# Can be exposure IDs or visit IDs

89421037  # Tracking failure
89421042  # Guiding error
89421055

# Space or comma separated also works
89421100, 89421101, 89421102
```

## Output and Logging

The script creates detailed logs in `logs/batch/`:

- `batch_TIMESTAMP.log` - Full execution log with all command output
- `batch_TIMESTAMP_summary.txt` - Summary with status of each night

Example summary:
```
Batch Processing Summary
========================
Started: Thu Dec 18 10:30:00 PST 2025
Nights: 3
Jobs: 8

Processing Log:
===============

[10:30:15] 20240625 | calibs | SUCCESS
[10:35:22] 20240625 | science | SUCCESS
[10:40:18] 20240626 | calibs | SUCCESS
[10:45:30] 20240626 | science | SUCCESS
[10:50:12] 20240627 | calibs | SUCCESS
[10:55:45] 20240627 | science | SUCCESS

Results:
  Total nights: 3
  Successful: 3
  Failed: 0
```

## Options Reference

### Required (one of)
- `--nights-file FILE` - File with list of nights
- `--nights "N1,N2,..."` - Comma-separated nights

### Processing Options
- `-j, --jobs N` - Parallel jobs for pipetask (default: 8)
- `--skip-download` - Skip downloading from archive (use existing data)
- `--download-overwrite` - Re-download files even if they exist
- `--skip-calibs` - Skip 10_calibs.sh
- `--skip-science` - Skip 20_science.sh
- `--skip-coadds` - Skip per-night coadds in 20_science.sh
- `--object NAME` - Filter by OBJECT header
- `--bad-file FILE` - File with bad exposure IDs
- `--continue-on-error` - Continue on failure
- `--dry-run` - Print commands without executing

### Multi-night Template Options
- `--build-template` - Build deep template after processing
- `--template-tract TRACT` - Tract ID (required with --build-template)
- `--template-band BAND` - Band (b/v/r/i, required with --build-template)
- `--template-patch PATCH` - Specific patch (optional)

### Other Options
- `--log-dir DIR` - Custom log directory (default: logs/batch)
- `-h, --help` - Show help message

## Performance Tips

1. **Parallel jobs**: Increase `-j` based on your CPU cores and memory
   - 8 jobs: Safe default for most systems
   - 16 jobs: Good for high-memory systems (64+ GB RAM)
   - 32 jobs: Only for very large systems (128+ GB RAM)

2. **Continue on error**: Use `--continue-on-error` for large batches to process all nights even if some fail

3. **Skip stages**: If calibrations are already processed, use `--skip-calibs` to save time

4. **Process in chunks**: For very large batches (50+ nights), process in chunks of 10-20 nights

## Troubleshooting

### Download fails
- Check that `LICK_ARCHIVE_DIR` is set in `.env` or that `lick_archive` is pip-installed
- Verify network connectivity to `https://archive.ucolick.org`
- Check logs for specific error messages
- Try downloading a single night manually: `./scripts/fetch_archive_night.py --night YYYYMMDD`

### Script fails on first night
- Check that the night has raw data in `$RAW_PARENT_DIR/YYYYMMDD/raw/` (or use download)
- Verify calibration data exists (bias, flats)
- Check logs in `logs/batch/`

### Some nights fail
- Review the summary log to identify which nights failed
- Check individual night logs for error messages
- Use `--continue-on-error` to process remaining nights
- Reprocess failed nights individually with the underlying scripts

### Out of memory errors
- Reduce `-j` value (fewer parallel jobs)
- Process nights in smaller batches
- Increase system swap space

### Template building fails
- Ensure all input nights processed successfully
- Verify tract/band coverage exists in all nights
- Check that 30_coadds.sh works on individual nights

## Integration with Existing Scripts

This script is a wrapper around:
- [fetch_archive_night.py](fetch_archive_night.py) - Download from Lick archive
- [10_calibs.sh](10_calibs.sh) - Nightly calibrations
- [20_science.sh](20_science.sh) - Science processing
- [30_coadds.sh](30_coadds.sh) - Multi-night coadds (optional)

You can still run these scripts individually for single-night processing or troubleshooting.

## Examples of Real Workflows

### Standard survey processing
Process a week of data:
```bash
# Create nights list
seq -f "202406%02g" 1 7 > week1_nights.txt

# Process
./scripts/batch_process_nights.sh \
  --nights-file week1_nights.txt \
  -j 12 \
  --continue-on-error
```

### Transient follow-up campaign
Process specific nights for a transient:
```bash
# Nights with good conditions
cat > sn_nights.txt <<EOF
20240625
20240627
20240629
20240701
20240703
EOF

# Process and build template
./scripts/batch_process_nights.sh \
  --nights-file sn_nights.txt \
  --object "SN2024xyz" \
  --build-template \
  --template-tract 1099 \
  --template-band r \
  -j 16
```

### Reprocessing with updated calibrations
Reprocess science only:
```bash
./scripts/batch_process_nights.sh \
  --nights-file nights_to_reprocess.txt \
  --skip-calibs \
  -j 16
```
