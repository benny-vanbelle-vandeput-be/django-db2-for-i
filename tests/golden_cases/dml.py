"""DML goldens (rolled back on IBM i): INSERT, UPDATE, DELETE, savepoints."""

from __future__ import annotations

import datetime as dt

from django.db.models.sql import DeleteQuery, InsertQuery, UpdateQuery

from tests.golden_cases.base import AUTHOR, AWARE, BOOK, Case
from tests.testapp.models import Author, Book


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


def _savepoints(connection):
    """Django's nested atomic(): create, rollback to + release (error), release."""
    ops = connection.ops
    sid, inner = "s140234567890123_x1", "s140234567890123_x2"
    statements = [
        ops.savepoint_create_sql(sid),
        f"INSERT INTO {ops.quote_name('testapp_author')} ({ops.quote_name('name')}) "
        "VALUES ('savepoint')",
        ops.savepoint_create_sql(inner),
        ops.savepoint_rollback_sql(inner),
        ops.savepoint_commit_sql(inner),
        ops.savepoint_commit_sql(sid),
    ]
    return [(sql, ()) for sql in statements]


CASES: tuple[Case, ...] = (
    Case("dml/insert_book", "dml", _insert_book, (BOOK,)),
    Case("dml/update_boolean", "dml", _update_boolean, (BOOK,)),
    Case("dml/delete_filtered", "dml", _delete_filtered, (AUTHOR,)),
    # Savepoints, as nested atomic() blocks use them (in the rolled-back transaction).
    Case("dml/savepoints", "dml", _savepoints, (AUTHOR,)),
)
