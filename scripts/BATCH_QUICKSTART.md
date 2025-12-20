# Batch Processing Quick Start

Process multiple nights in one command.

## Prerequisites

**For automatic downloads from Lick archive:**
```bash
cd /Users/dangause/Developer/lick/lick_searchable_archive
pip install -e .
```

See [ARCHIVE_SETUP.md](ARCHIVE_SETUP.md) for details. Or use `--skip-download` if you already have the data.

## TL;DR

```bash
# 1. Create nights list
cat > nights.txt <<EOF
20240625
20240626
20240627
EOF

# 2. Run batch processing
./scripts/batch_process_nights.sh --nights-file nights.txt
```

Done! All nights will be:
1. Downloaded from Lick archive (automatic, if `lick_archive` installed)
2. Processed through calibs → science → coadds

---

## Common Workflows

### Download and process ~20 nights from a date range

```bash
# Generate list
./scripts/generate_nights_list.py \
  --start 20240601 \
  --end 20240620 \
  -o june_nights.txt

# Download from archive and process with high parallelism
./scripts/batch_process_nights.sh \
  --nights-file june_nights.txt \
  -j 16 \
  --continue-on-error
```

### Process existing data (skip download)

```bash
# If you already have raw data downloaded
./scripts/batch_process_nights.sh \
  --nights-file nights.txt \
  --skip-download \
  -j 16
```

### Auto-discover and process all available nights

```bash
# Find all nights with raw data
./scripts/generate_nights_list.py \
  --auto-discover \
  -o all_nights.txt

# Review the list
cat all_nights.txt

# Process
./scripts/batch_process_nights.sh \
  --nights-file all_nights.txt \
  -j 12
```

### Process specific object across multiple nights

```bash
# Create nights list
./scripts/generate_nights_list.py \
  --nights "20240625,20240627,20240629,20240701" \
  -o sn_nights.txt

# Process only exposures of target
./scripts/batch_process_nights.sh \
  --nights-file sn_nights.txt \
  --object "SN2024abc" \
  -j 16
```

### Build multi-night template for difference imaging

```bash
# Process nights and build template in one go
./scripts/batch_process_nights.sh \
  --nights-file nights.txt \
  --build-template \
  --template-tract 1099 \
  --template-band r \
  -j 16
```

### Reprocess science (calibs already done)

```bash
./scripts/batch_process_nights.sh \
  --nights-file nights.txt \
  --skip-calibs \
  -j 16
```

---

## Monitoring Progress

### In another terminal

```bash
# Watch the summary log
./scripts/monitor_batch.sh --watch

# Or tail the full log
tail -f logs/batch/batch_*.log
```

### Check status

```bash
# View most recent batch summary
./scripts/monitor_batch.sh
```

---

## What Gets Processed?

Each night goes through:

1. **Download** (fetch_archive_night.py) - Automatic
   - Downloads raw data from Lick searchable archive
   - Skips files that already exist (unless `--download-overwrite`)
   - ~2-10 minutes per night (depends on data size and network)

2. **Calibrations** (10_calibs.sh)
   - Ingest raw data
   - Build combined bias
   - Build combined flats (per filter)
   - Generate defect masks
   - ~5-10 minutes per night

3. **Science** (20_science.sh)
   - ISR (bias/flat correction)
   - Source detection
   - Astrometric calibration (WCS)
   - Photometric calibration
   - Per-night coadds
   - ~10-30 minutes per night (depends on exposure count)

4. **Template** (30_coadds.sh) - Optional
   - Multi-night deep coadd
   - Only runs if `--build-template` specified
   - ~5-15 minutes

**Total time**: ~25-50 minutes per night (with `-j 8`, including download)

---

## Options Quick Reference

### Essential
- `--nights-file FILE` - List of nights to process
- `--nights "N1,N2,..."` - Comma-separated nights
- `-j N` - Parallel jobs (default: 8, try 16-32 for speed)

### Download Control
- `--skip-download` - Skip archive download (use existing data)
- `--download-overwrite` - Re-download even if files exist

### Processing Control
- `--skip-calibs` - Skip calibration processing
- `--skip-science` - Skip science processing
- `--skip-coadds` - Skip per-night coadds (faster)
- `--continue-on-error` - Keep going if a night fails

### Filtering
- `--object NAME` - Process only specific target
- `--bad-file FILE` - Exclude bad exposures

### Template
- `--build-template` - Build multi-night template
- `--template-tract N` - Tract ID
- `--template-band X` - Band (b/v/r/i)

### Utilities
- `--dry-run` - Show what would run
- `--help` - Full help message

---

## Output Locations

### Butler Collections
```
Nickel/
├── raw/{NIGHT}/{TIMESTAMP}/        Raw exposures
├── calib/{NIGHT}/                  Nightly calibrations
├── runs/{NIGHT}/processCcd/*/run   Science products
├── runs/{NIGHT}/coadd/*/run        Per-night coadds
└── templates/deep/tract*/band/     Multi-night templates
```

### Logs
```
logs/batch/
├── batch_{TIMESTAMP}.log           Full execution log
└── batch_{TIMESTAMP}_summary.txt   Status summary
```

---

## Troubleshooting

### Script fails immediately
```bash
# Check syntax with dry-run
./scripts/batch_process_nights.sh --nights-file nights.txt --dry-run
```

### Night fails during processing
```bash
# Review summary
./scripts/monitor_batch.sh

# Check specific night logs
less logs/batch/batch_*.log | grep "NIGHT.*20240625" -A 50
```

### Out of memory
```bash
# Reduce parallelism
./scripts/batch_process_nights.sh --nights-file nights.txt -j 4
```

### Want to retry failed nights
```bash
# Extract failed nights from summary
grep "FAILED" logs/batch/batch_*_summary.txt | \
  awk '{print $2}' | sort -u > failed_nights.txt

# Reprocess
./scripts/batch_process_nights.sh --nights-file failed_nights.txt
```

---

## Full Documentation

See [BATCH_PROCESSING.md](BATCH_PROCESSING.md) for:
- Detailed options reference
- Advanced usage examples
- Performance tuning
- Integration with existing workflows
