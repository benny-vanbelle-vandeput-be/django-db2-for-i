"""tests/table_registry.py and scripts/ibmi_cleanup.py: the cleanup list (no server needed)."""

import contextlib
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


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ('RENAME TABLE "T_OLD" TO "T_NEW"', ("LIB", "T_OLD", "T_NEW")),
        ('rename table "MYLIB"."T_OLD" to t_new', ("MYLIB", "T_OLD", "T_NEW")),
        ("RENAME TABLE T_OLD TO T_NEW FOR SYSTEM NAME TNEW", ("LIB", "T_OLD", "T_NEW")),
    ],
)
def test_table_renames_are_recognised(sql, expected) -> None:
    assert registry.parse_rename(sql, "lib") == expected


def test_index_renames_are_not_table_renames() -> None:
    assert registry.parse_rename('RENAME INDEX "I" TO "J"', "lib") is None


def _run(statements, path, failing=()):
    """The wrapper around a fake execute; ``seen`` is the list as each statement ran."""
    seen = []

    def execute(sql, params, many, context):
        seen.append((sql, [e.name for e in registry.read(path)]))
        if sql in failing:
            raise RuntimeError("SQL0204")

    context = {"connection": FakeConnection()}
    for sql in statements:
        with contextlib.suppress(RuntimeError):
            registry.wrapper(execute, sql, None, False, context)
    return seen


def test_a_rename_updates_the_entry_before_it_runs_and_again_on_the_way_back(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "created-objects.txt"
    monkeypatch.setenv(registry.ENV, str(path))
    seen = _run(
        [
            'CREATE TABLE "T_OLD" (X INT)',
            'RENAME TABLE "T_OLD" TO "T_NEW"',
            'RENAME TABLE "T_NEW" TO "T_OLD"',
        ],
        path,
    )
    assert [names for _sql, names in seen] == [["T_OLD"], ["T_NEW"], ["T_OLD"]]
    (entry,) = registry.read(path)
    assert (entry.kind, entry.library, entry.name) == ("TABLE", "TESTLIB", "T_OLD")


def test_a_pending_rename_holds_both_names(tmp_path, monkeypatch) -> None:
    path = tmp_path / "created-objects.txt"
    monkeypatch.setenv(registry.ENV, str(path))
    rename = 'RENAME TABLE "T_OLD" TO "T_NEW"'
    pending = []

    def execute(sql, params, many, context):
        pending.extend(registry.read(path))

    context = {"connection": FakeConnection()}
    registry.wrapper(execute, 'CREATE TABLE "T_OLD" (X INT)', None, False, context)
    pending.clear()
    registry.wrapper(execute, rename, None, False, context)
    ((name, old, names),) = [(e.name, e.renamed_from, e.names) for e in pending]
    assert (name, old, names) == ("T_NEW", "T_OLD", {"T_NEW", "T_OLD"})
    assert path.read_text().splitlines()[0].endswith("\tT_NEW\t" + pending[0].created)
    (done,) = registry.read(path)
    assert (done.name, done.renamed_from) == ("T_NEW", "")


def test_a_failed_rename_sets_the_entry_back(tmp_path, monkeypatch) -> None:
    path = tmp_path / "created-objects.txt"
    monkeypatch.setenv(registry.ENV, str(path))
    rename = 'RENAME TABLE "T_OLD" TO "T_NEW"'
    seen = _run(['CREATE TABLE "T_OLD" (X INT)', rename], path, failing={rename})
    assert seen[-1] == (rename, ["T_NEW"])  # written before the statement ran
    assert [e.name for e in registry.read(path)] == ["T_OLD"]


def test_a_rename_never_adds_a_table_that_is_not_on_the_list(tmp_path, monkeypatch) -> None:
    path = tmp_path / "created-objects.txt"
    monkeypatch.setenv(registry.ENV, str(path))
    _run(['CREATE TABLE "LISTED" (X INT)', 'RENAME TABLE "REAL_TABLE" TO "STOLEN"'], path)
    assert [e.name for e in registry.read(path)] == ["LISTED"]


def test_cleanup_drops_a_table_renamed_before_a_crash(tmp_path, monkeypatch) -> None:
    """A run creates a table, renames it, and dies before the rename back: the
    list names the renamed table, and the cleanup plan drops it (marker rule
    and snapshot unchanged)."""
    path = tmp_path / "created-objects.txt"
    monkeypatch.setenv(registry.ENV, str(path))
    _run(['CREATE TABLE "TESTAPP_RENAMEPROBE" (X INT)'], path)
    _run(['RENAME TABLE "TESTAPP_RENAMEPROBE" TO "TESTAPP_RENAMED_PROBE"'], path)
    # The crash: no rename back. The library holds the renamed table only.
    inventory = {"TESTAPP_RENAMED_PROBE": "T", "DJDB2I_TEST_MARKER": "T", "KEEP": "T"}
    drop, unlisted = cleanup.plan(
        registry.read(path), "TESTLIB", inventory, {"KEEP"}, "DJDB2I_TEST_MARKER"
    )
    assert drop == ["TESTAPP_RENAMED_PROBE"]
    assert unlisted == []
    # The same leftover in another library (no entry there) is never dropped.
    drop, unlisted = cleanup.plan(
        registry.read(path), "OTHERLIB", inventory, set(), "DJDB2I_TEST_MARKER"
    )
    assert drop == [] and "TESTAPP_RENAMED_PROBE" in unlisted


def _crash_during_rename(path, monkeypatch):
    """Create a listed table, then die while its RENAME TABLE runs (no except
    clause runs for a process that dies; KeyboardInterrupt stands in for it)."""
    monkeypatch.setenv(registry.ENV, str(path))
    _run(['CREATE TABLE "TESTAPP_RENAMEPROBE" (X INT)'], path)

    def dies(sql, params, many, context):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        registry.wrapper(
            dies,
            'RENAME TABLE "TESTAPP_RENAMEPROBE" TO "TESTAPP_RENAMED_PROBE"',
            None,
            False,
            {"connection": FakeConnection()},
        )
    (entry,) = registry.read(path)
    assert entry.names == {"TESTAPP_RENAMEPROBE", "TESTAPP_RENAMED_PROBE"}
    return registry.read(path)


@pytest.mark.parametrize(
    "existing",
    ["TESTAPP_RENAMEPROBE", "TESTAPP_RENAMED_PROBE"],
    ids=["rename-did-not-happen", "rename-happened"],
)
def test_cleanup_drops_whichever_name_exists_after_a_crash_during_the_rename(
    tmp_path, monkeypatch, existing
) -> None:
    entries = _crash_during_rename(tmp_path / "created-objects.txt", monkeypatch)
    inventory = {existing: "T", "DJDB2I_TEST_MARKER": "T", "KEEP": "T"}
    drop, unlisted = cleanup.plan(entries, "TESTLIB", inventory, {"KEEP"}, "DJDB2I_TEST_MARKER")
    assert (drop, unlisted) == ([existing], [])


def test_a_rename_updates_the_newest_entry_of_a_name(tmp_path, monkeypatch) -> None:
    """Every run appends a CREATE; the rename belongs to the table that exists now."""
    path = tmp_path / "created-objects.txt"
    monkeypatch.setenv(registry.ENV, str(path))
    _run(['CREATE TABLE "T" (X INT)', 'CREATE TABLE "T" (X INT)'], path)
    _run(['RENAME TABLE "T" TO "T_NEW"'], path)
    assert [e.name for e in registry.read(path)] == ["T", "T_NEW"]
