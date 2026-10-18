"""GROUP BY expressions with parameters or nested use: the LATERAL grouping
table (django_db2_for_i/compiler.py)."""

import pytest
from django.db import connection
from django.db.models import Case, Count, F, Max, Min, Q, Sum, Value, When
from django.db.models.functions import ExtractYear, Greatest, Least, Mod

from tests.testapp.models import Author, Book

pytestmark = pytest.mark.offline

TABLE = '"DJDB2I_GROUPING"'
G1 = f'{TABLE}."G1"'


def sql_of(queryset):
    return queryset.query.get_compiler(connection=connection).as_sql()


def test_plain_grouping_keeps_its_sql() -> None:
    for queryset in (
        Book.objects.values("author").annotate(n=Count("id")),
        Book.objects.values(year=ExtractYear("published")).annotate(n=Count("id")),
        Author.objects.annotate(n=Count("book")),
    ):
        sql, _params = sql_of(queryset)
        assert "LATERAL" not in sql


def test_expression_with_a_parameter() -> None:
    sql, params = sql_of(Book.objects.values(m=Mod("pages", 10)).annotate(n=Count("id")))
    assert sql == (
        f'SELECT {G1} AS "M", COUNT("TESTAPP_BOOK"."ID") AS "N" FROM "TESTAPP_BOOK" '
        'CROSS JOIN LATERAL (SELECT MOD("TESTAPP_BOOK"."PAGES", CAST(%s AS INTEGER)) AS "G1" '
        f"FROM SYSIBM.SYSDUMMY1) AS {TABLE} GROUP BY {G1}"
    )
    assert params == (10,)


def test_nested_expression_without_parameters() -> None:
    """Db2 for i matches a grouped expression only when it is selected whole."""
    queryset = (
        Book.objects.annotate(double=F("pages") + F("pages"))
        .values("double")
        .annotate(low=Min("pages"), least=Least("low", "double"))
        .values("least")
    )
    sql, params = sql_of(queryset)
    assert sql.startswith(f'SELECT LEAST(MIN("TESTAPP_BOOK"."PAGES"), {G1}) AS "LEAST" FROM')
    assert sql.endswith(f"GROUP BY {G1}")
    assert params == ()


def test_parameters_follow_the_sql_order() -> None:
    """Select list, FROM (joins, then the grouping table), WHERE, HAVING, ORDER BY."""
    queryset = (
        Book.objects.filter(title="x")
        .values(g=Greatest("pages", Value(600)))
        .annotate(n=Count("id") + Value(1))
        .filter(n__gt=2)
        .order_by("g")
    )
    sql, params = sql_of(queryset)
    assert sql.index("LATERAL") < sql.index(" WHERE ") < sql.index(" HAVING ")
    assert params == (1, 600, "x", 1, 2)


def test_joins_having_order_by_and_where_use_the_column() -> None:
    queryset = (
        Author.objects.values(b=Q(book__pages__lt=100))
        .annotate(n=Count("id"))
        .filter(b=True)
        .order_by("b")
    )
    sql, _params = sql_of(queryset)
    from_clause = sql.split(" FROM ", 1)[1]
    assert from_clause.index("LEFT OUTER JOIN") < from_clause.index("CROSS JOIN LATERAL")
    assert f"WHERE {G1}" in sql
    assert sql.endswith(f"GROUP BY {G1} ORDER BY 1 ASC") or sql.endswith(
        f"GROUP BY {G1} ORDER BY {G1} ASC"
    )


def test_selected_annotation_of_a_grouped_model_query() -> None:
    """Grouping by model instances also groups by selected non-aggregates."""
    good = Case(When(book__pages__gt=100, then=Value(True)), default=Value(False))
    sql, params = sql_of(Author.objects.annotate(total=Sum("book__pages"), good=good))
    assert f'{G1} AS "GOOD"' in sql
    assert sql.endswith(f'GROUP BY "TESTAPP_AUTHOR"."ID", "TESTAPP_AUTHOR"."NAME", {G1}')
    assert params == (100, True, False)


def test_count_of_a_grouped_query() -> None:
    """.count() wraps the grouped query: the inner query keeps the grouping table."""
    from django.db.models.sql.subqueries import AggregateQuery

    inner = Book.objects.values(m=Mod("pages", 10)).annotate(n=Count("id")).query.clone()
    inner.subquery = True
    outer = AggregateQuery(Book, inner)
    outer.add_annotation(Count("*"), "__count")
    sql, params = outer.get_compiler(using="default").as_sql()
    assert sql.startswith("SELECT COUNT(*) FROM (SELECT")
    assert "CROSS JOIN LATERAL" in sql and params == (10,)


def test_max_of_a_grouped_value_stays_an_aggregate() -> None:
    sql, _params = sql_of(Book.objects.values("author").annotate(m=Max(Mod("pages", 10))))
    assert "LATERAL" not in sql
