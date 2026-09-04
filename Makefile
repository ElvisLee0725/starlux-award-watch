# starlux-award-watch — common tasks.  Run `make` (or `make help`) for the list.
# The venv is created/updated automatically on first use; you never call
# .venv/bin/python yourself.

.DEFAULT_GOAL := help
VENV := .venv
PY   := $(VENV)/bin/python
PIP  := $(VENV)/bin/pip

# venv sentinel: (re)build it whenever pyproject.toml changes
$(PY): pyproject.toml
	python3 -m venv $(VENV)
	$(PIP) install -q --upgrade pip
	$(PIP) install -q -e ".[dev]"
	$(VENV)/bin/playwright install chromium
	@touch $(PY)
	@echo "venv ready."

.PHONY: setup
setup: $(PY) ## create the venv + install deps and Chromium
	@test -f .env || (cp .env.example .env && echo "created .env — fill in PUSHOVER_* then run 'make warm'")

.PHONY: warm
warm: $(PY) ## open the profile browser to clear an Akamai CAPTCHA
	$(PY) scripts/warm.py

.PHONY: run
run: $(PY) ## THE DAILY RUN: one sweep of all routes, visible window
	$(PY) -m starlux_award_watch --once --headed

.PHONY: loop
loop: $(PY) ## run continuously (full sweep ~2h, far-edge ~20m) + daily heartbeat
	$(PY) -m starlux_award_watch --headed

.PHONY: test-push
test-push: $(PY) ## send one test Pushover notification and exit
	$(PY) -m starlux_award_watch --test-sms

.PHONY: test
test: $(PY) ## run the test suite
	$(PY) -m pytest -q

.PHONY: lint
lint: $(PY) ## ruff check
	$(VENV)/bin/ruff check src tests

.PHONY: clean
clean: ## remove the venv + caches (keeps data/ and .env)
	rm -rf $(VENV) .pytest_cache .ruff_cache .mypy_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +

.PHONY: help
help: ## show this list
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-11s\033[0m %s\n", $$1, $$2}'
