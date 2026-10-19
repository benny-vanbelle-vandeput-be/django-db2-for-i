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


def test_in_subquery_outside_a_search_condition(live, empty) -> None:
    """IN (subquery) as a selected value and in XOR (CASE WHEN on Db2 for i, where
    IN (subquery) is rejected) gives exactly the rows of the same condition in a
    WHERE clause (plain IN): with a NULL in x and NULLs in the subquery, positive
    and negated; the positive form also equals raw SQL IN."""
    from django.db.models import Q

    from tests.testapp.models import Link

    a1, a2, a3 = (Author.objects.create(name=n) for n in ("a1", "a2", "a3"))
    links = [Link.objects.create(author=a) for a in (a1, a2, a3, None)]  # x NULL in the last
    by_name = {
        "match and NULL": Link.objects.filter(pk__in=[links[0].pk, links[3].pk]),
        "no NULL": Link.objects.filter(pk=links[1].pk),
        "only NULL": Link.objects.filter(pk=links[3].pk),
        "empty": Link.objects.filter(pk=-1),
    }
    table, column = '"TESTAPP_LINK"', '"AUTHOR_ID"'
    for name, rows in by_name.items():
        ids = ", ".join(str(pk) for pk in rows.values_list("pk", flat=True)) or "-1"
        with live.cursor() as cursor:
            plain = {}
            for op in ("IN", "NOT IN"):
                cursor.execute(
                    f"SELECT ID FROM {table} WHERE {column} {op} "
                    f"(SELECT {column} FROM {table} WHERE ID IN ({ids}))"
                )
                plain[op] = {row[0] for row in cursor.fetchall()}
        subquery = rows.values("author")
        selected = Link.objects.annotate(
            yes=Q(author__in=subquery), no=~Q(author__in=subquery)
        ).values_list("pk", "yes", "no")
        assert {pk for pk, yes, _ in selected if yes} == plain["IN"], name
        # ~Q on a nullable column is Django's NOT (x IN (...) AND x IS NOT NULL), not
        # SQL's NOT IN: compare with the same ~Q in WHERE (plain IN there).
        negated = set(Link.objects.filter(~Q(author__in=subquery)).values_list("pk", flat=True))
        assert {pk for pk, _, no in selected if no} == negated, name
        assert negated >= plain["NOT IN"], name
        xor = Link.objects.filter(Q(author__in=subquery) ^ Q(pk=links[1].pk))
        expected = plain["IN"] ^ {links[1].pk}
        assert set(xor.values_list("pk", flat=True)) == expected, name
