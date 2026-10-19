"""compiler.py: hidden columns for SELECT DISTINCT with emulated NULL ordering."""

from django.db import connection
from django.db.models import Case, Exists, F, OuterRef, Q, Value, When
from django.db.models.lookups import Exact

from django_db2_for_i import compiler
from tests.testapp.models import Account, Author, Book, Contact


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
        # Three-valued: NULL when the predicate is UNKNOWN (no ELSE; issue #75).
        assert " THEN TRUE WHEN NOT (" in sql
        assert ' THEN FALSE END AS "B" FROM' in sql


def test_group_by_a_predicate_with_a_value_uses_the_lateral_column() -> None:
    from django.db.models import Count

    queryset = Book.objects.annotate(b=Q(pages__lt=100)).values("b").annotate(n=Count("id"))
    sql, params = queryset.query.get_compiler(connection=connection).as_sql()
    assert sql.startswith('SELECT "DJDB2I_GROUPING"."G1" AS "B", ')
    assert sql.endswith(' GROUP BY "DJDB2I_GROUPING"."G1"')
    pages = '"TESTAPP_BOOK"."PAGES" < %s'
    assert (
        f"CROSS JOIN LATERAL (SELECT {WRAPPED}{pages} THEN TRUE WHEN NOT ({pages}) THEN FALSE "
        'END AS "G1" FROM SYSIBM.SYSDUMMY1) AS "DJDB2I_GROUPING"'
    ) in sql
    assert params == (100, 100)


def test_conditions_and_exists_are_not_wrapped() -> None:
    _, sql = compiled(Book.objects.annotate(b=Q(pages__lt=100)).filter(b=True).values("id"))
    assert WRAPPED not in sql
    _, sql = compiled(Author.objects.annotate(has=books()).values("has"))
    assert sql.startswith("SELECT ((SELECT (1)")


def test_in_subquery_stays_plain_in_a_search_condition() -> None:
    queryset = Book.objects.filter(author__in=Author.objects.values("id"))
    _, sql = compiled(queryset)
    assert ' IN (SELECT "U0"."ID" AS "ID" FROM "TESTAPP_AUTHOR" "U0")' in sql
    assert "DJDB2I_IN" not in sql


def test_in_subquery_as_a_value_is_three_valued() -> None:
    queryset = Book.objects.annotate(b=Q(author__in=Author.objects.values("id"))).values("b")
    sql, _params = queryset.query.get_compiler(connection=connection).as_sql()
    rows = 'LATERAL (SELECT "U0"."ID" AS "ID" FROM "TESTAPP_AUTHOR" "U0") AS "DJDB2I_IN" (V1)'
    assert sql.count(rows) == 2  # a match, a row that may match (NULL)
    x = '"TESTAPP_BOOK"."AUTHOR_ID"'
    assert f'WHERE "DJDB2I_IN".V1 = {x} FETCH' in sql
    assert f'("DJDB2I_IN".V1 = {x} OR "DJDB2I_IN".V1 IS NULL OR {x} IS NULL)' in sql
    # Selected as it is: the rewrite's three-valued BOOLEAN, its subqueries once.
    assert 'THEN NULL ELSE FALSE END) AS "B" FROM' in sql
    assert "= TRUE" not in sql


def test_tuple_in_subquery_is_not_rewritten_in_a_search_condition() -> None:
    """RelatedIn renders as TupleIn on the same lhs: still a search condition, so
    a row-value IN (subquery), not the IN rewrite."""
    queryset = Contact.objects.filter(account__in=Account.objects.filter(number__gt=1))
    _, sql = compiled(queryset)
    assert '("TESTAPP_CONTACT"."COMPANY", "TESTAPP_CONTACT"."ACCOUNT_NUMBER") IN (SELECT' in sql
    assert "DJDB2I_IN" not in sql


def test_tuple_in_subquery_as_a_value_has_a_column_per_element() -> None:
    queryset = Contact.objects.annotate(
        b=Q(account__in=Account.objects.filter(number__gt=1))
    ).values("b")
    sql, params = queryset.query.get_compiler(connection=connection).as_sql()
    assert sql.count('AS "DJDB2I_IN" (V1, V2)') == 2
    assert (
        'WHERE "DJDB2I_IN".V1 = "TESTAPP_CONTACT"."COMPANY" '
        'AND "DJDB2I_IN".V2 = "TESTAPP_CONTACT"."ACCOUNT_NUMBER" FETCH' in sql
    )
    assert params == (1, 1)


def test_a_lookup_as_an_operand_is_not_a_search_condition() -> None:
    """A lookup compiled inside a condition lookup, on another lhs, stays a value."""
    queryset = Book.objects.filter(
        Exact(Q(author__in=Author.objects.values("id")), Q(pages__lt=10))
    )
    _, sql = compiled(queryset)
    assert "DJDB2I_IN" in sql


def test_tuple_in_subquery_in_case_contexts_uses_the_rewrite() -> None:
    """The search-condition context of WHERE never reaches XOR, a selected value
    or a When condition: no plain IN (subquery) inside CASE (SQL0115 on Db2 for i;
    XOR's first half is a search condition and keeps the row-value IN)."""
    in_accounts = Q(account__in=Account.objects.filter(number__gt=1))
    querysets = (
        Contact.objects.filter(in_accounts ^ Q(company="c")),
        Contact.objects.annotate(b=in_accounts).values("b"),
        Contact.objects.annotate(x=Case(When(in_accounts, then=Value(1)), default=Value(0))),
    )
    for queryset in querysets:
        _, sql = compiled(queryset)
        assert 'AS "DJDB2I_IN" (V1, V2)' in sql
        assert " IN (SELECT" not in sql[sql.index("CASE WHEN") :]
