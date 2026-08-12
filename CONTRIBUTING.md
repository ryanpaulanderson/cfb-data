# Contributing

This repository is in a foundation-rebuild phase. Changes should keep the
development workflow predictable while avoiding premature decisions about the
eventual public client API.

## Development setup

Python 3.11 or newer is required.

```sh
make install
make hooks
make check
```

`make install` creates a local `.venv` and installs the package in editable
mode with the `dev` dependency group. `make check` is the quality contract used
both locally and in GitHub Actions. It uses Ruff for formatting, imports,
linting, and docstring conventions; mypy checks production code in strict mode;
and pytest verifies behavior. The same command runs under Python 3.11 and 3.13
in CI.

## Code expectations

- Follow [`AGENTS.md`](AGENTS.md), the authoritative repository engineering
  guide for documentation, typing, design, project structure, testing,
  dependencies, security, and Git history. If this document and `AGENTS.md`
  differ, follow `AGENTS.md`.

Run `make format` when formatting is needed, followed by `make check` before
opening a pull request.

## Static type checking

The project uses mypy rather than Pyright because mypy provides a compact,
Python-native dependency for a library that supports several Python versions,
and its strict mode makes gradual typing escape hatches visible in review.
Pyright generally reports errors faster and can be attractive for editor-heavy
application development, but using both would create overlapping policies.

The mypy configuration in `pyproject.toml` checks production modules with
`strict = true`. External JSON starts as `object` and must be validated or
narrowed before domain code uses it. Do not introduce `Any`, broad ignores, or
unchecked casts to make the checker pass. A genuinely untyped third-party
boundary must be localized and documented with the narrowest possible
suppression.

Mypy targets the Python interpreter running the shared command, so the CI
matrix checks both the oldest and newest supported language versions. The
configuration skips only NumPy's installed implementation stubs, whose syntax
tracks its build interpreter, and marks pandas imports as untyped because
pandas does not ship inline type information. These exceptions do not suppress
errors in project modules. The package ships `py.typed` because all production
modules now pass the strict contract and the marker is included explicitly in
package data.

## Git workflow

- Use the conventional branch names and detailed Conventional Commits defined
  in `AGENTS.md`; do not commit directly to `main`.
- Reference the relevant GitHub issue when a change implements tracked work.
- Do not merge unless the shared quality contract passes.
