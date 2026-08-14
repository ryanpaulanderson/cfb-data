"""Render packaged SQLite templates through one strict SQL handler."""

from __future__ import annotations

from pathlib import PurePosixPath

from jinja2 import (
    BaseLoader,
    Environment,
    PackageLoader,
    StrictUndefined,
    TemplateError,
)


class SQLTemplateHandler:
    """Own strict loading and rendering for one SQL template source."""

    def __init__(self, loader: BaseLoader) -> None:
        """Create a strict Jinja environment over ``loader``."""
        self._environment = Environment(
            loader=loader,
            undefined=StrictUndefined,
            autoescape=False,
            auto_reload=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(self, name: str, **parameters: int) -> str:
        """Load and strictly render one packaged SQL template.

        Data values must remain database-bound parameters. Jinja parameters
        are reserved for validated structural values that cannot be bound by
        SQLite, such as a PRAGMA integer or a repeated placeholder count.

        :param name: Package-relative ``.sql`` template name.
        :param parameters: Validated structural template parameters.
        :return: Non-empty rendered SQL text.
        :raises ValueError: If the template name, parameters, or output is invalid.
        """
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or path.suffix != ".sql":
            raise ValueError(
                "SQLite template name must be a package-relative .sql path"
            )
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
            for value in parameters.values()
        ):
            raise ValueError(
                "SQLite structural template parameters must be positive integers"
            )
        try:
            rendered = self._environment.get_template(name).render(**parameters).strip()
        except TemplateError as exc:
            raise ValueError(f"SQLite template {name!r} could not be rendered") from exc
        if not rendered:
            raise ValueError(f"SQLite template {name!r} rendered empty SQL")
        return rendered


class SQLiteSQL(SQLTemplateHandler):
    """Load installed SQLite templates from the cache package."""

    def __init__(self) -> None:
        """Bind the strict handler to packaged cache SQL resources."""
        super().__init__(PackageLoader("cfb_data.cache", "sql"))
