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
both locally and in GitHub Actions.

## Code expectations

- Follow [`AGENTS.md`](AGENTS.md), the authoritative repository engineering
  guide for documentation, typing, design, project structure, testing,
  dependencies, security, and Git history. If this document and `AGENTS.md`
  differ, follow `AGENTS.md`.

Run `make format` when formatting is needed, followed by `make check` before
opening a pull request.

## Git workflow

- Use the conventional branch names and detailed Conventional Commits defined
  in `AGENTS.md`; do not commit directly to `main`.
- Reference the relevant GitHub issue when a change implements tracked work.
- Do not merge unless the shared quality contract passes.
