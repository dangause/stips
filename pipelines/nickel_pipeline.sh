#!/usr/bin/env zsh
# nickel_pipeline.zsh — modular LSST obs_nickel runner with reusable calibs & structured logs
# Usage examples:
#   ./nickel_pipeline.zsh --all
#   ./nickel_pipeline.zsh --stages process
#   ./nickel_pipeline.zsh --stages flat,defects,calibchain --force
#   DEBUG=1 ./nickel_pipeline.zsh --stages repo --dry-run

# -------- debug & strict --------
[[ "${DEBUG:-0}" == "1" ]] && set -x
set -euo pipefail

echo "[start] nickel_pipeline.zsh launching…"

# ===== Minimal, explicit LSST env bootstrap =====
# Your stack root (you asked to cd and source loadLSST.zsh)
LSST_ROOT="/Users/dangause/Desktop/lick/lsst/lsst_stack"

if [[ ! -r "$LSST_ROOT/loadLSST.zsh" ]]; then
  echo "[env] ERROR: $LSST_ROOT/loadLSST.zsh not found"; exit 1
fi

pushd "$LSST_ROOT" >/dev/null
source "$LSST_ROOT/loadLSST.zsh"
popd >/dev/null

# Bring products into THIS shell
setup lsst_distrib || true

# -------- USER CONFIG BLOCK (overridable via env) --------
: ${REPO:="/Users/dangause/Desktop/lick/lsst/data/nickel/062424"}
: ${RAWDIR:="/Users/dangause/Desktop/lick/data/062424/raw"}
: ${OBS_NICKEL:="/Users/dangause/Desktop/lick/lsst/lsst_stack/stack/obs_nickel"}
: ${REFCAT_REPO:="/Users/dangause/Desktop/lick/lsst/lsst_stack/stack/refcats"}

# Make your obs_nickel visible
setup -r "$OBS_NICKEL" || true

# Instrument / collections
: ${INSTRUMENT_PY:="lsst.obs.nickel.Nickel"}
: ${INSTRUMENT:="Nickel"}
: ${RAW_RUN:="Nickel/raw/all"}
: ${CALIB_CHAIN:="Nickel/calib/current"}
: ${DEFECTS_CURRENT:="Nickel/calib/defects/current"}
: ${REFCATS_CHAIN:="refcats"}

# cpPipe directory root (safe default if CP_PIPE_DIR unset)
: ${CP_PIPE_DIR:="$OBS_NICKEL"}

# ProcessCcd bits
: ${PIPE:="$OBS_NICKEL/pipelines/ProcessCcd.yaml"}
: ${PROC_LABEL:="processCcd"}
: ${BAD:="1032,1033,1034,1043,1046,1047,1048,1049,1050,1051,1052,1056,1058,1059,1060"}

# cpPipe configs
CP_BIAS_PIPE="${CP_BIAS_PIPE:-$CP_PIPE_DIR/pipelines/_ingredients/cpBias.yaml}"
CP_FLAT_PIPE="${CP_FLAT_PIPE:-$CP_PIPE_DIR/pipelines/_ingredients/cpFlat.yaml}"
CP_FLAT_OVERRIDES=( "cpFlatIsr:doDark=False" "cpFlatIsr:doOverscan=True" )

# Defects generation args
DEFECT_MANUAL_BOXES=( "255 0 2 1025" "783 0 2 977" "1000 0 25 1024" )

# -------- RUNTIME / LOGGING --------
TS_UTC="$(date -u +%Y%m%dT%H%M%SZ)"
: ${RUN_ROOT:="Nickel/run"}
: ${LOG_DIR:="$OBS_NICKEL/logs/$TS_UTC"}
mkdir -p "$LOG_DIR"

# Colors
c_blue=$'%{\e[34m%}'; c_green=$'%{\e[32m%}'; c_yellow=$'%{\e[33m%}'; c_red=$'%{\e[31m%}'; c_dim=$'%{\e[2m%}'; c_off=$'%{\e[0m%}'

# CLI flags
DO_ALL=false
DRY_RUN=false
FORCE=false
SHOW_LIST=false
typeset -a WANT_STAGES
WANT_STAGES=()

echo "[cfg] OBS_NICKEL=$OBS_NICKEL"
echo "[cfg] REPO=$REPO"
echo "[cfg] RAWDIR=$RAWDIR"
echo "[cfg] LOG_DIR base=$LOG_DIR"
echo "[cfg] CP_PIPE_DIR=$CP_PIPE_DIR"
echo "[cfg] CP_BIAS_PIPE=$CP_BIAS_PIPE"
echo "[cfg] CP_FLAT_PIPE=$CP_FLAT_PIPE"

