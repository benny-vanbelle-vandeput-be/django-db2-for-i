"""Aggregates against the IBM i: Avg, empty filters, StringAgg, AnyValue,
subqueries in GROUP BY (writes).

The tests.testapp tables are created for this module and dropped again
(``testapp_tables`` in conftest.py).
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.db import models
from django.db.models import (
    Avg,
    Case,
    Count,
    F,
    Max,
    OuterRef,
    Q,
    Subquery,
    Value,
    When,
)
from django.db.models.functions import Cast

from django_db2_for_i import compat
from tests.testapp.models import Author, Book

pytestmark = pytest.mark.usefixtures("testapp_tables")

# General aggregates from Django 6.0 (on 5.2, StringAgg only in contrib.postgres).
needs_string_agg = pytest.mark.skipif(
    compat.StringAgg is None, reason="StringAgg requires Django 6.0+ (Known limitations)"
)
needs_any_value = pytest.mark.skipif(
    not hasattr(models, "AnyValue"), reason="AnyValue is a Django 6.0+ aggregate"
)


def test_avg_keeps_fractions(live, empty) -> None:
    """Avg of an integer is fractional (AVG of INTEGER is an INTEGER on Db2 for i);
    Avg of a DecimalField stays an exact Decimal."""
    author = Author.objects.create(name="a")
    other = Author.objects.create(name="b")
    for pages in (1, 2, 2):
        Book.objects.create(author=author, title="t", pages=pages)
    assert Book.objects.aggregate(avg=Avg("pages")) == {"avg": pytest.approx(5 / 3)}
    by_author = Author.objects.annotate(avg=Avg("book__pages")).order_by("id")
    assert [(a, a.avg) for a in by_author] == [(author, pytest.approx(5 / 3)), (other, None)]
    assert Book.objects.aggregate(avg=Avg("pages", filter=Q(pages__gt=1)))["avg"] == 2.0
    # AVG of DECIMAL(5, 2) is DECIMAL(31, 28) on Db2 for i: exact, no float rounding.
    as_decimal = Cast("pages", models.DecimalField(max_digits=5, decimal_places=2))
    assert Book.objects.aggregate(avg=Avg(as_decimal))["avg"] == Decimal(
        "1.6666666666666666666666666666"
    )


def test_aggregate_filter_matching_nothing(live, empty) -> None:
    """filter=Q(...__in=[]) collapses Django's CASE to NULL (typed: SQL0171 otherwise)."""
    from django.db.models import Sum

    author = Author.objects.create(name="a")
    Book.objects.create(author=author, title="t", pages=10)
    nothing = Q(pk__in=[])
    authors = Author.objects.annotate(n=Count("book", filter=Q(book__in=[])))
    assert [(a, a.n) for a in authors] == [(author, 0)]
    assert Book.objects.aggregate(m=Max("pages", filter=nothing)) == {"m": None}
    assert Book.objects.aggregate(s=Sum("pages", filter=nothing, default=0)) == {"s": 0}
    pages = Case(When(nothing, then=F("pages")))
    assert list(Book.objects.annotate(p=pages).values_list("p", flat=True)) == [None]


@needs_string_agg
def test_string_agg(live, empty) -> None:
    """StringAgg as LISTAGG: per group, filtered, with a default, beyond NVARCHAR's
    2000 character LISTAGG limit, and non-ASCII values and separators."""
    from django.db.models import StringAgg

    author = Author.objects.create(name="a")
    nobody = Author.objects.create(name="b")
    for title in ["één", "two"] + ["x" * 199] * 11:
        Book.objects.create(author=author, title=title, pages=len(title))
    by_author = Author.objects.order_by("id")
    titles = by_author.annotate(t=StringAgg("book__title", Value(" · "), default=Value("-")))
    assert [(a, len(a.t)) for a in titles] == [(author, 3 + 3 + 11 * 199 + 12 * 3), (nobody, 1)]
    assert sorted(titles[0].t.split(" · ")) == ["two"] + ["x" * 199] * 11 + ["één"]
    assert titles[1].t == "-"
    short = Book.objects.aggregate(t=StringAgg("title", Value("'"), filter=Q(pages__lt=10)))
    assert sorted(short["t"].split("'")) == ["two", "één"]
    long = Book.objects.aggregate(t=StringAgg("title", Value(","), filter=Q(pages__gt=10)))
    assert long == {"t": ",".join(["x" * 199] * 11)}  # 2199 characters
    # LISTAGG over no values is fetched as "" by the ODBC driver; the backend keeps NULL,
    # and a real empty string stays one.
    assert Book.objects.filter(pages=0).aggregate(t=StringAgg("title", Value(","))) == {"t": None}
    Book.objects.create(author=nobody, title="", pages=0)
    assert Book.objects.filter(pages=0).aggregate(t=StringAgg("title", Value(","))) == {"t": ""}


@needs_any_value
def test_any_value(live, empty) -> None:
    """The real-world pattern: one value of a non-grouped column per group."""
    from django.db.models import AnyValue

    author = Author.objects.create(name="a")
    other = Author.objects.create(name="b")
    for title in ("t1", "t2"):
        Book.objects.create(author=author, title=title, pages=10)
    Book.objects.create(author=other, title="u", pages=500)
    per_author = (
        Book.objects.values("author")
        .annotate(title=AnyValue("title"), n=Count("id"))
        .order_by("author")
    )
    rows = [(row["author"], row["title"], row["n"]) for row in per_author]
    assert rows[0][0] == author.pk and rows[0][1] in ("t1", "t2") and rows[0][2] == 2
    assert rows[1] == (other.pk, "u", 1)
    filtered = Author.objects.annotate(t=AnyValue("book__title", filter=Q(book__pages__gt=100)))
    assert {a.name: a.t for a in filtered} == {"a": None, "b": "u"}


