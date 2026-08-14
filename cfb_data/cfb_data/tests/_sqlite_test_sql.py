"""Render test-only SQLite diagnostics from dedicated SQL templates."""

from pathlib import Path

from cfb_data.cache._sqlite_sql import SQLTemplateHandler
from jinja2 import FileSystemLoader

_SQL = SQLTemplateHandler(FileSystemLoader(Path(__file__).with_name("sql")))


def sqlite_test_sql(name: str, **parameters: int) -> str:
    """Return one strictly rendered test-only SQLite statement."""
    return _SQL.render(name, **parameters)
