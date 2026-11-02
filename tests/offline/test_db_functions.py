"""Database functions where Db2 for i differs from Django's SQL (no server needed)."""

import pytest
from django.db import NotSupportedError
from django.db.models import F, Value
from django.db.models.functions import (
    MD5,
    SHA1,
    SHA224,
    SHA256,
    SHA384,
    SHA512,
    ATan2,
    Cast,
    Concat,
    Length,
    Log,
    LPad,
    Repeat,
    Reverse,
    RPad,
)

from tests.testapp.models import Author, Book


def select_of(queryset) -> tuple[str, tuple]:
    """The SELECT list item ``X`` of ``queryset`` and the query's params."""
    sql, params = queryset.query.get_compiler("default").as_sql()
    return sql.removeprefix("SELECT ").split(' AS "X"')[0], tuple(params)


def test_length_counts_characters() -> None:
    sql, _params = select_of(Author.objects.annotate(x=Length("name")).values("x"))
    assert sql == 'CHARACTER_LENGTH("TESTAPP_AUTHOR"."NAME")'


def test_log_is_a_quotient_of_natural_logarithms() -> None:
    sql, _params = select_of(Book.objects.annotate(x=Log("pages", F("id"))).values("x"))
    assert sql == '(LN("TESTAPP_BOOK"."ID") / LN("TESTAPP_BOOK"."PAGES"))'


def test_log_keeps_the_params_in_their_places() -> None:
    queryset = Book.objects.annotate(x=Log(Value(2.0), Value(8.0))).values("x")
    sql, params = select_of(queryset)
    assert sql == "(LN(CAST(%s AS DOUBLE)) / LN(CAST(%s AS DOUBLE)))"
    assert params == (8.0, 2.0)


def test_concat_treats_null_as_empty_text() -> None:
    queryset = Author.objects.annotate(x=Concat("name", Value("!"))).values("x")
    sql, params = select_of(queryset)
    assert sql == (
        'CONCAT(COALESCE("TESTAPP_AUTHOR"."NAME", CAST(%s AS NVARCHAR(32))), '
        "CAST(%s AS NVARCHAR(32)))"
    )
    assert params == ("", "!")


def test_concat_coalesces_a_null_value() -> None:
    queryset = Author.objects.annotate(x=Concat("name", Value(None))).values("x")
    sql, _params = select_of(queryset)
    assert sql.count("COALESCE(") == 2


@pytest.mark.parametrize("function", [Reverse, SHA224, SHA384])
def test_functions_db2_for_i_lacks_are_refused(function) -> None:
    queryset = Author.objects.annotate(x=function("name")).values("x")
    with pytest.raises(NotSupportedError, match="has no such function"):
        queryset.query.get_compiler("default").as_sql()


def test_atan2_passes_x_first() -> None:
    sql, _params = select_of(Book.objects.annotate(x=ATan2("pages", "id")).values("x"))
    assert sql == 'ATAN2("TESTAPP_BOOK"."ID", "TESTAPP_BOOK"."PAGES")'


@pytest.mark.parametrize(
    ("function", "name"),
    [(MD5, "HASH_MD5"), (SHA1, "HASH_SHA1"), (SHA256, "HASH_SHA256"), (SHA512, "HASH_SHA512")],
)
def test_hashes_take_the_text_as_utf8(function, name: str) -> None:
    sql, _params = select_of(Author.objects.annotate(x=function("name")).values("x"))
    assert sql == f'LOWER(HEX({name}(CAST("TESTAPP_AUTHOR"."NAME" AS CLOB(2G) CCSID 1208))))'


@pytest.mark.parametrize("function", [LPad, RPad])
def test_padding_null_casts_it(function) -> None:
    sql, _params = select_of(Author.objects.annotate(x=function(Value(None), 1)).values("x"))
    assert sql.startswith(f"{function.function}(CAST(NULL AS NVARCHAR(32)), ")


def test_repeat_casts_null_text_and_null_number() -> None:
    sql, _params = select_of(Author.objects.annotate(x=Repeat(Value(None), 4)).values("x"))
    assert sql.startswith("REPEAT(CAST(NULL AS NVARCHAR(32)), ")
    sql, _params = select_of(Author.objects.annotate(x=Repeat("name", None)).values("x"))
    assert sql == 'REPEAT("TESTAPP_AUTHOR"."NAME", CAST(NULL AS INTEGER))'


def test_a_number_cast_to_a_decimal_is_rounded_first() -> None:
    from django.db.models import DecimalField, FloatField

    field = DecimalField(max_digits=8, decimal_places=1)
    queryset = Book.objects.annotate(x=Cast(Cast("pages", FloatField()), field)).values("x")
    sql, _params = select_of(queryset)
    assert sql == (
        'CAST(ROUND(CAST(CAST("TESTAPP_BOOK"."PAGES" AS DOUBLE) AS DECFLOAT(34)), 1) '
        "AS DECIMAL(8, 1))"
    )
    text = Author.objects.annotate(x=Cast("name", field)).values("x")
    assert select_of(text)[0] == 'CAST("TESTAPP_AUTHOR"."NAME" AS DECIMAL(8, 1))'
