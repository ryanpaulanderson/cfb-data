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

The repository currently contains usable domain clients for all nine endpoints
in the official Games category and the single endpoint in the Drives category.
Their request and response contracts track the official CFBD API v5.24.0
documentation. Deciding how they should be presented as one stable top-level
client remains deliberately deferred.

## Current domain clients

Set an API key issued by CollegeFootballData and choose the response layer:

```python
from cfb_data.games import CFBDGamesValidationAPI

api = CFBDGamesValidationAPI(api_key="...")
games = await api.make_request(
    "/games",
    {"year": 2024, "team": "Michigan"},
)
```

- `CFBDGamesAPI` and `CFBDDrivesAPI` return raw JSON after validating request
  parameters.
- `CFBDGamesValidationAPI` and `CFBDDrivesValidationAPI` return Pydantic
  response models.
- `CFBDGamesPandasAPI` and `CFBDDrivesPandasAPI` return Pandera-validated
  DataFrames.

The domain packages intentionally mirror one another as `cfb_data.games` and
`cfb_data.drives`, each with raw, Pydantic-validation, and pandas client layers.

See [`docs/cfbd_api/`](docs/cfbd_api/) for the implemented routes, selectors,
response shapes, and access restrictions. The client uses the canonical
`https://api.collegefootballdata.com` host, normal TLS verification, and a
finite request timeout.

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
by GitHub Actions: Ruff linting and formatting, strict mypy type checking, and
the complete pytest suite. The CI matrix runs this command on Python 3.11 and
3.13.

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
│   ├── games/                Games-related handlers and models
│   ├── drives/               Drives handler and models
│   └── tests/                Current internal test suite
├── docs/
│   ├── project-status.md     Current state and known gaps
│   ├── cfbd_api/             Endpoint research and reference notes
│   └── history/              Archived design analyses and plans
├── pyproject.toml            Packaging, dependencies, and tool configuration
└── Makefile                  Shared local/CI development contract
```

## Tracked deferred work

- [Design a cohesive public client API (#53)](https://github.com/ryanpaulanderson/cfb-data/issues/53)
- [Harden the HTTP transport and error handling (#54)](https://github.com/ryanpaulanderson/cfb-data/issues/54)

The transport now has normal TLS verification and finite timeouts. Issue #54
continues to track reusable session ownership, richer error context, and
credentialed installed-user end-to-end coverage.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). New development should use a feature
branch and pass `make check` before review.

## License

This project is licensed under the MIT License. See [`LICENSE`](LICENSE).

This project is not affiliated with CollegeFootballData.com.
