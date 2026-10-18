"""Expression goldens: CASE, COALESCE, arithmetic, select-list predicates, casts."""

from __future__ import annotations

from django.db.models import Case as CaseExpr
from django.db.models import (
    CharField,
    F,
    Value,
    When,
)
from django.db.models.functions import Cast, Coalesce
from django.db.models.lookups import LessThan

from tests.golden_cases.base import AUTHOR, Case, annotate

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
)
