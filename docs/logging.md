# Logs and debugging

Each `stips run` writes its logs to a new directory named by a run ID (the
start time and process ID). It prints the path when it starts and when it
ends.

```text
logs/20260211_143022_12345/
├── summary.txt            # what succeeded and failed: read this first
├── pipeline.log           # everything STIPS itself logged
├── run_info.txt           # run metadata
├── bootstrap/bootstrap.log
├── templates/<band>/      # ps1_template.log or coadd_template.log
├── calibs/<night>.log
├── science/<night>_<bands>.log
├── dia/<night>_<band>.log
├── fphot/<night>_<band>.log
└── lightcurve/
```

Science runs the broadband filters (B, V, R, I) of a night together, in a log
such as `science/20230521_r_i.log`, and each other band separately, such as
`science/20230519_rp.log`.

Coadd-template runs add `calibs_template/` and `science_template/`, and
SkyMapper templates log to `skymapper_template/<band>.log`. Each step log
holds the complete output of the Rubin commands for that step, so the error
from `pipetask` or `butler` is there in full.

`logs/` sits two levels above `INSTRUMENT_DIR`: in the STIPS checkout for the
bundled instruments, and at `/opt/stips/logs` in the container. Old run
directories are never removed, so delete them when you no longer need them.

## Finding a failure

```bash
cat logs/<run id>/summary.txt
grep -rn "ERROR" logs/<run id>/
less logs/<run id>/science/20230519_rp.log
```

Rubin log lines carry a timestamp and the data ID of the quantum they belong
to, for example the exposure and detector, so a failure can be tied to one
frame. {doc}`troubleshooting` lists the common errors and their causes.

## Untangling parallel runs

With `options.jobs` above 1, several quanta write to one log at the same time
and their lines interleave. Three utilities in `scripts/utilities/` help:

```bash
# Re-sort a log by timestamp (in place, or to a second file)
python scripts/utilities/sort_lsst_log.py logs/<run id>/science/20230519_rp.log

# Split a log into one file per exposure (or detector, band, or a combination)
python scripts/utilities/split_log_by_quantum.py logs/<run id>/science/20230519_rp.log \
    --output-dir science_by_exposure --split-by exposure

# Retrieve the Butler's own per-quantum logs (run with the stack activated)
python scripts/utilities/extract_butler_logs.py $REPO \
    --collection "Nickel/runs/20230519/processCcd/*" \
    --output-dir butler_logs --task-label calibrateImage
```

Splitting works on the log files immediately and approximately; the Butler
logs are exact but exist only for quanta that ran. For a clean log of a
problem night, rerun it with `jobs: 1`.
