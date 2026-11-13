"""Expression goldens: CASE, COALESCE, arithmetic, select-list predicates, casts."""

from __future__ import annotations

import datetime as dt

from django.db.models import Case as CaseExpr
from django.db.models import (
    CharField,
    DecimalField,
    DurationField,
    ExpressionWrapper,
    F,
    FloatField,
    Sum,
    Value,
    ValueRange,
    When,
    Window,
)
from django.db.models.functions import (
    MD5,
    SHA256,
    ATan2,
    Cast,
    Chr,
    Coalesce,
    Concat,
    CumeDist,
    Lag,
    Length,
    Log,
    LPad,
    NthValue,
    Ord,
    Repeat,
)
from django.db.models.lookups import LessThan

from tests.golden_cases.base import AUTHOR, MEASURE, SCHEDULE, Case, annotate, select
from tests.testapp.models import Measure, Schedule

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
    # Database functions where Django's SQL does not work on Db2 for i
    # (expressions.py, probes db_functions, db_function_args).
    Case("expressions/function_length", "query", annotate(lambda: Length("name")), (AUTHOR,)),
    # Through UTF-16, with surrogate pairs above U+FFFF (probe qtemp_supplementary_chars).
    Case("expressions/function_chr", "query", annotate(lambda: Chr("id")), (AUTHOR,)),
    Case("expressions/function_ord", "query", annotate(lambda: Ord("name")), (AUTHOR,)),
    Case(
        "expressions/function_concat",
        "query",
        annotate(lambda: Concat("name", Value("!"), "name")),
        (AUTHOR,),
    ),
    Case("expressions/function_md5", "query", annotate(lambda: MD5("name")), (AUTHOR,)),
    Case("expressions/function_sha256", "query", annotate(lambda: SHA256("name")), (AUTHOR,)),
    Case(
        "expressions/function_lpad_null",
        "query",
        annotate(lambda: LPad(Value(None), 3, Value("x"))),
        (AUTHOR,),
    ),
    Case(
        "expressions/function_repeat_null",
        "query",
        annotate(lambda: Repeat("name", None)),
        (AUTHOR,),
    ),
    *(
        Case(
            f"expressions/function_{name}",
            "query",
            select(lambda make=make: Measure.objects.annotate(x=make()).values("x")),
            (MEASURE,),
        )
        for name, make in (
            ("log", lambda: Log("small", "big")),
            ("atan2", lambda: ATan2("small", "big")),
            # A number cast to a DecimalField is rounded first; a DOUBLE through DECFLOAT.
            (
                "cast_float_to_decimal",
                lambda: Cast(
                    Cast("amount", FloatField()), DecimalField(max_digits=8, decimal_places=1)
                ),
            ),
            (
                "cast_decimal_to_decimal",
                lambda: Cast("amount", DecimalField(max_digits=8, decimal_places=1)),
            ),
            # A DOUBLE as text: through DECFLOAT(16) + 0, so 3 and 300, not 3E0 and 3E+2.
            ("cast_float_to_text", lambda: Cast(Cast("amount", FloatField()), CharField())),
            # Window functions: LAG's offset and NTH_VALUE's position as constants,
            # CUME_DIST as a DOUBLE, a RANGE frame over a number.
            (
                "window_lag_default",
                lambda: Window(Lag("amount", 2, default=Value(0)), order_by=F("big").asc()),
            ),
            (
                "window_nth_value",
                lambda: Window(NthValue("amount", 2), partition_by=F("small"), order_by="big"),
            ),
            ("window_cume_dist", lambda: Window(CumeDist(), order_by=F("amount").desc())),
            (
                "window_range_frame",
                lambda: Window(
                    Sum("amount"), order_by=F("big").asc(), frame=ValueRange(start=-5, end=5)
                ),
            ),
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
    # Subtraction in exact microseconds: DAYS(), MIDNIGHT_SECONDS(), MICROSECOND().
    Case(
        "expressions/subtract_datetimes",
        "query",
        select(
            lambda: Schedule.objects.annotate(
                x=F("start") - Value(dt.datetime(2026, 1, 31, 1, 0, 0, 2, tzinfo=dt.UTC))
            ).values("x")
        ),
        (SCHEDULE,),
    ),
    Case(
        "expressions/subtract_dates",
        "query",
        select(
            lambda: Schedule.objects.annotate(x=F("day") - Value(dt.date(2001, 1, 1))).values("x")
        ),
        (SCHEDULE,),
    ),
    Case(
        "expressions/subtract_times",
        "query",
        select(lambda: Schedule.objects.annotate(x=F("clock") - Value(dt.time(6, 0))).values("x")),
        (SCHEDULE,),
    ),
)
