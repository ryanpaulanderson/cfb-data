VENV ?= .venv
PYTHON ?= python3
VENV_PYTHON := $(VENV)/bin/python
PRE_COMMIT := $(VENV)/bin/pre-commit
RUFF := $(VENV)/bin/ruff
SPHINXBUILD := $(VENV)/bin/sphinx-build

.PHONY: help install hooks format docs check test build redis-up redis-down test-redis test-live

help:
	@echo "make install  Create .venv and install runtime + development dependencies"
	@echo "make hooks    Install the pre-commit Git hook"
	@echo "make format   Format and auto-fix Python source with Ruff"
	@echo "make docs     Build strict Sphinx HTML documentation"
	@echo "make check    Run the complete local/CI quality contract"
	@echo "make test     Run the test suite"
	@echo "make build    Build and validate release distributions"
	@echo "make redis-up Build and start the local persistent Redis service"
	@echo "make redis-down Stop the local Redis service without deleting its volume"
	@echo "make test-redis Run integration tests against the local Redis service"
	@echo "make test-live Spend one real API call using CFBD_API_KEY from .env"

install:
	test -d $(VENV) || $(PYTHON) -m venv $(VENV)
	$(VENV_PYTHON) -m pip install --upgrade pip
	$(VENV_PYTHON) -m pip install --editable ".[dev,polars,redis]"

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

build:
	$(VENV_PYTHON) -m build
	$(VENV_PYTHON) -m twine check --strict dist/*
