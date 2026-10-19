"""The Case type, the builders shared by the golden groups, and the create
goldens' names (the ``depends`` of most cases)."""

from __future__ import annotations

import contextlib
import dataclasses
import datetime as dt
from collections.abc import Callable, Iterator

from django.db.models import OuterRef

from django_db2_for_i import capabilities
from tests.testapp.models import Author, Book

KINDS = ("create", "query", "dml", "flush", "drop")

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


def select(make_queryset):
    def build(connection):
        sql, params = make_queryset().query.get_compiler(connection.alias).as_sql()
        return [(sql, params)]

    return build


def exists(make_queryset):
    def build(connection):
        query = make_queryset().query.exists()
        sql, params = query.get_compiler(connection.alias).as_sql()
        return [(sql, params)]

    return build


def books_of_author():
    return Book.objects.filter(author=OuterRef("pk"))


def annotate(make_expression):
    """SELECT <expression> AS "X" FROM the author table."""
    return select(lambda: Author.objects.annotate(x=make_expression()).values("x"))


AUTHOR, BOOK, NODE, TAG, DEFAULTS = (
    "ddl/create_author",
    "ddl/create_book",
    "ddl/create_node_fk",
    "ddl/create_tag",
    "ddl/create_defaults",
)
SCHEDULE = "ddl/create_schedule"
