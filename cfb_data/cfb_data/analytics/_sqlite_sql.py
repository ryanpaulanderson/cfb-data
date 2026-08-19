"""Load analytics SQLite templates through the shared strict handler."""

from __future__ import annotations

from jinja2 import PackageLoader

from cfb_data._sqlite_sql import SQLTemplateHandler


class AnalyticsSQLiteSQL(SQLTemplateHandler):
    """Load installed SQLite templates from the analytics package."""

    def __init__(self) -> None:
        """Bind the strict handler to packaged analytics SQL resources."""
        super().__init__(PackageLoader("cfb_data.analytics", "sql"))


__all__ = ["AnalyticsSQLiteSQL"]
