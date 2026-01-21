SHELL := /bin/bash
ENV_FILE ?= .env
EXTRA_ENV ?=
PYTHON ?= python
PIP ?= $(PYTHON) -m pip
PACKAGES := packages/obs_nickel packages/data_tools packages/defects packages/refcats packages/testdata packages/tuning packages/colorterms

# Multi-repo support:
# - Switch primary env file:   ENV_FILE=repo2.env make calibs NIGHT=20240625
# - Layer common overrides:    EXTRA_ENV=".env.common .env.prod" make calibs NIGHT=20240625
define load_envs
for f in $(ENV_FILE) $(EXTRA_ENV); do \
	if [[ -n "$$f" && -f "$$f" ]]; then \
		set -a; source "$$f"; set +a; \
	elif [[ -n "$$f" && "$$f" != ".env" ]]; then \
		echo "Warning: env file $$f not found" >&2; \
	fi; \
done; \
if [[ -f "$${PWD}/scripts/utilities/repo_paths.sh" ]]; then \
	source "$${PWD}/scripts/utilities/repo_paths.sh"; \
fi; \
export REPO_ROOT="$${REPO_ROOT:-$${PWD}}"; \
export OBS_NICKEL="$${OBS_NICKEL:-$${REPO_ROOT}/packages/obs_nickel}"; \
export TESTDATA_NICKEL_DIR="$${TESTDATA_NICKEL_DIR:-$${REPO_ROOT}/packages/testdata}"; \
export REPO="$${REPO:-}"; \
export LSST_CONDA_ENV_NAME="$${LSST_CONDA_ENV_NAME:-}";
endef

define envsource
$(load_envs)
endef

define setup_stack
$(load_envs); \
if [ -f "$${STACK_DIR}/loadLSST.zsh" ]; then \
	source "$${STACK_DIR}/loadLSST.zsh"; \
	setup lsst_distrib; \
	if [[ -d "$${OBS_NICKEL}/ups" ]]; then eups declare -r "$${OBS_NICKEL}" obs_nickel -t current 2>/dev/null || true; fi; \
	setup obs_nickel; \
	if [[ -d "$${REPO_ROOT}/packages/obs_nickel_data/ups" ]]; then eups declare -r "$${REPO_ROOT}/packages/obs_nickel_data" obs_nickel_data -t current 2>/dev/null || true; fi; \
	setup obs_nickel_data; \
	if [[ -d "$${TESTDATA_NICKEL_DIR}/ups" ]]; then eups declare -r "$${TESTDATA_NICKEL_DIR}" testdata_nickel -t current 2>/dev/null || true; fi; \
	setup testdata_nickel; \
elif [ -f "$${STACK_DIR}/loadLSST.bash" ]; then \
	source "$${STACK_DIR}/loadLSST.bash"; \
	setup lsst_distrib; \
	if [[ -d "$${OBS_NICKEL}/ups" ]]; then eups declare -r "$${OBS_NICKEL}" obs_nickel -t current 2>/dev/null || true; fi; \
	setup obs_nickel; \
	if [[ -d "$${REPO_ROOT}/packages/obs_nickel_data/ups" ]]; then eups declare -r "$${REPO_ROOT}/packages/obs_nickel_data" obs_nickel_data -t current 2>/dev/null || true; fi; \
	setup obs_nickel_data; \
	if [[ -d "$${TESTDATA_NICKEL_DIR}/ups" ]]; then eups declare -r "$${TESTDATA_NICKEL_DIR}" testdata_nickel -t current 2>/dev/null || true; fi; \
	setup testdata_nickel; \
else \
	echo "Warning: LSST stack not found at $${STACK_DIR}"; \
fi;
endef

.PHONY: setup-dev
setup-dev: ## Install all packages in editable mode with dev tools
	uv sync --group dev

.PHONY: setup-dev-full
setup-dev-full: ## Install all packages + notebooks + analysis tools
	uv sync --all-groups

.PHONY: bootstrap
bootstrap: ## Bootstrap Butler repo + refcats + skymap
	$(SHELL) -lc '$(setup_stack) ./scripts/pipeline/00_bootstrap_repo.sh'

.PHONY: archive-night
archive-night: ## Download a night from the archive (NIGHT=YYYYMMDD)
ifndef NIGHT
	$(error NIGHT is required, e.g. NIGHT=20201207)
