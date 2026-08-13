VENV ?= .venv
PYTHON ?= python3
VENV_PYTHON := $(VENV)/bin/python
PRE_COMMIT := $(VENV)/bin/pre-commit
RUFF := $(VENV)/bin/ruff
SPHINXBUILD := $(VENV)/bin/sphinx-build

.PHONY: help install hooks format docs check test build

help:
	@echo "make install  Create .venv and install runtime + development dependencies"
	@echo "make hooks    Install the pre-commit Git hook"
	@echo "make format   Format and auto-fix Python source with Ruff"
	@echo "make docs     Build strict Sphinx HTML documentation"
	@echo "make check    Run the complete local/CI quality contract"
	@echo "make test     Run the test suite"
	@echo "make build    Build and validate release distributions"

install:
	test -d $(VENV) || $(PYTHON) -m venv $(VENV)
	$(VENV_PYTHON) -m pip install --upgrade pip
	$(VENV_PYTHON) -m pip install --editable ".[dev,polars]"

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

build:
	$(VENV_PYTHON) -m build
	$(VENV_PYTHON) -m twine check --strict dist/*
