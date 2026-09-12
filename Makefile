# Development foundation. Network installation is explicit; check stays offline.
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
.PHONY: check check-docs check-dev check-browser doctor setup setup-tooling setup-deps setup-browser init-env dev commerce commerce-smoke commerce-contract world-smoke world-fixtures agent-preflight agent-run policy-smoke operating operating-smoke operating-sdk-smoke smoke-local help

help:
	@echo "make setup           Install pinned repo-local runtimes and locked dependencies"
	@echo "make check           Offline docs, imports, lint, types, tests and web build"
	@echo "make check-browser   Local browser behavior checks; no model calls"
	@echo "make dev             API + React development shell (Ctrl+C to stop)"
	@echo "make commerce        Independent Medusa + DB services (Ctrl+C to stop)"
	@echo "make commerce-smoke  Migrate, verify health, stop owned services"

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

operating:
	$(DEV) uv run --offline --no-sync python -m rehearsal.operating.local

operating-sdk-smoke:
	$(DEV) uv run --offline --no-sync python scripts/dev/operating_sdk.py

operating-smoke:
	$(DEV) uv run --offline --no-sync python -m rehearsal.operating.local --smoke

policy-smoke:
	$(DEV) uv run --offline --no-sync python -m rehearsal.experiments.rehearse

.PHONY: review-smoke review-preflight
review-smoke:
	$(DEV) uv run --offline --no-sync python -m rehearsal.experiments.review_runner --offline-fixture

review-preflight:
	$(DEV) uv run --offline --no-sync python -m rehearsal.experiments.review_runner

.PHONY: b3-smoke b3-preflight
b3-smoke:
	$(DEV) uv run --offline --no-sync python -m rehearsal.experiments.b3 --offline-fixture

b3-preflight:
	$(DEV) uv run --offline --no-sync python -m rehearsal.experiments.b3

.PHONY: pilot-smoke
pilot-smoke:
	$(DEV) uv run --offline --no-sync python -m rehearsal.evaluation.pilot

.PHONY: b2-smoke b2-preflight
b2-smoke:
	$(DEV) uv run --offline --no-sync python -m rehearsal.experiments.b2 --offline-fixture

b2-preflight:
	$(DEV) uv run --offline --no-sync python -m rehearsal.experiments.b2

.PHONY: frozen-evaluation-smoke frozen-evaluation-preflight
frozen-evaluation-smoke:
	$(DEV) uv run --offline --no-sync python -m rehearsal.evaluation.frozen_run --offline-fixture

frozen-evaluation-preflight:
	$(DEV) uv run --offline --no-sync python -m rehearsal.evaluation.frozen_run

.PHONY: evaluation-batch-smoke
evaluation-batch-smoke:
	$(DEV) uv run --offline --no-sync python -m rehearsal.evaluation.batch --offline-fixture

agent-preflight:
	$(DEV) uv run --offline --no-sync python -m rehearsal.agents.runner

agent-run:
	$(DEV) uv run --offline --no-sync python -m rehearsal.agents.runner --execute

world-fixtures:
	$(DEV) uv run --offline --no-sync python -m rehearsal.evaluation.fixtures

world-smoke:
	$(DEV) uv run --offline --no-sync python -m rehearsal.world.demo

commerce-contract:
	$(DEV) uv run --offline --no-sync python scripts/commerce/contract_spike.py

.PHONY: commerce-adapter-smoke
commerce-adapter-smoke:
	$(DEV) uv run --offline --no-sync python scripts/commerce/adapter_smoke.py

.PHONY: commerce-operating-smoke
commerce-operating-smoke:
	$(DEV) uv run --offline --no-sync python scripts/commerce/operating_smoke.py

.PHONY: commerce-transfer-smoke
commerce-transfer-smoke:
	$(DEV) uv run --offline --no-sync python scripts/commerce/transfer_smoke.py

.PHONY: commerce-model-smoke
commerce-model-smoke:
	$(DEV) uv run --offline --no-sync python scripts/commerce/model_smoke.py

.PHONY: commerce-model-session-preflight
commerce-model-session-preflight:
	$(DEV) uv run --offline --no-sync python scripts/commerce/model_session.py

