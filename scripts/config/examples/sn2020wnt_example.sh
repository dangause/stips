#!/usr/bin/env bash
#
# Example: SN 2020wnt Transient DIA Campaign
#
# This example shows how to use run_transient_dia.sh for a supernova follow-up campaign

# Transient properties
TRANSIENT_NAME="2020wnt"
TRANSIENT_RA=56.658
TRANSIENT_DEC=43.229
BAND="r"

# Create nights files
cat > template_nights_2020wnt.txt <<EOF
# Template nights (pre-discovery, Dec 2020 - Feb 2021)
20201207
20201219
20210208
20210218
EOF

cat > science_nights_2020wnt.txt <<EOF
# Science nights (post-discovery, Jan-Feb 2022)
20220105
20220108
20220110
20220118
20220124
20220126
20220129
20220208
20220212
EOF

# Run transient DIA pipeline
./scripts/pipeline/run_transient_dia.sh \
  --name "$TRANSIENT_NAME" \
  --ra $TRANSIENT_RA \
  --dec $TRANSIENT_DEC \
  --band $BAND \
  --template-nights template_nights_2020wnt.txt \
  --science-nights science_nights_2020wnt.txt \
  --exclude-dates-start 20220101 \
  --exclude-dates-end 20220301 \
  --bad-sub-threshold 0.35 \
  --jobs 4 \
  --skip-bootstrap

# Output will be in: transient_dia_results/2020wnt_YYYYMMDD_HHMMSS/
# - workflow.log
# - 2020wnt_lightcurve.ecsv
