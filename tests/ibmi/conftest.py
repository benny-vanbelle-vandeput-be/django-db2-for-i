"""IBM i tests: one connection per run, closed at the end of the session.

``testapp_tables`` creates the tests.testapp tables in the default library
(journaled) for one test module and drops them again; a module uses it with
``pytestmark = pytest.mark.usefixtures("testapp_tables")``. Like the golden
check, it works in a marked library (marked_library.py): the creation safety
gate and the DJDB2I_TEST_MARKER table come first, so a crashed module leaves
tables that bin/ibmi-cleanup may drop, and teardown leaves the library without
tables, marker included. Foreign keys are enabled while the tables are
created, to execute the NO ACTION foreign key DDL and the DELETE path of
sql_flush(); the feature flag itself stays off until Django's test suite
backs it.
"""

import pytest
from django.core.management.color import no_style
from django.db import connection, connections

from tests.ibmi.connection_guard import replace_if_unusable
from tests.ibmi.marked_library import install_guard, marked_library
from tests.ibmi.testapp_tables import MODELS, TABLES


@pytest.fixture(scope="session", autouse=True)
def _tables_only_in_a_marked_library():
    """Every own IBM i test creates tables inside marked_library() or in QTEMP."""
    install_guard()


@pytest.fixture(scope="session", autouse=True)
def _close_connections_at_end(django_db_blocker):
    yield
    with django_db_blocker.unblock():
        connections.close_all()


@pytest.fixture(scope="module")
def testapp_tables(django_db_blocker, request):
    with django_db_blocker.unblock(), marked_library(request.node.nodeid):
        with connection.schema_editor() as editor:
            for model in MODELS:
                editor.create_model(model)
        yield


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
