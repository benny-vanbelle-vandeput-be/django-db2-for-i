"""compiler.py: hidden columns for SELECT DISTINCT with emulated NULL ordering."""

from django.db import connection
from django.db.models import F

from django_db2_for_i import compiler
from tests.testapp.models import Book


def compiled(queryset):
    sql_compiler = queryset.query.get_compiler(connection=connection)
    sql, _params = sql_compiler.as_sql()
    return sql_compiler, sql


def test_the_backend_uses_its_compiler_module() -> None:
    assert isinstance(
        Book.objects.all().query.get_compiler(connection=connection), compiler.SQLCompiler
    )


def test_distinct_selects_the_null_ordering_predicate_as_a_hidden_column() -> None:
    queryset = Book.objects.order_by(F("published").asc(nulls_first=True)).distinct()
    sql_compiler, sql = compiled(queryset.values_list("title", flat=True))
    select, order_by = sql.split(" FROM ")[0], sql.split(" ORDER BY ")[1]
    assert select == (
        'SELECT DISTINCT "TESTAPP_BOOK"."TITLE" AS "TITLE", '
        '"TESTAPP_BOOK"."PUBLISHED" IS NOT NULL, "TESTAPP_BOOK"."PUBLISHED"'
    )
    # By position: an expression with parameter markers never matches a
    # selected one in Db2 for i (SQL0214).
    assert order_by == "2 ASC, 3 ASC"
    # Rows are trimmed to the requested column.
    assert sql_compiler.has_extra_select
    assert sql_compiler.col_count == 1


def test_nulls_last_uses_is_null() -> None:
    queryset = Book.objects.order_by(F("published").desc(nulls_last=True)).distinct()
    _, sql = compiled(queryset.values_list("title"))
    assert '"TESTAPP_BOOK"."PUBLISHED" IS NULL, "TESTAPP_BOOK"."PUBLISHED" FROM' in sql
    assert sql.endswith("ORDER BY 2 ASC, 3 DESC")


def test_without_distinct_nothing_is_added() -> None:
    queryset = Book.objects.order_by(F("published").asc(nulls_first=True)).values("title")
    sql_compiler, sql = compiled(queryset)
    assert sql.startswith('SELECT "TESTAPP_BOOK"."TITLE" AS "TITLE" FROM')
    assert not sql_compiler.has_extra_select


def test_plain_distinct_ordering_keeps_djangos_rule() -> None:
    queryset = Book.objects.order_by("published").distinct().values_list("title")
    sql_compiler, sql = compiled(queryset)
    assert sql.startswith(
        'SELECT DISTINCT "TESTAPP_BOOK"."TITLE" AS "TITLE", "TESTAPP_BOOK"."PUBLISHED" FROM'
    )
    assert sql_compiler.col_count == 1


def test_parameters_stay_in_the_select_list() -> None:
    queryset = (
        Book.objects.filter(title__icontains="db")
        .order_by(F("published").asc(nulls_first=True))
        .distinct()
        .values_list("title")
    )
    _, sql = compiled(queryset)
    assert sql.endswith("ORDER BY 2 ASC, 3 ASC")
