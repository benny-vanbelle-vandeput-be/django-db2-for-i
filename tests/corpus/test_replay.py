"""Replay the offline query corpus (nox -s corpus; docs/proposals/offline-query-corpus.md).

Each entry is a statement a passing Django test sent to Db2 for i (captured on
PUB400). Its pickled query is loaded, compiled again with the backend under the
offline capability profile, with the USE_TZ / TIME_ZONE it was captured with,
and the SQL and params must equal the recorded ones. A mismatch means "this SQL
is no longer the SQL that passed on IBM i", the same rule as for the goldens.

``--update-corpus`` (refused when CI is set) writes the new SQL and clears the
entry's stamp, like ``--update-goldens``. Entries whose pickle cannot be loaded
are skipped and counted in the coverage report, and so are entries whose
compilation would need the database (the capture no longer records those).
"""

from __future__ import annotations

import os
import pickle

import django
import pytest
from django.db import connection
from django.test.utils import override_settings

from tests.corpus import store
from tests.golden import UNVERIFIED

DJANGO = os.environ.get("DB2I_CORPUS_DJANGO") or ".".join(map(str, django.VERSION[:2]))
DIRECTORY = store.corpus_dir(DJANGO)
COVERAGE: dict[str, dict[str, int]] = {}


def replay(entry: store.Entry, pickle_format: int = store.PICKLE_FORMAT) -> list[list]:
    """The [sql, params] pairs the backend writes now for the entry's query."""
    query = store.loads(store.decode_query(entry.query), pickle_format)
    with override_settings(**entry.settings):
        # With an alias too: nested compilers (subqueries) call get_compiler(self.using).
        compiled = query.get_compiler(using=connection.alias, connection=connection).as_sql()
    statements = compiled if isinstance(compiled, list) else [compiled]
    return store.encode_statements(statements)


@pytest.mark.parametrize("module", store.modules(DIRECTORY) or ["(none)"])
def test_corpus_module_replays(module, request) -> None:
    if module == "(none)":
        pytest.skip(f"no corpus for Django {DJANGO}")
    entries = store.read_module(DIRECTORY, module)
    manifest = store.read_manifest(DIRECTORY).get("modules", {}).get(module, {})
    pickle_format = manifest.get("pickle_format", 1)  # 1 for the first captures
    mismatches, not_loadable, not_replayable, updated = [], 0, 0, False
    for entry in entries:
        try:
            current = replay(entry, pickle_format)
        except (pickle.UnpicklingError, AttributeError, ImportError, LookupError):
            not_loadable += 1
            continue
        except (RuntimeError, AssertionError) as exc:  # compiling needs the database
            if "Database access not allowed" not in str(exc) and "connection" not in str(exc):
                raise
            not_replayable += 1
            continue
        if current != entry.sql:
            if request.config.getoption("--update-corpus"):
                entry.sql, entry.verified, updated = current, UNVERIFIED, True
            else:
                mismatches.append((entry.tests[0], entry.sql, current))
    COVERAGE[module] = {
        "entries": len(entries),
        "replayed": len(entries) - not_loadable - not_replayable,
        "not_loadable": not_loadable,
        "not_replayable": not_replayable,
        "unverified": sum(entry.verified == UNVERIFIED for entry in entries),
    }
    if updated:
        store.write_module(DIRECTORY, module, entries)
    if mismatches:
        test, recorded, now = mismatches[0]
        pytest.fail(
            f"{len(mismatches)} of {len(entries)} corpus entries of {module} write different "
            f"SQL now (run with --update-corpus if intended); first, from {test}:\n"
            f"recorded: {recorded}\nnow:      {now}"
        )
