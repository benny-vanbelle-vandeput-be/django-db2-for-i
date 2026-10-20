"""Query goldens: pagination, DISTINCT, Exists(), predicates as operands,
parameters, LIKE and regular expressions.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.db.models import Case as CaseExpr
from django.db.models import (
    CharField,
    Count,
    Exists,
    F,
    Max,
    OuterRef,
    Q,
    Subquery,
    Value,
    When,
)
from django.db.models.lookups import LessThan

from tests.golden_cases.base import (
    ACCOUNT,
    AUTHOR,
    AWARE,
    BOOK,
    CONTACT,
    MEASURE,
    SWITCH,
    Case,
    books_of_author,
    exists,
    select,
)
from tests.testapp.models import Account, Author, Book, Contact, Measure, Switch


def _last_insert_id(connection):
    class Recorder:
        sql = None

        def execute(self, sql):
            self.sql = sql

        def fetchone(self):
            return (Decimal(1),)

    cursor = Recorder()
    connection.ops.last_insert_id(cursor, "testapp_author", "id")
    return [(cursor.sql, ())]


CASES: tuple[Case, ...] = (
    # Pagination (OFFSET / FETCH FIRST) and exists().
    # Ordering by a Value: Django wraps it in Cast(..., output_field); a
    # CharField without max_length uses cast_char_field_without_max_length.
    Case(
        "queries/order_by_value_char",
        "query",
        select(lambda: Author.objects.order_by(Value("1", output_field=CharField()), "-name")),
        (AUTHOR,),
    ),
    # SELECT DISTINCT with emulated NULL ordering: the predicate is selected
    # as a hidden column (compiler.py; SQL0214 otherwise).
    Case(
        "queries/distinct_nulls_last",
        "query",
        select(
            lambda: (
                Book.objects.order_by(F("published").desc(nulls_last=True))
                .distinct()
                .values_list("title", flat=True)
            )
        ),
        (AUTHOR, BOOK),
    ),
    Case(
        "queries/distinct_nulls_first_annotation",
        "query",
        select(
            lambda: (
                Author.objects.annotate(
                    last=Subquery(
                        Book.objects.filter(author=OuterRef("pk"))
                        .order_by()
                        .values("author")
                        .annotate(m=Max("published"))
                        .values("m")
                    )
                )
                .order_by(F("last").asc(nulls_first=True))
                .distinct()
            )
        ),
        (AUTHOR, BOOK),
    ),
    # Exists(): EXISTS only as a search condition of WHERE; elsewhere the
    # first-row subquery IS NOT NULL (compiler.py).
    Case(
        "queries/filter_exists",
        "query",
        select(lambda: Author.objects.filter(Exists(books_of_author()))),
        (AUTHOR, BOOK),
    ),
    Case(
        "queries/filter_not_exists",
        "query",
        select(lambda: Author.objects.filter(~Exists(books_of_author()))),
        (AUTHOR, BOOK),
    ),
    Case(
        "queries/annotate_exists",
        "query",
        select(lambda: Author.objects.annotate(has=Exists(books_of_author())).values("has")),
        (AUTHOR, BOOK),
    ),
    Case(
        "queries/annotate_not_exists",
        "query",
        select(lambda: Author.objects.annotate(has=~Exists(books_of_author())).values("has")),
        (AUTHOR, BOOK),
    ),
    Case(
        "queries/case_when_exists",
        "query",
        select(
            lambda: Author.objects.annotate(
                x=CaseExpr(When(Exists(books_of_author()), then=Value(1)), default=Value(0))
            ).values("x")
        ),
        (AUTHOR, BOOK),
    ),
    Case(
        "queries/order_by_exists",
        "query",
        select(lambda: Author.objects.order_by(Exists(books_of_author()).desc(), "id")),
        (AUTHOR, BOOK),
    ),
    Case(
        "queries/group_by_exists",
        "query",
        select(
            lambda: (
                Author.objects.annotate(has=Exists(books_of_author()))
                .values("has")
                .annotate(n=Count("id"))
                .order_by("has")
            )
        ),
        (AUTHOR, BOOK),
    ),
    # Predicates as comparison operands: CASE WHEN ... THEN TRUE ELSE FALSE END
    # (expressions.py); boolean columns stay as they are.
    Case(
        "queries/filter_lookup_operands",
        "query",
        select(
            lambda: Book.objects.annotate(b=LessThan(F("pages"), 2000)).filter(
                b=LessThan(F("pages"), 1900)
            )
        ),
        (AUTHOR, BOOK),
    ),
    Case(
        "queries/filter_boolean_column_equals_q",
        "query",
        select(lambda: Book.objects.filter(available=Q(pages__lt=100))),
        (AUTHOR, BOOK),
    ),
    Case(
        "queries/filter_exists_equals_exists",
        "query",
        select(
            lambda: Author.objects.annotate(has=Exists(books_of_author())).filter(
                has=Exists(books_of_author())
            )
        ),
        (AUTHOR, BOOK),
    ),
    Case(
        "queries/slice_offset_fetch",
        "query",
        select(lambda: Author.objects.order_by("id")[1:3]),
        (AUTHOR,),
    ),
    Case(
        "queries/slice_offset_only",
        "query",
        select(lambda: Author.objects.order_by("id")[3:]),
        (AUTHOR,),
    ),
    Case(
        "queries/slice_first_only",
        "query",
        select(lambda: Author.objects.order_by("id")[:2]),
        (AUTHOR,),
    ),
    Case("queries/exists", "query", exists(lambda: Author.objects.filter(name="a")), (AUTHOR,)),
    # Booleans, date/time parameters (aware -> naive UTC, TIME truncated).
    Case(
        "queries/filter_boolean",
        "query",
        select(lambda: Book.objects.filter(available=True)),
        (BOOK,),
    ),
    Case(
        "queries/filter_datetime_aware",
        "query",
        select(lambda: Book.objects.filter(published__gte=AWARE)),
        (BOOK,),
    ),
    Case(
        "queries/filter_time_truncated",
        "query",
        select(lambda: Book.objects.filter(reading_time=dt.time(1, 2, 3, 456789))),
        (BOOK,),
    ),
    # LIKE with ESCAPE and escaped wildcards; case-insensitive lookups.
    Case(
        "queries/filter_startswith_escaped",
        "query",
        select(lambda: Author.objects.filter(name__startswith="50%_off")),
        (AUTHOR,),
    ),
    Case(
        "queries/filter_iexact",
        "query",
        select(lambda: Author.objects.filter(name__iexact="Ada")),
        (AUTHOR,),
    ),
    # Regular expressions: REGEXP_LIKE with a typed pattern marker.
    Case(
        "queries/filter_regex",
        "query",
        select(lambda: Author.objects.filter(name__regex=r"^A(d)a\1?$")),
        (AUTHOR,),
    ),
    Case(
        "queries/filter_iregex",
        "query",
        select(lambda: Author.objects.filter(name__iregex="^ada")),
        (AUTHOR,),
    ),
    Case(
        "queries/filter_regex_integer",
        "query",
        select(lambda: Book.objects.filter(pages__regex="^1[0-9]+$")),
        (BOOK,),
    ),
    Case("queries/last_insert_id", "query", _last_insert_id),
    # UNION: an ordered compound query is wrapped in SELECT * FROM LATERAL (...)
    # (its ORDER BY accepts no expressions; LATERAL keeps outer references
    # visible; compiler.py).
    Case(
        "queries/union",
        "query",
        select(lambda: Author.objects.filter(name="a").union(Author.objects.filter(name="b"))),
        (AUTHOR,),
    ),
    Case(
        "queries/union_order_by_nulls_first",
        "query",
        select(
            lambda: (
                Book.objects.filter(pages__lt=10)
                .values("published")
                .union(Book.objects.filter(pages__gt=100).values("published"))
                .order_by(F("published").asc(nulls_first=True))
            )
        ),
        (AUTHOR, BOOK),
    ),
    Case(
        "queries/union_in_correlated_subquery",
        "query",
        select(
            lambda: Author.objects.annotate(
                title=Subquery(
                    books_of_author()
                    .values("title")
                    .union(Book.objects.filter(pages__gt=OuterRef("id")).values("title"))
                    .order_by("title")[:1]
                )
            ).values("title")
        ),
        (AUTHOR, BOOK),
    ),
    # NOT <BOOLEAN value> as a comparison operand: CASE <value> WHEN TRUE THEN
    # FALSE WHEN FALSE THEN TRUE END (a predicate is no operand; NULL stays NULL).
    Case(
        "queries/filter_boolean_column_equals_negated_value",
        "query",
        select(lambda: Book.objects.filter(available=~Value(False))),
        (AUTHOR, BOOK),
    ),
    # NOT <BOOLEAN column> is TRUE for NULL on Db2 for i: CASE form in WHERE too.
    Case(
        "queries/filter_negated_boolean_column",
        "query",
        select(lambda: Book.objects.filter(~F("available"))),
        (AUTHOR, BOOK),
    ),
    # iexact compares with = UPPER(%s): the value is not escaped for LIKE.
    Case(
        "queries/filter_iexact_wildcards",
        "query",
        select(lambda: Author.objects.filter(name__iexact="50%_Off\\x")),
        (AUTHOR,),
    ),
    # A string value longer than the column: the driver would size an untyped
    # marker by the column (CWB0111); only too-long values become typed markers.
    Case(
        "queries/filter_exact_longer_than_column",
        "query",
        select(lambda: Author.objects.filter(name="x" * 101)),
        (AUTHOR,),
    ),
    Case(
        "queries/filter_in_one_value_longer_than_column",
        "query",
        select(lambda: Author.objects.filter(name__in=["fits", "y" * 120])),
        (AUTHOR,),
    ),
    # IN (subquery) inside CASE WHEN (XOR, selected Q) is rejected by Db2 for i:
    # a three-valued BOOLEAN of first-row subqueries, compared with TRUE.
    Case(
        "queries/xor_in_subquery",
        "query",
        select(
            lambda: Book.objects.filter(
                Q(author__in=Author.objects.filter(name="a").values("id")) ^ Q(pages=10)
            )
        ),
        (AUTHOR, BOOK),
    ),
    Case(
        "queries/annotate_in_subquery",
        "query",
        select(
            lambda: Book.objects.annotate(
                b=Q(author__in=Author.objects.filter(name="a").values("id"))
            ).values("b")
        ),
        (AUTHOR, BOOK),
    ),
    # INTERSECT / EXCEPT (Db2 for i rejects their ALL forms, which Django never uses).
    Case(
        "queries/intersection",
        "query",
        select(
            lambda: Author.objects.filter(name__startswith="a").intersection(
                Author.objects.filter(name__endswith="z")
            )
        ),
        (AUTHOR,),
    ),
    Case(
        "queries/difference_ordered",
        "query",
        select(
            lambda: (
                Author.objects.filter(name__startswith="a")
                .difference(Author.objects.filter(name__endswith="z"))
                .order_by("-name")
            )
        ),
        (AUTHOR,),
    ),
    # A two-column relation: (a, b) IN (subquery) in WHERE, and the rewrite
    # with one column per tuple element outside a search condition.
    Case(
        "queries/filter_tuple_in_subquery",
        "query",
        select(lambda: Contact.objects.filter(account__in=Account.objects.filter(number__gt=1))),
        (ACCOUNT, CONTACT),
    ),
    Case(
        "queries/xor_tuple_in_subquery",
        "query",
        select(
            lambda: Contact.objects.filter(
                Q(account__in=Account.objects.filter(number__gt=1)) ^ Q(company="b")
            )
        ),
        (ACCOUNT, CONTACT),
    ),
    # The search-condition context of a tuple IN never reaches a CASE context:
    # a selected value and a When condition use the rewrite (SQL0115 otherwise).
    Case(
        "queries/annotate_tuple_in_subquery",
        "query",
        select(
            lambda: Contact.objects.annotate(
                b=Q(account__in=Account.objects.filter(number__gt=1))
            ).values("b")
        ),
        (ACCOUNT, CONTACT),
    ),
    Case(
        "queries/case_when_tuple_in_subquery",
        "query",
        select(
            lambda: Contact.objects.annotate(
                x=CaseExpr(
                    When(Q(account__in=Account.objects.filter(number__gt=1)), then=Value(1)),
                    default=Value(0),
                )
            ).values("x")
        ),
        (ACCOUNT, CONTACT),
    ),
    # allow_sliced_subqueries_with_in: IN (... FETCH FIRST n ROWS ONLY).
    Case(
        "queries/filter_in_sliced_subquery",
        "query",
        select(
            lambda: Author.objects.filter(
                pk__in=Book.objects.order_by("-published").values("author")[1:3]
            )
        ),
        (AUTHOR, BOOK),
    ),
    # supports_tuple_lookups: row-value = stays; a row-value IN list and > use
    # Django's expanded form (Db2 for i rejects them: SQL0104 / SQL0115).
    Case(
        "queries/filter_tuple_exact",
        "query",
        select(lambda: Contact.objects.filter(account=Account(id=1, company="a", number=1))),
        (ACCOUNT, CONTACT),
    ),
    # A value longer than its column ("ab" for CharField(max_length=1)): a larger
    # typed marker, so it matches nothing instead of failing (CWB0111).
    Case(
        "queries/filter_tuple_exact_longer_than_column",
        "query",
        select(lambda: Contact.objects.filter(account=Account(id=1, company="ab", number=1))),
        (ACCOUNT, CONTACT),
    ),
    Case(
        "queries/filter_tuple_in_list",
        "query",
        select(
            lambda: Contact.objects.filter(
                account__in=[
                    Account(id=1, company="a", number=1),
                    Account(id=2, company="b", number=2),
                ]
            )
        ),
        (ACCOUNT, CONTACT),
    ),
    Case(
        "queries/filter_tuple_gt",
        "query",
        select(lambda: Contact.objects.filter(account__gt=Account(id=1, company="a", number=1))),
        (ACCOUNT, CONTACT),
    ),
    Case(
        "queries/exclude_tuple_in_subquery",
        "query",
        select(lambda: Contact.objects.exclude(account__in=Account.objects.filter(number__gt=1))),
        (ACCOUNT, CONTACT),
    ),
    # supports_slicing_ordering_in_compound / supports_parentheses_in_compound:
    # parts in parentheses with their own ORDER BY and FETCH FIRST, nested
    # compound queries, and sliced parts in a subquery.
    Case(
        "queries/union_of_sliced_parts",
        "query",
        select(
            lambda: (
                Book.objects.filter(pages__lt=100)
                .order_by("-published")[:2]
                .union(Book.objects.filter(pages__gte=100).order_by(F("published").asc())[1:3])
                .order_by("-pages")
            )
        ),
        (AUTHOR, BOOK),
    ),
    Case(
        "queries/nested_compound",
        "query",
        select(
            lambda: (
                Author.objects.filter(name="a")
                .union(Author.objects.filter(name="b"))
                .intersection(Author.objects.filter(name__startswith="a"))
            )
        ),
        (AUTHOR,),
    ),
    Case(
        "queries/filter_in_union_of_sliced_parts",
        "query",
        select(
            lambda: Author.objects.filter(
                pk__in=Author.objects.order_by("name")
                .values("pk")[:1]
                .union(Author.objects.order_by("-name").values("pk")[:1])
            )
        ),
        (AUTHOR,),
    ),
    # A BOOLEAN value as a condition: compared with TRUE / FALSE (Db2 for i's
    # NOT <value> is TRUE for NULL); a negated value is unwrapped.
    Case(
        "queries/filter_nullable_boolean_false",
        "query",
        select(lambda: Switch.objects.filter(flag=False)),
        (SWITCH,),
    ),
    Case(
        "queries/exclude_negated_nullable_boolean",
        "query",
        select(lambda: Switch.objects.exclude(~F("flag"))),
        (SWITCH,),
    ),
    Case(
        "queries/filter_boolean_annotation_false",
        "query",
        select(lambda: Switch.objects.annotate(neg=~F("flag")).filter(neg=False)),
        (SWITCH,),
    ),
    # Numeric values that do not fit the column get a type of their own (#69):
    # never rounded or truncated, compared exactly; values that fit stay untyped.
    Case(
        "queries/filter_in_integer_out_of_range",
        "query",
        select(lambda: Measure.objects.filter(small__in=[1, 100000])),
        (MEASURE,),
    ),
    Case(
        "queries/filter_range_integer_out_of_range",
        "query",
        select(lambda: Measure.objects.filter(small__range=(0, 100000))),
        (MEASURE,),
    ),
    Case(
        "queries/filter_decimal_more_digits",
        "query",
        select(lambda: Measure.objects.filter(amount=Decimal("1.005"))),
        (MEASURE,),
    ),
)
