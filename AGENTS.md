# Repository Engineering Guide

This file governs the entire repository. Direct user instructions take
precedence; otherwise, this is the authoritative engineering and Git policy
when another repository document conflicts. A more deeply nested `AGENTS.md`
may add stricter, local rules for its subtree.

## Work collaboratively

- Read `README.md`, `docs/project-status.md`, `CONTRIBUTING.md`, and the relevant
  code and tests before proposing changes. Treat `docs/history/` as context,
  never as the current roadmap or implementation status.
- Before material edits, state the intended outcome, scope, assumptions, and
  verification plan. Surface consequential design choices instead of silently
  deciding them.
- Preserve unrelated work and keep changes within the agreed scope. Do not
  commit, push, open a pull request, merge, or rename a shared branch without
  explicit authorization.

## Repository contract

- Support Python 3.12 and 3.13. Do not use syntax or APIs introduced after
  3.12 unless the supported versions are deliberately changed together.
- `pyproject.toml` is the single source of truth for packaging, supported
  Python versions, dependencies, and tool configuration. Keep runtime packages
  in `project.dependencies` and development tools in
  `project.optional-dependencies.dev`; do not duplicate requirement lists or
  package modules from the standard library.
- Use the shared commands: `make install` for setup, `make format` for
  formatting, `make test` for the test suite, and `make check` for the complete
  local/CI quality contract.
- Importable code lives under `cfb_data/cfb_data/`. Keep domain code within its
  domain package; put code in `base/` only after it is genuinely shared.

## Build durable software

- Write production-quality code for known requirements. Do not use “POC,”
  “MVP,” “temporary,” or future cleanup as reasons to weaken correctness,
  security, validation, error handling, observability, or resource ownership.
- Choose the simplest design that is sound and maintainable for credible
  extension points. Avoid both knowingly inferior shortcuts and speculative
  abstractions for hypothetical features.
- If the correct solution materially exceeds the agreed scope, explain the
  tradeoff and obtain direction. If deferral is approved, create a tracked
  issue; do not quietly ship debt behind a TODO.

## Documentation and docstrings

- Follow PEP 257 and use Sphinx/reStructuredText docstrings for every public
  module, class, function, and method, plus private code whose contract is not
  obvious. Start with an imperative one-line summary and separate further
  detail with a blank line.
- Document behavior and meaning: parameter semantics, return semantics,
  raised exceptions, units, mutation, side effects, invariants, and resource
  ownership when relevant. Do not narrate the implementation.
- Use `:param name:`, `:return:`, and `:raises ExceptionType:` fields. Types
  belong in annotations; never duplicate them with `:type:` or `:rtype:` fields
  or restate the signature/defaults in prose.

```python
def games_for_year(year: int) -> list[Game]:
    """Return the games played during a season.

    :param year: Four-digit season year.
    :return: Games in API order.
    :raises ValueError: If the year is outside the supported range.
    """
```

## Typing

- Keep new and changed code type-complete. Annotate every function and method
  parameter and return value (including `-> None`), callbacks, module state,
  class and instance attributes, empty containers, and local variables whose
  type or domain meaning is not immediately stable from inference.
- Prefer Python 3.12 forms such as `list[str]`, `dict[str, int]`, and
  `Result | None`. Accept the narrowest useful abstract interface from
  `collections.abc`; return the concrete type actually promised.
- Use `Final`, `Literal`, `NewType`, `TypedDict`, dataclasses, generics,
  `Protocol`, `TypeVar`, and `Self` when they encode real constraints. Import
  typing tools when needed rather than weakening an annotation.
- Do not introduce `Any` as an escape hatch. Use `object` for an unknown value
  and narrow it before use; model structured data with a recursive JSON type,
  `TypedDict`, Pydantic, Pandera, or a domain type. If an untyped third-party
  boundary truly cannot be expressed, confine `Any` to that boundary, explain
  why, validate or narrow immediately, and never let it propagate.
- Put an import under `if TYPE_CHECKING:` only when it is exclusively for
  static analysis or must avoid a cycle/heavy runtime import. Keep types needed
  by Pydantic, Pandera, decorators, or `get_type_hints()` available at runtime.
- A `cast`, `# type: ignore`, or untyped decorator does not prove safety. Use a
  narrow suppression only after proving the invariant, documenting the reason,
  and selecting the specific error code where the checker supports one.
- Treat type hints as static contracts, not runtime validation. Validate all
  untrusted external data at the system boundary.

