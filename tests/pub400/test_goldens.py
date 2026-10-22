"""Execute every stored golden on IBM i: is the SQL accepted by Db2 for i?

"Verified" means "accepted by Db2 for i", not "returns correct results"
(CONTRIBUTING.md). The goldens are executed exactly as stored, in this order:

1. the test library's safety gate only (journal check, no foreign objects,
   leftovers of a marked library dropped, marker written), without migrate;
2. ``create`` goldens, which create the testapp tables the others use;
3. ``query`` goldens; ``dml`` goldens in a transaction that is rolled back;
4. ``flush`` goldens, after checking that the catalog metadata they were
   generated with matches what the create goldens created;
5. ``drop`` goldens; teardown drops whatever remains, then the marker.

A golden whose create dependency did not pass is skipped with a reason.
``pytest --record-verification`` stamps a golden that passed with "<level>,
<date>" only when it was unverified or verified on another level (IBM i release,
TR, Db2 PTF Group, Django version), and writes the run's date and counts to
tests/offline/golden/last-verification.txt (review the diff, commit it in a PR).
"""

import dataclasses
import datetime as dt

import django
import pytest
from django.db import connection, transaction

from django_db2_for_i import capabilities
from django_db2_for_i.compat import DJANGO_SERIES
from tests.golden import (
    LAST_VERIFICATION,
    golden_path,
    new_stamp,
    read,
    render_last_verification,
    verification_level,
)
from tests.golden_cases import FLUSH_METADATA, TESTAPP_TABLES, ordered_cases
from tests.pub400.marked_library import marked_library
from tests.verification_gate import reasons as unverifiable_reasons

RESULTS: dict[str, str] = {}  # golden name -> "passed" | "failed" | "skipped"

# Goldens Db2 for i cannot execute on the test system, with the reason:
# tests/offline/golden/unverifiable.toml, shared with the CI gate
# (nox -s gate). strict: once the SQL is accepted, the test reports it.
REJECTED: dict[str, str] = unverifiable_reasons(DJANGO_SERIES)

CASES = [
    pytest.param(
        case, id=case.name, marks=pytest.mark.xfail(reason=REJECTED[case.name], strict=True)
    )
    if case.name in REJECTED
    else pytest.param(case, id=case.name)
    for case in ordered_cases()
]


@pytest.fixture(scope="module", autouse=True)
def marked_empty_library(django_db_blocker, request):
    with django_db_blocker.unblock(), marked_library(request.node.nodeid):
        yield


@pytest.fixture
def live(django_db_blocker):
    with django_db_blocker.unblock():
        yield connection


def execute(cursor, sql, params, kind) -> None:
    # DDL and flush goldens are final SQL (collected without parameters);
    # query and DML goldens use %s placeholders.
    if kind in ("create", "drop", "flush"):
        cursor.execute(sql)
    else:
        cursor.execute(sql, list(params))
        if cursor.description:
            cursor.fetchall()


def run_golden(live, kind, golden) -> None:
    if kind == "flush":
        actual = live.ops._flush_metadata([table.upper() for table in TESTAPP_TABLES])
        if actual != FLUSH_METADATA:
            pytest.fail(
                "the catalog metadata the flush golden was generated with does not match "
                f"the tables the create goldens made: generated with {FLUSH_METADATA}, "
                f"catalog has {actual}. Not verified."
            )
        live.ops.execute_sql_flush([sql for sql, _ in golden.statements])
        return
    if kind == "dml":
        with transaction.atomic(using=live.alias), live.cursor() as cursor:
            for sql, params in golden.statements:
                execute(cursor, sql, params, kind)
            transaction.set_rollback(True, using=live.alias)
        return
    with live.cursor() as cursor:
        for sql, params in golden.statements:
            execute(cursor, sql, params, kind)


@pytest.fixture(scope="module")
def level(django_db_blocker, request):
    """The system level of this run; the run summary is written at the end."""
    # TR and Db2 PTF Group levels are not queried here: on PUB400 the PTF group
    # service fails with SQL0443, and a parameterized statement failing that way
    # leaves the connection unusable (drivers/pyodbc.py). They come from the
    # capabilities when those ever carry them; otherwise "unknown", never a guess.
    with django_db_blocker.unblock():
        capabilities_ = connection.capabilities
        value = verification_level(
            capabilities_.release_name,
            getattr(capabilities_, "technology_refresh", None) or "unknown",
            getattr(capabilities_, "db2_ptf_group", None) or "unknown",
            django.get_version(),
        )
    yield value
    if request.config.getoption("--record-verification"):
        today = f"{dt.datetime.now(dt.UTC):%Y-%m-%d}"
        LAST_VERIFICATION.write_text(render_last_verification(value, today, RESULTS))


@pytest.mark.parametrize("case", CASES)
def test_golden_is_accepted(case, live, level, request) -> None:
    release = live.capabilities.release
    profile = capabilities.profile_for_release(release)
    path = golden_path(DJANGO_SERIES, profile, case.name)
    golden = read(path)
    blocked = [name for name in golden.depends if RESULTS.get(name) != "passed"]
    if blocked:
        RESULTS[case.name] = "skipped"
        pytest.skip(f"depends on {', '.join(blocked)}, which did not pass")
    RESULTS[case.name] = "failed"
    run_golden(live, case.kind, golden)
    RESULTS[case.name] = "passed"
    if request.config.getoption("--record-verification"):
        stamp = new_stamp(golden.verified, level, f"{dt.datetime.now(dt.UTC):%Y-%m-%d}")
        if stamp is not None:
            path.write_text(dataclasses.replace(golden, verified=stamp).render())
