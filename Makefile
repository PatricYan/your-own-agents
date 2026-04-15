.PHONY: setup activate lint format test serve clean frontend help

CONDA_ENV = agentpipe
SHELL := /bin/bash

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

setup: ## Create conda env, install deps, install hooks, build frontend
	conda env create -f environment.yml || conda env update -f environment.yml --prune
	@echo ""
	@echo "Run: conda activate $(CONDA_ENV)"
	@echo "Then: make post-setup"

post-setup: ## Run after 'conda activate agentpipe' — installs hooks and builds frontend
	pre-commit install --hook-type pre-commit --hook-type commit-msg
	cd web/frontend && npm install && npm run build
	@echo ""
	@echo "Setup complete. Verify with: make check"

check: ## Verify everything works
	agentpipe --version
	ruff check src/
	pytest --tb=short
	agentpipe pipelines validate examples/01-hello-world.yaml
	@echo ""
	@echo "All checks passed."

lint: ## Run linter
	ruff check src/ tests/ --fix

format: ## Format code
	ruff format src/ tests/

test: ## Run tests
	pytest -v

serve: ## Start web UI + API server
	agentpipe serve

frontend: ## Build React frontend
	cd web/frontend && npm install && npm run build

clean: ## Remove conda env
	conda env remove -n $(CONDA_ENV) -y

update: ## Update conda env from environment.yml
	conda env update -f environment.yml --prune
