"""The golden cases: backend-specific SQL for the testapp models.

Each case builds a list of ``(sql, params)`` statements from a connection
whose capabilities follow the profile being generated. The same cases are
compared offline (tests/offline/test_goldens.py) and executed against
IBM i (tests/pub400/test_goldens.py).

The selection is deliberately narrow: pagination, quoting, booleans,
date/time parameters, LIKE escaping, identity handling, flush and DDL types.
Plain SQL that Django generates the same way for every backend is left out;
it would only add churn on Django upgrades.

Kinds, in execution order on IBM i: ``create`` (DDL that creates the tables
the other cases use), ``query``, ``dml`` (rolled back), ``flush``, ``drop``.
"""

from __future__ import annotations

import contextlib
import dataclasses
import datetime as dt
from collections.abc import Callable, Iterator
from decimal import Decimal

from django.core.management.color import no_style
from django.db.models import Case as CaseExpr
from django.db.models import CharField, DecimalField, IntegerField, Value, When
from django.db.models.functions import Coalesce
from django.db.models.sql import DeleteQuery, InsertQuery, UpdateQuery

from django_db2_for_i import capabilities
from tests.testapp.models import Author, Book, Node, Tag

KINDS = ("create", "query", "dml", "flush", "drop")

TESTAPP_TABLES = ["testapp_author", "testapp_book", "testapp_node", "testapp_tag"]

# The catalog metadata sql_flush() reads, as the create goldens define it:
# only TESTAPP_NODE has a foreign key (to itself); every model except Tag has
# an identity primary key starting at 1. The IBM i verification compares this
# with the real catalog before it executes the flush golden.
FLUSH_METADATA = (
    {("TESTAPP_NODE", "TESTAPP_NODE")},
    {
        "TESTAPP_AUTHOR": ("ID", 1),
        "TESTAPP_BOOK": ("ID", 1),
        "TESTAPP_NODE": ("ID", 1),
    },
)

AWARE = dt.datetime(2026, 10, 17, 15, 30, 0, 123456, tzinfo=dt.timezone(dt.timedelta(hours=2)))


@dataclasses.dataclass(frozen=True)
class Case:
    name: str
    kind: str
    build: Callable[[object], list[tuple[str, tuple]]]
    depends: tuple[str, ...] = ()


@contextlib.contextmanager
def use_profile(connection, profile: str) -> Iterator[None]:
    """Generate SQL with the capabilities of ``profile`` (no connection needed)."""
    saved = connection._capabilities
    connection._capabilities = capabilities.from_profile(profile)
    try:
        yield
    finally:
        connection._capabilities = saved


def build_case(case: Case, connection, profile: str) -> list[tuple[str, tuple]]:
    with use_profile(connection, profile):
        return [(sql, tuple(params)) for sql, params in case.build(connection)]


# --- Builders ----------------------------------------------------------------------


def _ddl(*models, foreign_keys: bool = False):
    def build(connection):
        features = connection.features
        saved = features.supports_foreign_keys
        features.supports_foreign_keys = foreign_keys
        try:
            with connection.schema_editor(collect_sql=True) as editor:
                for model in models:
                    editor.create_model(model)
        finally:
            features.supports_foreign_keys = saved
        return [(sql.removesuffix(";"), ()) for sql in editor.collected_sql]

    return build


def _drop(model):
    def build(connection):
        with connection.schema_editor(collect_sql=True) as editor:
            editor.delete_model(model)
        return [(sql.removesuffix(";"), ()) for sql in editor.collected_sql]

    return build


def _select(make_queryset):
    def build(connection):
        sql, params = make_queryset().query.get_compiler(connection.alias).as_sql()
        return [(sql, params)]

    return build


def _exists(make_queryset):
    def build(connection):
        query = make_queryset().query.exists()
        sql, params = query.get_compiler(connection.alias).as_sql()
        return [(sql, params)]

    return build


