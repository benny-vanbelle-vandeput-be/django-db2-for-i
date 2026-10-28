"""The reference for tests/scenarios/boolean_condition_scenarios.py: Django writing the
SQL it writes for a backend with native booleans (has_native_boolean_field, as
on PostgreSQL: ``flag``, ``NOT flag``), evaluated by an in-memory SQLite
database with standard three-valued logic. Plain SQLite would not do: without
native booleans Django writes ``~F("flag")`` as ``CASE WHEN flag = 0 THEN 1
ELSE 0 END``, which is two-valued."""

import pytest
from django.db import connections

from tests.offline.reference_db import sqlite_reference
from tests.scenarios import boolean_condition_scenarios as scenarios
from tests.testapp.models import Switch


@pytest.fixture
def reference(django_db_blocker):
    with sqlite_reference(django_db_blocker, (Switch,)) as alias:
        connections[alias].features.has_native_boolean_field = True
        scenarios.create(alias)
        yield alias


def test_the_reference_writes_native_boolean_sql(reference) -> None:
    sql, _ = (
        scenarios.querysets(reference)["filter(~F(flag))"].query.get_compiler(reference).as_sql()
    )
    assert sql.endswith('WHERE NOT "testapp_switch"."flag"')


def test_expected_rows_are_the_reference(reference) -> None:
    actual = {name: scenarios.rows(qs) for name, qs in scenarios.querysets(reference).items()}
    assert actual == scenarios.EXPECTED
