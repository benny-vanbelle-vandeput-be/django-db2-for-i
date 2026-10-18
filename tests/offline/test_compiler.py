"""compiler.py: hidden columns for SELECT DISTINCT with emulated NULL ordering."""

from django.db import connection
from django.db.models import Case, Exists, F, OuterRef, Q, Value, When

from django_db2_for_i import compiler
from tests.testapp.models import Author, Book


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


# --- Exists(): EXISTS only as a search condition --------------------------------------


def books():
    return Exists(Book.objects.filter(author=OuterRef("pk")))


FIRST_ROW = "FETCH FIRST 1 ROWS ONLY) IS NOT NULL)"


def where_and_select(queryset):
    """The outer query's select list and WHERE clause (subqueries have their own)."""
    _, sql = compiled(queryset)
    select, _, rest = sql.rpartition(' FROM "TESTAPP_AUTHOR"')
    where = rest.removeprefix(" WHERE ")
    return select, where


def test_exists_in_where_stays_exists() -> None:
    _, where = where_and_select(Author.objects.filter(books()))
    assert where.startswith("EXISTS(") and FIRST_ROW not in where
    _, where = where_and_select(Author.objects.filter(~books()))
    assert where.startswith("NOT EXISTS(")
    _, where = where_and_select(Author.objects.filter(Q(name="a") | books()))
    assert " OR EXISTS(" in where


def test_exists_in_the_select_list_is_a_first_row_subquery() -> None:
    select, where = where_and_select(Author.objects.annotate(has=books()).filter(has=True))
    assert FIRST_ROW in select and "EXISTS(" not in select
    assert where.startswith("EXISTS(")  # the annotation, filtered as a condition
    select, _ = where_and_select(Author.objects.annotate(has=~books()))
    assert "NOT ((SELECT" in select and FIRST_ROW in select


def test_exists_inside_case_when_is_a_first_row_subquery() -> None:
    case = Case(When(books(), then=Value(1)), default=Value(0))
    select, _ = where_and_select(Author.objects.annotate(x=case))
    assert "CASE WHEN ((SELECT" in select
    # Also in a WHERE clause: CASE WHEN EXISTS is rejected there too.
    _, where = where_and_select(Author.objects.annotate(x=case).filter(x=1))
    assert "CASE WHEN ((SELECT" in where and "EXISTS(" not in where


def test_q_annotation_with_exists_is_a_first_row_subquery() -> None:
    select, _ = where_and_select(Author.objects.annotate(x=Q(name="a") | books()))
    assert FIRST_ROW in select and "EXISTS(" not in select


def test_exists_in_order_by_and_group_by() -> None:
    _, sql = compiled(Author.objects.order_by(books().desc()))
    assert sql.split(" ORDER BY ")[1].startswith("((SELECT")
    from django.db.models import Count

    _, sql = compiled(Author.objects.annotate(has=books()).values("has").annotate(n=Count("id")))
    assert sql.split(" GROUP BY ")[1].startswith("((SELECT")


def test_exists_subquery_never_selects_a_parameter_marker() -> None:
    """A marker in an EXISTS subquery's select list fails in the IBM i host server."""
    for queryset in (
        Author.objects.filter(books()),
        Author.objects.exclude(~books()),
        Author.objects.annotate(has=books()),
    ):
        sql_compiler = queryset.query.get_compiler(connection=connection)
        sql, params = sql_compiler.as_sql()
        subquery = sql.split("(SELECT ", 1)[1]
        assert subquery.startswith('(1) AS "A" FROM'), sql
        assert params == ()


# --- Predicates as select columns -------------------------------------------------------

WRAPPED = "CASE WHEN "


def test_q_and_lookup_annotations_are_case_values() -> None:
    from django.db.models.lookups import LessThan

    for annotation in (Q(pages__lt=100), ~Q(pages__lt=100), LessThan(F("pages"), 100)):
        _, sql = compiled(Book.objects.annotate(b=annotation).values("b"))
        assert sql.startswith(f"SELECT {WRAPPED}") and sql.count(WRAPPED) == 1
        assert ' THEN TRUE ELSE FALSE END AS "B" FROM' in sql


def test_group_by_uses_the_same_case_value() -> None:
    from django.db.models import Count

    queryset = Book.objects.annotate(b=Q(pages__lt=100)).values("b").annotate(n=Count("id"))
    _, sql = compiled(queryset)
    select, group_by = sql.split(" FROM ")[0], sql.split(" GROUP BY ")[1]
    assert group_by.startswith(WRAPPED)
    assert select.split(" AS ")[0].removeprefix("SELECT ") == group_by


def test_conditions_and_exists_are_not_wrapped() -> None:
    _, sql = compiled(Book.objects.annotate(b=Q(pages__lt=100)).filter(b=True).values("id"))
    assert WRAPPED not in sql
    _, sql = compiled(Author.objects.annotate(has=books()).values("has"))
    assert sql.startswith("SELECT ((SELECT (1)")
