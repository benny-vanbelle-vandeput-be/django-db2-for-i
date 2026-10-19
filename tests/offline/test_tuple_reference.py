"""The reference for tests/tuple_lookup_scenarios.py: Django on SQLite, a
backend with supports_tuple_lookups and standard row-value semantics (an
in-memory database, no IBM i)."""

import pytest
from django.db import connections

from tests import tuple_lookup_scenarios as scenarios
from tests.testapp.models import Account, Contact

ALIAS = "tuple_reference"


@pytest.fixture
def reference(django_db_blocker):
    settings = connections.configure_settings(
        {
            "default": connections.settings["default"],
            ALIAS: {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"},
        }
    )
    connections.settings[ALIAS] = settings[ALIAS]
    django_db_blocker.unblock()
    try:
        connection = connections[ALIAS]
        assert connection.features.supports_tuple_lookups
        with connection.schema_editor() as editor:
            editor.create_model(Account)
            editor.create_model(Contact)
        scenarios.create(ALIAS)
        yield ALIAS
    finally:
        connections[ALIAS].close()
        del connections[ALIAS]
        del connections.settings[ALIAS]
        django_db_blocker.restore()


def test_expected_rows_are_the_reference(reference) -> None:
    actual = {name: scenarios.rows(qs) for name, qs in scenarios.querysets(reference).items()}
    assert actual == scenarios.EXPECTED


def test_known_differences_are_only_unknown_as_false() -> None:
    """The backend differs from the reference only where a selected UNKNOWN is
    False (issue #75): no other row or context."""
    for differences in scenarios.KNOWN_DIFFERENCES.values():
        for name, rows in differences.items():
            expected = scenarios.EXPECTED[name]
            assert len(rows) == len(expected)
            changed = set(rows) ^ set(expected)
            assert all(row[-1] in (None, False) for row in changed), name
