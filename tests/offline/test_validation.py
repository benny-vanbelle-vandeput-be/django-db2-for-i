"""The system check for journaled libraries (validation.py), with a fake cursor."""

from __future__ import annotations

import django.db
import pytest
from django.db import connections
from django.test import override_settings

from django_db2_for_i.base import DatabaseWrapper
from django_db2_for_i.validation import W001, W002, journal_problem

# JOURNALED, INHERIT_JOURNALING, JOURNAL_LIBRARY, JOURNAL_NAME, QSQJRN count
QSQJRN = ("NO", "NO", None, None, 1)
STRJRNLIB = ("YES", "YES", "JRNLIB", "APPJRN", 0)
NO_INHERIT = ("YES", "NO", "JRNLIB", "APPJRN", 0)
NONE = ("NO", "NO", None, None, 0)


class FakeCursor:
    """Answers the journaling query per library and records every statement."""

    def __init__(self, rows: dict[str, tuple], error: Exception | None = None):
        self.rows = rows
        self.error = error
        self.executed: list[tuple[str, object]] = []
        self._row = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        if self.error:
            raise self.error
        library = sql.split("LIBRARY_NAME => '", 1)[1].split("'", 1)[0]
        self._row = self.rows.get(library)

    def fetchone(self):
        return self._row


def make_wrapper(name="APPLIB", test_name="DJTEST") -> DatabaseWrapper:
    settings_dict = dict(connections["default"].settings_dict)
    settings_dict["NAME"] = name
    settings_dict["TEST"] = {**settings_dict["TEST"], "NAME": test_name}
    return DatabaseWrapper(settings_dict, alias="offline_test")


@pytest.mark.parametrize("row", [QSQJRN, STRJRNLIB, None], ids=["qsqjrn", "strjrnlib", "missing"])
def test_journaled_or_missing_library_is_no_problem(row) -> None:
    assert journal_problem(FakeCursor({"APPLIB": row}), "APPLIB") is None


def test_library_without_journal() -> None:
    problem = journal_problem(FakeCursor({"APPLIB": NONE}), "APPLIB")
    assert problem == "library APPLIB has no QSQJRN journal and is not journaled (STRJRNLIB)"


def test_journaled_library_without_inheritance() -> None:
    problem = journal_problem(FakeCursor({"APPLIB": NO_INHERIT}), "APPLIB")
    assert "journaled to JRNLIB/APPJRN, but new objects do not inherit journaling" in problem


def test_padded_catalog_values() -> None:
    row = ("YES       ", "YES ", "JRNLIB    ", "APPJRN    ", 0)
    assert journal_problem(FakeCursor({"APPLIB": row}), "APPLIB") is None


def test_the_library_is_a_literal_not_a_parameter() -> None:
    # A failing service with parameters would poison the connection (drivers/pyodbc.py).
    cursor = FakeCursor({"APPLIB": QSQJRN})
    journal_problem(cursor, "APPLIB")
    [(sql, params)] = cursor.executed
    assert params is None
    assert "QSYS2.OBJECT_STATISTICS('APPLIB', '*JRN', 'QSQJRN')" in sql
    assert "QSYS2.LIBRARY_INFO(LIBRARY_NAME => 'APPLIB', IGNORE_ERRORS => 'YES', " in sql


@pytest.mark.parametrize("name", ["TOOLONGNAME1", "A'B", "1ABC", ""])
def test_only_system_names_reach_the_query(name) -> None:
    cursor = FakeCursor({})
    with pytest.raises(ValueError, match="not the system name"):
        journal_problem(cursor, name)
    assert cursor.executed == []


def check(wrapper, cursor, monkeypatch):
    monkeypatch.setattr(wrapper, "cursor", lambda: cursor)
    return wrapper.validation.check()


def test_name_and_test_name_are_checked(monkeypatch) -> None:
    cursor = FakeCursor({"APPLIB": QSQJRN, "DJTEST": NONE})
    [issue] = check(make_wrapper(test_name="djtest"), cursor, monkeypatch)
    assert issue.id == W001
    assert issue.msg.startswith(
        "DATABASES['offline_test']['TEST']['NAME']: library DJTEST has no QSQJRN journal"
    )
    assert "CRTJRN JRN(DJTEST/QSQJRN) JRNRCV(DJTEST/QSQJRN0001)" in issue.hint
    assert f"SILENCED_SYSTEM_CHECKS = ['{W001}']" in issue.hint
    assert len(cursor.executed) == 2


def test_same_library_is_checked_once(monkeypatch) -> None:
    cursor = FakeCursor({"APPLIB": NONE})
    [issue] = check(make_wrapper(test_name="applib"), cursor, monkeypatch)
    assert issue.msg.startswith("DATABASES['offline_test']['NAME']: library APPLIB")
    assert len(cursor.executed) == 1


def test_journaled_libraries_pass(monkeypatch) -> None:
    cursor = FakeCursor({"APPLIB": QSQJRN, "DJTEST": STRJRNLIB})
    assert check(make_wrapper(), cursor, monkeypatch) == []


def test_without_test_name_only_name(monkeypatch) -> None:
    cursor = FakeCursor({"APPLIB": QSQJRN})
    assert check(make_wrapper(test_name=None), cursor, monkeypatch) == []
    assert len(cursor.executed) == 1


def test_database_error_is_a_separate_warning(monkeypatch) -> None:
    cursor = FakeCursor({}, error=django.db.OperationalError("SQL0443 failed"))
    issues = check(make_wrapper(), cursor, monkeypatch)
    assert [issue.id for issue in issues] == [W002, W002]
    assert "Could not check whether DATABASES['offline_test']['NAME'] (APPLIB)" in issues[0].msg


def test_name_that_is_no_system_name_is_a_separate_warning(monkeypatch) -> None:
    cursor = FakeCursor({"DJTEST": QSQJRN})
    [issue] = check(make_wrapper(name="A_LONG_SQL_SCHEMA"), cursor, monkeypatch)
    assert issue.id == W002


@override_settings(SILENCED_SYSTEM_CHECKS=[W001])
def test_silenced_check_does_not_query(monkeypatch) -> None:
    wrapper = make_wrapper()

    def no_cursor():
        raise AssertionError("the silenced check opened a cursor")

    monkeypatch.setattr(wrapper, "cursor", no_cursor)
    assert wrapper.validation.check() == []
