"""pub400 tier: one connection per run, closed at the end of the session.

``testapp_tables`` creates the tests.testapp tables in the default library
(journaled) for one test module and drops them again; a module uses it with
``pytestmark = pytest.mark.usefixtures("testapp_tables")``. It refuses to
start if any of these tables already exist, and never drops tables it did
not create. Foreign keys are enabled while the tables are created, to execute
the NO ACTION foreign key DDL and the DELETE path of sql_flush(); the feature
flag itself stays off until Django's test suite backs it.
"""

import pytest
from django.core.management.color import no_style
from django.db import connection, connections

from tests.pub400.connection_guard import replace_if_unusable
from tests.pub400.testapp_tables import MODELS, TABLES


@pytest.fixture(scope="session", autouse=True)
def _close_connections_at_end(django_db_blocker):
    yield
    with django_db_blocker.unblock():
        connections.close_all()


@pytest.fixture(scope="module")
def testapp_tables(django_db_blocker):
    with django_db_blocker.unblock(), pytest.MonkeyPatch.context() as patch:
        existing = TABLES & set(connection.introspection.table_names())
        if existing:
            pytest.fail(f"tables already exist, remove them first: {sorted(existing)}")
        patch.setattr(connection.features, "supports_foreign_keys", True)
        created = []
        try:
            with connection.schema_editor() as editor:
                for model in MODELS:
                    editor.create_model(model)
                    created.append(model)
            yield
        finally:
            replace_if_unusable()
            errors = []
            for model in reversed(created):
                try:
                    with connection.schema_editor() as editor:
                        editor.delete_model(model)
                except Exception as exc:  # report every leftover table
                    errors.append(f"{model._meta.db_table}: {exc}")
            assert not errors, f"tables NOT dropped, remove manually: {errors}"


@pytest.fixture
def live(django_db_blocker):
    with django_db_blocker.unblock():
        yield connection


@pytest.fixture
def empty(live):
    """Empty all testapp tables (and restart identities) after the test."""
    yield
    replace_if_unusable(live)
    live.ops.execute_sql_flush(live.ops.sql_flush(no_style(), sorted(TABLES), reset_sequences=True))
