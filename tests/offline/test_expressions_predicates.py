"""expressions.py: predicates as comparison operands (no server needed)."""

from django.db import connection
from django.db.models import BooleanField, Exists, ExpressionWrapper, F, OuterRef, Q, Value
from django.db.models.expressions import RawSQL
from django.db.models.lookups import LessThan

from django_db2_for_i.expressions import PredicateValue, renders_as_predicate
from tests.testapp.models import Author, Book

CASE = "CASE WHEN "


def where(queryset) -> str:
    """The outer query's WHERE clause (subqueries have their own)."""
    sql, _params = queryset.query.get_compiler(connection=connection).as_sql()
    table = queryset.model._meta.db_table.upper()
    return sql.rpartition(f' FROM "{table}"')[2].removeprefix(" WHERE ")


def test_renders_as_predicate() -> None:
    assert renders_as_predicate(LessThan(F("pages"), 1))
    assert renders_as_predicate(Exists(Book.objects.all()))
    assert renders_as_predicate(~Exists(Book.objects.all()))
    assert renders_as_predicate(
        ExpressionWrapper(LessThan(F("pages"), 1), output_field=BooleanField())
    )
    assert not renders_as_predicate(F("available"))
    assert not renders_as_predicate(Value(True))


def test_both_predicate_operands_are_wrapped() -> None:
    queryset = Book.objects.annotate(b=LessThan(F("pages"), 2000)).filter(
        b=LessThan(F("pages"), 1900)
    )
    clause = where(queryset)
    assert clause.startswith(CASE) and clause.count(CASE) == 2
    assert clause.count("THEN TRUE ELSE FALSE END") == 2


def test_a_boolean_column_is_not_wrapped() -> None:
    clause = where(Book.objects.filter(available=Q(pages__lt=100)))
    assert clause.startswith('"TESTAPP_BOOK"."AVAILABLE" = (CASE WHEN ')


def test_exists_operands_use_the_first_row_form() -> None:
    books = Exists(Book.objects.filter(author=OuterRef("pk")))
    clause = where(Author.objects.annotate(has=books).filter(has=books))
    assert clause.startswith("CASE WHEN ((SELECT (1)")
    assert "EXISTS(" not in clause


def test_conditions_compared_with_true_are_not_wrapped() -> None:
    books = Exists(Book.objects.filter(author=OuterRef("pk")))
    assert where(Author.objects.annotate(has=books).filter(has=True)).startswith("EXISTS(")


def test_predicate_value_sql() -> None:
    compiler = Book.objects.all().query.get_compiler(connection=connection)
    sql, params = PredicateValue(Value(True)).as_sql(compiler, connection)
    assert sql == "CASE WHEN CAST(%s AS BOOLEAN) THEN TRUE ELSE FALSE END"
    assert params == [True] or params == (True,)


def test_negated_boolean_value_as_an_operand_keeps_null() -> None:
    queryset = Book.objects.filter(available=~Value(None, output_field=BooleanField()))
    assert where(queryset) == (
        '"TESTAPP_BOOK"."AVAILABLE" = (CASE CAST(NULL AS BOOLEAN) WHEN TRUE THEN FALSE '
        "WHEN FALSE THEN TRUE END)"
    )


def test_boolean_values_as_conditions_are_comparisons() -> None:
    """NOT <BOOLEAN value> is TRUE for NULL on Db2 for i: a BOOLEAN value used as a
    condition is compared with TRUE / FALSE (three-valued, index-friendly)."""
    column = '"TESTAPP_BOOK"."AVAILABLE"'
    assert where(Book.objects.filter(available=True)) == f"{column} = TRUE"
    assert where(Book.objects.filter(available=False)) == f"{column} = FALSE"
    assert where(Book.objects.exclude(available=True)) == f"NOT ({column} = TRUE)"
    assert where(Book.objects.filter(~F("available"))) == f"{column} = FALSE"
    assert where(Book.objects.annotate(x=~F("available")).filter(x=False)) == f"{column} = TRUE"
    wrapped = ExpressionWrapper(F("available"), output_field=BooleanField())
    assert where(Book.objects.filter(wrapped)) == f"{column} = TRUE"


def test_a_conditional_raw_sql_stays_a_condition() -> None:
    """Django trusts a conditional RawSQL to be a condition; = TRUE after a predicate
    would be SQL0104 (Django's test_filtering_on_rawsql_that_is_boolean)."""
    raw = RawSQL("pages > %s", (3,), output_field=BooleanField())
    assert where(Book.objects.filter(raw)) == "(pages > %s)"


def test_negated_boolean_column_is_a_case_value_when_selected() -> None:
    """NOT <BOOLEAN value> is TRUE for NULL on Db2 for i; the CASE form keeps NULL."""
    negated = 'CASE "TESTAPP_BOOK"."AVAILABLE" WHEN TRUE THEN FALSE WHEN FALSE THEN TRUE END'
    sql, _params = (
        Book.objects.annotate(x=~F("available"))
        .values("x")
        .query.get_compiler(connection=connection)
        .as_sql()
    )
    assert sql.startswith(f'SELECT {negated} AS "X"')
    # A negated predicate stays NOT <predicate>.
    assert where(Author.objects.filter(~Exists(Book.objects.all()))).startswith("NOT EXISTS")
