"""No comparison is ever emitted with untyped parameter markers on both sides.

Db2 for i accepts ``WHERE ? > ?`` with two untyped markers but returns a wrong
result (no row for 2 > 1; probe ``queries``, docs/IBMI_NOTES.md). The backend
types values (``CAST(? AS ...)``); these tests guard that rule.
"""

import re

import pytest
from django.db import connection
from django.db.models import F, Q, Value
from django.db.models.lookups import Exact, GreaterThan, LessThan

from tests.golden import all_golden_paths, read
from tests.testapp.models import Author, Book

COMPARISON = r"(?:=|<>|!=|<=|>=|<|>)"
# A bare marker on both sides: not CAST(%s ..., not %s AS ...
BOTH_UNTYPED = re.compile(rf"(?<!CAST\()(?:%s|\?)\s*{COMPARISON}\s*(?:%s|\?)(?!\s+AS\b)")


def test_pattern_catches_untyped_comparisons() -> None:
    assert BOTH_UNTYPED.search("WHERE %s > %s")
    assert BOTH_UNTYPED.search("WHERE ? = ?")
    assert not BOTH_UNTYPED.search("WHERE CAST(%s AS INTEGER) > CAST(%s AS INTEGER)")
    assert not BOTH_UNTYPED.search('WHERE "A"."X" > %s')


@pytest.mark.parametrize("path", all_golden_paths(), ids=lambda path: path.stem)
def test_no_golden_compares_two_untyped_markers(path) -> None:
    for sql, _params in read(path).statements:
        assert not BOTH_UNTYPED.search(sql), sql


@pytest.mark.parametrize(
    "queryset",
    [
        lambda: Author.objects.filter(GreaterThan(2, 1)),
        lambda: Author.objects.filter(Exact(Value(1), Value(1))),
        lambda: Author.objects.filter(LessThan(Value("a"), Value("b"))),
        lambda: Author.objects.filter(Exact(Value(True), Q(name="x"))),
        lambda: Book.objects.filter(GreaterThan(F("pages"), 1)),
        lambda: Book.objects.annotate(b=GreaterThan(Value(2), 1)).values("b"),
    ],
    ids=["direct values", "two Values", "strings", "Value = Q", "column", "annotation"],
)
def test_compiled_comparisons_type_their_values(queryset) -> None:
    sql, _params = queryset().query.get_compiler(connection=connection).as_sql()
    assert not BOTH_UNTYPED.search(sql), sql
