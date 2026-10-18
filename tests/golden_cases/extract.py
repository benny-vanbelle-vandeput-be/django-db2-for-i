"""Extract goldens: one per lookup type on a DateTimeField, on a DateField and
a TimeField, and the week_day / iso_week_day mapping in WHERE.
"""

from __future__ import annotations

from django.db.models.functions import Extract

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
)
