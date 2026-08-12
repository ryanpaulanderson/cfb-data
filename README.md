# College Football Data Python Toolkit

An experimental Python toolkit for fetching and validating data from the
[CollegeFootballData API](https://collegefootballdata.com/).

> **Project status:** foundation rebuild. The package is installable for
> development, but it does not yet offer a cohesive or supported public client
> API. See [`docs/project-status.md`](docs/project-status.md) for the honest
> current-state assessment.

## Original direction

The project was conceived as a hand-written alternative to generated API
clients, centered on three capabilities:

- asynchronous requests with `aiohttp`;
- Pydantic validation for request and response data;
- Pandera-validated pandas DataFrames for analysis.

The repository currently contains internal implementations of those layers for
several games endpoints and the drives endpoint. Deciding how they should be
presented as a stable public client is deliberately deferred until the
foundation is sound.

## Development setup

Python 3.11 or newer is required.

```sh
git clone https://github.com/ryanpaulanderson/cfb-data.git
cd cfb-data
make install
make hooks
make check
```

`make install` creates `.venv` and installs the project in editable mode with
its development dependencies. `make check` runs the same quality contract used
by GitHub Actions: all pre-commit checks followed by the complete pytest suite.

To work directly in the environment:

```sh
source .venv/bin/activate
```

## Package and dependency layout

`pyproject.toml` is the source of truth for package metadata and dependencies:

- `project.dependencies` contains runtime requirements.
- `project.optional-dependencies.dev` contains test and development tools.
- `pip install -e ".[dev]"` performs an editable development install.
- `pip install .` installs runtime requirements only.

There is no separate hand-maintained `requirements.txt`; this avoids keeping
duplicate dependency declarations in sync.

## Repository layout

```text
cfb_data/
├── cfb_data/                 Python package
│   ├── base/                 HTTP, validation, and DataFrame foundations
│   ├── game/                 Games-related handlers and models
│   ├── drives/               Drives handler and models
│   └── tests/                Current internal test suite
├── docs/
│   ├── project-status.md     Current state and known gaps
│   ├── cfbd_api/             Endpoint research and reference notes
│   └── history/              Archived design analyses and plans
├── api_reference/            Stored CFBD OpenAPI reference
├── pyproject.toml            Packaging, dependencies, and tool configuration
└── Makefile                  Shared local/CI development contract
```

## Tracked deferred work

- [Design a cohesive public client API (#53)](https://github.com/ryanpaulanderson/cfb-data/issues/53)
- [Harden the HTTP transport and error handling (#54)](https://github.com/ryanpaulanderson/cfb-data/issues/54)

The second issue includes restoring normal TLS verification, adding timeouts,
managing the `aiohttp` session lifecycle, improving errors, and adding genuine
installed-user end-to-end coverage.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). New development should use a feature
branch and pass `make check` before review.

## License

This project is licensed under the MIT License. See [`LICENSE`](LICENSE).

This project is not affiliated with CollegeFootballData.com.
