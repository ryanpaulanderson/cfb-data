VENV ?= .venv
PYTHON ?= python3
VENV_PYTHON := $(VENV)/bin/python
PRE_COMMIT := $(VENV)/bin/pre-commit

.PHONY: help install hooks format check test

help:
	@echo "make install  Create .venv and install runtime + development dependencies"
	@echo "make hooks    Install the pre-commit Git hook"
	@echo "make format   Format Python source with Black and isort"
	@echo "make check    Run the complete local/CI quality contract"
	@echo "make test     Run the test suite"

install:
	test -d $(VENV) || $(PYTHON) -m venv $(VENV)
	$(VENV_PYTHON) -m pip install --upgrade pip
	$(VENV_PYTHON) -m pip install --editable ".[dev]"

hooks:
	$(PRE_COMMIT) install

format:
	$(VENV_PYTHON) -m black cfb_data
	$(VENV_PYTHON) -m isort cfb_data

check:
	$(PRE_COMMIT) run --all-files
	$(VENV_PYTHON) -m pytest

test:
	$(VENV_PYTHON) -m pytest
