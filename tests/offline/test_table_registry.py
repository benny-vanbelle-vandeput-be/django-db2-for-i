"""tests/table_registry.py and scripts/ibmi_cleanup.py: the cleanup list (no server needed)."""

import importlib.util
import sys
from pathlib import Path

import pytest

from tests import table_registry as registry

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ibmi_cleanup.py"
spec = importlib.util.spec_from_file_location("scripts_ibmi_cleanup", SCRIPT)
cleanup = importlib.util.module_from_spec(spec)
sys.modules["scripts_ibmi_cleanup"] = cleanup
spec.loader.exec_module(cleanup)


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ('CREATE TABLE "TESTAPP_AUTHOR" ("ID" INTEGER)', ("TABLE", "LIB", "TESTAPP_AUTHOR")),
        (
            'CREATE TABLE "MYLIB"."DJDB2I_TEST_MARKER" (X INT)',
            ("TABLE", "MYLIB", "DJDB2I_TEST_MARKER"),
        ),
        ("create table mylib.plain (x int)", ("TABLE", "MYLIB", "PLAIN")),
        ('  CREATE OR REPLACE VIEW "V_1" AS SELECT 1', ("VIEW", "LIB", "V_1")),
        ('CREATE ALIAS "A" FOR "T"', ("ALIAS", "LIB", "A")),
        ('CREATE TABLE "Mixed""Case" (X INT)', ("TABLE", "LIB", 'Mixed"Case')),
    ],
)
def test_created_objects_are_recognised(sql, expected) -> None:
    entry = registry.parse(sql, "lib")
    assert (entry.kind, entry.library, entry.name) == expected


@pytest.mark.parametrize(
    "sql",
    [
        'CREATE INDEX "I" ON "T" ("X")',
        'INSERT INTO "T" VALUES (1)',
        'SELECT * FROM "CREATE TABLE"',
        'DROP TABLE "T"',
    ],
)
def test_other_statements_are_not_recorded(sql) -> None:
    assert registry.parse(sql, "lib") is None


def test_record_read_write(tmp_path) -> None:
    path = tmp_path / "state" / "created-objects.txt"
    registry.record(path, registry.Entry("TABLE", "LIB", "T1"))
    registry.record(path, registry.Entry("VIEW", "LIB", "V1"))
    entries = registry.read(path)
    assert [(e.kind, e.name) for e in entries] == [("TABLE", "T1"), ("VIEW", "V1")]
    assert entries[0].created.endswith("Z")
    registry.write(path, entries[1:])
    assert [e.name for e in registry.read(path)] == ["V1"]
    assert registry.read(tmp_path / "missing.txt") == []


class FakeConnection:
    vendor = "db2_for_i"

    def __init__(self):
        self.settings_dict = {"NAME": "testlib"}
        self.execute_wrappers = []


def test_the_wrapper_records_before_the_statement_runs(tmp_path, monkeypatch) -> None:
    path = tmp_path / "created-objects.txt"
    monkeypatch.setenv(registry.ENV, str(path))
    seen = []

    def execute(sql, params, many, context):
        seen.append(([e.name for e in registry.read(path)], sql))

    context = {"connection": FakeConnection()}
    registry.wrapper(execute, 'CREATE TABLE "T1" (X INT)', None, False, context)
    registry.wrapper(execute, "SELECT 1", None, False, context)
    assert seen == [(["T1"], 'CREATE TABLE "T1" (X INT)'), (["T1"], "SELECT 1")]
    assert registry.read(path)[0].library == "TESTLIB"


def test_without_the_list_nothing_is_recorded(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv(registry.ENV, raising=False)
    calls = []
    registry.wrapper(lambda *a: calls.append(a), 'CREATE TABLE "T" (X INT)', None, False, {})
    assert len(calls) == 1 and list(tmp_path.iterdir()) == []


def test_the_wrapper_is_added_once_per_connection_of_this_backend() -> None:
    connection = FakeConnection()
    registry._on_connection_created(None, connection)
    registry._on_connection_created(None, connection)
    assert connection.execute_wrappers == [registry.wrapper]
    other = FakeConnection()
    other.vendor = "sqlite"
    registry._on_connection_created(None, other)
    assert other.execute_wrappers == []


def test_both_ibmi_settings_install_the_registry() -> None:
    root = Path(__file__).resolve().parents[2] / "tests" / "django_settings"
    for name in ("settings_pub400.py", "settings_runtests_pub400.py"):
        assert "table_registry.install()" in (root / name).read_text()


def test_cleanup_drops_only_listed_leftovers() -> None:
    entries = [
        registry.Entry("TABLE", "LIB", "T_LISTED"),
        registry.Entry("TABLE", "LIB", "T_IN_SNAPSHOT"),
        registry.Entry("TABLE", "LIB", "T_GONE"),
        registry.Entry("TABLE", "OTHER", "T_UNLISTED"),
        registry.Entry("TABLE", "LIB", "DJDB2I_TEST_MARKER"),
    ]
    inventory = {
        "T_LISTED": "T",
        "T_IN_SNAPSHOT": "T",
        "T_UNLISTED": "T",
        "DJDB2I_TEST_MARKER": "T",
    }
    drop, unlisted = cleanup.plan(
        entries, "LIB", inventory, {"T_IN_SNAPSHOT"}, "DJDB2I_TEST_MARKER"
    )
    assert drop == ["T_LISTED"]
    assert unlisted == ["T_UNLISTED"]


def test_cleanup_refuses_without_the_list(monkeypatch, capsys) -> None:
    monkeypatch.delenv(registry.ENV, raising=False)
    assert cleanup.main([]) == 2
    assert "DB2I_TABLE_LIST is not set" in capsys.readouterr().out