def test_subqueries_in_group_by(live, empty) -> None:
    """The real-world patterns: an aggregate next to a subquery annotation (the
    subquery is grouped), and grouping by a subquery value."""
    old = dt.datetime(2020, 1, 1, tzinfo=dt.UTC)
    new = dt.datetime(2025, 1, 1, tzinfo=dt.UTC)
    author = Author.objects.create(name="a")
    other = Author.objects.create(name="b")
    Author.objects.create(name="c")
    for title, published in (("old", old), ("new", new)):
        Book.objects.create(author=author, title=title, pages=10, published=published)
    Book.objects.create(author=other, title="only", pages=20, published=old)
    latest = Book.objects.filter(author=OuterRef("pk")).order_by("-published").values("title")
    authors = Author.objects.annotate(latest=Subquery(latest[:1]), n=Count("book"))
    assert {(a.name, a.latest, a.n) for a in authors} == {
        ("a", "new", 2),
        ("b", "only", 1),
        ("c", None, 0),
    }
    books = Book.objects.filter(author=OuterRef("pk")).values("author")
    count = Subquery(books.annotate(c=Count("pk")).values("c"))
    breakdown = Author.objects.values(books=count).annotate(n=Count("id"))
    assert {(row["books"], row["n"]) for row in breakdown} == {(None, 1), (1, 1), (2, 1)}


@needs_string_agg
def test_string_agg_order_by(live, empty) -> None:
    """The real-world pattern: an ordered list per group, also with NULL ordering
    and a filter."""
    from django.db.models import StringAgg

    old = dt.datetime(2020, 1, 1, tzinfo=dt.UTC)
    new = dt.datetime(2025, 1, 1, tzinfo=dt.UTC)
    author = Author.objects.create(name="a")
    for title, pages, published in (("b", 30, old), ("a", 10, None), ("c", 20, new)):
        Book.objects.create(author=author, title=title, pages=pages, published=published)

    def titles(**options):
        annotation = StringAgg("book__title", Value(","), **options)
        return Author.objects.annotate(t=annotation).get().t

    assert titles(order_by="book__title") == "a,b,c"
    assert titles(order_by="-book__pages") == "b,c,a"
    assert titles(order_by=F("book__published").desc(nulls_last=True)) == "c,b,a"
    assert titles(order_by=F("book__published").asc(nulls_first=True)) == "a,b,c"
    assert titles(order_by="book__title", filter=Q(book__pages__gt=10)) == "b,c"


def test_group_by_expressions_with_values(live, empty) -> None:
    """The real-world report patterns behind the LATERAL grouping table: grouping
    by an annotation with a value, across a join, with HAVING, ORDER BY, a
    nested use and .count(); a grouped subquery with a value; model instances
    with a computed flag."""
    from django.db.models import Exists, Min, Sum
    from django.db.models.functions import Greatest, Least, Mod

    author = Author.objects.create(name="a")
    other = Author.objects.create(name="b")
    for title, pages in (("s1", 50), ("s2", 70), ("l1", 500)):
        Book.objects.create(author=author, title=title, pages=pages)
    Book.objects.create(author=other, title="l2", pages=900)

    by_size = Book.objects.annotate(small=Q(pages__lt=100)).values("small")
    counts = by_size.annotate(n=Count("id"), total=Sum("pages")).order_by("-total")
    assert list(counts) == [
        {"small": False, "n": 2, "total": 1400},
        {"small": True, "n": 2, "total": 120},
    ]
    assert by_size.annotate(n=Count("id")).count() == 2
    assert list(by_size.annotate(n=Count("id")).filter(n__gt=1, small=True)) == [
        {"small": True, "n": 2}
    ]
    # Across a join: authors grouped by the size of their books.
    per_author = (
        Author.objects.values(small=Q(book__pages__lt=100))
        .annotate(authors=Count("id", distinct=True))
        .order_by("small")
    )
    assert [(row["small"], row["authors"]) for row in per_author] == [(False, 2), (True, 1)]
    # A value inside the grouped expression, also nested in a select expression.
    buckets = Book.objects.values(bucket=Mod("pages", 100)).annotate(n=Count("id"))
    assert sorted((row["bucket"], row["n"]) for row in buckets) == [(0, 2), (50, 1), (70, 1)]
    nested = (
        Book.objects.annotate(at_least=Greatest("pages", Value(600)))
        .values("at_least")
        .annotate(low=Min("pages"), least=Least("low", "at_least"))
        .values_list("least", flat=True)
    )
    assert sorted(nested) == [50, 900]
    # A grouped subquery and Exists() that filter with a value.
    long_books = Book.objects.filter(author=OuterRef("pk"), pages__gt=400)
    has_long = Author.objects.values_list(Exists(long_books)).annotate(n=Count("*"))
    assert dict(has_long) == {True: 2}
    count = Subquery(long_books.values("author").annotate(c=Count("pk")).values("c"))
    assert dict(Author.objects.values_list(count).annotate(n=Count("*"))) == {1: 2}
    # Model instances with a computed flag next to an aggregate.
    flag = Case(When(book__pages__gt=600, then=Value(True)), default=Value(False))
    rows = Author.objects.annotate(total=Sum("book__pages"), big=flag).order_by("name", "big")
    assert [(a.name, a.big, a.total) for a in rows] == [
        ("a", False, 620),
        ("b", True, 900),
    ]