endif
	$(SHELL) -lc '$(envsource) ./scripts/pipeline/01_download_archive.sh --night $(NIGHT)'

.PHONY: calibs
calibs: ## Run nightly calibrations (bias/flat/defects). NIGHT=YYYYMMDD
ifndef NIGHT
	$(error NIGHT is required, e.g. NIGHT=20201207)
endif
	$(SHELL) -lc '$(setup_stack) ./scripts/pipeline/10_calibs.sh --night $(NIGHT)'

.PHONY: science
science: ## Run single-night science processing. NIGHT=YYYYMMDD
ifndef NIGHT
	$(error NIGHT is required, e.g. NIGHT=20201207)
endif
	$(SHELL) -lc '$(setup_stack) ./scripts/pipeline/20_science.sh --night $(NIGHT) $(SCIENCE_ARGS)'

.PHONY: coadds
coadds: ## Build coadds/templates. Requires TRACT and BAND (e.g. BAND=r).
ifndef TRACT
	$(error TRACT is required, e.g. TRACT=1099)
endif
ifndef BAND
	$(error BAND is required, e.g. BAND=r)
endif
	$(SHELL) -lc '$(setup_stack) ./scripts/pipeline/30_coadds.sh --tract $(TRACT) --band $(BAND) $(COADD_ARGS)'

.PHONY: dia
dia: ## Run DIA for a night. NIGHT=YYYYMMDD
ifndef NIGHT
	$(error NIGHT is required, e.g. NIGHT=20201207)
endif
	$(SHELL) -lc '$(setup_stack) ./scripts/pipeline/40_diff_imaging.sh --night $(NIGHT) $(DIA_ARGS)'

.PHONY: dia-multiband
dia-multiband: ## Run multi-band DIA helper (wraps run_dia_multi_band.sh)
	$(SHELL) -lc '$(setup_stack) ./scripts/pipeline/run_dia_multi_band.sh $(ARGS)'

.PHONY: forced-phot
forced-phot: ## Run forced photometry for a night. NIGHT=YYYYMMDD [BAND=r]
ifndef NIGHT
	$(error NIGHT is required, e.g. NIGHT=20201207)
endif
	$(SHELL) -lc '$(setup_stack) ./scripts/pipeline/45_forced_photometry.sh --night $(NIGHT) $(if $(BAND),--band $(BAND),) $(FORCED_PHOT_ARGS)'

.PHONY: forced-phot-radec
forced-phot-radec: ## Forced photometry at RA/Dec. NIGHT=YYYYMMDD RA=deg DEC=deg [IMAGE_TYPE=both|visit|diffim]
ifndef NIGHT
	$(error NIGHT is required, e.g. NIGHT=20201207)
endif
ifndef RA
	$(error RA is required in degrees, e.g. RA=185.7285)
endif
ifndef DEC
	$(error DEC is required in degrees, e.g. DEC=15.8225)
endif
	$(SHELL) -lc '$(setup_stack) ./scripts/pipeline/46_forced_photometry_radec.sh --night $(NIGHT) --ra $(RA) --dec $(DEC) $(if $(IMAGE_TYPE),--image-type $(IMAGE_TYPE),) $(if $(BAND),--band $(BAND),) $(FORCED_PHOT_RADEC_ARGS)'

.PHONY: forced-phot-radec-file
forced-phot-radec-file: ## Forced photometry from coordinate file. NIGHT=YYYYMMDD COORDS_FILE=targets.csv
ifndef NIGHT
	$(error NIGHT is required, e.g. NIGHT=20201207)
endif
ifndef COORDS_FILE
	$(error COORDS_FILE is required, e.g. COORDS_FILE=targets.csv)
endif
	$(SHELL) -lc '$(setup_stack) ./scripts/pipeline/46_forced_photometry_radec.sh --night $(NIGHT) --coords-file $(COORDS_FILE) $(if $(IMAGE_TYPE),--image-type $(IMAGE_TYPE),) $(if $(BAND),--band $(BAND),) $(FORCED_PHOT_RADEC_ARGS)'

.PHONY: refcat-cones
refcat-cones: ## Generate cones.csv + htm7_list.txt via nickel-refcats (pass ARGS="--ras ... --decs ...")
	$(SHELL) -lc 'cd $(PWD) && $(setup_stack) \
		PYTHONPATH=$${PYTHONPATH}:$${PWD}/packages/refcats/src python -u -m nickel_refcats cones $(ARGS)'