# -------- UTILS --------
say()  { print -r -- "$c_blue[$1]$c_off ${*:2}"; }
ok()   { print -r -- "$c_green[ok]$c_off $*"; }
warn() { print -r -- "$c_yellow[warn]$c_off $*"; }
die()  { print -r -- "$c_red[err]$c_off $*"; exit 1; }

log_wrap() {
  local stage="$1"; shift
  local log="$LOG_DIR/${stage}.log"
  say "$stage" "starting → $log"
  local start=$(date +%s)
  if $DRY_RUN; then
    print -r -- "[dry-run] $*" | tee -a "$log"
    ok "$stage dry-run complete"
    return 0
  fi
  ( set -o pipefail; "$@" 2>&1 | tee -a "$log" )
  local rc=$?
  local end=$(date +%s)
  if [[ $rc -eq 0 ]]; then
    ok "$stage finished in $((end-start))s"
  else
    die "$stage failed (rc=$rc). See $log"
  fi
}

butler_has_collection() {
  butler query-collections "$REPO" --chains --explain | awk '{print $1}' | grep -Fxq "$1"
}

butler_has_dataset_in_collection() {
  # $1 datasetType, $2 collection
  butler query-datasets "$REPO" "$1" --collections "$2" --limit 1 >/dev/null 2>&1
}

ensure_repo() {
  if [[ ! -f "$REPO/butler.yaml" ]]; then
    log_wrap repo-create butler create "$REPO"
  fi
}

maybe_skip() {
  local stage="$1"; shift
  local sentinel="$1"; shift || true
  $FORCE && return 1
  if [[ -n "${sentinel:-}" ]]; then
    eval "$sentinel" && { warn "skip $stage (already satisfied)"; return 0; }
  fi
  return 1
}

# -------- STAGES --------
stage_repo() {
  ensure_repo
  log_wrap repo-register butler register-instrument "$REPO" "$INSTRUMENT_PY" || true
}

stage_ingest() {
  ensure_repo
  log_wrap ingest-raws butler ingest-raws "$REPO" "$RAWDIR" --transfer symlink --output-run "$RAW_RUN"
  log_wrap define-visits butler define-visits "$REPO" "$INSTRUMENT"
}

stage_curated() {
  ensure_repo
  local CURATED="Nickel/run/curated/$TS_UTC"
  maybe_skip curated 'butler_has_collection "'"$CURATED"'"' || \
    log_wrap curated butler write-curated-calibrations "$REPO" "$INSTRUMENT" "$RAW_RUN" --collection "$CURATED"
  log_wrap curated-chain butler collection-chain "$REPO" "$CALIB_CHAIN" "$CURATED" --mode extend
}

stage_bias() {
  ensure_repo
  local OUT="Nickel/run/cp_bias/$TS_UTC"
  maybe_skip bias 'butler_has_dataset_in_collection bias "'"$OUT"'"' || \
    log_wrap cp-bias pipetask run -b "$REPO" -i "$CALIB_CHAIN","$RAW_RUN" -o "$OUT" \
      -p "$CP_BIAS_PIPE" \
      -d "instrument='${INSTRUMENT}' AND exposure.observation_type='bias'" \
      --register-dataset-types
  log_wrap certify-bias butler certify-calibrations "$REPO" "$OUT" "$CALIB_CHAIN" bias \
       --begin-date 2020-01-01 --end-date 2030-01-01
}

stage_flat() {
  ensure_repo
  local OUT="Nickel/run/cp_flat/$TS_UTC"
  local -a flat_cfg; flat_cfg=()
  for kv in "${CP_FLAT_OVERRIDES[@]}"; do flat_cfg+=( -c "$kv" ); done
  maybe_skip flat 'butler_has_dataset_in_collection flat "'"$OUT"'"' || \
    log_wrap cp-flat pipetask run -b "$REPO" -i "$CALIB_CHAIN","$RAW_RUN" -o "$OUT" \
      -p "$CP_FLAT_PIPE" "${flat_cfg[@]}" \
      -d "instrument='${INSTRUMENT}' AND exposure.observation_type='flat'" \
      --register-dataset-types
  log_wrap flat-chain butler collection-chain "$REPO" "$CALIB_CHAIN" "$OUT" --mode extend
}

