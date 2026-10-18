"""Value goldens: typed parameter markers, one per type rule
(django_db2_for_i/expressions.py).
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from django.db.models import Case as CaseExpr
from django.db.models import (
    CharField,
    DecimalField,
    IntegerField,
    Value,
    When,
)

from tests.golden_cases.base import AUTHOR, AWARE, Case, annotate

CASES: tuple[Case, ...] = (
    Case("values/integer", "query", annotate(lambda: Value(1)), (AUTHOR,)),
    Case("values/bigint", "query", annotate(lambda: Value(2**40)), (AUTHOR,)),
    Case(
        "values/string_length",
        "query",
        annotate(lambda: Value("h\u00e9llo \U0001f600")),
        (AUTHOR,),
    ),
    Case("values/string_empty", "query", annotate(lambda: Value("")), (AUTHOR,)),
    Case("values/string_bucket_1024", "query", annotate(lambda: Value("x" * 300)), (AUTHOR,)),
    Case("values/float", "query", annotate(lambda: Value(1.5)), (AUTHOR,)),
    Case(
        "values/string_max_length",
        "query",
        annotate(lambda: Value("x", output_field=CharField(max_length=20))),
        (AUTHOR,),
    ),
    Case(
        "values/null_typed",
        "query",
        annotate(lambda: Value(None, output_field=IntegerField())),
        (AUTHOR,),
    ),
    Case(
        "values/null_untyped_in_case",
        "query",
        annotate(lambda: CaseExpr(When(name="a", then=Value(1)), default=Value(None))),
        (AUTHOR,),
    ),
    Case("values/boolean", "query", annotate(lambda: Value(True)), (AUTHOR,)),
    Case("values/decimal", "query", annotate(lambda: Value(Decimal("12.345"))), (AUTHOR,)),
    Case(
        "values/decimal_field",
        "query",
        annotate(
            lambda: Value(
                Decimal("1.5"), output_field=DecimalField(max_digits=10, decimal_places=2)
            )
        ),
        (AUTHOR,),
    ),
    Case("values/date", "query", annotate(lambda: Value(dt.date(2026, 10, 17))), (AUTHOR,)),
    Case("values/time", "query", annotate(lambda: Value(dt.time(1, 2, 3, 456789))), (AUTHOR,)),
    Case("values/datetime_aware", "query", annotate(lambda: Value(AWARE)), (AUTHOR,)),
    Case(
        "values/uuid",
        "query",
        annotate(lambda: Value(uuid.UUID("12345678-1234-5678-1234-567812345678"))),
        (AUTHOR,),
    ),
)
