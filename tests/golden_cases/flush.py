"""Flush goldens: TRUNCATE ... RESTART IDENTITY, DELETE + RESTART for
referenced tables.
"""

from __future__ import annotations

from django.core.management.color import no_style

from tests.golden_cases.base import AUTHOR, BOOK, NODE, TAG, Case

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


def _flush(connection):
    ops = connection.ops
    saved = ops._flush_metadata
    ops._flush_metadata = lambda tables: FLUSH_METADATA
    try:
        statements = ops.sql_flush(no_style(), TESTAPP_TABLES, reset_sequences=True)
    finally:
        ops._flush_metadata = saved
    return [(sql, ()) for sql in statements]


CASES: tuple[Case, ...] = (
    Case("flush/testapp_reset_sequences", "flush", _flush, (AUTHOR, BOOK, NODE, TAG)),
)
