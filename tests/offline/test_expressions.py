"""Typed parameter markers for Value expressions (no server needed)."""

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from django.db import NotSupportedError, connection
from django.db.models import (
    BigIntegerField,
    BooleanField,
    CharField,
    DecimalField,
    F,
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
        (Value(b"\x00\x01"), "bytes"),
        (Value({"a": 1}, output_field=JSONField()), "dict"),
    ],
    ids=["bytes", "json"],
)
def test_types_without_a_rule_are_refused(expression, type_name: str) -> None:
    with pytest.raises(NotSupportedError, match=f"Value of type {type_name}"):
        cast_of(expression)


def test_uuid_values_are_char_32() -> None:
    assert cast_of(Value(uuid.UUID(int=1))) == "CAST(%s AS CHAR(32))"
    assert cast_of(Value(None, output_field=UUIDField())) == "CAST(NULL AS CHAR(32))"


def test_duration_values_are_bigint_microseconds() -> None:
    assert cast_of(Value(dt.timedelta(days=1))) == "CAST(%s AS BIGINT)"


def test_value_without_any_type_is_refused() -> None:
    # A value Django cannot type (no output_field resolved) is never sent as an
    # untyped marker.
    from django.db import connection

    with pytest.raises(NotSupportedError, match="Value of type dict has no SQL type"):
        Value({"a": 1}).as_db2_for_i(None, connection)


def test_untyped_null_stays_null() -> None:
    from django.db import connection

    sql, params = Value(None).as_db2_for_i(None, connection)
    assert (sql, tuple(params)) == ("NULL", ())  # a list on Django 6.0


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
        (Value("a" * 10, output_field=CharField(max_length=10)), "CAST(%s AS NVARCHAR(10))"),
        (Value("a" * 40, output_field=CharField(max_length=10)), "CAST(%s AS NVARCHAR(256))"),
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
        "string as max_length",
        "longer string: its own bucket, never cut short",
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


def test_duration_arithmetic_repeats_the_duration_parameters() -> None:
    """ts + d is split into DAYS + MICROSECONDS, so d's parameters appear twice."""
    from django.db.models import F

    from tests.testapp.models import Schedule

    queryset = Schedule.objects.annotate(x=F("start") - Value(dt.timedelta(microseconds=5)))
    sql, params = queryset.values("x").query.get_compiler("default").as_sql()
    assert (
        '("TESTAPP_SCHEDULE"."START" - INTEGER((CAST(%s AS BIGINT)) / 86400000000) DAYS '
        "- MOD((CAST(%s AS BIGINT)), 86400000000) MICROSECONDS)"
    ) in sql
    assert params == (5, 5)


# --- String values longer than the column -----------------------------------------------


def where_of(queryset) -> tuple[str, tuple]:
    sql, params = queryset.query.get_compiler("default").as_sql()
    return sql.split(" WHERE ", 1)[1], params


def test_values_that_fit_keep_untyped_markers() -> None:
    from tests.testapp.models import Author

    assert where_of(Author.objects.filter(name="x" * 100)) == (
        '"TESTAPP_AUTHOR"."NAME" = %s',
        ("x" * 100,),
    )


def test_a_value_longer_than_the_column_is_typed() -> None:
    from tests.testapp.models import Author

    for queryset, op in (
        (Author.objects.filter(name="x" * 101), "="),
        (Author.objects.filter(name__gt="x" * 101), ">"),
        (Author.objects.filter(name__lte="x" * 101), "<="),
    ):
        assert where_of(queryset)[0] == f'"TESTAPP_AUTHOR"."NAME" {op} CAST(%s AS NVARCHAR(256))'


def test_only_too_long_in_values_are_typed() -> None:
    from tests.testapp.models import Author

    sql, params = where_of(Author.objects.exclude(name__in=["fits", "y" * 120, "also"]))
    assert sql == 'NOT ("TESTAPP_AUTHOR"."NAME" IN (%s, CAST(%s AS NVARCHAR(256)), %s))'
    assert params == ("fits", "y" * 120, "also")


def test_length_is_measured_in_utf16_units() -> None:
    """An emoji is one character for len() but two UTF-16 units in NVARCHAR."""
    from tests.testapp.models import Tag

    fits = "e" * 49 + "é"  # 50 units in a SlugField(max_length=50)
    too_long = "e" * 49 + "\U0001f600"  # 50 by len(), 51 units
    assert len(too_long) == 50
    assert where_of(Tag.objects.filter(label=fits))[0] == '"TESTAPP_TAG"."LABEL" = %s'
    assert "CAST(%s AS NVARCHAR(256))" in where_of(Tag.objects.filter(label=too_long))[0]


