"""Typed parameter markers for Value expressions (no server needed)."""

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from django.db import NotSupportedError
from django.db.models import (
    BigIntegerField,
    BooleanField,
    CharField,
    DecimalField,
    FloatField,
    IntegerField,
    JSONField,
    TextField,
    UUIDField,
    Value,
)

from django_db2_for_i.expressions import NVARCHAR_MAX, STRING_BUCKETS
from tests.testapp.models import Author


def cast_of(expression) -> str:
    """The SQL of ``expression`` in a SELECT list, without the FROM clause."""
    queryset = Author.objects.annotate(x=expression).values("x")
    sql, _params = queryset.query.get_compiler("default").as_sql()
    return sql.removeprefix("SELECT ").split(' AS "X"')[0]


# --- bool is not int ---------------------------------------------------------------


@pytest.mark.parametrize("value", [True, False])
def test_booleans_cast_to_boolean_not_integer(value: bool) -> None:
    assert cast_of(Value(value)) == "CAST(%s AS BOOLEAN)"


# --- String buckets and the maximum ---------------------------------------------


@pytest.mark.parametrize(
    ("length", "bucket"),
    [
        (0, 32),
        (1, 32),
        (32, 32),
        (33, 256),
        (256, 256),
        (257, 1024),
        (1024, 1024),
        (1025, 4000),
        (4000, 4000),
        (4001, NVARCHAR_MAX),
        (NVARCHAR_MAX, NVARCHAR_MAX),
    ],
)
def test_string_lengths_round_up_to_buckets(length: int, bucket: int) -> None:
    assert cast_of(Value("x" * length)) == f"CAST(%s AS NVARCHAR({bucket}))"


def test_buckets_count_utf16_units() -> None:
    # 31 BMP characters + 1 emoji (2 units) = 33 units: the next bucket.
    assert cast_of(Value("é" * 31 + "\U0001f600")) == "CAST(%s AS NVARCHAR(256))"


def test_same_bucket_same_sql_text() -> None:
    assert cast_of(Value("a")) == cast_of(Value("a" * 30))


@pytest.mark.parametrize(
    "expression",
    [
        Value("x" * (NVARCHAR_MAX + 1)),
        Value("x", output_field=CharField(max_length=NVARCHAR_MAX + 1)),
        Value("x" * (NVARCHAR_MAX + 1), output_field=TextField()),
    ],
    ids=["inferred", "explicit max_length", "TextField"],
)
def test_strings_above_the_maximum_are_refused(expression) -> None:
    with pytest.raises(NotSupportedError, match=f"longer than NVARCHAR\\({NVARCHAR_MAX}\\)"):
        cast_of(expression)


def test_buckets_end_at_the_maximum() -> None:
    assert STRING_BUCKETS[-1] == NVARCHAR_MAX == 16370


# --- Types without a rule ----------------------------------------------------------


@pytest.mark.parametrize(
    ("expression", "type_name"),
    [
        (Value(uuid.uuid4()), "UUID"),
        (Value(b"\x00\x01"), "bytes"),
        (Value(dt.timedelta(days=1)), "timedelta"),
        (Value({"a": 1}, output_field=JSONField()), "dict"),
        (Value(None, output_field=UUIDField()), "NoneType"),
    ],
    ids=["uuid", "bytes", "timedelta", "json", "null uuid"],
)
def test_types_without_a_rule_are_refused(expression, type_name: str) -> None:
    with pytest.raises(NotSupportedError, match=f"Value of type {type_name}"):
        cast_of(expression)


def test_value_without_any_type_is_refused() -> None:
    # A value Django cannot type (no output_field resolved) is never sent as an
    # untyped marker.
    from django.db import connection

    with pytest.raises(NotSupportedError, match="Value of type dict has no SQL type"):
        Value({"a": 1}).as_db2_for_i(None, connection)


def test_untyped_null_stays_null() -> None:
    from django.db import connection

    assert Value(None).as_db2_for_i(None, connection) == ("NULL", ())


# --- Explicit output_field takes precedence ------------------------------------


@pytest.mark.parametrize(
    ("expression", "sql"),
    [
        (Value(1, output_field=BigIntegerField()), "CAST(%s AS BIGINT)"),
        (Value(1, output_field=FloatField()), "CAST(%s AS DOUBLE)"),
        (
            Value(1, output_field=DecimalField(max_digits=7, decimal_places=2)),
            "CAST(%s AS DECIMAL(7, 2))",
        ),
        (Value(2**40, output_field=IntegerField()), "CAST(%s AS INTEGER)"),
        (Value("a" * 40, output_field=CharField(max_length=10)), "CAST(%s AS NVARCHAR(10))"),
        (Value(1, output_field=BooleanField()), "CAST(%s AS BOOLEAN)"),
        (
            Value(Decimal("12.345"), output_field=DecimalField(max_digits=10, decimal_places=4)),
            "CAST(%s AS DECIMAL(10, 4))",
        ),
    ],
    ids=[
        "int as bigint",
        "int as float",
        "int as decimal",
        "big int as integer",
        "long string as max_length",
        "int as boolean",
        "decimal precision",
    ],
)
def test_explicit_output_field_takes_precedence(expression, sql: str) -> None:
    assert cast_of(expression) == sql


def test_inferred_integer_types_follow_the_range() -> None:
    assert cast_of(Value(2**31 - 1)) == "CAST(%s AS INTEGER)"
    assert cast_of(Value(2**31)) == "CAST(%s AS BIGINT)"
    assert cast_of(Value(2**63)) == "CAST(%s AS DECIMAL(19, 0))"
