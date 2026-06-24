SHELL := /bin/bash
ENV_FILE ?= .env
EXTRA_ENV ?=
PYTHON ?= python
PIP ?= $(PYTHON) -m pip

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
export INSTRUMENT_DIR="$${INSTRUMENT_DIR:-$${REPO_ROOT}/instruments/nickel}"; \
export TESTDATA_NICKEL_DIR="$${TESTDATA_NICKEL_DIR:-$${REPO_ROOT}/packages/testdata}"; \
export REPO="$${REPO:-}"; \
export LSST_CONDA_ENV_NAME="$${LSST_CONDA_ENV_NAME:-}"
endef

define envsource
$(load_envs)
endef

define setup_stack
$(load_envs); \
if [ -f "$${STACK_DIR}/loadLSST.zsh" ]; then \
	source "$${STACK_DIR}/loadLSST.zsh"; \
elif [ -f "$${STACK_DIR}/loadLSST.bash" ]; then \
	source "$${STACK_DIR}/loadLSST.bash"; \
else \
	echo "Error: LSST stack not found at $${STACK_DIR}" >&2; exit 1; \
fi; \
setup lsst_distrib; \
_setup_local() { [[ -d "$$1/ups" ]] && { eups declare -r "$$1" "$$2" -t current 2>/dev/null || true; setup "$$2" 2>/dev/null || setup -r "$$1" "$$2"; }; }; \
OBS_STIPS_LOCAL="$${REPO_ROOT}/packages/obs_stips"; \
OBS_NICKEL_DATA_LOCAL="$${REPO_ROOT}/packages/obs_nickel_data"; \
_setup_local "$$OBS_STIPS_LOCAL" obs_stips; \
_setup_local "$$OBS_NICKEL_DATA_LOCAL" obs_nickel_data; \
_setup_local "$${TESTDATA_NICKEL_DIR}" testdata_nickel; \
export PYTHONPATH="$${REPO_ROOT}/packages/stips/src:$${OBS_STIPS_LOCAL}/python:$${OBS_NICKEL_DATA_LOCAL}/python:$${PYTHONPATH:-}";
endef

# =============================================================================
# Development targets
# =============================================================================

.PHONY: setup-dev
setup-dev: ## Install all packages in editable mode with dev tools
	uv sync --group dev

.PHONY: setup-dev-full
setup-dev-full: ## Install all packages + notebooks + analysis tools
	uv sync --all-groups

# =============================================================================
# LSST stack targets
# =============================================================================

.PHONY: bootstrap
bootstrap: ## Bootstrap Butler repo + refcats + skymap
	$(SHELL) -lc '$(setup_stack) ./scripts/pipeline/00_bootstrap_repo.sh'

# Pipeline operations (calibs, science, DIA, fphot, lightcurve) are handled
# by the `stips` CLI. Run `stips --help` for usage, or use YAML-driven
# orchestration with `stips -c <config.yaml> run`.

.PHONY: refcat-cones
refcat-cones: ## Generate cones.csv + htm7_list.txt via nickel-refcats (pass ARGS="--ras ... --decs ...")
	$(SHELL) -lc 'cd $(PWD) && $(setup_stack) \
		PYTHONPATH=$${PYTHONPATH}:$${PWD}/packages/refcats/src python -u -m nickel_refcats cones $(ARGS)'

.PHONY: declare-eups
declare-eups: ## Declare obs_stips, obs_nickel_data, and testdata_nickel in the current stack (uses STACK_DIR and env files)
	$(SHELL) -lc '$(envsource) \
	  if [ -f "$${STACK_DIR}/loadLSST.zsh" ]; then source "$${STACK_DIR}/loadLSST.zsh"; \
	  elif [ -f "$${STACK_DIR}/loadLSST.bash" ]; then source "$${STACK_DIR}/loadLSST.bash"; \
	  else echo "STACK_DIR loader not found (loadLSST)"; exit 1; fi; \
	  cd "$(PWD)/packages/obs_stips" && eups declare obs_stips git -r . -t current || true; \
	  cd "$(PWD)/packages/obs_nickel_data" && eups declare obs_nickel_data git -r . -t current || true; \
	  cd "$(PWD)/packages/testdata" && eups declare testdata_nickel git -r . -t current 2>/dev/null || true'

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

# =============================================================================
# Linting & testing
# =============================================================================

.PHONY: lint
lint: ## Ruff lint across the workspace
	$(PYTHON) -m ruff check .

.PHONY: format
format: ## Ruff format across the workspace
	$(PYTHON) -m ruff format .

.PHONY: test
test: ## Run pytest suite (requires stack env)
	$(SHELL) -lc '$(setup_stack) python -m pytest -q packages/stips/tests packages/obs_stips/tests instruments/nickel/tests'

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
		printf "REPO_ROOT=%s\nSTACK_DIR=%s\nREPO=%s\nINSTRUMENT_DIR=%s\nCP_PIPE_DIR=%s\nLSST_CONDA_ENV_NAME=%s\n" \
			"$${REPO_ROOT:-<unset>}" "$${STACK_DIR:-<unset>}" "$${REPO:-<unset>}" "$${INSTRUMENT_DIR:-<unset>}" "$${CP_PIPE_DIR:-<unset>}" "$${LSST_CONDA_ENV_NAME:-<unset>}"; \
	'

# =============================================================================
# Docker targets
# =============================================================================

DOCKER_REGISTRY ?= ghcr.io
DOCKER_IMAGE ?= $(DOCKER_REGISTRY)/lick-observatory/nps
DOCKER_TAG ?= latest
LSST_TAG ?= v30_0_3

.PHONY: docker-build
docker-build: ## Build Docker image locally
	docker build -t $(DOCKER_IMAGE):$(DOCKER_TAG) \
		--build-arg LSST_TAG=$(LSST_TAG) \
		-f docker/Dockerfile .

.PHONY: docker-build-dev
docker-build-dev: ## Build Docker image for development (with source mounts)
	docker build -t nps:dev \
		--build-arg LSST_TAG=$(LSST_TAG) \
		-f docker/Dockerfile .

.PHONY: docker-push
docker-push: ## Push Docker image to registry
	docker push $(DOCKER_IMAGE):$(DOCKER_TAG)

.PHONY: docker-run
docker-run: ## Run NPS container interactively
ifndef REPO
	$(error REPO is required for docker-run)
endif
	docker run --rm -it \
		-v $(REPO):/data/repo \
		-v $(RAW_PARENT_DIR):/data/raw \
		-v $(REFCAT_REPO):/data/refcats:ro \
		$(DOCKER_IMAGE):$(DOCKER_TAG) \
		$(CMD)

.PHONY: docker-compose-up
docker-compose-up: ## Start services via docker-compose
	docker-compose -f docker/docker-compose.yml up -d

.PHONY: docker-compose-down
docker-compose-down: ## Stop services via docker-compose
	docker-compose -f docker/docker-compose.yml down

.PHONY: singularity-build
singularity-build: docker-build ## Build Singularity image from Docker
	singularity build nps.sif docker-daemon://$(DOCKER_IMAGE):$(DOCKER_TAG)

.PHONY: help
help: ## Show this help message
	@echo "STIPS (Small Telescope Image Processing Suite) - Available targets:"
	@echo ""
	@echo "  Pipeline operations use the 'stips' CLI. Run: stips --help"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
