"""Queries against the IBM i: DISTINCT, Exists(), predicates, comparisons,
logged queries, pagination and extracting date/time parts (writes).

The tests.testapp tables are created for this module and dropped again
(``testapp_tables`` in conftest.py).
"""

import datetime as dt

import pytest
from django.db import IntegrityError, models, transaction
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


def test_union(live, empty) -> None:
    """The real-world patterns: two filters combined as model instances, ordered
    (also with NULL ordering), counted and sliced, and inside a correlated subquery."""
    old = dt.datetime(2020, 1, 1, tzinfo=dt.UTC)
    author = Author.objects.create(name="a")
    other = Author.objects.create(name="b")
    short = Book.objects.create(author=author, title="short", pages=5, published=old)
    long = Book.objects.create(author=other, title="long", pages=500)
    Book.objects.create(author=other, title="medium", pages=50, published=old)
    combined = Book.objects.filter(pages__lt=10).union(Book.objects.filter(pages__gt=100))
    assert list(combined.order_by("-pages")) == [long, short]
    assert combined.count() == 2
    assert list(combined.order_by("title")[:1]) == [long]
    nulls_first = combined.order_by(F("published").asc(nulls_first=True))
    assert list(nulls_first.values_list("title", flat=True)) == ["long", "short"]
    nulls_last = combined.order_by(F("published").desc(nulls_last=True))
    assert list(nulls_last.values_list("title", flat=True)) == ["short", "long"]
    everything = combined.union(Book.objects.filter(title="medium"), all=True)
    assert sorted(everything.values_list("pages", flat=True)) == [5, 50, 500]
    own = Book.objects.filter(author=OuterRef("pk")).values("title")
    big = Book.objects.filter(pages__gt=OuterRef("id") * 200).values("title")
    first = Subquery(own.union(big).order_by("title")[:1])
    titles = Author.objects.annotate(first=first).order_by("id").values_list("first", flat=True)
    assert list(titles) == ["long", "long"]


def test_ordered_and_sliced_parts_of_compound_queries(live, empty) -> None:
    """The real-world patterns of supports_slicing_ordering_in_compound: the two
    newest short books plus the two newest long books, as model instances, ordered,
    counted and as values; a nested compound query; and a union of sliced parts in
    filter(pk__in=...) and exclude(pk__in=...). NULL dates sort as the largest."""
    author = Author.objects.create(name="a")
    books = {}
    for title, pages, year in (
        ("s2019", 10, 2019),
        ("s2021", 20, 2021),
        ("s2023", 30, 2023),
        ("snull", 40, None),
        ("l2020", 300, 2020),
        ("l2022", 400, 2022),
        ("l2024", 500, 2024),
    ):
        published = dt.datetime(year, 1, 1, tzinfo=dt.UTC) if year else None
        books[title] = Book.objects.create(
            author=author, title=title, pages=pages, published=published
        )
    short = Book.objects.filter(pages__lt=100)
    long = Book.objects.filter(pages__gte=100)
    newest = short.order_by(F("published").desc(nulls_last=True))[:2].union(
        long.order_by("-published")[:2]
    )
    assert sorted(b.title for b in newest) == ["l2022", "l2024", "s2021", "s2023"]
    assert [b.title for b in newest.order_by("pages")] == ["s2021", "s2023", "l2022", "l2024"]
    assert newest.count() == 4
    assert list(newest.order_by("-pages").values_list("title", flat=True)[:1]) == ["l2024"]
    # DESC without nulls_last: the NULL date comes first.
    with_null = short.order_by("-published")[:1].union(long.order_by("published")[1:2])
    assert sorted(with_null.values_list("title", flat=True)) == ["l2022", "snull"]
    nested = (
        short.order_by("pages")[:1]
        .union(long.order_by("pages")[:1])
        .intersection(Book.objects.filter(title__endswith="0"))
    )
    assert sorted(nested.values_list("title", flat=True)) == ["l2020"]
    oldest = (
        short.order_by("published")
        .values("pk")[:1]
        .union(long.order_by("published").values("pk")[:1])
    )
    assert sorted(Book.objects.filter(pk__in=oldest).values_list("title", flat=True)) == [
        "l2020",
        "s2019",
    ]
    assert Book.objects.exclude(pk__in=oldest).count() == len(books) - 2