def _annotate(make_expression):
    """SELECT <expression> AS "X" FROM the author table."""
    return _select(lambda: Author.objects.annotate(x=make_expression()).values("x"))


def _insert_book(connection):
    book = Book(
        author_id=1,
        title="Db2 for i",
        published=AWARE,
        reading_time=dt.time(1, 2, 3, 456789),
        available=True,
        pages=10,
    )
    fields = [f for f in Book._meta.local_concrete_fields if not f.primary_key]
    query = InsertQuery(Book)
    query.insert_values(fields, [book])
    return [(sql, params) for sql, params in query.get_compiler(connection.alias).as_sql()]


def _update_boolean(connection):
    query = Book.objects.filter(pk=1).query.chain(UpdateQuery)
    query.add_update_values({"available": False})
    sql, params = query.get_compiler(connection.alias).as_sql()
    return [(sql, params)]


def _delete_filtered(connection):
    query = Author.objects.filter(name__startswith="tmp").query.chain(DeleteQuery)
    sql, params = query.get_compiler(connection.alias).as_sql()
    return [(sql, params)]


def _last_insert_id(connection):
    class Recorder:
        sql = None

        def execute(self, sql):
            self.sql = sql

        def fetchone(self):
            return (Decimal(1),)

    cursor = Recorder()
    connection.ops.last_insert_id(cursor, "testapp_author", "id")
    return [(cursor.sql, ())]


def _flush(connection):
    ops = connection.ops
    saved = ops._flush_metadata
    ops._flush_metadata = lambda tables: FLUSH_METADATA
    try:
        statements = ops.sql_flush(no_style(), TESTAPP_TABLES, reset_sequences=True)
    finally:
        ops._flush_metadata = saved
    return [(sql, ()) for sql in statements]


AUTHOR, BOOK, NODE, TAG = (
    "ddl/create_author",
    "ddl/create_book",
    "ddl/create_node_fk",
    "ddl/create_tag",
)