def test_an_expression_on_the_left_has_no_known_size() -> None:
    from django.db.models.functions import Lower

    from tests.testapp.models import Author

    queryset = Author.objects.annotate(low=Lower("name")).filter(low="abc")
    assert where_of(queryset)[0] == 'LOWER("TESTAPP_AUTHOR"."NAME") = CAST(%s AS NVARCHAR(32))'


def test_values_longer_than_the_largest_bucket_are_refused() -> None:
    from tests.testapp.models import Author

    with pytest.raises(NotSupportedError, match="never truncated"):
        where_of(Author.objects.filter(name="x" * 16371))


# --- Numeric values that do not fit the column (issue #69) ------------------------------


@pytest.mark.parametrize(
    ("value", "digits"),
    [
        ("1.005", (4, 3)),
        ("123456.789", (9, 3)),
        ("1E+5", (6, 0)),  # exponent form: 100000
        ("1.50", (3, 2)),  # trailing zeros count
        ("-1.50", (3, 2)),
        ("0.005", (3, 3)),
        ("-0", (1, 0)),
        ("-0.0", (1, 0)),
        ("0E-70", (1, 0)),
        (str(10**62), (63, 0)),  # the largest precision
        ("1." + "0" * 70, (1, 0)),  # trailing zeros dropped only beyond 63 digits
    ],
)
def test_decimal_digits_hold_the_value_exactly(value, digits) -> None:
    from django_db2_for_i.expressions import decimal_digits

    assert decimal_digits(Decimal(value)) == digits


def test_decimal_type_from_an_exponent_form() -> None:
    from django_db2_for_i.expressions import decimal_type

    assert decimal_type(Decimal("1E+5")) == "DECIMAL(6, 0)"


@pytest.mark.parametrize("value", ["NaN", "-NaN", "sNaN", "Infinity", "-Infinity"])
def test_non_finite_decimals_are_refused(value) -> None:
    from django_db2_for_i.expressions import decimal_digits

    with pytest.raises(NotSupportedError, match="NaN and infinities"):
        decimal_digits(Decimal(value))


@pytest.mark.parametrize("value", [str(10**63), "1E-70", "0." + "1234567890" * 7])
def test_decimals_beyond_63_digits_are_refused(value) -> None:
    from django_db2_for_i.expressions import decimal_digits

    with pytest.raises(NotSupportedError, match="at most 63"):
        decimal_digits(Decimal(value))


def test_integer_values_beyond_bigint_are_decimals_with_the_same_limit() -> None:
    from django_db2_for_i.expressions import value_cast_type

    field = IntegerField()
    assert value_cast_type(10**20, field, connection, explicit=False) == "DECIMAL(21, 0)"
    assert value_cast_type(-(10**20), field, connection, explicit=False) == "DECIMAL(21, 0)"
    with pytest.raises(NotSupportedError, match="at most 63"):
        value_cast_type(10**63, field, connection, explicit=False)


def test_a_non_finite_decimal_value_is_refused_clearly() -> None:
    """Django's DecimalField refuses NaN / infinities itself (a ValidationError, before
    the backend); decimal_digits refuses them too, for any other path."""
    from django.core.exceptions import ValidationError

    from tests.testapp.models import Measure

    for value in ("NaN", "Infinity", "-Infinity"):
        with pytest.raises(ValidationError):
            where_of(Measure.objects.filter(amount=Decimal(value)))
        queryset = Author.objects.annotate(x=Value(Decimal(value), output_field=DecimalField()))
        with pytest.raises(ValidationError):
            queryset.values("x").query.get_compiler("default").as_sql()


def test_integers_out_of_the_column_range_are_typed_in_in_lists_and_ranges() -> None:
    from tests.testapp.models import Measure

    small = '"TESTAPP_MEASURE"."SMALL"'
    assert where_of(Measure.objects.filter(small__in=[1, 100000])) == (
        f"{small} IN (%s, CAST(%s AS DECIMAL(6, 0)))",
        (1, 100000),
    )
    assert where_of(Measure.objects.exclude(small__in=[1, 100000]))[0] == (
        f"NOT ({small} IN (%s, CAST(%s AS DECIMAL(6, 0))) AND {small} IS NOT NULL)"
    )
    assert where_of(Measure.objects.filter(small__range=(0, 100000)))[0] == (
        f"{small} BETWEEN %s AND CAST(%s AS DECIMAL(6, 0))"
    )
    assert where_of(Measure.objects.filter(small__range=(-100000, 0)))[0] == (
        f"{small} BETWEEN CAST(%s AS DECIMAL(6, 0)) AND %s"
    )
    # Values that fit keep their untyped markers and SQL.
    assert where_of(Measure.objects.filter(small__in=[1, 32767, -32768]))[0] == (
        f"{small} IN (%s, %s, %s)"
    )
    big = '"TESTAPP_MEASURE"."BIG"'
    assert where_of(Measure.objects.filter(big__in=[1, 10**20])) == (
        f"{big} IN (%s, CAST(%s AS DECIMAL(21, 0)))",
        (1, 10**20),
    )


