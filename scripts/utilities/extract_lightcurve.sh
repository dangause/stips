#!/usr/bin/env bash
# Extract light curve from DIA or calibrated sources
# Wrapper around extract_lightcurve.py with common presets

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/logging.sh"

# Default dataset type
DATASET_TYPE="${DATASET_TYPE:-diaSourceTable}"

# Show usage
usage() {
    cat << EOF
Usage: $(basename "$0") [OPTIONS]

Extract light curve from Butler repository.

OPTIONS:
    --repo PATH              Butler repository path (required)
    --object NAME            Object name to extract (required)
    --ra RA                  RA in degrees (required)
    --dec DEC                Dec in degrees (required)
    --radius ARCSEC          Search radius in arcseconds (default: 1.0)
    --dataset-type TYPE      Dataset type: diaSourceTable, sourceTable,
                            forcedSourceTable (default: diaSourceTable)
    --collection COLL        Butler collection (default: auto-detect latest)
    --output FILE            Output CSV file (default: lc_<object>.csv)
    -h, --help              Show this help message

EXAMPLES:
    # Extract DIA lightcurve
    $(basename "$0") --repo /data/butler --object SN2020wnt \\
        --ra 150.123 --dec 45.678

    # Extract from calibrated sources
    $(basename "$0") --repo /data/butler --object SN2023ixf \\
        --ra 210.456 --dec 54.321 --dataset-type sourceTable

    # Extract forced photometry
    DATASET_TYPE=forcedSourceTable $(basename "$0") \\
        --repo /data/butler --object SN2020wnt --ra 150.123 --dec 45.678

EOF
    exit 1
}

# Parse arguments and pass through to Python script
ARGS=()
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            usage
            ;;
        --dataset-type)
            DATASET_TYPE="$2"
            shift 2
            ;;
        *)
            ARGS+=("$1")
            shift
            ;;
    esac
done

# Call the Python implementation
log_info "Extracting lightcurve using dataset type: ${DATASET_TYPE}"
python -m obs_nickel_data_tools.pipeline_tools.extract_lightcurve \
    --dataset-type "${DATASET_TYPE}" \
    "${ARGS[@]}"
