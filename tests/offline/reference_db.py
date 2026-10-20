"""An in-memory SQLite database as a reference: Django on a backend with
standard three-valued SQL semantics, for comparing the rows the backend gets
on IBM i (no IBM i needed)."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator

from django.db import connections

ALIAS = "reference"


@contextlib.contextmanager
def sqlite_reference(django_db_blocker, models) -> Iterator[str]:
    """Create ``models``' tables in a fresh in-memory SQLite database; yield its alias."""
    settings = connections.configure_settings(
        {
            "default": connections.settings["default"],
            ALIAS: {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"},
        }
    )
    connections.settings[ALIAS] = settings[ALIAS]
    django_db_blocker.unblock()
    # SQLite has row values (3.15+); Django 6.0+ uses them, 5.2 emulates them
    # with AND/OR. Native everywhere, so the reference SQL is the same.
    connections[ALIAS].features.supports_tuple_lookups = True
    try:
        with connections[ALIAS].schema_editor() as editor:
            for model in models:
                editor.create_model(model)
        yield ALIAS
    finally:
        connections[ALIAS].close()
        del connections[ALIAS]
        del connections.settings[ALIAS]
        django_db_blocker.restore()
