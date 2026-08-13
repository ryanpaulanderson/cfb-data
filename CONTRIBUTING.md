# Contributing

## Development setup

Python 3.12 and 3.13 are supported.

```sh
make install
make hooks
make format
make docs
make check
```

`make install` creates `.venv` and installs `.[dev,polars]` so the contributor
environment exercises the canonical PyArrow layer, default pandas backend,
and optional Polars backend. `make check` is the shared local and CI contract:
Ruff lint/format checks, strict mypy, a warning-free Sphinx HTML build, and the
complete pytest suite. `make docs` writes the site to `docs/_build/html`. CI
runs the shared contract on Python 3.12 and 3.13, separately smoke-tests base
and Polars installations, and publishes the documentation from `main` through
GitHub Pages.

Follow [`AGENTS.md`](AGENTS.md), the authoritative repository engineering and
Git guide. Run `make format` before `make check`; report every failure, skip,
warning, or environment limitation during handoff.

## Contribution licensing

By submitting a contribution, you agree that it may be licensed under the
project's [MIT License](LICENSE).

## Architecture expectations

Read
[`docs/architecture/0001-validated-models-before-dataframes.md`](docs/architecture/0001-validated-models-before-dataframes.md)
and
[`docs/architecture/0003-canonical-arrow-parquet.md`](docs/architecture/0003-canonical-arrow-parquet.md)
before changing endpoint, validation, Arrow, DataFrame, Parquet, dataset, or
workflow code.

- Pydantic models own external request and response contracts.
- The transport owns HTTP resources and retries; domain resources do not.
- The endpoint executor returns validated models without depending on a
  DataFrame backend.
- Logical schemas are derived from model annotations and map explicitly to one
  canonical Arrow schema before either DataFrame adapter runs.
- Public endpoint behavior must remain backend-neutral apart from concrete
  frame type and native nested representation.
- pandas and Polars preserve their established public dtypes. Their native
  Parquet methods are not the cfb-data persistence contract; library-owned
  persistence must use the versioned internal codec.
- Preserve nested source data. Flattening and exploding belong in a dataset or
  feature layer with a declared row grain, not endpoint conversion.
- Future datasets validate their final joined row model before conversion;
  workflows orchestrate endpoints and datasets above that layer.

Do not reintroduce raw/model/pandas client hierarchies, generic public path
routing, Pandera schemas, or backend-specific endpoint methods.

## Testing

Black-box tests through the installed `CFBDClient` are the primary acceptance
evidence. Use a local `aiohttp` server or fake the HTTP transport boundary; do
not make live credentialed calls in the default suite.

For tabular behavior, cover the canonical Arrow table, pandas, and Polars and
assert concrete type, exact field/column/row order, recursive nullability,
nullable and UTC dtypes, typed empty and all-null frames, nested values, and no
row loss. Parquet tests must cover populated and empty round trips, versioned
metadata, physical-schema compatibility, strict validation, tagged mixed
scalars, atomic replacement, sanitized failures, and the checked-in v1
compatibility fixture. Request tests must prove invalid input stops before
HTTP. Transport tests must be deterministic and must not expose credentials,
query parameters, or response payloads in failure text.

## Static type checking

Production modules run under mypy strict mode with the Pydantic plugin. The
package ships `py.typed`. Preserve literal-backend inference for
`CFBDClient`: default construction yields pandas results and a literal
`"polars"` backend yields Polars results.

External JSON begins as `object` and must be validated or narrowed before use.
Do not introduce `Any`, broad ignores, or unchecked casts to silence errors.
Localize and explain any unavoidable third-party boundary.

## Dependencies and Git

`pyproject.toml` is the only dependency and package-metadata source. pandas and
PyArrow are core dependencies; Polars belongs only to the `polars` extra;
development tools and third-party typing stubs belong to `dev`.

Use the branch names and detailed Conventional Commits defined in `AGENTS.md`.
Do not commit directly to `main`, and do not merge unless the shared quality
contract passes.

## Releases

To create a release, update `[project].version` in `pyproject.toml` to a
strictly higher `MAJOR.MINOR.PATCH` version in a pull request. When that pull
request is merged into `main`, the release workflow creates the matching
`vMAJOR.MINOR.PATCH` tag and published GitHub release at the merge commit. It
then builds and validates the wheel and source distribution from that exact
commit before publishing them to PyPI through Trusted Publishing. GitHub
generates the release notes from merged pull requests and groups them by their
`enhancement`, `bug`, `documentation`, or `dependencies` labels, with an
additional catch-all section.

The PyPI publisher is scoped to `.github/workflows/release.yml` and the
protected `pypi` GitHub environment. The publishing job alone receives the
`id-token: write` permission; the build job cannot request PyPI credentials,
and no long-lived PyPI token is stored in GitHub. Release actions are pinned to
immutable commits.

Before proposing a version bump, validate the distributions locally in
addition to the normal quality contract:

```sh
make format
make check
make build
```

Release automation relies on and validates the repository's merge-commit-only
policy so the merge commit's first parent identifies the exact pre-merge state
of `main`. Update the version-comparison workflow before enabling another merge
method.

Pull requests that change `pyproject.toml` without increasing the project
version do not create a release. A version decrease or a version outside the
documented three-component form fails the release check. PyPI versions and
distribution files are immutable, so never reuse a version after any artifact
for it has been uploaded.