stage_defects() {
  ensure_repo
  local LAST_FLAT; LAST_FLAT="$(butler query-collections "$REPO" | awk '{print $1}' | grep '^Nickel/run/cp_flat/' | sort | tail -n1 || true)"
  [[ -z "$LAST_FLAT" ]] && die "No cp_flat run found. Run stage 'flat' first."
  butler_has_dataset_in_collection flat "$LAST_FLAT" || die "Collection $LAST_FLAT has no flat datasets; cannot build defects."

  local DEF_TS="$(date -u +%Y%m%dT%H%M%SZ)"
  local DEF_RUN="Nickel/calib/defects/$DEF_TS"
  local QA_DIR="$OBS_NICKEL/scripts/defects/qa_$DEF_TS"
  local -a boxes; boxes=()
  for b in "${DEFECT_MANUAL_BOXES[@]}"; do boxes+=( --manual-box $b ); done

  maybe_skip defects 'butler_has_collection "'"$DEF_RUN"'"' || \
    log_wrap defects python "$OBS_NICKEL/scripts/defects/make_defects_from_flats.py" \
        --repo "$REPO" \
        --collection "$LAST_FLAT" \
        "${boxes[@]}" \
        --register \
        --ingest \
        --defects-run "$DEF_RUN" \
        --plot \
        --qa-dir "$QA_DIR"

  if butler_has_collection "$DEF_RUN"; then
    log_wrap defects-current butler collection-chain "$REPO" "$DEFECTS_CURRENT" "$DEF_RUN" --mode redefine
  else
    warn "defects run $DEF_RUN not found; skipping current relink."
  fi
}

