"""Queries against the IBM i: DISTINCT, Exists(), predicates, comparisons,
logged queries, pagination and extracting date/time parts (writes).

The tests.testapp tables are created for this module and dropped again
(``testapp_tables`` in conftest.py).
"""

import datetime as dt

import pytest
from django.db import models
from django.db.models import (
    BooleanField,
    Case,
    Count,
    Exists,
    ExpressionWrapper,
    F,
    Max,
    OuterRef,
    Q,
    Subquery,
    Value,
    When,
)
from django.db.models.lookups import GreaterThan, LessThan

from django_db2_for_i.features import REASON_GROUP_BY_MARKERS
from tests.testapp.models import Author, Book

pytestmark = pytest.mark.usefixtures("testapp_tables")


def test_distinct_with_emulated_null_ordering(live, empty) -> None:
    """SELECT DISTINCT + nulls_first / nulls_last (hidden predicate column, compiler.py).

    Same rows as computed in Python, duplicates removed, and the hidden
    columns never reach model instances, values() or values_list().
    """
    one = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    two = dt.datetime(2026, 2, 1, tzinfo=dt.UTC)
    a1, a2, _ = (Author.objects.create(name=name) for name in ("a1", "a2", "a3"))
    for author, title, published in [
        (a1, "t1", None),
        (a1, "t1", None),  # duplicate row
        (a1, "t2", one),
        (a2, "t2", one),  # same (title, published) as the row before
        (a2, "t3", two),
    ]:
        Book.objects.create(author=author, title=title, published=published)

    first = F("published").asc(nulls_first=True)
    pairs = Book.objects.order_by(first, "title").distinct().values_list("title", "published")
    assert list(pairs) == [("t1", None), ("t2", one), ("t3", two)]
    last = F("published").desc(nulls_last=True)
    titles = Book.objects.order_by(last).distinct().values_list("title", flat=True)
    assert list(titles) == ["t3", "t2", "t1"]
    dicts = list(Book.objects.order_by(first, "title").distinct().values("title", "published"))
    assert dicts == [
        {"title": "t1", "published": None},
        {"title": "t2", "published": one},
        {"title": "t3", "published": two},
    ]

    # Django's own case: order authors by an annotated subquery, NULLs first.
    newest = (
        Book.objects.filter(author=OuterRef("pk"))
        .order_by()
        .values("author")
        .annotate(m=Max("published"))
        .values("m")
    )
    authors = (
        Author.objects.annotate(last=Subquery(newest, output_field=models.DateTimeField()))
        .order_by(F("last").asc(nulls_first=True), "name")
        .distinct()
    )
    assert [(a.name, a.last) for a in authors] == [("a3", None), ("a1", one), ("a2", two)]
    assert list(authors.values_list("name", "last")) == [
        ("a3", None),
        ("a1", one),
        ("a2", two),
    ]
    assert [sorted(row) for row in authors.values("name")] == [["name"]] * 3
    # With a parameter in the subquery (as in Django's ordering tests).
    newest_t = newest.filter(title__icontains="T")
    with_param = (
        Author.objects.annotate(last=Subquery(newest_t, output_field=models.DateTimeField()))
        .order_by(F("last").desc(nulls_last=True), "name")
        .distinct()
        .values_list("name", "last")
    )
    assert list(with_param) == [("a2", two), ("a1", one), ("a3", None)]


def test_exists_filter_regression(live, empty) -> None:
    """Plain filter(Exists()) and exclude(~Exists()) return the right rows.

    Regression: the Exists subquery selected a parameter marker, which fails
    in the IBM i host server ("Error in host server data stream", 30187), so
    every Exists() condition raised an error (fixed in compiler.py).
    """
    with_book, without_book = Author.objects.create(name="a1"), Author.objects.create(name="a2")
    Book.objects.create(author=with_book, title="t")
    books = Exists(Book.objects.filter(author=OuterRef("pk")))
    assert list(Author.objects.filter(books)) == [with_book]
    assert list(Author.objects.exclude(~books)) == [with_book]
    assert list(Author.objects.exclude(books)) == [without_book]


def test_exists_in_every_position(live, empty) -> None:
    """Exists(): EXISTS in WHERE, a first-row subquery elsewhere (compiler.py)."""
    a1, a2 = Author.objects.create(name="a1"), Author.objects.create(name="a2")
    Book.objects.create(author=a1, title="t")
    books = Exists(Book.objects.filter(author=OuterRef("pk")))
    by_id = Author.objects.order_by("id")
    assert list(by_id.filter(books)) == [a1]
    assert list(by_id.filter(~books)) == [a2]
    assert list(by_id.filter(Q(name="a2") | books)) == [a1, a2]
    assert list(by_id.annotate(has=books).values_list("name", "has")) == [
        ("a1", True),
        ("a2", False),
    ]
    assert list(by_id.annotate(has=~books).values_list("has", flat=True)) == [False, True]
    assert list(by_id.annotate(has=books).filter(has=False)) == [a2]
    case = Case(When(books, then=Value(1)), default=Value(0))
    assert list(by_id.annotate(x=case).values_list("x", flat=True)) == [1, 0]
    assert list(by_id.annotate(x=case).filter(x=1)) == [a1]
    assert list(Author.objects.order_by(books.desc(), "id")) == [a1, a2]
    grouped = Author.objects.annotate(has=books).values("has").annotate(n=Count("id"))
    assert sorted((row["has"], row["n"]) for row in grouped) == [(False, 1), (True, 1)]
    # Nested Exists with OuterRef(OuterRef()) (Django's lookup tests).
    nested = Exists(
        Book.objects.annotate(
            same=Exists(Author.objects.filter(name=OuterRef(OuterRef("name"))))
        ).filter(same=True)
    )
    assert Author.objects.filter(nested).count() == 2


