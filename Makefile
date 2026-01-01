SHELL := /bin/bash
ENV_FILE ?= .env
PYTHON ?= python
PIP ?= $(PYTHON) -m pip
PACKAGES := packages/obs_nickel packages/archive_tools packages/defects packages/refcats packages/testdata packages/tuning packages/colorterms

# Multi-repo support: Allow REPO override via environment variable
# Usage: REPO=/path/to/repo2 make calibs NIGHT=20240625
# Or:    ENV_FILE=repo2.env make calibs NIGHT=20240625
define envsource
if [ -f "$(ENV_FILE)" ]; then \
	source $(ENV_FILE); \
elif [ "$(ENV_FILE)" != ".env" ]; then \
	echo "Warning: ENV_FILE=$(ENV_FILE) not found, using defaults"; \
fi; \
export REPO="$${REPO:-}";
endef

define setup_stack
if [ -f "$(ENV_FILE)" ]; then \
	set -a; source $(ENV_FILE); set +a; \
elif [ "$(ENV_FILE)" != ".env" ]; then \
	echo "Warning: ENV_FILE=$(ENV_FILE) not found"; \
fi; \
export REPO="$${REPO:-}"; \
if [ -f "$${STACK_DIR}/loadLSST.zsh" ]; then \
	source "$${STACK_DIR}/loadLSST.zsh"; \
	setup lsst_distrib; \
	setup obs_nickel; \
	setup testdata_nickel; \
elif [ -f "$${STACK_DIR}/loadLSST.bash" ]; then \
	source "$${STACK_DIR}/loadLSST.bash"; \
	setup lsst_distrib; \
	setup obs_nickel; \
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
	$(SHELL) -lc '$(envsource); \
	  prefix="$${STACK_PREFIX:-}"; \
	  if [[ -z "$$prefix" && -n "$$STACK_DIR" ]]; then prefix="$$STACK_DIR"; fi; \
	  if [[ -z "$$prefix" ]]; then prefix="$$HOME/lsst_stacks"; fi; \
	  ./scripts/utilities/install_stack_version.sh --release $(TAG) --prefix "$$prefix"'

.PHONY: lint
lint: ## Ruff lint across the workspace
	$(PYTHON) -m ruff check .

.PHONY: format
format: ## Ruff format across the workspace
	$(PYTHON) -m ruff format .

.PHONY: test
test: ## Run pytest suite (requires stack env)
	$(SHELL) -lc '$(setup_stack) export OBS_NICKEL_DIR=$${PWD}/packages/obs_nickel && export TESTDATA_NICKEL_DIR=$${PWD}/packages/testdata/data && PYTHONPATH=$${PYTHONPATH}:packages/obs_nickel/python python -m pytest -q'

.PHONY: notebook
notebook: ## Start Jupyter Lab with LSST stack + UV venv active
	@echo "Starting Jupyter Lab with LSST stack..."
	@echo "Note: You may need to select the .venv kernel in Jupyter"
	$(SHELL) -lc '$(setup_stack) source .venv/bin/activate && jupyter lab'

.PHONY: help
help: ## Show this help message
	@echo "Nickel Processing Suite - Available targets:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
