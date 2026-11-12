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

from pathlib import Path

import pytest
from django.core.management.color import no_style
from django.db import connection, connections

from tests.ibmi.connection_guard import replace_if_unusable
from tests.ibmi.marked_library import install_guard, marked_library
from tests.ibmi.testapp_tables import MODELS, TABLES

SMOKE_LIST = Path(__file__).with_name("smoke.txt")


def smoke_ids(path: Path = SMOKE_LIST) -> set[str]:
    """The node ids of the smoke set (comments and blank lines left out)."""
    lines = (line.strip() for line in path.read_text().splitlines())
    return {line for line in lines if line and not line.startswith("#")}


def pytest_collection_modifyitems(config, items) -> None:
    """Mark the smoke set (nox -s smoke runs -m "ibmi and smoke"); a parametrized
    test belongs to it with all its parameters."""
    ids = smoke_ids()
    for item in items:
        if item.nodeid.split("[", 1)[0] in ids:
            item.add_marker(pytest.mark.smoke)


@pytest.fixture(scope="session", autouse=True)
def _tables_only_in_a_marked_library():
    """Every own IBM i test creates tables inside marked_library() or in QTEMP."""
    install_guard()


@pytest.fixture(scope="session", autouse=True)
def _clean_before_a_resumed_part(django_db_blocker):
    """A resumed run (tests/progress.py) first drops what the interrupted test left:
    bin/ibmi-cleanup's logic, under its standing approval (only listed tables, only
    in the marked library)."""
    clean_if_resuming(django_db_blocker)


def _load_cleanup():
    import importlib.util
    from pathlib import Path

    script = Path(__file__).resolve().parents[2] / "scripts" / "ibmi_cleanup.py"
    spec = importlib.util.spec_from_file_location("ibmi_cleanup", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def clean_if_resuming(blocker, load_cleanup=_load_cleanup) -> bool:
    """True if a resumed part cleaned up first; stops the run if that failed."""
    from tests import progress

    run = progress.active()
    if run is None or not run.resuming:
        return False
    print("\nprogress: resumed part: dropping the interrupted test's leftover tables first")
    with blocker.unblock():
        if load_cleanup().clean(yes=True) != 0:
            pytest.exit("resume: the leftover tables could not be cleaned up", returncode=3)
    return True


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
