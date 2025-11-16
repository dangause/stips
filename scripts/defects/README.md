# Nickel defect masks (obs_nickel)

This folder holds the **recipe** and **artifacts** for persistent sensor defect masks
(“defects”) for the Nickel instrument. Defects are rectangular masks used by `IsrTask`
to ignore bad pixels/columns/blemishes during ISR.

## TL;DR (first-time setup)

1. Create defects from cpFlat outputs and ingest:

   ```bash
   python obs_nickel/calib/defects/make_defects_from_flats.py \
     --repo ~/Developer/lick/lsst/data/nickel/062424 \
     --collection Nickel/run/cp_flat/20250730T135912Z \
     --detectors 0 \
     --register --ingest --defects-run Nickel/calib/defects/$(date -u +%Y%m%dT%H%M%SZ) \
     --plot --qa-dir obs_nickel/calib/defects/qa_$(date -u +%Y%m%d)
