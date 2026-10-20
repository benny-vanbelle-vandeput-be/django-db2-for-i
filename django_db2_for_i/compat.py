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
# Nothing yet (5.2 support is phase 3, step B).

# --- Before 6.1: Django 6.0 and 5.2 (delete when both are dropped) -------------------

# Django 6.1 prepares duration values through ops.adapt_durationfield_value();
# before 6.1, DurationField.get_db_prep_value() converts them itself.
DJANGO_CALLS_ADAPT_DURATIONFIELD_VALUE = django.VERSION >= (6, 1)


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
