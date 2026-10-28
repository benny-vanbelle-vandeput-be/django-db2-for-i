"""The golden cases: backend-specific SQL for the testapp models.

Each case builds a list of ``(sql, params)`` statements from a connection
whose capabilities follow the profile being generated. The same cases are
compared offline (tests/offline/test_goldens.py) and executed against
IBM i (tests/ibmi/test_goldens.py).

The selection is deliberately narrow: pagination, quoting, booleans,
date/time parameters, LIKE escaping, identity handling, flush and DDL types.
Plain SQL that Django generates the same way for every backend is left out;
it would only add churn on Django upgrades.

Kinds, in execution order on IBM i: ``create`` (DDL that creates the tables
the other cases use), ``query``, ``dml`` (rolled back), ``flush``, ``drop``.

One module per golden group (the directory under tests/offline/golden/<django>/
<profile>/): ddl, queries, values, expressions, aggregates, extract, dml, flush.
A new case goes into the module of its group; tests/offline/test_goldens.py
checks that every name starts with its module's group.
"""

from __future__ import annotations

from tests.golden_cases import (
    aggregates,
    ddl,
    dml,
    expressions,
    extract,
    flush,
    queries,
    values,
)
from tests.golden_cases.base import KINDS, Case, build_case, use_profile
from tests.golden_cases.flush import FLUSH_METADATA, TESTAPP_TABLES

__all__ = [
    "CASES",
    "CASES_BY_NAME",
    "FLUSH_METADATA",
    "GROUPS",
    "KINDS",
    "TESTAPP_TABLES",
    "Case",
    "build_case",
    "ordered_cases",
    "use_profile",
]

GROUPS = {
    module.__name__.rsplit(".", 1)[1]: module.CASES
    for module in (ddl, queries, values, expressions, aggregates, extract, dml, flush)
}

CASES: tuple[Case, ...] = tuple(case for cases in GROUPS.values() for case in cases)

CASES_BY_NAME = {case.name: case for case in CASES}


def ordered_cases() -> list[Case]:
    """Cases in the order they run on IBM i."""
    return sorted(CASES, key=lambda case: KINDS.index(case.kind))
