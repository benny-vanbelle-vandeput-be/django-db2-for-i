"""The reference for tests/tuple_lookup_scenarios.py: Django on SQLite, a
backend with supports_tuple_lookups and standard row-value semantics (an
in-memory database, no IBM i)."""

import pytest
from django.db import connections

from tests import tuple_lookup_scenarios as scenarios
from tests.offline.reference_db import sqlite_reference
from tests.testapp.models import Account, Contact


@pytest.fixture
def reference(django_db_blocker):
    with sqlite_reference(django_db_blocker, (Account, Contact)) as alias:
        assert connections[alias].features.supports_tuple_lookups
        scenarios.create(alias)
        yield alias


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