stage_calibchain() {
  ensure_repo
  local -a CURATEDS; CURATEDS=($(butler query-collections "$REPO" | awk '{print $1}' | grep '^Nickel/run/curated/' || true))
  local LAST_BIAS; LAST_BIAS="$(butler query-collections "$REPO" | awk '{print $1}' | grep '^Nickel/run/cp_bias/' | sort | tail -n1 || true)"
  local LAST_FLAT; LAST_FLAT="$(butler query-collections "$REPO" | awk '{print $1}' | grep '^Nickel/run/cp_flat/' | sort | tail -n1 || true)"

  local -a args; args=()
  for c in "${CURATEDS[@]}"; do args+=( "$c" ); done
  [[ -n "$LAST_BIAS" ]] && args+=( "$LAST_BIAS" )
  [[ -n "$LAST_FLAT" ]] && args+=( "$LAST_FLAT" )
  args+=( "$DEFECTS_CURRENT" )
  (( ${#args[@]} > 0 )) || die "No calibrations found to chain."

  log_wrap calib-chain butler collection-chain "$REPO" "$CALIB_CHAIN" "${args[@]}" --mode redefine
}

stage_refcats() {
  ensure_repo
  (
    cd "$REFCAT_REPO" || die "Cannot cd to REFCAT_REPO=$REFCAT_REPO"

    : > "$LOG_DIR/convert-gaia.log"
    log_wrap refcat-gaia-convert bash -lc "convertReferenceCatalog data/gaia-refcat/ scripts/gaia_dr3_config.py ./data/gaia_dr3_all_cones/gaia_dr3_all_cones.csv &>> '$LOG_DIR/convert-gaia.log'"

    log_wrap refcat-gaia-register butler register-dataset-type "$REPO" gaia_dr3_20250728 SimpleCatalog htm7 || true
    log_wrap refcat-gaia-ingest   butler ingest-files -t direct "$REPO" gaia_dr3_20250728 refcats/gaia_dr3_20250728 data/gaia-refcat/filename_to_htm.ecsv
    log_wrap refcat-gaia-chain    butler collection-chain "$REPO" --mode extend "$REFCATS_CHAIN" refcats/gaia_dr3_20250728

    : > "$LOG_DIR/convert-ps1.log"
    log_wrap refcat-ps1-convert bash -lc "convertReferenceCatalog data/ps1-refcat/ scripts/ps1_config.py ./data/ps1_all_cones/merged_ps1_cones.csv &>> '$LOG_DIR/convert-ps1.log'"

    log_wrap refcat-ps1-register butler register-dataset-type "$REPO" panstarrs1_dr2_20250730 SimpleCatalog htm7 || true
    log_wrap refcat-ps1-ingest   butler ingest-files -t direct "$REPO" panstarrs1_dr2_20250730 refcats/panstarrs1_dr2_20250730 data/ps1-refcat/filename_to_htm.ecsv
    log_wrap refcat-ps1-chain    butler collection-chain "$REPO" --mode extend "$REFCATS_CHAIN" refcats/panstarrs1_dr2_20250730
  )
}

stage_process() {
  ensure_repo
  log_wrap sanity bash -lc "butler query-collections '$REPO' | grep -E 'Nickel/calib/(current|defects/current)|^refcats$' || true"

  local OUT="$RUN_ROOT/processCcd/$(date +%Y%m%d%H%M%S)"
  local sel="instrument='${INSTRUMENT}' AND exposure.observation_type='science'"
  [[ -n "$BAD" ]] && sel="${sel} AND NOT (exposure IN (${BAD}))"

  log_wrap processCcd pipetask run -b "$REPO" \
      -i "$RAW_RUN","$CALIB_CHAIN","$REFCATS_CHAIN" \
      -o "$OUT" \
      -p "$PIPE#$PROC_LABEL" \
      -d "$sel" \
      --register-dataset-types
  print -r -- "ProcessCcd run: $OUT" | tee -a "$LOG_DIR/summary.txt"
}

# -------- DRIVER --------
print_help() {
  cat <<EOF
Usage: $(basename "$0") [--all] [--stages s1,s2,...] [--bad EXPOSURES] [--force] [--dry-run] [--list] [--debug]
Stages: repo, ingest, curated, bias, flat, defects, calibchain, refcats, process
EOF
}

parse_args() {
  local -a argv; argv=("$@")
  local i=1
  while (( i <= ${#argv} )); do
    case "${argv[$i]}" in
      --all) DO_ALL=true ;;
      --stages) ((i++)); IFS=',' read -rA WANT_STAGES <<< "${argv[$i]:-}";;
      --bad)    ((i++)); BAD="${argv[$i]:-}";;
      --force)  FORCE=true ;;
      --dry-run) DRY_RUN=true ;;
      --list)   SHOW_LIST=true ;;
      --debug)  set -x ;;
      -h|--help) print_help; exit 0 ;;
      *) die "Unknown arg: ${argv[$i]}" ;;
    esac
    ((i++))
  done
  if $DO_ALL && (( ${#WANT_STAGES[@]} > 0 )); then
    die "Use either --all or --stages, not both."
  fi
  if ! $DO_ALL && (( ${#WANT_STAGES[@]} == 0 )); then
    WANT_STAGES=( process )
  fi
}

run_plan() {
  local -a plan; plan=("$@")
  print -r -- "${c_dim}Plan${c_off} @$TS_UTC"
  for s in "${plan[@]}"; do print -r -- "  - $s"; done
  print -r -- "BAD exposures: ${BAD:-<none>}"
  print -r -- "Logs: $LOG_DIR"
}

main() {
  parse_args "$@"

  local -a STAGE_ORDER; STAGE_ORDER=( repo ingest curated bias flat defects calibchain refcats process )
  local -a run_stages; run_stages=()

  if $DO_ALL; then
    run_stages=("${STAGE_ORDER[@]}")
  else
    for s in "${WANT_STAGES[@]}"; do
      if [[ " ${STAGE_ORDER[*]} " == *" $s "* ]]; then
        run_stages+=("$s")
      else
        die "Unknown stage: $s"
      fi
    done
  fi

  run_plan "${run_stages[@]}"
  $SHOW_LIST && exit 0

  exec > >(tee -a "$LOG_DIR/combined.log") 2>&1
  say "begin" "Nickel pipeline start @ $TS_UTC"

  for s in "${run_stages[@]}"; do
    case "$s" in
      repo)        stage_repo ;;
      ingest)      stage_ingest ;;
      curated)     stage_curated ;;
      bias)        stage_bias ;;
      flat)        stage_flat ;;
      defects)     stage_defects ;;
      calibchain)  stage_calibchain ;;
      refcats)     stage_refcats ;;
      process)     stage_process ;;
      *) die "Unhandled stage: $s" ;;
    esac
  done

  say "done"  "Finished. Logs in $LOG_DIR"
  print -r -- "Summary:" | tee -a "$LOG_DIR/summary.txt"
  print -r -- "  REPO:        $REPO" | tee -a "$LOG_DIR/summary.txt"
  print -r -- "  RAW_RUN:     $RAW_RUN" | tee -a "$LOG_DIR/summary.txt"
  print -r -- "  CALIB_CHAIN: $CALIB_CHAIN" | tee -a "$LOG_DIR/summary.txt"
  print -r -- "  DEFECTS:     $DEFECTS_CURRENT" | tee -a "$LOG_DIR/summary.txt"
  print -r -- "  REFCATS:     $REFCATS_CHAIN" | tee -a "$LOG_DIR/summary.txt"
}

main "$@"