def test_truncation(live, empty) -> None:
    """The real-world patterns: Trunc* annotations, dates() / datetimes(), and
    counts per month; weeks start on Monday (Sunday 2023-01-01 is in the week of
    Monday 2022-12-26)."""
    from django.db.models.functions import (
        Trunc,
        TruncDate,
        TruncMonth,
        TruncTime,
        TruncWeek,
    )

    author = Author.objects.create(name="a")
    sunday = dt.datetime(2023, 1, 1, 13, 45, 30, 123456, tzinfo=dt.UTC)
    for published in (sunday, dt.datetime(2023, 1, 20, 8, 0, tzinfo=dt.UTC)):
        Book.objects.create(
            author=author, title="t", published=published, reading_time=dt.time(6, 7, 8)
        )
    kinds = ("year", "quarter", "month", "week", "day", "hour", "minute", "second")
    first = Book.objects.order_by("published").values(
        **{kind: Trunc("published", kind) for kind in kinds}
    )[0]
    utc = dt.UTC
    assert first == {
        "year": dt.datetime(2023, 1, 1, tzinfo=utc),
        "quarter": dt.datetime(2023, 1, 1, tzinfo=utc),
        "month": dt.datetime(2023, 1, 1, tzinfo=utc),
        "week": dt.datetime(2022, 12, 26, tzinfo=utc),
        "day": dt.datetime(2023, 1, 1, tzinfo=utc),
        "hour": dt.datetime(2023, 1, 1, 13, tzinfo=utc),
        "minute": dt.datetime(2023, 1, 1, 13, 45, tzinfo=utc),
        "second": dt.datetime(2023, 1, 1, 13, 45, 30, tzinfo=utc),
    }
    assert list(Book.objects.dates("published", "week")) == [
        dt.date(2022, 12, 26),
        dt.date(2023, 1, 16),
    ]
    assert list(Book.objects.datetimes("published", "month")) == [
        dt.datetime(2023, 1, 1, tzinfo=utc)
    ]
    per_month = Book.objects.values(month=TruncMonth("published")).annotate(n=Count("id"))
    assert list(per_month) == [{"month": dt.datetime(2023, 1, 1, tzinfo=utc), "n": 2}]
    row = Book.objects.order_by("published").values(
        d=TruncDate("published"),
        t=TruncTime("published"),
        w=TruncWeek("published"),
        h=Trunc("reading_time", "hour"),
    )[0]
    assert row == {
        "d": dt.date(2023, 1, 1),
        "t": dt.time(13, 45, 30),  # TIME has no fractions on Db2 for i
        "w": dt.datetime(2022, 12, 26, tzinfo=utc),
        "h": dt.time(6, 0),
    }
    assert Book.objects.filter(published__date=dt.date(2023, 1, 1)).count() == 1


def test_truncating_a_timestamp_to_a_time(live, empty) -> None:
    """Trunc of a timestamp with a TimeField output goes through time_trunc_sql."""
    from django.db.models import TimeField
    from django.db.models.functions import TruncHour

    author = Author.objects.create(name="a")
    published = dt.datetime(2023, 1, 1, 13, 45, 30, tzinfo=dt.UTC)
    Book.objects.create(author=author, title="t", published=published)
    hour = TruncHour("published", output_field=TimeField())
    assert Book.objects.values_list(hour, flat=True).get() == dt.time(13, 0)


def test_operators(live, empty) -> None:
    """%, **, bitwise operators and shifts, also of negative numbers: -5 >> 1 rounds
    down to -3 as in Python (integer division would give -2)."""
    author = Author.objects.create(name="a")
    Book.objects.create(author=author, title="t", pages=13)
    pages = F("pages")
    values = Book.objects.values(
        mod=pages % 5,
        power=pages**2,
        bitand=pages.bitand(6),
        bitor=pages.bitor(6),
        bitxor=pages.bitxor(6),
        left=pages.bitleftshift(2),
        right=pages.bitrightshift(2),
    ).get()
    assert values == {
        "mod": 3,
        "power": 169,
        "bitand": 4,
        "bitor": 15,
        "bitxor": 11,
        "left": 52,
        "right": 3,
    }
    negative = Value(-5)
    signed = Author.objects.values(
        right=negative.bitrightshift(1),
        right_far=Value(-1).bitrightshift(62),
        left=negative.bitleftshift(1),
        xor=negative.bitxor(3),
    ).get()
    assert signed == {"right": -5 >> 1, "right_far": -1 >> 62, "left": -10, "xor": -5 ^ 3}
    assert Book.objects.filter(pages=13).filter(pages__lt=pages.bitleftshift(1)).count() == 1


def test_negated_boolean_values(live, empty) -> None:
    """The real-world pattern: a negated flag compared with a boolean column
    (a predicate is no comparison operand); NULL stays NULL."""
    from django.db.models import BooleanField

    author = Author.objects.create(name="a")
    yes = Book.objects.create(author=author, title="yes", available=True)
    no = Book.objects.create(author=author, title="no", available=False)
    assert list(Book.objects.filter(available=~Value(False))) == [yes]
    flagged = Book.objects.annotate(unavailable=~F("available")).order_by("id")
    assert [b.unavailable for b in flagged] == [False, True]
    assert list(flagged.filter(available=F("unavailable"))) == []
    assert list(flagged.exclude(available=F("unavailable"))) == [yes, no]
    unknown = ~Value(None, output_field=BooleanField())
    assert Book.objects.filter(available=unknown).count() == 0


