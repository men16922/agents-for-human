# Rehearsal setup and offline checks. Model calls are explicit.
.DEFAULT_GOAL := check
.PHONY: commerce-reaction-ui-smoke
commerce-reaction-ui-smoke:
	$(DEV) uv run --offline --no-sync python scripts/commerce/reaction_ui_smoke.py

.PHONY: commerce-demo
commerce-demo:
	$(DEV) uv run --offline --no-sync python scripts/commerce/reaction_ui_smoke.py --inspect

.PHONY: commerce-reaction-video
commerce-reaction-video:
	REHEARSAL_RECORD_VIDEO=1 $(DEV) uv run --offline --no-sync python scripts/commerce/reaction_ui_smoke.py

PYTHON ?= python3
DEV := scripts/dev/with-env.sh
.PHONY: check check-docs check-dev check-browser doctor setup setup-tooling setup-deps setup-browser init-env dev commerce commerce-smoke commerce-contract world-smoke world-fixtures agent-preflight agent-run policy-smoke operating operating-smoke operating-sdk-smoke help

help:
	@echo "make setup           Install pinned repo-local runtimes and locked dependencies"
	@echo "make check           Offline docs, imports, lint, types, tests and web build"
	@echo "make check-browser   Local browser behavior checks; no model calls"
	@echo "make dev             API + React development shell (Ctrl+C to stop)"
	@echo "make commerce        Independent Medusa + DB services (Ctrl+C to stop)"
	@echo "make commerce-smoke  Check the optional local Medusa backend"

setup-tooling:
	$(PYTHON) scripts/dev/tooling.py

setup-deps:
	$(DEV) uv sync --locked
	$(DEV) npm ci --no-audit

setup-browser:
	$(DEV) npx --no-install playwright install chromium

init-env:
	$(PYTHON) scripts/dev/local.py init-env

setup: setup-tooling
	$(MAKE) setup-deps
	$(MAKE) setup-browser
	$(MAKE) init-env
	$(MAKE) check

doctor:
	$(DEV) python3 scripts/dev/doctor.py

check-docs:
	$(PYTHON) scripts/check.py

check-dev: doctor
	$(DEV) uv lock --check --offline
	$(DEV) uv run --offline --no-sync ruff check src tests scripts/dev scripts/commerce
	$(DEV) uv run --offline --no-sync mypy
	$(DEV) uv run --offline --no-sync pytest
	$(DEV) npm run build:web

check: check-docs check-dev

check-browser: doctor
	$(DEV) npm run test:browser

dev:
	$(DEV) uv run --offline --no-sync python scripts/dev/local.py dev

commerce:
	$(DEV) uv run --offline --no-sync python scripts/dev/local.py commerce

include scripts/commerce/targets.mk
-include .local/harness-targets.mk
