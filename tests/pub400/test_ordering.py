"""Ordering with NULLs against the IBM i (writes).

The tests.testapp tables are created for this module and dropped again
(``testapp_tables`` in conftest.py).
"""

import datetime as dt

import pytest
from django.db.models import F

from tests.testapp.models import Author, Book

pytestmark = pytest.mark.usefixtures("testapp_tables")


def test_nulls_order_largest(live, empty) -> None:
    """NULL sorts as the largest value (nulls_order_largest): last ascending and
    first descending by default; nulls_first / nulls_last override that."""
    author = Author.objects.create(name="a")
    for title, published in (
        ("old", dt.datetime(2020, 1, 1, tzinfo=dt.UTC)),
        ("none", None),
        ("new", dt.datetime(2025, 1, 1, tzinfo=dt.UTC)),
    ):
        Book.objects.create(author=author, title=title, published=published)

    def titles(*ordering):
        return list(Book.objects.order_by(*ordering).values_list("title", flat=True))

    assert titles("published") == ["old", "new", "none"]
    assert titles("-published") == ["none", "new", "old"]
    assert titles(F("published").asc(nulls_first=True)) == ["none", "old", "new"]
    assert titles(F("published").asc(nulls_last=True)) == ["old", "new", "none"]
    assert titles(F("published").desc(nulls_first=True)) == ["none", "new", "old"]
    assert titles(F("published").desc(nulls_last=True)) == ["new", "old", "none"]
