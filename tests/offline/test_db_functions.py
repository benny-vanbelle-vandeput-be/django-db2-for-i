"""Database functions where Db2 for i differs from Django's SQL (no server needed)."""

import dataclasses

import pytest
from django.db import NotSupportedError, connection, connections
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

from django_db2_for_i import compat
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


def test_a_float_cast_to_text_goes_through_decfloat() -> None:
    from django.db.models import CharField, FloatField, TextField

    double = Cast("pages", FloatField())
    for field in (CharField(), TextField()):
        sql, _params = select_of(Book.objects.annotate(x=Cast(double, field)).values("x"))
        assert sql.startswith(
            'CAST(CAST(CAST("TESTAPP_BOOK"."PAGES" AS DOUBLE) AS DECFLOAT(16)) + 0 AS '
        )
    number = Author.objects.annotate(x=Cast("id", CharField())).values("x")
    assert "DECFLOAT" not in select_of(number)[0]


def test_window_offsets_are_constants() -> None:
    """A LAG / LEAD offset and NTH_VALUE's position as literals (Db2 for i refuses
    a marker there); the default stays a typed marker."""
    from django.db.models import Window
    from django.db.models.functions import Lag, Lead, NthValue

    order = F("pages").asc()
    lag = Window(Lag("pages", 2, default=Value(0)), order_by=order)
    sql, params = select_of(Book.objects.annotate(x=lag).values("x"))
    assert sql.startswith('LAG("TESTAPP_BOOK"."PAGES", 2, CAST(%s AS ')
    assert params == (0,)
    lead = Window(Lead("pages"), order_by=order)
    assert select_of(Book.objects.annotate(x=lead).values("x")) == (
        'LEAD("TESTAPP_BOOK"."PAGES", 1) OVER (ORDER BY "TESTAPP_BOOK"."PAGES" ASC)',
        (),
    )
    nth = Window(NthValue("pages", 3), order_by=order)
    assert select_of(Book.objects.annotate(x=nth).values("x"))[0].startswith(
        'NTH_VALUE("TESTAPP_BOOK"."PAGES", 3) OVER'
    )


def test_percent_rank_and_cume_dist_are_doubles() -> None:
    from django.db.models import Window
    from django.db.models.functions import CumeDist, PercentRank, Rank

    order = F("pages").asc()
    for function in (PercentRank, CumeDist):
        window = Window(function(), order_by=order)
        assert select_of(Book.objects.annotate(x=window).values("x"))[0] == (
            f'CAST({function.function}() OVER (ORDER BY "TESTAPP_BOOK"."PAGES" ASC) AS DOUBLE)'
        )
    rank = select_of(Book.objects.annotate(x=Window(Rank(), order_by=order)).values("x"))[0]
    assert rank == 'RANK() OVER (ORDER BY "TESTAPP_BOOK"."PAGES" ASC)'


uuid4_only = pytest.mark.skipif(compat.UUID4 is None, reason="UUID4() is new in Django 6.1")


@pytest.fixture
def generate_uuid(request):
    """The capability has_generate_uuid on or off for this test (the profile has it on)."""
    wrapper = connections["default"]
    original = wrapper.capabilities
    wrapper._capabilities = dataclasses.replace(original, has_generate_uuid=request.param)
    wrapper.features.__dict__.pop("supports_uuid4_function", None)
    try:
        yield request.param
    finally:
        wrapper._capabilities = original
        wrapper.features.__dict__.pop("supports_uuid4_function", None)


@uuid4_only
@pytest.mark.parametrize("generate_uuid", [True], indirect=True)
def test_uuid4_is_generate_uuid_as_32_lowercase_digits(generate_uuid) -> None:
    assert connection.features.supports_uuid4_function is True
    sql, params = select_of(Author.objects.annotate(x=compat.UUID4()).values("x"))
    assert (sql, params) == ("LOWER(REPLACE(GENERATE_UUID(), '-', ''))", ())


@uuid4_only
@pytest.mark.parametrize("generate_uuid", [False], indirect=True)
def test_uuid4_without_generate_uuid_raises(generate_uuid) -> None:
    assert connection.features.supports_uuid4_function is False
    queryset = Author.objects.annotate(x=compat.UUID4()).values("x")
    with pytest.raises(
        NotSupportedError, match=r"not supported on this database backend\..*SF99950"
    ):
        select_of(queryset)
