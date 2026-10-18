"""Aggregate goldens: Avg casts, typed NULL for empty filters, StringAgg."""

from __future__ import annotations

from django.db.models import (
    Avg,
    Count,
    F,
    Q,
    StringAgg,
    Value,
)

from tests.golden_cases.base import AUTHOR, BOOK, DEFAULTS, Case, select
from tests.testapp.models import Author, Defaults

CASES: tuple[Case, ...] = (
    # Avg of an integer: the argument is cast to DOUBLE (AVG of INTEGER is an
    # INTEGER on Db2 for i); Avg of a DecimalField or FloatField is unchanged.
    Case(
        "aggregates/avg_integer",
        "query",
        select(lambda: Author.objects.annotate(x=Avg("book__pages")).values("x")),
        (AUTHOR, BOOK),
    ),
    Case(
        "aggregates/avg_decimal",
        "query",
        select(lambda: Defaults.objects.values("flag").annotate(x=Avg("amount")).values("x")),
        (DEFAULTS,),
    ),
    Case(
        "aggregates/avg_float",
        "query",
        select(lambda: Defaults.objects.values("flag").annotate(x=Avg("ratio")).values("x")),
        (DEFAULTS,),
    ),
    # An aggregate filter that matches nothing collapses Django's CASE to a
    # plain NULL, which Db2 for i rejects as an argument: typed NULL.
    Case(
        "aggregates/count_empty_filter",
        "query",
        select(lambda: Author.objects.annotate(x=Count("book", filter=Q(book__in=[]))).values("x")),
        (AUTHOR, BOOK),
    ),
    # StringAgg as LISTAGG of an NCLOB (results up to 1M characters), with a
    # typed separator; a filter wraps the argument in CASE.
    Case(
        "aggregates/string_agg",
        "query",
        select(
            lambda: Author.objects.annotate(
                x=StringAgg("book__title", Value(", "), filter=Q(book__pages__gt=10))
            ).values("x")
        ),
        (AUTHOR, BOOK),
    ),
    # StringAgg(order_by=...): LISTAGG(...) WITHIN GROUP (ORDER BY ...); a
    # nulls_last item is ordered by a CASE NULL rank first (no IS NULL there).
    Case(
        "aggregates/string_agg_order_by",
        "query",
        select(
            lambda: Author.objects.annotate(
                x=StringAgg(
                    "book__title",
                    Value(", "),
                    order_by=(F("book__published").desc(nulls_last=True), "book__title"),
                )
            ).values("x")
        ),
        (AUTHOR, BOOK),
    ),
)
