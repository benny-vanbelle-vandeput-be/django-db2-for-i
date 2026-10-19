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


def test_values_longer_than_the_column_never_match_a_truncated_row(live, empty) -> None:
    """A value longer than NVARCHAR(100) must not fail (CWB0111) and must never
    match a row holding its truncated form."""
    truncated = "n" * 100
    longer = truncated + "x"  # 101 characters
    Author.objects.create(name=truncated)
    Author.objects.create(name="other")
    assert names(Author.objects.filter(name=longer)) == []
    assert names(Author.objects.filter(name__in=[longer, "other"])) == ["other"]
    assert names(Author.objects.exclude(name__in=[longer])) == sorted([truncated, "other"])
    assert names(Author.objects.exclude(name=longer)) == sorted([truncated, "other"])
    assert names(Author.objects.filter(name__gt=longer)) == ["other"]  # "nnn...n" < "nnn...nx"
    assert names(Author.objects.filter(name__lt=longer)) == [truncated]


def test_utf16_units_decide_whether_a_value_fits(live, empty) -> None:
    from tests.testapp.models import Tag

    fits = "e" * 49 + "é"
    too_long = "e" * 49 + "\U0001f600"  # 50 by len(), 51 UTF-16 units
    Tag.objects.create(label=fits)
    assert list(Tag.objects.filter(label=fits).values_list("label", flat=True)) == [fits]
    assert Tag.objects.filter(label=too_long).count() == 0


def test_expressions_compare_long_values(live, empty) -> None:
    from django.db.models.functions import Lower, Substr

    Author.objects.create(name="Abcdef")
    lowered = Author.objects.annotate(low=Lower("name"))
    assert names(lowered.filter(low="abcdef")) == ["Abcdef"]
    assert names(lowered.filter(low="x" * 150)) == []
    start = Author.objects.annotate(start=Substr("name", 1, 3))
    assert names(start.filter(start="Abc")) == ["Abcdef"]
    assert names(start.filter(start="Abcdef")) == []  # longer than SUBSTR(..., 1, 3)