def test_uuid_values(live, empty) -> None:
    """The real-world patterns: update a UUIDField with a Value, select a UUID Value."""
    import uuid

    from tests.testapp.models import Tag

    code = uuid.UUID("12345678-1234-5678-1234-567812345678")
    tag = Tag.objects.create(label="a")
    Tag.objects.update(id=Value(code))
    assert Tag.objects.get(label="a").pk == code
    assert Tag.objects.values_list(Value(code), flat=True).get() == code
    assert Tag.objects.filter(pk=Value(code)).exists() and tag.pk != code


def test_null_column_compared_with_a_negated_value(live, empty) -> None:
    """TRUE, FALSE and NULL column values (NULL: an author without books, LEFT
    OUTER JOIN). Db2 for i's NOT is TRUE for NULL; the backend's CASE form keeps
    NULL as a selected value, and boolean values as conditions are compared with
    TRUE / FALSE, so filter(~F()), exclude(flag=True) and a selected ~F() follow
    SQL's three-valued logic (and Django's semantics on other databases)."""
    yes = Author.objects.create(name="a: true")
    no = Author.objects.create(name="b: false")
    Author.objects.create(name="c: no book")
    Book.objects.create(author=yes, title="t", available=True)
    Book.objects.create(author=no, title="f", available=False)
    authors = Author.objects.annotate(available=F("book__available")).order_by("name")
    names = lambda queryset: list(queryset.values_list("name", flat=True))  # noqa: E731
    assert names(authors.filter(available=~Value(False))) == ["a: true"]
    assert names(authors.filter(available__isnull=True)) == ["c: no book"]
    # filter(~F("flag")): only the FALSE row, not the NULL row.
    assert names(authors.filter(~F("book__available"))) == ["b: false"]
    # exclude(flag=True) on this annotation: NOT (flag = TRUE), UNKNOWN for the NULL
    # row, so only the FALSE row (as on PostgreSQL; tests/boolean_condition_scenarios.py).
    assert names(authors.exclude(available=True)) == ["b: false"]
    # A selected ~F("flag"): NULL stays NULL.
    negated = authors.annotate(negated=~F("book__available"))
    assert list(negated.values_list("name", "negated")) == [
        ("a: true", False),
        ("b: false", True),
        ("c: no book", None),
    ]


def test_raw_sql_with_a_cast_parameter(live, empty) -> None:
    """The fix shown in Known Limitations: cast the parameter in RawSQL."""
    from django.db.models.expressions import RawSQL

    Author.objects.create(name="b")
    Author.objects.create(name="a")
    raw = RawSQL("CAST(%s AS NVARCHAR(20))", ["value"])
    authors = Author.objects.annotate(foo=raw).filter(foo="value").order_by("name")
    assert [(a.name, a.foo) for a in authors] == [("a", "value"), ("b", "value")]


def test_extra_with_a_cast_parameter(live, empty) -> None:
    """The fix shown in Known Limitations for extra(): cast the parameter."""
    Author.objects.create(name="a")
    rows = Author.objects.extra(select={"foo": "CAST(%s AS INTEGER)"}, select_params=(1,))
    assert [(a.name, a.foo) for a in rows] == [("a", 1)]


def test_intersection_and_difference(live, empty) -> None:
    """The real-world patterns: authors in both / only one of two filters, as model
    instances, ordered, counted, as values, and as a subquery."""
    for name in ("abz", "abc", "xyz", "axz"):
        Author.objects.create(name=name)
    starts = Author.objects.filter(name__startswith="a")
    ends = Author.objects.filter(name__endswith="z")
    both = starts.intersection(ends)
    only_starts = starts.difference(ends)
    assert sorted(a.name for a in both) == ["abz", "axz"]
    assert [a.name for a in both.order_by("-name")] == ["axz", "abz"]
    assert both.count() == 2
    assert list(only_starts.values_list("name", flat=True)) == ["abc"]
    assert sorted(ends.difference(starts).values_list("name", flat=True)) == ["xyz"]
    ids = both.values("pk")
    assert sorted(Author.objects.filter(pk__in=ids).values_list("name", flat=True)) == [
        "abz",
        "axz",
    ]


def test_delete_with_a_subquery_on_its_own_table(live, empty) -> None:
    """Django deletes through pk IN (SELECT * FROM (...) subquery): a search condition."""
    author = Author.objects.create(name="a")
    for pages in (10, 50, 200, 300):
        Book.objects.create(author=author, title=str(pages), pages=pages)
    long_books = Book.objects.filter(pages__gt=100).values("pk")
    assert Book.objects.filter(pk__in=long_books).update(title="long") == 2
    Book.objects.filter(pk__in=long_books).delete()
    assert sorted(Book.objects.values_list("title", flat=True)) == ["10", "50"]
    Book.objects.exclude(pk__in=Book.objects.filter(pages__lt=20).values("pk")).delete()
    assert list(Book.objects.values_list("title", flat=True)) == ["10"]


