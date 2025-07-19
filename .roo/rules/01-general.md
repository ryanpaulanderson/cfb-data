# Coding Agent Guidelines for College Football Data Python Project

These are the expectations and standards for all coding contributions to this repository, whether via human or AI developer (e.g., ChatGPT Codex). **All code, documentation, and tests must strictly follow these requirements.**

## Formatting and Style

- **Black formatting:** All code must be auto-formatted using [`black`](https://github.com/psf/black) before commit. No exceptions.
- **Type hints:** Every function definition (including all arguments and return types) and all variables must have [PEP 484](https://peps.python.org/pep-0484/) style type hints. This includes class attributes and local variables.
- **Docstrings:** Every function, class, and method must have a complete [Sphinx-style docstring](https://sphinxcontrib-napoleon.readthedocs.io/en/latest/example_google.html).
- **Imports:** Use absolute imports within the package unless a clear case for relative imports is made. Group and order imports using [isort](https://pycqa.github.io/isort/).
- **No commented-out code** should be left in PRs or commits.

## Documentation
- Public functions and classes must have clear docstrings including arguments, return types, and raised exceptions.
- Docstrings must be written in Sphinx format, and should be suitable for automatic API docs generation.
### Example Docstring
```python

    async def make_request_validated(
        self,
        path: str,
        model: Type[T],
        params: Optional[Dict[str, Any]] = None,
    ) -> Union[T, List[T]]:
        """Make a request and validate the JSON response.

        :param path: API endpoint path to request
        :type path: str
        :param model: Pydantic model class used for validation
        :type model: Type[T]
        :param params: Optional query parameters for the request
        :type params: Optional[Dict[str, Any]]
        :return: Validated model instance or list of instances
        :rtype: Union[T, List[T]]
        :raises TypeError: If the returned data is not a ``list`` or ``dict``
        """
        data: Union[List[Any], Dict[str, Any]] = await super().make_request(
            path, params
        )
        if isinstance(data, list):
            return [model.model_validate(item) for item in data]
        if isinstance(data, dict):
            return model.model_validate(data)
        raise TypeError("Response data must be list or dict")
```

## Testing
- **Unit tests:** Every new function, class, or feature must be accompanied by one or more unit tests, located in the `tests/` directory, covering all expected behaviors and edge cases.
- **Test-driven:** Unit tests must be written and pass locally before code can be committed or merged.
- Use [pytest](https://docs.pytest.org/) as the testing runner.
- Include at least one negative test (for error/failure) for every public-facing function.

## Git & CI
- Ensure all tests pass and pre-commit hooks succeed before pushing code.
- Do not commit directly to the main branch.
- Write clear, concise commit messages that describe _why_ as well as _what_ ("Fix bug in team stats endpoint parsing" not just "fix").
- PRs should reference related issues or tickets where applicable.

## Python Best Practices
- Avoid using bare excepts; catch specific exceptions.
- No hardcoded credentials or secrets—use environment variables/config.
- Prefer f-strings for string formatting (Python 3.6+).
- Use comprehensions over manual loops for list/set/dict construction when it improves clarity.
- Use logging, not print, for status/debug output.
- Use [pydantic](https://docs.pydantic.dev/) models for structured data whenever possible; only use dataclasses if pydantic is not suitable.
- Avoid global state; use dependency injection or function arguments where possible.
- Ensure all external dependencies are listed in `requirements.txt` and are not unnecessarily pinned to overly specific versions.
- For anything that is ambiguous, prefer explicitness, readability, and maintainability.

## Example Function Template
```python
def fetch_games(year: int, season_type: str = "regular") -> pd.DataFrame:
    """
    Fetch games for a given year and season type.

    :param year: The year of the season.
    :type year: int
    :param season_type: The season type (e.g., 'regular', 'postseason').
    :type season_type: str
    :return: DataFrame containing game data.
    :rtype: pd.DataFrame
    """
    pass
```

## Example Unit Test Template
```python
def test_fetch_games_success():
    """
    Test that fetch_games returns a non-empty DataFrame for valid input.
    """
    df = fetch_games(2024)
    assert not df.empty

def test_fetch_games_invalid_year():
    """
    Test that fetch_games raises ValueError for invalid year.
    """
    with pytest.raises(ValueError):
        fetch_games(-1)
```
```python
def test_fetch_games_success():
    """Test that fetch_games returns a non-empty DataFrame for valid input."""
    df = fetch_games(2024)
    assert not df.empty

def test_fetch_games_invalid_year():
    """Test that fetch_games raises ValueError for invalid year."""
    with pytest.raises(ValueError):
        fetch_games(-1)
```

---
**Any code not conforming to these standards will not be accepted.**