.PHONY: declare-eups
declare-eups: ## Declare obs_nickel, obs_nickel_data, and testdata_nickel in the current stack (uses STACK_DIR and env files)
	$(SHELL) -lc '$(envsource) \
	  if [ -f "$${STACK_DIR}/loadLSST.zsh" ]; then source "$${STACK_DIR}/loadLSST.zsh"; \
	  elif [ -f "$${STACK_DIR}/loadLSST.bash" ]; then source "$${STACK_DIR}/loadLSST.bash"; \
	  else echo "STACK_DIR loader not found (loadLSST)"; exit 1; fi; \
	  cd "$(PWD)/packages/obs_nickel" && eups declare obs_nickel git -r . -t current || true; \
	  cd "$(PWD)/packages/obs_nickel_data" && eups declare obs_nickel_data git -r . -t current || true; \
	  cd "$(PWD)/packages/testdata" && eups declare testdata_nickel git -r . -t current 2>/dev/null || true'

.PHONY: batch
batch: ## Batch process nights file. NIGHTS_FILE=path/to/nights.txt
ifndef NIGHTS_FILE
	$(error NIGHTS_FILE is required)
endif
	$(SHELL) -lc '$(setup_stack) ./scripts/pipeline/batch_process_nights.sh --nights-file $(NIGHTS_FILE) $(BATCH_ARGS)'

.PHONY: transient-pipeline
transient-pipeline: ## Run the full transient pipeline wrapper (run_full_transient_pipeline.sh)
	$(SHELL) -lc '$(setup_stack) ./scripts/pipeline/run_full_transient_pipeline.sh $(ARGS)'

.PHONY: stack-install
stack-install: ## Install an LSST stack release (TAG=w_2025_10 or r_28_0_0). Does not touch existing stack.
ifndef TAG
	$(error TAG is required, e.g. TAG=w_2025_10)
endif
	$(SHELL) -lc '$(envsource) \
	  prefix="$${STACK_PREFIX:-}"; \
	  if [[ -z "$$prefix" && -n "$$STACK_DIR" ]]; then prefix="$$STACK_DIR"; fi; \
	  if [[ -z "$$prefix" ]]; then prefix="$$HOME/lsst_stacks"; fi; \
	  ./scripts/utilities/install_stack_version.sh --release $(TAG) --prefix "$$prefix" $(if $(INSTALL_DISTRIB),--install-distrib,)'

.PHONY: lint
lint: ## Ruff lint across the workspace
	$(PYTHON) -m ruff check .

.PHONY: format
format: ## Ruff format across the workspace
	$(PYTHON) -m ruff format .

.PHONY: test
test: ## Run pytest suite (requires stack env)
	$(SHELL) -lc '$(setup_stack) PYTHONPATH=$${PYTHONPATH}:$${OBS_NICKEL}/python python -m pytest -q'

.PHONY: notebook
notebook: ## Start Jupyter Lab with LSST stack + UV venv active
	@echo "Starting Jupyter Lab with LSST stack..."
	@echo "Note: You may need to select the .venv kernel in Jupyter"
	$(SHELL) -lc '$(setup_stack) source .venv/bin/activate && jupyter lab'

.PHONY: env-info
env-info: ## Show which env file(s) will be loaded and key paths
	$(SHELL) -lc '$(load_envs); \
		echo "ENV_FILE=$(ENV_FILE)"; \
		echo "EXTRA_ENV=$(EXTRA_ENV)"; \
		printf "REPO_ROOT=%s\nSTACK_DIR=%s\nREPO=%s\nOBS_NICKEL=%s\nCP_PIPE_DIR=%s\nLSST_CONDA_ENV_NAME=%s\n" \
			"$${REPO_ROOT:-<unset>}" "$${STACK_DIR:-<unset>}" "$${REPO:-<unset>}" "$${OBS_NICKEL:-<unset>}" "$${CP_PIPE_DIR:-<unset>}" "$${LSST_CONDA_ENV_NAME:-<unset>}"; \
	'

.PHONY: help
help: ## Show this help message
	@echo "Nickel Processing Suite - Available targets:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
