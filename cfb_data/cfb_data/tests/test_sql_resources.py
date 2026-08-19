"""Test the dedicated SQLite SQL resource boundary."""

import ast
import re
from importlib.resources import files as resource_files
from pathlib import Path

import pytest
from cfb_data._sqlite_sql import SQLTemplateHandler
from cfb_data.analytics._sqlite_sql import AnalyticsSQLiteSQL
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


def test_cache_and_analytics_use_the_shared_sql_handler() -> None:
    """Use one strict rendering implementation for both persistence domains."""
    cache_sql = SQLiteSQL()
    analytics_sql = AnalyticsSQLiteSQL()

    assert isinstance(cache_sql, SQLTemplateHandler)
    assert isinstance(analytics_sql, SQLTemplateHandler)
    assert "cache_meta" in cache_sql.render("schema.sql")
    assert "CREATE TABLE runs" in analytics_sql.render("migrations/001_initial.sql")
    assert "node_artifact_bindings" in analytics_sql.render(
        "artifacts/select_eligible_for_prune.sql"
    )


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


def test_analytics_python_contains_no_embedded_statements() -> None:
    """Keep every analytics DDL and query in organized SQL resources."""
    analytics_path = Path(__file__).resolve().parents[1] / "analytics"
    statement_start = re.compile(
        r"(?:BEGIN IMMEDIATE|CREATE (?:INDEX|TABLE|TRIGGER)|DELETE FROM|"
        r"INSERT INTO|PRAGMA [a-z_]+|SELECT\s|UPDATE [a-z_]+|ALTER TABLE)",
        re.IGNORECASE,
    )

    embedded: list[tuple[Path, str]] = []
    for module_path in analytics_path.rglob("*.py"):
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        docstrings = {
            docstring
            for node in ast.walk(tree)
            if isinstance(
                node,
                (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
            )
            if (docstring := ast.get_docstring(node, clean=False)) is not None
        }
        embedded.extend(
            (module_path.relative_to(analytics_path), node.value)
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value not in docstrings
            and statement_start.match(node.value.lstrip()) is not None
        )

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


def test_packaged_analytics_sql_is_organized_by_persistence_domain() -> None:
    """Expose analytics migrations and statements from installed resources."""
    sql_directory = resource_files("cfb_data.analytics").joinpath("sql")
    directories = {
        resource.name for resource in sql_directory.iterdir() if resource.is_dir()
    }

    assert directories == {
        "artifacts",
        "attempts",
        "checkpoints",
        "config",
        "migrations",
        "nodes",
        "runs",
        "transaction",
    }
    assert sql_directory.joinpath(
        "migrations", "004_attempt_reservations.sql"
    ).is_file()
    assert sql_directory.joinpath("nodes", "insert_binding.sql").is_file()
