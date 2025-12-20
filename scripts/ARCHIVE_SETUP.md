# Lick Archive Client Setup

The batch processing script can automatically download data from the Lick Observatory searchable archive. However, the `lick_archive` Python module needs to be installed first.

## Quick Setup (Recommended)

Install the `lick_archive` package in editable mode so it's available to Python:

```bash
cd /Users/dangause/Developer/lick/lick_searchable_archive
pip install -e .
```

This installs the package and all its dependencies (`tenacity`, `requests`, etc.) into your Python environment.

## Verify Installation

Test that the archive client works:

```bash
./scripts/fetch_archive_night.py --night 20220212 --help
```

If you see the help message without errors, it's installed correctly.

## Alternative: Use Without Installation

If you don't want to install the package, you can skip downloads and use existing data:

```bash
./scripts/batch_process_nights.sh \
  --nights-file nights.txt \
  --skip-download
```

## Environment Variables

The `.env` file should already have these set:

```bash
LICK_ARCHIVE_DIR=/Users/dangause/Developer/lick/lick_searchable_archive
LICK_ARCHIVE_URL=https://archive.ucolick.org/archive
LICK_ARCHIVE_INSTR=NICKEL_DIR
RAW_PARENT_DIR=/Users/dangause/Developer/lick/data
```

## Troubleshooting

### "ModuleNotFoundError: No module named 'tenacity'"

The `lick_archive` package isn't installed. Run:

```bash
cd /Users/dangause/Developer/lick/lick_searchable_archive
pip install -e .
```

### "Could not import lick_archive client"

Either:
1. Install the package: `cd $LICK_ARCHIVE_DIR && pip install -e .`
2. Or skip downloads: `--skip-download`

### Download is very slow

The archive client includes rate limiting (500ms between requests) to avoid overwhelming the server. This is normal. For 100+ exposures, expect 1-2 minutes per night.

### Network errors

- Check internet connectivity to `https://archive.ucolick.org`
- The archive client has automatic retry logic with exponential backoff
- Use `--continue-on-error` to process remaining nights if one fails

## Testing Archive Downloads

Test downloading a single night:

```bash
# Download one night's data
./scripts/fetch_archive_night.py \
  --night 20220212 \
  --client-path /Users/dangause/Developer/lick/lick_searchable_archive \
  --raw-root /Users/dangause/Developer/lick/data
```

Or use the batch script in download-only mode:

```bash
./scripts/batch_process_nights.sh \
  --nights "20220212" \
  --skip-calibs \
  --skip-science
```

## Full Workflow After Setup

Once `lick_archive` is installed:

```bash
# 1. Create nights list
cat > nights.txt <<EOF
20220208
20220212
EOF

# 2. Download and process everything
./scripts/batch_process_nights.sh --nights-file nights.txt

# The script will:
# - Download raw data from archive
# - Build calibrations
# - Process science data
# - Generate coadds
```

## Performance Notes

**Download speed** depends on:
- Number of exposures per night (~50-150 typical)
- Network bandwidth
- Archive server load
- Rate limiting (500ms per request)

**Typical times:**
- ~2-10 minutes per night for downloads
- ~25-50 minutes total per night (download + processing)

For 20 nights with downloads: **~8-17 hours total**
