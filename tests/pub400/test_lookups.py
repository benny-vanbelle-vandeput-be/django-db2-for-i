"""Lookups against the IBM i (writes).

The tests.testapp tables are created for this module and dropped again
(``testapp_tables`` in conftest.py).
"""

import pytest

from tests.testapp.models import Author

pytestmark = pytest.mark.usefixtures("testapp_tables")


def names(queryset) -> list[str]:
    return sorted(queryset.values_list("name", flat=True))


def test_iexact_with_wildcard_characters(live, empty) -> None:
    """iexact compares the value as it is: _, % and \\ are no wildcards there,
    and must not match other rows."""
    for name in ("a_b", "axb", "x%y", "xzzy", "back\\slash", "backxslash"):
        Author.objects.create(name=name)
    assert names(Author.objects.filter(name__iexact="A_B")) == ["a_b"]
    assert names(Author.objects.filter(name__iexact="X%Y")) == ["x%y"]
    assert names(Author.objects.filter(name__iexact="BACK\\SLASH")) == ["back\\slash"]
    # The LIKE lookups keep escaping the wildcards.
    assert names(Author.objects.filter(name__icontains="_")) == ["a_b"]
    assert names(Author.objects.filter(name__istartswith="X%")) == ["x%y"]


def test_iexact_with_non_ascii_letters(live, empty) -> None:
    """UPPER() on NVARCHAR: how Db2 for i uppercases é, Ü and ß."""
    for name in ("café", "MÜNCHEN", "straße"):
        Author.objects.create(name=name)
    assert names(Author.objects.filter(name__iexact="CAFÉ")) == ["café"]
    assert names(Author.objects.filter(name__iexact="münchen")) == ["MÜNCHEN"]
    assert names(Author.objects.filter(name__iexact="STRASSE")) == []
    assert names(Author.objects.filter(name__iexact="STRAßE")) == ["straße"]