def test_decimals_with_more_digits_than_the_column_are_typed() -> None:
    from tests.testapp.models import Measure

    amount = '"TESTAPP_MEASURE"."AMOUNT"'
    cases = [
        (Measure.objects.filter(amount=Decimal("1.005")), f"{amount} = CAST(%s AS DECIMAL(4, 3))"),
        (
            Measure.objects.filter(amount__gt=Decimal("123456.789")),
            f"{amount} > CAST(%s AS DECIMAL(9, 3))",
        ),
        (
            Measure.objects.filter(amount__lt=Decimal("1E+5")),
            f"{amount} < CAST(%s AS DECIMAL(6, 0))",
        ),
        (Measure.objects.filter(amount=Decimal("1.500")), f"{amount} = CAST(%s AS DECIMAL(4, 3))"),
        (
            Measure.objects.filter(amount__in=[Decimal("0.00"), Decimal("1.005")]),
            f"{amount} IN (%s, CAST(%s AS DECIMAL(4, 3)))",
        ),
        (
            Measure.objects.filter(amount__range=(Decimal("0.995"), Decimal("1.005"))),
            f"{amount} BETWEEN CAST(%s AS DECIMAL(3, 3)) AND CAST(%s AS DECIMAL(4, 3))",
        ),
        # Fits DECIMAL(5, 2): untyped.
        (Measure.objects.filter(amount=Decimal("1.50")), f"{amount} = %s"),
        (Measure.objects.filter(amount=Decimal("-999.99")), f"{amount} = %s"),
    ]
    for queryset, expected in cases:
        assert where_of(queryset)[0] == expected


def test_comparison_numbers_beyond_63_digits_are_refused() -> None:
    from tests.testapp.models import Measure

    with pytest.raises(NotSupportedError, match="never rounded or truncated"):
        where_of(Measure.objects.filter(amount=Decimal(10**63)))


def test_numbers_against_an_expression_of_unknown_size() -> None:
    """Decimals are typed; integers only outside the INTEGER range."""
    from tests.testapp.models import Measure

    annotated = Measure.objects.annotate(x=F("small") + 1)
    assert where_of(annotated.filter(x__in=[1, 2]))[0].endswith("IN (%s, %s)")
    assert where_of(annotated.filter(x__in=[1, 3000000000]))[0].endswith(
        "IN (%s, CAST(%s AS DECIMAL(10, 0)))"
    )
    sums = Measure.objects.annotate(x=F("amount") + F("amount"))
    assert where_of(sums.filter(x=Decimal("1.5")))[0].endswith("= CAST(%s AS DECIMAL(2, 1))")


# --- Values of relations and IP addresses -------------------------------------------


@pytest.mark.parametrize(
    ("field", "cast"),
    [
        ("author", "INTEGER"),  # ForeignKey to an AutoField
        ("code", "NVARCHAR(8)"),  # to a CharField primary key
        ("tag", "CHAR(32)"),  # to a UUIDField primary key
        ("profile", "INTEGER"),  # to a OneToOneField primary key, to Author.id
        ("ip", "VARCHAR(39)"),  # GenericIPAddressField
    ],
)
def test_values_of_relations_take_the_target_type(field, cast) -> None:
    from tests.testapp.models import Link

    output_field = Link._meta.get_field(field)
    assert cast_of(Value(None, output_field=output_field)) == f"CAST(NULL AS {cast})"


def test_a_uuid_key_value_is_sent_as_hex() -> None:
    import uuid as uuid_module

    from tests.testapp.models import Link

    value = uuid_module.UUID("12345678-1234-5678-1234-567812345678")
    queryset = Author.objects.annotate(x=Value(value, output_field=Link._meta.get_field("tag")))
    sql, params = queryset.values("x").query.get_compiler("default").as_sql()
    assert "CAST(%s AS CHAR(32))" in sql and params == ("12345678123456781234567812345678",)
