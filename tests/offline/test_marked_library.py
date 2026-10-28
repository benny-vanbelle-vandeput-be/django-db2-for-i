"""The own IBM i tests create tables only inside a marked library (no server needed).

tests/ibmi/marked_library.py's guard() fails a CREATE TABLE / VIEW / ALIAS
outside QTEMP while no module owns the marker; conftest.py installs it on
every connection of the IBM i tests.
"""

import types

import pytest

from tests.ibmi import marked_library

CONTEXT = {"connection": types.SimpleNamespace(settings_dict={"NAME": "TESTLIB"})}


def run(sql: str) -> list[str]:
    executed: list[str] = []

    def execute(sql, params, many, context):
        executed.append(sql)

    marked_library.guard(execute, sql, (), False, CONTEXT)
    return executed


@pytest.fixture
def unowned(monkeypatch):
    monkeypatch.setattr(marked_library, "_owner", None)
    monkeypatch.setattr(marked_library, "_allowed", 0)


@pytest.mark.parametrize(
    "sql",
    [
        'CREATE TABLE "DJANGO_MIGRATIONS" ("ID" INTEGER)',
        'CREATE TABLE "TESTLIB"."TESTAPP_AUTHOR" ("ID" INTEGER)',
        'CREATE TABLE "OTHERLIB"."T" ("ID" INTEGER)',
        "create or replace table t (id integer)",
        'CREATE VIEW "V" AS SELECT 1 FROM SYSIBM.SYSDUMMY1',
        'CREATE ALIAS "A" FOR "T"',
    ],
)
def test_no_table_outside_a_marked_library(unowned, sql) -> None:
    with pytest.raises(pytest.fail.Exception, match="outside a marked library"):
        run(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "CREATE TABLE QTEMP.DJINQ (A INTEGER, B INTEGER)",
        'CREATE OR REPLACE TABLE "QTEMP"."T" (A INTEGER)',
        'INSERT INTO "TESTAPP_AUTHOR" ("NAME") VALUES (%s)',
        'DROP TABLE "DJANGO_MIGRATIONS"',
        'CREATE INDEX "I" ON "T" ("A")',
    ],
)
def test_qtemp_and_other_statements_pass(unowned, sql) -> None:
    assert run(sql) == [sql]


def test_inside_a_marked_library(monkeypatch) -> None:
    monkeypatch.setattr(marked_library, "_owner", "tests/ibmi/test_cpa32b2.py")
    sql = 'CREATE TABLE "DJANGO_MIGRATIONS" ("ID" INTEGER)'
    assert run(sql) == [sql]


def test_the_creation_gate_may(unowned) -> None:
    sql = 'CREATE TABLE "DJDB2I_TEST_MARKER" ("RUN_ID" CHAR(32))'
    with marked_library.unmarked_creates_allowed():
        assert run(sql) == [sql]
    with pytest.raises(pytest.fail.Exception):
        run(sql)


def test_conftest_installs_the_guard() -> None:
    from pathlib import Path

    conftest = Path(marked_library.__file__).with_name("conftest.py").read_text()
    assert "install_guard()" in conftest