CASES: tuple[Case, ...] = (
    # DDL types: identity columns, NVARCHAR, TIMESTAMP(6), TIME, BOOLEAN,
    # CHECK, UUID as CHAR(32), UNIQUE, indexes, NO ACTION foreign key.
    Case(AUTHOR, "create", _ddl(Author)),
    Case(BOOK, "create", _ddl(Book)),
    Case(NODE, "create", _ddl(Node, foreign_keys=True)),
    Case(TAG, "create", _ddl(Tag)),
    # Pagination (OFFSET / FETCH FIRST) and exists().
    Case(
        "queries/slice_offset_fetch",
        "query",
        _select(lambda: Author.objects.order_by("id")[1:3]),
        (AUTHOR,),
    ),
    Case(
        "queries/slice_offset_only",
        "query",
        _select(lambda: Author.objects.order_by("id")[3:]),
        (AUTHOR,),
    ),
    Case(
        "queries/slice_first_only",
        "query",
        _select(lambda: Author.objects.order_by("id")[:2]),
        (AUTHOR,),
    ),
    Case("queries/exists", "query", _exists(lambda: Author.objects.filter(name="a")), (AUTHOR,)),
    # Booleans, date/time parameters (aware -> naive UTC, TIME truncated).
    Case(
        "queries/filter_boolean",
        "query",
        _select(lambda: Book.objects.filter(available=True)),
        (BOOK,),
    ),
    Case(
        "queries/filter_datetime_aware",
        "query",
        _select(lambda: Book.objects.filter(published__gte=AWARE)),
        (BOOK,),
    ),
    Case(
        "queries/filter_time_truncated",
        "query",
        _select(lambda: Book.objects.filter(reading_time=dt.time(1, 2, 3, 456789))),
        (BOOK,),
    ),
    # LIKE with ESCAPE and escaped wildcards; case-insensitive lookups.
    Case(
        "queries/filter_startswith_escaped",
        "query",
        _select(lambda: Author.objects.filter(name__startswith="50%_off")),
        (AUTHOR,),
    ),
    Case(
        "queries/filter_iexact",
        "query",
        _select(lambda: Author.objects.filter(name__iexact="Ada")),
        (AUTHOR,),
    ),
    Case("queries/last_insert_id", "query", _last_insert_id),
    # Value expressions: typed parameter markers (SQL0418 otherwise), one
    # golden per type rule (django_db2_for_i/expressions.py).
    Case("values/integer", "query", _annotate(lambda: Value(1)), (AUTHOR,)),
    Case("values/bigint", "query", _annotate(lambda: Value(2**40)), (AUTHOR,)),
    Case(
        "values/string_length",
        "query",
        _annotate(lambda: Value("h\u00e9llo \U0001f600")),
        (AUTHOR,),
    ),
    Case("values/string_empty", "query", _annotate(lambda: Value("")), (AUTHOR,)),
    Case("values/string_bucket_1024", "query", _annotate(lambda: Value("x" * 300)), (AUTHOR,)),
    Case("values/float", "query", _annotate(lambda: Value(1.5)), (AUTHOR,)),
    Case(
        "values/string_max_length",
        "query",
        _annotate(lambda: Value("x", output_field=CharField(max_length=20))),
        (AUTHOR,),
    ),
    Case(
        "values/null_typed",
        "query",
        _annotate(lambda: Value(None, output_field=IntegerField())),
        (AUTHOR,),
    ),
    Case(
        "values/null_untyped_in_case",
        "query",
        _annotate(lambda: CaseExpr(When(name="a", then=Value(1)), default=Value(None))),
        (AUTHOR,),
    ),
    Case("values/boolean", "query", _annotate(lambda: Value(True)), (AUTHOR,)),
    Case("values/decimal", "query", _annotate(lambda: Value(Decimal("12.345"))), (AUTHOR,)),
    Case(
        "values/decimal_field",
        "query",
        _annotate(
            lambda: Value(
                Decimal("1.5"), output_field=DecimalField(max_digits=10, decimal_places=2)
            )
        ),
        (AUTHOR,),
    ),
    Case("values/date", "query", _annotate(lambda: Value(dt.date(2026, 10, 17))), (AUTHOR,)),
    Case("values/time", "query", _annotate(lambda: Value(dt.time(1, 2, 3, 456789))), (AUTHOR,)),
    Case("values/datetime_aware", "query", _annotate(lambda: Value(AWARE)), (AUTHOR,)),
    Case(
        "expressions/case_when",
        "query",
        _annotate(lambda: CaseExpr(When(name="a", then=Value(1)), default=Value(0))),
        (AUTHOR,),
    ),
    Case(
        "expressions/coalesce",
        "query",
        _annotate(lambda: Coalesce("name", Value("none"))),
        (AUTHOR,),
    ),
    Case("expressions/arithmetic", "query", _annotate(lambda: Value(1) + Value(2)), (AUTHOR,)),
    # DML with backend-specific values.
    Case("dml/insert_book", "dml", _insert_book, (BOOK,)),
    Case("dml/update_boolean", "dml", _update_boolean, (BOOK,)),
    Case("dml/delete_filtered", "dml", _delete_filtered, (AUTHOR,)),
    # Flush: TRUNCATE ... RESTART IDENTITY, DELETE + RESTART for referenced tables.
    Case("flush/testapp_reset_sequences", "flush", _flush, (AUTHOR, BOOK, NODE, TAG)),
    # DROP TABLE (cascades on Db2 for i).
    Case("ddl/drop_tag", "drop", _drop(Tag), (TAG,)),
)

CASES_BY_NAME = {case.name: case for case in CASES}


def ordered_cases() -> list[Case]:
    """Cases in the order they run on IBM i."""
    return sorted(CASES, key=lambda case: KINDS.index(case.kind))
