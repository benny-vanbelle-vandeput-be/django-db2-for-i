"""Expression goldens: CASE, COALESCE, arithmetic, select-list predicates, casts."""

from __future__ import annotations

import datetime as dt

from django.db.models import Case as CaseExpr
from django.db.models import (
    CharField,
    DurationField,
    ExpressionWrapper,
    F,
    Value,
    When,
)
from django.db.models.functions import Cast, Coalesce
from django.db.models.lookups import LessThan

from tests.golden_cases.base import AUTHOR, SCHEDULE, Case, annotate, select
from tests.testapp.models import Schedule

CASES: tuple[Case, ...] = (
    Case(
        "expressions/case_when",
        "query",
        annotate(lambda: CaseExpr(When(name="a", then=Value(1)), default=Value(0))),
        (AUTHOR,),
    ),
    Case(
        "expressions/coalesce",
        "query",
        annotate(lambda: Coalesce("name", Value("none"))),
        (AUTHOR,),
    ),
    Case("expressions/arithmetic", "query", annotate(lambda: Value(1) + Value(2)), (AUTHOR,)),
    # A predicate in the select list stays a BOOLEAN predicate.
    Case(
        "expressions/annotate_lookup",
        "query",
        annotate(lambda: LessThan(F("id"), 2)),
        (AUTHOR,),
    ),
    Case(
        "expressions/cast_char_without_max_length",
        "query",
        annotate(lambda: Cast("id", CharField())),
        (AUTHOR,),
    ),
    # Operators Db2 for i does not have: MOD, POWER, BITAND / BITOR / BITXOR,
    # shifts with exact powers of two; >> rounds down in DECFLOAT (operations.py).
    *(
        Case(
            f"expressions/operator_{name}",
            "query",
            annotate(lambda make=make: make(F("id"))),
            (AUTHOR,),
        )
        for name, make in (
            ("modulo", lambda f: f % 3),
            ("power", lambda f: f**2),
            ("bitand", lambda f: f.bitand(6)),
            ("bitor", lambda f: f.bitor(6)),
            ("bitxor", lambda f: f.bitxor(6)),
            ("left_shift", lambda f: f.bitleftshift(2)),
            ("right_shift", lambda f: f.bitrightshift(1)),
        )
    ),
    # Durations: timestamp +/- labeled durations split into DAYS + MICROSECONDS
    # (one MICROSECONDS duration gives NULL from 10**15 on); DATE cast to
    # TIMESTAMP(6), TIME through a timestamp; duration * number stays BIGINT.
    Case(
        "expressions/duration_datetime_plus_field",
        "query",
        select(lambda: Schedule.objects.annotate(x=F("start") + F("length")).values("x")),
        (SCHEDULE,),
    ),
    Case(
        "expressions/duration_datetime_minus_value",
        "query",
        select(
            lambda: Schedule.objects.annotate(x=F("start") - Value(dt.timedelta(days=40))).values(
                "x"
            )
        ),
        (SCHEDULE,),
    ),
    Case(
        "expressions/duration_date_plus_field",
        "query",
        select(lambda: Schedule.objects.annotate(x=F("day") + F("length")).values("x")),
        (SCHEDULE,),
    ),
    Case(
        "expressions/duration_time_plus_field",
        "query",
        select(lambda: Schedule.objects.annotate(x=F("clock") + F("length")).values("x")),
        (SCHEDULE,),
    ),
    Case(
        "expressions/duration_times_number",
        "query",
        select(
            lambda: Schedule.objects.annotate(
                x=ExpressionWrapper(F("length") * 3.2, output_field=DurationField())
            ).values("x")
        ),
        (SCHEDULE,),
    ),
)