def test_logged_queries_show_parameters(live, empty) -> None:
    """last_executed_query(): the logged SQL has the values (logging only)."""
    from django.test.utils import CaptureQueriesContext

    author = Author.objects.create(name="O'Brien")
    with CaptureQueriesContext(live) as ctx:
        assert list(Author.objects.filter(id__in=[None, author.id], name="O'Brien")) == [author]
    assert f"IN ({author.id})" in ctx.captured_queries[0]["sql"]
    assert "= 'O''Brien'" in ctx.captured_queries[0]["sql"]


def test_predicate_annotations_on_full_querysets(live, empty) -> None:
    """The real-world pattern: a Q / lookup annotation selected with the model.

    A select-list predicate with an untyped marker fails (SQL0418); the
    compiler writes it as CASE WHEN ... THEN TRUE ELSE FALSE END.
    """
    author = Author.objects.create(name="a")
    small = Book.objects.create(author=author, title="small", pages=50)
    big = Book.objects.create(author=author, title="big", pages=500)
    by_id = Book.objects.order_by("id")
    for annotation in (Q(pages__lt=100), LessThan(F("pages"), 100)):
        books = list(by_id.annotate(b=annotation))
        assert books == [small, big]
        assert [book.b for book in books] == [True, False]
    assert [book.b for book in by_id.annotate(b=~Q(pages__lt=100))] == [False, True]
    assert list(by_id.annotate(b=Q(pages__lt=100)).filter(b=True)) == [small]


@pytest.mark.xfail(strict=True, reason=REASON_GROUP_BY_MARKERS)
def test_group_by_predicate_annotation_with_a_value(live, empty) -> None:
    author = Author.objects.create(name="a")
    Book.objects.create(author=author, title="small", pages=50)
    Book.objects.create(author=author, title="big", pages=500)
    grouped = Book.objects.annotate(b=Q(pages__lt=100)).values("b").annotate(n=Count("id"))
    assert sorted((row["b"], row["n"]) for row in grouped) == [(False, 1), (True, 1)]


def test_predicates_as_operands(live, empty) -> None:
    """A predicate compared with another conditional expression (expressions.py)."""
    author = Author.objects.create(name="a")
    small = Book.objects.create(author=author, title="small", pages=50, available=True)
    big = Book.objects.create(author=author, title="big", pages=500, available=True)
    odd = Book.objects.create(author=author, title="odd", pages=50, available=False)
    by_id = Book.objects.order_by("id")
    # (pages < 100) = (pages < 1000): small and odd (True = True), none False = False.
    lt100 = LessThan(F("pages"), 100)
    assert list(by_id.annotate(b=lt100).filter(b=LessThan(F("pages"), 1000))) == [small, odd]
    wrapped = ExpressionWrapper(Q(pages__lt=100), output_field=BooleanField())
    # The full queryset selects the annotation (a Q with a plain value).
    assert list(by_id.annotate(b=wrapped).filter(b=LessThan(F("pages"), 10))) == [big]
    # A boolean column compared with a predicate.
    assert list(by_id.filter(available=Q(pages__lt=100))) == [small]
    assert list(
        by_id.filter(available=ExpressionWrapper(Q(pages__lt=100), output_field=BooleanField()))
    ) == [small]
    # Exists compared with Exists.
    books = Exists(Book.objects.filter(author=OuterRef("pk")))
    assert list(Author.objects.annotate(has=books).filter(has=books)) == [author]


def test_comparisons_of_two_values_are_correct(live, empty) -> None:
    """Untyped markers on both sides compare wrongly on Db2 for i; values are typed."""
    Author.objects.create(name="a")
    assert Author.objects.filter(GreaterThan(2, 1)).exists() is True
    assert Author.objects.filter(GreaterThan(1, 2)).exists() is False
    assert Author.objects.filter(LessThan(Value("a"), Value("b"))).exists() is True


def test_pagination(live, empty) -> None:
    for name in "abcde":
        Author.objects.create(name=name)
    names = Author.objects.order_by("id").values_list("name", flat=True)
    assert list(names[1:3]) == ["b", "c"]
    assert list(names[3:]) == ["d", "e"]
    assert list(names[:2]) == ["a", "b"]


# --- Extracting date/time parts --------------------------------------------------------


def test_extract_values(live, empty) -> None:
    """Django's conventions on an ISO week edge: Sunday 2023-01-01 is ISO 2022-W52."""
    from django.db.models.functions import Extract

    author = Author.objects.create(name="a")
    Book.objects.create(
        author=author,
        title="t",
        published=dt.datetime(2023, 1, 1, 13, 45, 30, 123456, tzinfo=dt.UTC),
        reading_time=dt.time(6, 7, 8),
    )
    lookups = ("year", "iso_year", "quarter", "month", "week", "week_day", "iso_week_day")
    lookups += ("day", "hour", "minute", "second")
    values = Book.objects.values(**{lookup: Extract("published", lookup) for lookup in lookups})
    assert values.get() == {
        "year": 2023,
        "iso_year": 2022,
        "quarter": 1,
        "month": 1,
        "week": 52,
        "week_day": 1,
        "iso_week_day": 7,
        "day": 1,
        "hour": 13,
        "minute": 45,
        "second": 30,
    }
    assert Book.objects.filter(published__week_day=1, published__iso_week_day=7).count() == 1
    assert Book.objects.filter(reading_time__second=8).count() == 1
