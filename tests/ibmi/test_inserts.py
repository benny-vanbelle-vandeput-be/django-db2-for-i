"""Inserts against the IBM i: returning columns through ``SELECT ... FROM
FINAL TABLE (INSERT ...)`` (phase 5, step A) on full model instances.

The tests.testapp tables are created for this module and dropped again
(``testapp_tables`` in conftest.py).
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.test.utils import CaptureQueriesContext

from tests.testapp.models import Author, Book, Defaults

pytestmark = pytest.mark.usefixtures("testapp_tables")


def test_create_reads_the_key_from_the_insert(live, empty) -> None:
    with CaptureQueriesContext(live) as queries:
        first = Author.objects.create(name="first")
        second = Author.objects.create(name="second")
    assert second.pk == first.pk + 1
    assert Author.objects.get(pk=second.pk).name == "second"
    statements = [query["sql"] for query in queries.captured_queries]
    assert all("FROM FINAL TABLE (INSERT INTO" in sql for sql in statements)
    assert not any("IDENTITY_VAL_LOCAL" in sql for sql in statements)


def test_save_sets_the_db_defaults_on_the_instance(live, empty) -> None:
    row = Defaults(number=5)
    row.save()
    # The values come from the insert itself, without a refresh.
    assert row.pk is not None
    assert row.number == 5
    assert row.text == "O'Brien 100%"
    assert row.flag is True
    assert row.amount == Decimal("1.50")
    assert row.day == dt.date(2026, 1, 2)
    assert row.nothing is None
    assert Defaults.objects.get(pk=row.pk).text == "O'Brien 100%"


def test_explicit_zero_key(live, empty) -> None:
    author = Author.objects.create(pk=0, name="zero")
    assert author.pk == 0
    assert Author.objects.get(pk=0).name == "zero"
    # The identity continues from its own counter (an explicit key does not move it).
    assert Author.objects.create(name="next").pk >= 1


def test_insert_in_a_transaction_is_rolled_back(live, empty) -> None:
    with pytest.raises(RuntimeError), transaction.atomic():
        author = Author.objects.create(name="rolled back")
        Book.objects.create(author=author, title="gone", pages=1)
        raise RuntimeError("roll back")
    assert not Author.objects.exists()
    assert not Book.objects.exists()


def test_duplicate_key_raises_integrity_error(live, empty) -> None:
    Author.objects.create(pk=7, name="first")
    with pytest.raises(IntegrityError), transaction.atomic():
        Author.objects.create(pk=7, name="duplicate")
    assert Author.objects.get(pk=7).name == "first"
