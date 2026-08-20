VENV ?= .venv
PYTHON ?= python3
VENV_PYTHON := $(VENV)/bin/python
PRE_COMMIT := $(VENV)/bin/pre-commit
RUFF := $(VENV)/bin/ruff
SPHINXBUILD := $(VENV)/bin/sphinx-build

.PHONY: help install hooks format docs check test build update-reference-enums redis-up redis-down test-redis test-live test-live-all test-live-analytics

help:
	@echo "make install  Create .venv and install runtime + development dependencies"
	@echo "make hooks    Install the pre-commit Git hook"
	@echo "make format   Format and auto-fix Python source with Ruff"
	@echo "make docs     Build strict Sphinx HTML documentation"
	@echo "make check    Run the complete local/CI quality contract"
	@echo "make test     Run the test suite"
	@echo "make build    Build and validate release distributions"
	@echo "make update-reference-enums Regenerate team and conference enums from live API data"
	@echo "make redis-up Build and start the local persistent Redis service"
	@echo "make redis-down Stop the local Redis service without deleting its volume"
	@echo "make test-redis Run integration tests against the local Redis service"
	@echo "make test-live Spend one real API call using CFBD_API_KEY from .env"
	@echo "make test-live-all Run the quota-ledgered exhaustive SQLite/Redis live matrix"
	@echo "make test-live-analytics Run quota-ledgered modular recipe acceptance"

install:
	test -d $(VENV) || $(PYTHON) -m venv $(VENV)
	$(VENV_PYTHON) -m pip install --upgrade pip
	$(VENV_PYTHON) -m pip install --editable ".[dev,polars,redis,dask,yaml]"

hooks:
	$(PRE_COMMIT) install

format:
	$(RUFF) check --fix cfb_data
	$(RUFF) format cfb_data

docs:
	$(SPHINXBUILD) -E -W --keep-going -b html docs docs/_build/html

check:
	$(PRE_COMMIT) run --all-files
	$(MAKE) docs
	$(VENV_PYTHON) -m pytest

test:
	$(VENV_PYTHON) -m pytest

redis-up:
	docker compose -f compose.redis.yaml up --build --detach --wait

redis-down:
	docker compose -f compose.redis.yaml down

test-redis:
	CFB_DATA_TEST_REDIS_URL=redis://127.0.0.1:6379/0 $(VENV_PYTHON) -m pytest -m redis

test-live:
	set -a; . ./.env; set +a; CFB_DATA_RUN_LIVE_API=1 $(VENV_PYTHON) -m pytest -m live_api

test-live-all:
	set -a; . ./.env; set +a; CFB_DATA_RUN_LIVE_API_ALL=1 CFB_DATA_TEST_REDIS_URL=redis://127.0.0.1:6379/0 $(VENV_PYTHON) -m pytest cfb_data/cfb_data/tests/test_live_api_all.py -q

test-live-analytics:
	set -a; . ./.env; set +a; CFB_DATA_RUN_LIVE_ANALYTICS=1 CFB_DATA_TEST_REDIS_URL=redis://127.0.0.1:6379/0 $(VENV_PYTHON) -m pytest cfb_data/cfb_data/tests/test_live_analytics.py -q

build:
	$(VENV_PYTHON) -m build
	$(VENV_PYTHON) -m twine check --strict dist/*

update-reference-enums:
	test -n "$(REFERENCE_YEAR)" || (echo "Set REFERENCE_YEAR to the season to generate" && exit 1)
	set -a; . ./.env; set +a; $(VENV_PYTHON) scripts/generate_reference_enums.py --year $(REFERENCE_YEAR)
