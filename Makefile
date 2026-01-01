SHELL := /bin/bash
ENV_FILE ?= .env
PYTHON ?= python
PIP ?= $(PYTHON) -m pip
PACKAGES := packages/obs_nickel packages/archive_tools packages/defects packages/refcats packages/testdata
STACK_PREFIX ?= $(HOME)/lsst_stacks

define envsource
source $(ENV_FILE) 2>/dev/null || true;
endef

.PHONY: setup-dev
setup-dev: ## Install all packages in editable mode
	$(PIP) install -e $(PACKAGES)

.PHONY: bootstrap
bootstrap: ## Bootstrap Butler repo + refcats + skymap
	$(SHELL) -lc '$(envsource) ./scripts/pipeline/00_bootstrap_repo.sh'

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
	$(SHELL) -lc '$(envsource) ./scripts/pipeline/10_calibs.sh --night $(NIGHT)'

.PHONY: science
science: ## Run single-night science processing. NIGHT=YYYYMMDD
ifndef NIGHT
	$(error NIGHT is required, e.g. NIGHT=20201207)
endif
	$(SHELL) -lc '$(envsource) ./scripts/pipeline/20_science.sh --night $(NIGHT) $(SCIENCE_ARGS)'

.PHONY: coadds
coadds: ## Build coadds/templates. Requires TRACT and BAND (e.g. BAND=r).
ifndef TRACT
	$(error TRACT is required, e.g. TRACT=1099)
endif
ifndef BAND
	$(error BAND is required, e.g. BAND=r)
endif
	$(SHELL) -lc '$(envsource) ./scripts/pipeline/30_coadds.sh --tract $(TRACT) --band $(BAND) $(COADD_ARGS)'

.PHONY: dia
dia: ## Run DIA for a night. NIGHT=YYYYMMDD
ifndef NIGHT
	$(error NIGHT is required, e.g. NIGHT=20201207)
endif
	$(SHELL) -lc '$(envsource) ./scripts/pipeline/40_diff_imaging.sh --night $(NIGHT) $(DIA_ARGS)'

.PHONY: dia-multiband
dia-multiband: ## Run multi-band DIA helper (wraps run_dia_multi_band.sh)
	$(SHELL) -lc '$(envsource) ./scripts/pipeline/run_dia_multi_band.sh $(ARGS)'

.PHONY: batch
batch: ## Batch process nights file. NIGHTS_FILE=path/to/nights.txt
ifndef NIGHTS_FILE
	$(error NIGHTS_FILE is required)
endif
	$(SHELL) -lc '$(envsource) ./scripts/pipeline/batch_process_nights.sh --nights-file $(NIGHTS_FILE) $(BATCH_ARGS)'

.PHONY: transient-pipeline
transient-pipeline: ## Run the full transient pipeline wrapper (run_full_transient_pipeline.sh)
	$(SHELL) -lc '$(envsource) ./scripts/pipeline/run_full_transient_pipeline.sh $(ARGS)'

.PHONY: stack-install
stack-install: ## Install an LSST stack release (TAG=w_2025_10 or r_28_0_0). Does not touch existing stack.
ifndef TAG
	$(error TAG is required, e.g. TAG=w_2025_10)
endif
	$(SHELL) -lc './scripts/utilities/install_stack_version.sh --release $(TAG) --prefix $(STACK_PREFIX)'

.PHONY: lint
lint: ## Ruff lint across the workspace
	$(PYTHON) -m ruff check .

.PHONY: format
format: ## Ruff format across the workspace
	$(PYTHON) -m ruff format .

.PHONY: test
test: ## Run pytest suite (requires stack env)
	$(SHELL) -lc '$(envsource) pytest -q'
