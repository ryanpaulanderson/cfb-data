VENV ?= .venv
PYTHON ?= python3
VENV_PYTHON := $(VENV)/bin/python
PRE_COMMIT := $(VENV)/bin/pre-commit
RUFF := $(VENV)/bin/ruff

.PHONY: help install hooks format check test

help:
	@echo "make install  Create .venv and install runtime + development dependencies"
	@echo "make hooks    Install the pre-commit Git hook"
	@echo "make format   Format and auto-fix Python source with Ruff"
	@echo "make check    Run the complete local/CI quality contract"
	@echo "make test     Run the test suite"

install:
	test -d $(VENV) || $(PYTHON) -m venv $(VENV)
	$(VENV_PYTHON) -m pip install --upgrade pip
	$(VENV_PYTHON) -m pip install --editable ".[dev]"

hooks:
	$(PRE_COMMIT) install

format:
	$(RUFF) check --fix cfb_data
	$(RUFF) format cfb_data

check:
	$(PRE_COMMIT) run --all-files
	$(VENV_PYTHON) -m pytest

test:
	$(VENV_PYTHON) -m pytest