def test_sliced_subqueries_in_in(live, empty) -> None:
    """The real-world patterns of allow_sliced_subqueries_with_in: the authors of
    the newest books (IN (... FETCH FIRST n ROWS ONLY)), with an offset, in XOR,
    and a delete limited by a sliced subquery."""
    authors = [Author.objects.create(name=n) for n in ("a", "b", "c")]
    for year, author in ((2020, authors[0]), (2023, authors[1]), (2025, authors[2])):
        Book.objects.create(
            author=author, title=str(year), published=dt.datetime(year, 1, 1, tzinfo=dt.UTC)
        )
    newest = Book.objects.order_by("-published").values("author")
    assert sorted(Author.objects.filter(pk__in=newest[:2]).values_list("name", flat=True)) == [
        "b",
        "c",
    ]
    assert list(Author.objects.filter(pk__in=newest[1:2]).values_list("name", flat=True)) == ["b"]
    xor = Author.objects.filter(Q(pk__in=newest[:2]) ^ Q(name="c"))
    assert list(xor.values_list("name", flat=True)) == ["b"]
    Book.objects.filter(pk__in=Book.objects.order_by("published").values("pk")[:1]).delete()
    assert sorted(Book.objects.values_list("title", flat=True)) == ["2023", "2025"]


def test_boolean_conditions_match_the_reference(live, empty) -> None:
    """A nullable BooleanField used as a condition by every path Django has
    (filter / exclude with True and False, ~Q, ~F, a When condition, a boolean
    annotation in filter / exclude), on TRUE, FALSE and NULL rows, gives the rows
    of the reference (tests/boolean_condition_scenarios.py)."""
    from tests import boolean_condition_scenarios as scenarios

    scenarios.create("default")
    actual = {name: scenarios.rows(qs) for name, qs in scenarios.querysets("default").items()}
    differences = {
        name: (actual[name], expected)
        for name, expected in scenarios.EXPECTED.items()
        if actual[name] != expected
    }
    assert differences == {}


def test_selected_predicates_are_three_valued(live, empty) -> None:
    """Issue #75: a Q(...) as a selected value is True, False or None (UNKNOWN, a NULL
    operand), as on PostgreSQL, and the same predicate in filter() returns exactly
    the rows where it is True: a comparison, the IN rewrite over a subquery with a
    NULL, a correlated Exists, and a combination with AND."""
    from tests.testapp.models import Account, Contact

    Account.objects.create(company="a", number=1)
    for company, number in (("a", 1), ("b", 7), ("c", None)):
        Contact.objects.create(company=company, account_number=number)
    numbers = Contact.objects.values("account_number")  # holds a NULL
    predicates = {
        "lt": (Q(account_number__lt=5), {"a": True, "b": False, "c": None}),
        "in subquery with a NULL": (
            Q(account_number__in=numbers.filter(company="a")) | Q(account_number__in=numbers),
            {"a": True, "b": True, "c": None},
        ),
        "exists": (
            Q(Exists(Account.objects.filter(company=OuterRef("company")))),
            {"a": True, "b": False, "c": False},
        ),
        "and": (
            Q(account_number__lt=5) & Q(company__in=["a", "c"]),
            {"a": True, "b": False, "c": None},
        ),
        "not": (~Q(account_number__gte=5), {"a": True, "b": False, "c": True}),
    }
    for name, (predicate, expected) in predicates.items():
        selected = dict(Contact.objects.annotate(v=predicate).values_list("company", "v"))
        assert selected == expected, name
        matching = sorted(Contact.objects.filter(predicate).values_list("company", flat=True))
        assert matching == sorted(c for c, v in expected.items() if v is True), name


def test_check_constraint_violations_raise_integrity_error(live, empty) -> None:
    """A PositiveIntegerField's CHECK constraint: SQL0545 comes with SQLSTATE HY000,
    and still raises IntegrityError, on an insert and on an F() update (the case of
    Django's PositiveIntegerFieldTests.test_negative_values); the atomic block rolls
    back and the connection stays usable (#96)."""
    author = Author.objects.create(name="a")
    book = Book.objects.create(author=author, title="t", pages=0)
    with pytest.raises(IntegrityError, match="SQL0545"), transaction.atomic():
        Book.objects.create(author=author, title="negative", pages=-1)
    book.pages = F("pages") - 1
    with pytest.raises(IntegrityError, match="SQL0545"), transaction.atomic():
        book.save()
    assert list(Book.objects.values_list("title", "pages")) == [("t", 0)]