.PHONY: commerce-notification-smoke
commerce-notification-smoke:
	$(DEV) uv run --offline --no-sync python scripts/commerce/notification_smoke.py

.PHONY: commerce-stock-smoke
commerce-stock-smoke:
	$(DEV) uv run --offline --no-sync python scripts/commerce/stock_smoke.py

.PHONY: commerce-supplier-smoke
commerce-supplier-smoke:
	$(DEV) uv run --offline --no-sync python scripts/commerce/supplier_smoke.py

.PHONY: commerce-observer-smoke
commerce-observer-smoke:
	$(DEV) uv run --offline --no-sync python scripts/commerce/observer_smoke.py

.PHONY: commerce-convergence-smoke
commerce-convergence-smoke:
	$(DEV) uv run --offline --no-sync python scripts/commerce/convergence_smoke.py

.PHONY: commerce-race-smoke
commerce-race-smoke:
	$(DEV) uv run --offline --no-sync python scripts/commerce/race_smoke.py

commerce-smoke:
	$(DEV) uv run --offline --no-sync python scripts/dev/local.py commerce-smoke

smoke-local: check _harness-guard
	bash "$(HARNESS_ROOT)/bin/harness-init.sh" --check
	$(MAKE) overnight-where

# ===== overnight harness targets (append to your Makefile) =====
# The overnight runner + helpers are the Single Source of Truth in the overnight-harness
# PLUGIN; this repo does NOT vendor them. These targets resolve the installed plugin at
# runtime and invoke its runner against THIS repo. Per-repo STATE stays here:
#   scripts/overnight/overnight-settings.json  — Claude permission boundary
#   scripts/overnight/opencode.json            — opencode permission boundary
#   .codex/rules/overnight.rules               — Codex command rules
#   scripts/overnight/PROMPT.md                — optional per-repo prompt override (else plugin default)
#   scripts/overnight/{logs,STOP,DONE}         — runtime state
#   docs/LESSONS.md                            — the actor's memory surface (committed)
#
# The loop's commit gate is $GATE_CMD (default `make check`). Define a `check` target that proves
# correctness OFFLINE + DETERMINISTICALLY and allow-list it in scripts/overnight/overnight-settings.json.
#
# Select the engine with ENGINE=claude|codex|opencode|agy|kiro. Default stays Claude.
ENGINE ?= claude

# Model routing (1.4.0, Claude engine). The actor does bounded implementation; the critic is a
# read-only reviewer whose judgment is what you pay for. Blank = the CLI's own default. These
# are per-repo policy, so edit them here rather than in the plugin.
CLAUDE_MODEL ?=
CLAUDE_EFFORT ?=
CLAUDE_CRITIC_MODEL ?=
OVERNIGHT_CRITIC_MODEL ?=
CLAUDE_CRITIC_EFFORT ?=
export CLAUDE_MODEL CLAUDE_EFFORT CLAUDE_CRITIC_MODEL OVERNIGHT_CRITIC_MODEL CLAUDE_CRITIC_EFFORT

# Codex routing is opt-in; preserve installed model/effort settings when blank.
# Astra preset: make overnight-codex-once CODEX_MODEL=gpt-6-astra
CODEX_MODEL ?=
CODEX_EFFORT ?=
CODEX_CRITIC_EFFORT ?=
export CODEX_MODEL CODEX_EFFORT CODEX_CRITIC_EFFORT

