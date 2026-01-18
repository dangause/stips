#!/usr/bin/env bash
#
# Example: M33 Variable Star Monitoring
#
# This example shows how to use run_variable_dia.sh for variable star campaigns

# Field properties
FIELD_NAME="M33_field1"
FIELD_RA=23.462
FIELD_DEC=30.660
BANDS="r,i"  # Multi-band monitoring

# Create nights files
cat > template_nights_m33.txt <<EOF
# Template nights (quiescent baseline, 5+ nights recommended)
20240601
20240602
20240605
20240610
20240615
20240620
EOF

cat > observation_nights_m33.txt <<EOF
# All observation nights (baseline + monitoring)
20240601
20240602
20240605
20240610
20240615
20240620
20240701
20240705
20240710
20240715
20240720
20240801
20240805
20240810
EOF

# Run variable star DIA pipeline
./scripts/pipeline/run_variable_dia.sh \
  --name "$FIELD_NAME" \
  --ra $FIELD_RA \
  --dec $FIELD_DEC \
  --bands $BANDS \
  --template-nights template_nights_m33.txt \
  --observation-nights observation_nights_m33.txt \
  --bad-sub-threshold 0.2 \
  --min-template-nights 5 \
  --jobs 4 \
  --skip-bootstrap

# Output will be in: variable_dia_results/M33_field1_YYYYMMDD_HHMMSS/
# - workflow.log
# - M33_field1_r_dia_collections.txt
# - M33_field1_i_dia_collections.txt
#
# Then extract individual variable light curves:
# obsn-dia-lightcurve \
#   --repo $REPO \
#   --collection $(cat variable_dia_results/M33_field1_*/M33_field1_r_dia_collections.txt) \
#   --ra <VAR_RA> --dec <VAR_DEC> \
#   --radius 1.0 --band r \
#   --output M33_var1_r_lc.ecsv
