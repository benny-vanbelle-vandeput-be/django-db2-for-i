"""Django-version axis: the only module allowed to check ``django.VERSION``.

Built from real differences between the supported Django versions (5.2 LTS,
6.0 and 6.1; docs/DJANGO_VERSIONS.md). Other modules import the named facts
below and never compare versions themselves (tests/offline/test_axes.py).

6.0 reaches end of life before 5.2, so the shims are grouped by when they can
go, not by version: each section's heading says when it is deleted. Dropping
a version also removes its goldens, its noxfile line and its pyproject range
(docs/DJANGO_VERSIONS.md, "Dropping a version").
"""

import functools

import django

# The running Django's feature release, e.g. "6.1". Golden files are kept per
# series (tests/offline/golden/<series>/...), since generated SQL can differ.
DJANGO_SERIES = f"{django.VERSION[0]}.{django.VERSION[1]}"

# --- Django 6.0 only (delete when 6.0 is dropped) ------------------------------------
# Nothing yet.

# --- Django 5.2 only (delete when 5.2 is dropped) ------------------------------------

# StringAgg is a general aggregate from Django 6.0; 5.2 has it only in
# contrib.postgres, which is not patched: on 5.2 it is not supported (None).
# When 5.2 is dropped: import StringAgg from django.db.models directly.
if django.VERSION >= (6, 0):
    from django.db.models import StringAgg
else:
    StringAgg = None

# Expected failures of features.py that pass on this Django version only
# (docs/DECISIONS.md, "The first per-version expected-failure list"). None
# since CPA32B2 is suppressed in migrations: the two schema tests that narrowed
# BigAutoField to INTEGER only from 6.0 on now pass everywhere.
PASSING_ON_THIS_VERSION: frozenset[str] = frozenset()

# Expected failures of features.py on this Django version only. Django 6.0
# added skipUnlessDBFeature("supports_json_field") to this test; 5.2 runs it,
# and it fails on its JSONField db_default (phase 6). When 5.2 is dropped:
# remove this and the features.py entry.
FAILING_ON_THIS_VERSION_ONLY: frozenset[str] = (
    frozenset()
    if django.VERSION >= (6, 0)
    else frozenset({"schema.tests.SchemaTests.test_db_default_output_field_resolving"})
)

# Django 6.0 refuses a composite field compared with a subquery (>, >=, <, <=)
# when supports_tuple_comparison_against_subquery is off; 5.2 writes a row-value
# comparison, which Db2 for i rejects (SQL0115). The tuple hook refuses it there.
DJANGO_CHECKS_TUPLE_SUBQUERY_COMPARISON = django.VERSION >= (6, 0)


class Before60OperationsMixin:
    """DatabaseOperations hooks under their Django 5.2 names. Django 6.0
    renamed return_insert_columns() to returning_columns() (the insert
    compiler calls it for the returning clause); 5.2's base version returns
    None, which the compiler cannot unpack. Harmless on 6.0+, which never
    calls it. When 5.2 is dropped: delete this class and its base in
    operations.py."""

    def return_insert_columns(self, fields):
        return self.returning_columns(fields)


# --- Before 6.1: Django 6.0 and 5.2 (delete when both are dropped) -------------------

# Django 6.1 prepares duration values through ops.adapt_durationfield_value();
# before 6.1, DurationField.get_db_prep_value() converts them itself.
DJANGO_CALLS_ADAPT_DURATIONFIELD_VALUE = django.VERSION >= (6, 1)


def relation(column: str, table: str, rule: str) -> tuple:
    """A value of introspection.get_relations(): ``(column, table, db_on_delete)``
    on 6.1, ``(column, table)`` before. ``rule`` is the catalog's delete rule
    (``QSYS2.SYSREFCST.DELETE_RULE``: ``"NO ACTION"``, ``"CASCADE"``, ...).
    Django 6.1's ``on_delete_types`` maps exactly these values (``None`` for
    ``RESTRICT``, which has no Django constant); it does not exist before 6.1."""
    if django.VERSION < (6, 1):
        return (column, table)
    from django.db.backends.base.introspection import BaseDatabaseIntrospection

    return (column, table, BaseDatabaseIntrospection.on_delete_types.get(rule))


def install_duration_adapter() -> None:
    """Before Django 6.1: route DurationField values through the backend's
    ``adapt_durationfield_value()`` (its BIGINT range check), as 6.1 does.

    Only for this backend's connections; for every other connection the
    original method runs unchanged. Idempotent: never wraps twice
    (docs/DECISIONS.md, "The duration range check before Django 6.1").
    """
    if DJANGO_CALLS_ADAPT_DURATIONFIELD_VALUE:
        return
    from django.db.models import DurationField

    original = DurationField.get_db_prep_value
    if getattr(original, "db2_for_i_adapter", False):
        return

    @functools.wraps(original)
    def get_db_prep_value(self, value, connection, prepared=False):
        if connection.vendor != "db2_for_i":
            return original(self, value, connection, prepared)
        return connection.ops.adapt_durationfield_value(value)

    get_db_prep_value.db2_for_i_adapter = True
    DurationField.get_db_prep_value = get_db_prep_value