# HARNESS_ROOT resolution (env override → per-repo pin → highest installed version). This mirrors
# the plugin's bin/harness-locate.sh; override ad hoc with `make overnight HARNESS_ROOT=/path`.
HARNESS_ROOT ?= $(shell \
  if [ -n "$$OVERNIGHT_HARNESS_ROOT" ] && [ -d "$$OVERNIGHT_HARNESS_ROOT/templates/scripts/overnight" ]; then \
    echo "$$OVERNIGHT_HARNESS_ROOT"; \
  elif [ -n "$$OVERNIGHT_HARNESS_ROOT" ] && [ -d "$$OVERNIGHT_HARNESS_ROOT/plugins/overnight-harness/templates/scripts/overnight" ]; then \
    echo "$$OVERNIGHT_HARNESS_ROOT/plugins/overnight-harness"; \
  elif [ -f .claude/harness-config.json ] && grep -q '"harness_root"' .claude/harness-config.json; then \
    pin="$$(sed -n 's/.*"harness_root"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' .claude/harness-config.json | head -1)"; \
    if [ -d "$$pin/templates/scripts/overnight" ]; then echo "$$pin"; \
    elif [ -d "$$pin/plugins/overnight-harness/templates/scripts/overnight" ]; then echo "$$pin/plugins/overnight-harness"; fi; \
  else \
    { \
      ls -d $$HOME/.claude/plugins/cache/overnight-harness/overnight-harness/*/ 2>/dev/null; \
      find $$HOME/.codex/plugins/cache -path '*/overnight-harness/*' -type d 2>/dev/null; \
      [ -d $$HOME/.gemini/antigravity-cli/plugins/overnight-harness ] && echo $$HOME/.gemini/antigravity-cli/plugins/overnight-harness; \
      [ -d $$HOME/.cache/opencode/node_modules/opencode-overnight-harness ] && echo $$HOME/.cache/opencode/node_modules/opencode-overnight-harness; \
    } | while read d; do [ -d "$$d/templates/scripts/overnight" ] && echo "$$d"; done | sort -V | tail -1; \
  fi)

# OVN_SRC = runner + helpers (in the plugin); OVN = per-repo state (in this repo).
# NB: no inline comments on these := lines — make would fold the gap into the value.
OVN_SRC := $(HARNESS_ROOT:%/=%)/templates/scripts/overnight
OVN := scripts/overnight

_harness-guard:
	@test -x "$(OVN_SRC)/run.sh" || { \
	  echo "overnight-harness not found (resolved HARNESS_ROOT='$(HARNESS_ROOT)')."; \
	  echo "Install the plugin, or pass HARNESS_ROOT=/path/to/plugin, or re-run /harness-init."; \
	  exit 1; }

overnight: _harness-guard           ## run the unattended loop (caffeinate keeps macOS awake)
	OVERNIGHT_ENGINE=$(ENGINE) caffeinate -dimsu $(OVN_SRC)/run.sh &
overnight-watch: overnight          ## start the loop and tail its log
	@sleep 1; tail -f $(OVN)/logs/runner.log
overnight-once: _harness-guard      ## single iteration (smoke test the loop)
	OVERNIGHT_ENGINE=$(ENGINE) $(OVN_SRC)/run.sh --once
overnight-claude-once: _harness-guard
	OVERNIGHT_ENGINE=claude $(OVN_SRC)/run.sh --once
overnight-codex-once: _harness-guard
	OVERNIGHT_ENGINE=codex $(OVN_SRC)/run.sh --once
overnight-opencode-once: _harness-guard
	OVERNIGHT_ENGINE=opencode $(OVN_SRC)/run.sh --once
overnight-agy-once: _harness-guard
	OVERNIGHT_ENGINE=agy $(OVN_SRC)/run.sh --once
overnight-kiro-once: _harness-guard
	OVERNIGHT_ENGINE=kiro $(OVN_SRC)/run.sh --once
overnight-stop:                     ## graceful stop after the current iteration
	@touch $(OVN)/STOP && echo "STOP created — loop will exit after current iteration"
overnight-clean:                    ## clear STOP/DONE sentinels before the next run
	@rm -f $(OVN)/STOP $(OVN)/DONE && echo "cleared STOP/DONE"
overnight-status: _harness-guard    ## aggregate iteration status across lanes
	@bash $(OVN_SRC)/status.sh
overnight-logs:                     ## tail the runner log
	@mkdir -p $(OVN)/logs; touch $(OVN)/logs/runner.log; tail -f $(OVN)/logs/runner.log
overnight-dashboard: _harness-guard ## tmux dashboard (falls back to status.sh)
	@bash $(OVN_SRC)/dashboard.sh
overnight-ledger-check: _harness-guard ## validate event history before trusting status/report
	@python3 $(OVN_SRC)/lib/ledger.py check $(OVN)/logs/events.jsonl
overnight-ledger-state: _harness-guard ## project deterministic per-mission state as JSON
	@python3 $(OVN_SRC)/lib/ledger.py project $(OVN)/logs/events.jsonl
overnight-trajectory: _harness-guard ## render causal node/edge trajectory; optional MISSION and FORMAT=json
	@python3 $(OVN_SRC)/lib/trajectory.py $(OVN)/logs/events.jsonl \
	  $(if $(MISSION),--mission "$(MISSION)",) --format "$(or $(FORMAT),text)"
overnight-resume: _harness-guard       ## resume MISSION with DECISION=approve|reject
	@test -x "$(OVN_SRC)/resume.sh" || { echo "installed overnight-harness does not provide resume.sh"; exit 1; }
	@test -n "$(MISSION)" || { echo "MISSION=<mission-id> is required"; exit 2; }
	@test "$(DECISION)" = "approve" -o "$(DECISION)" = "reject" || { echo "DECISION=approve|reject is required"; exit 2; }
	@HARNESS_REPO_ROOT="$(CURDIR)" bash $(OVN_SRC)/resume.sh "$(MISSION)" --"$(DECISION)"
overnight-provenance-compare: _harness-guard ## compare two manifests; optional LEFT_RESULT/RIGHT_RESULT
	@test -n "$(LEFT)" -a -n "$(RIGHT)" || { echo "LEFT=<manifest> and RIGHT=<manifest> are required"; exit 2; }
	@python3 $(OVN_SRC)/lib/provenance.py compare --left "$(LEFT)" --right "$(RIGHT)" \
	  --left-result "$(LEFT_RESULT)" --right-result "$(RIGHT_RESULT)"
overnight-where:                    ## print the resolved plugin location (debug)
	@echo "HARNESS_ROOT = $(HARNESS_ROOT)"; echo "runner       = $(OVN_SRC)/run.sh"

.PHONY: overnight overnight-watch overnight-once overnight-claude-once overnight-codex-once overnight-opencode-once overnight-agy-once overnight-kiro-once overnight-stop overnight-clean overnight-status overnight-logs overnight-dashboard overnight-ledger-check overnight-ledger-state overnight-trajectory overnight-resume overnight-provenance-compare overnight-where _harness-guard
# ===== end overnight harness targets =====

.PHONY: commerce-learning-smoke
commerce-learning-smoke:
	@scripts/dev/with-env.sh uv run --offline python scripts/commerce/learning_smoke.py

.PHONY: external-batch-smoke
external-batch-smoke:
	@scripts/dev/with-env.sh uv run --offline python scripts/commerce/external_batch_smoke.py

.PHONY: external-arms-smoke
external-arms-smoke:
	@scripts/dev/with-env.sh uv run --offline python scripts/commerce/all_arms_smoke.py

.PHONY: external-conditions-smoke
external-conditions-smoke:
	@scripts/dev/with-env.sh uv run --offline python scripts/commerce/conditions_smoke.py

.PHONY: external-events-smoke
external-events-smoke:
	$(DEV) uv run --offline --no-sync python scripts/commerce/events_smoke.py

.PHONY: commerce-delivery-smoke
commerce-delivery-smoke:
	$(DEV) uv run --offline --no-sync python scripts/commerce/delivery_smoke.py

.PHONY: external-response-smoke
external-response-smoke:
	$(DEV) uv run --offline --no-sync python scripts/commerce/response_smoke.py

.PHONY: external-notification-smoke
external-notification-smoke:
	$(DEV) uv run --offline --no-sync python scripts/commerce/notification_events_smoke.py

.PHONY: commerce-reaction-smoke
commerce-reaction-smoke:
	$(DEV) uv run --offline --no-sync python scripts/commerce/reaction_smoke.py

.PHONY: external-reaction-smoke
external-reaction-smoke:
	$(DEV) uv run --offline --no-sync python scripts/commerce/reaction_batch_smoke.py

.PHONY: commerce-latency-smoke
commerce-latency-smoke:
	$(DEV) uv run --offline --no-sync python scripts/commerce/latency_smoke.py
