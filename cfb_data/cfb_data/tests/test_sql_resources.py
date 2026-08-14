"""Test the dedicated SQLite SQL resource boundary."""

import ast
import re
from importlib.resources import files as resource_files
from pathlib import Path

import pytest
from cfb_data.cache._sqlite_sql import SQLiteSQL


def test_sql_handler_loads_packaged_templates_strictly() -> None:
    """Render packaged static and parameterized SQL with strict Jinja values."""
    sql = SQLiteSQL()

    assert "cache_meta" in sql.render("schema.sql")
    busy_timeout = sql.render("set_busy_timeout.sql", busy_timeout_ms=2_000)
    assert busy_timeout.endswith("2000")
    assert "{{" not in busy_timeout
    observations = sql.render("select_catalog_observations.sql", pair_count=2)
    assert observations.count("namespace = ? AND grain = ?") == 2

    with pytest.raises(ValueError, match="could not be rendered"):
        sql.render("set_busy_timeout.sql")
    with pytest.raises(ValueError, match="positive integers"):
        sql.render("set_busy_timeout.sql", busy_timeout_ms=0)
    with pytest.raises(ValueError, match="package-relative"):
        sql.render("../schema.sql")
    with pytest.raises(ValueError, match="could not be rendered"):
        sql.render("missing.sql")


def test_sqlite_backend_contains_no_embedded_statements() -> None:
    """Keep SQLite statement ownership in dedicated SQL resources."""
    backend_path = Path(__file__).resolve().parents[1] / "cache" / "_sqlite.py"
    tree = ast.parse(backend_path.read_text(encoding="utf-8"))
    statement_start = re.compile(
        r"(?:BEGIN IMMEDIATE|CREATE (?:INDEX|TABLE)|DELETE FROM|INSERT INTO|"
        r"PRAGMA [a-z_]+|SELECT\s|UPDATE [a-z_]+)",
        re.IGNORECASE,
    )

    embedded = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and statement_start.match(node.value.lstrip()) is not None
    ]

    assert embedded == []


def test_packaged_sql_directory_owns_every_backend_statement() -> None:
    """Verify the installed package exposes the DDL and query resources."""
    sql_directory = resource_files("cfb_data.cache").joinpath("sql")
    template_names = {
        resource.name for resource in sql_directory.iterdir() if resource.is_file()
    }

    assert "schema.sql" in template_names
    assert "find_games.sql" in template_names
    assert "upsert_catalog_observation.sql" in template_names
    assert all(name.endswith(".sql") for name in template_names)