Legacy untyped code is not precedent. Improve relevant adjacent annotations
when doing so is safe, but keep repository-wide typing migrations as dedicated,
reviewable changes. Mechanical enforcement through the shared contract is
tracked in [issue #55](https://github.com/ryanpaulanderson/cfb-data/issues/55).

## Design and structure

- Organize by domain and capability. Separate domain behavior from HTTP
  transport, validation/serialization, persistence, and DataFrame presentation.
  Avoid catch-all `utils`, `helpers`, `base`, or `constants` modules.
- Favor cohesive modules, small explicit interfaces, and high-level policy that
  does not depend directly on volatile I/O details. Inject transports, clocks,
  configuration, and other side-effecting dependencies at clear boundaries.
- Use a function when no identity or state is required. Use a class to protect
  a stable invariant, own a resource/lifecycle, or provide meaningful
  polymorphism—not merely to group functions.
- Prefer composition and dependency injection. Inherit only for genuine
  behavioral substitutability and keep hierarchies shallow. Use `Protocol` for
  small structural interfaces; use an ABC only when nominal membership or a
  shared enforced contract is required.
- Keep the public API intentionally small. Encapsulate internals with leading
  underscores and do not expose an implementation detail merely to test it.
- Make ownership and lifetime explicit for sessions, tasks, files, and other
  resources. Use context managers and preserve cancellation in asynchronous
  code.
- Reuse existing Pydantic, Pandera, or domain models when they express the same
  concept. Add a dataclass or parallel model only when it has a distinct
  semantic responsibility.

## Single sources of truth

- Remove duplicated knowledge, not merely similar-looking syntax. Give each
  configuration value, constant, endpoint, default, field mapping, schema, and
  domain invariant one authoritative owner and derive secondary forms where
  practical.
- Put shared knowledge at the narrowest stable layer that owns it. Do not create
  a global registry or abstraction for concepts that only happen to look alike;
  premature deduplication creates coupling instead of removing it.
- Avoid mutable global state and import-time side effects. Prefer immutable
  value/configuration objects and annotate true constants with `Final`.
- Do not add a runtime dependency when the standard library adequately solves
  the problem. Justify every new dependency by maintenance, security, and
  operational value.

## Errors, security, and external I/O

- Raise specific, actionable exceptions with relevant safe context. Preserve
  the original cause with `raise ... from ...`; do not use bare `except`,
  swallow failures, or silently return partial data.
- Validate external inputs and responses before they enter domain code. Never
  commit credentials, log secrets/tokens, disable TLS verification, or create
  unbounded network calls. Use explicit timeouts and deterministic cleanup.
- The existing transport hardening debt is tracked in
  [issue #54](https://github.com/ryanpaulanderson/cfb-data/issues/54); do not
  copy, expand, or normalize the insecure behavior while that work is pending.
- A TODO must reference a tracked issue and explain the remaining invariant or
  decision. It may record an explicitly approved deferral, but must not be used
  unilaterally to postpone correctness, security, or resource cleanup.

## Test behavior, not implementation

- Black-box tests are the default acceptance evidence. Exercise realistic data
  flow through the installed package and its public interface: inputs,
  transport boundary, validation/transformation, results, documented errors,
  and cleanup.
- Until the cohesive public client tracked in
  [issue #53](https://github.com/ryanpaulanderson/cfb-data/issues/53) exists,
  test through the nearest importable, externally usable method. Do not invent
  a public API as incidental test work.
- Fake or mock external boundaries such as HTTP, filesystem, clock, and
  environment. Do not mock the code under test's own helpers. Assert observable
  outputs, state, exceptions, and external effects—not private attributes,
  helper call order, or internal choreography unless that interaction is itself
  a public contract.
- Cover the successful path plus meaningful boundary and failure cases. A bug
  fix requires a regression test that fails through the public behavior before
  the fix. Focused unit tests are appropriate for complex pure logic, but they
  must still test its contract rather than its implementation.
- Keep tests deterministic, isolated, independent of execution order, and free
  of live network access by default. Do not manipulate `sys.path`; test the
  installed package. Maintain a clean-build/install/import smoke path.
- The current in-package test layout is legacy, not a structural precedent.
  Move it only as a dedicated change that updates packaging and pytest
  configuration atomically.

## Git history

- Name new branches `<type>/<short-kebab-case-description>`, for example
  `feat/public-client`, `fix/tls-verification`, `refactor/transport`,
  `docs/project-status`, `test/client-workflow`, or `ci/python-matrix`. Allowed
  types are `feat`, `fix`, `refactor`, `docs`, `test`, `build`, `ci`, `perf`,
  and `chore`. Do not use an agent/tool prefix such as `codex/`.
- Use Conventional Commits:
  `<type>[optional scope][!]: <imperative description>`. For every non-trivial
  commit, add a body explaining the motivation, behavioral/design impact,
  important tradeoffs, and verification performed. Add `Refs: #123` or
  `Closes: #123` as appropriate; mark breaking changes with `!` and a
  `BREAKING CHANGE:` footer.
- Make each commit one coherent, reviewable change that passes its relevant
  checks. Split large work into dependency-ordered commits by behavior or
  architectural layer. Keep unrelated refactors, formatting churn, generated
  output, and behavior changes separate; do not leave `WIP`/`fixup` commits in
  final history.
- Apply the naming rule when creating the next branch. Do not rename an active
  or shared branch without explicit approval.

## Definition of done

- Update tests, public documentation, examples, and package metadata alongside
  the behavior they describe.
- Run `make format`, then `make check`. Report exactly what ran and disclose any
  failure, skipped check, warning, or environment limitation.
- Review the diff for accidental API changes, duplicate sources of truth,
  leaked secrets, insecure I/O, stale comments, and unrelated edits.

## Primary references

- [PEP 8 — Style Guide for Python Code](https://peps.python.org/pep-0008/)
- [PEP 257 — Docstring Conventions](https://peps.python.org/pep-0257/)
- [Sphinx Python-domain field lists](https://www.sphinx-doc.org/en/master/usage/domains/python.html#info-field-lists)
- [Python typing guidance for libraries](https://typing.python.org/en/latest/guides/libraries.html)
- [Python typing best practices](https://typing.python.org/en/latest/reference/best_practices.html)
- [Python Packaging User Guide — `pyproject.toml`](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/)
- [Python Packaging User Guide — source layout](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/)
- [pytest good integration practices](https://docs.pytest.org/en/stable/explanation/goodpractices.html)
- [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/)
