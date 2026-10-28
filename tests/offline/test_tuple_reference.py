"""The reference for tests/scenarios/tuple_lookup_scenarios.py: Django on SQLite, a
backend with supports_tuple_lookups and standard row-value semantics (an
in-memory database, no IBM i)."""

import pytest
from django.db import connections

from tests.offline.reference_db import sqlite_reference
from tests.scenarios import tuple_lookup_scenarios as scenarios
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


def test_there_are_no_known_differences() -> None:
    """The backend gets the reference rows in every context (issue #75 fixed the
    selected UNKNOWN, the last difference)."""
    assert scenarios.KNOWN_DIFFERENCES == {}
