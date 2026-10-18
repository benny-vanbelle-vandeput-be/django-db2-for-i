"""Extract goldens: one per lookup type on a DateTimeField, on a DateField and
a TimeField, and the week_day / iso_week_day mapping in WHERE.
"""

from __future__ import annotations

from django.db.models.functions import Extract, Trunc, TruncDate, TruncTime

from tests.golden_cases.base import BOOK, DEFAULTS, Case, select
from tests.testapp.models import Book, Defaults

EXTRACT_LOOKUPS = (
    "year",
    "iso_year",
    "quarter",
    "month",
    "week",
    "week_day",
    "iso_week_day",
    "day",
    "hour",
    "minute",
    "second",
)

CASES: tuple[Case, ...] = (
    *(
        Case(
            f"extract/datetime_{lookup}",
            "query",
            select(
                lambda lookup=lookup: Book.objects.annotate(x=Extract("published", lookup)).values(
                    "x"
                )
            ),
            (BOOK,),
        )
        for lookup in EXTRACT_LOOKUPS
    ),
    Case(
        "extract/date_week_day",
        "query",
        select(lambda: Defaults.objects.annotate(x=Extract("day", "week_day")).values("x")),
        (DEFAULTS,),
    ),
    Case(
        "extract/time_second",
        "query",
        select(lambda: Book.objects.annotate(x=Extract("reading_time", "second")).values("x")),
        (BOOK,),
    ),
    Case(
        "extract/filter_week_day_sunday",
        "query",
        select(lambda: Book.objects.filter(published__week_day=1)),
        (BOOK,),
    ),
    Case(
        "extract/filter_iso_week_day_sunday",
        "query",
        select(lambda: Book.objects.filter(published__iso_week_day=7)),
        (BOOK,),
    ),
    # Truncation: TRUNC_TIMESTAMP ('IW' starts the week on Monday); DATE and
    # TIME results; TruncDate / TruncTime casts.
    *(
        Case(
            f"extract/trunc_datetime_{kind}",
            "query",
            select(lambda kind=kind: Book.objects.annotate(x=Trunc("published", kind)).values("x")),
            (BOOK,),
        )
        for kind in ("year", "quarter", "month", "week", "day", "hour", "minute", "second")
    ),
    Case(
        "extract/trunc_date_week",
        "query",
        select(lambda: Defaults.objects.annotate(x=Trunc("day", "week")).values("x")),
        (DEFAULTS,),
    ),
    Case(
        "extract/trunc_time_minute",
        "query",
        select(lambda: Book.objects.annotate(x=Trunc("reading_time", "minute")).values("x")),
        (BOOK,),
    ),
    Case(
        "extract/trunc_date_and_time_of_datetime",
        "query",
        select(
            lambda: Book.objects.annotate(
                x=TruncDate("published"), b=TruncTime("published")
            ).values("x", "b")
        ),
        (BOOK,),
    ),
)
