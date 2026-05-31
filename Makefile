SHELL := /usr/bin/env bash

BASE_URL ?= http://localhost
PYTEST ?= pytest
RUFF ?= ruff
COMPOSE_FILE ?= docker-compose.prod.yml

.PHONY: preflight backend-check webapp-check compose-check smoke-webapp local-check ci-check vps-check

preflight:
	@scripts/preflight_check.sh

backend-check:
	@command -v $(PYTEST) >/dev/null 2>&1 || { echo "pytest is required. Activate the backend venv or install backend test dependencies."; exit 127; }
	@command -v $(RUFF) >/dev/null 2>&1 || { echo "ruff is required. Activate the backend venv or install backend lint dependencies."; exit 127; }
	cd backend && $(PYTEST)
	cd backend && $(RUFF) check .

webapp-check:
	@command -v npm >/dev/null 2>&1 || { echo "npm is required for webapp-check. Install Node.js/npm or run this check in CI/VPS."; exit 127; }
	cd webapp && npm ci
	cd webapp && npm run build

compose-check:
	@command -v docker >/dev/null 2>&1 || { echo "Docker is required for compose-check. Install Docker Desktop/Engine or run this check on VPS."; exit 127; }
	docker compose -f $(COMPOSE_FILE) config

smoke-webapp:
	@command -v curl >/dev/null 2>&1 || { echo "curl is required for smoke-webapp."; exit 127; }
	BASE_URL="$(BASE_URL)" scripts/smoke_test_webapp.sh

local-check: preflight backend-check webapp-check compose-check
	@echo "local-check passed. Production release still requires vps-check."

ci-check: backend-check webapp-check compose-check
	@echo "ci-check passed."

vps-check: compose-check
	@command -v curl >/dev/null 2>&1 || { echo "curl is required for vps-check."; exit 127; }
	@command -v jq >/dev/null 2>&1 || { echo "jq is required for vps-check."; exit 127; }
	BASE_URL="$(BASE_URL)" scripts/smoke_test_mvp.sh
	BASE_URL="$(BASE_URL)" scripts/smoke_test_bot_webhook.sh
	BASE_URL="$(BASE_URL)" scripts/smoke_test_reminders.sh
	BASE_URL="$(BASE_URL)" scripts/smoke_test_webapp.sh
	BASE_URL="$(BASE_URL)" scripts/smoke_test_max_sender.sh
	@echo "vps-check passed. Production release gate is complete."
