"""Run read-only IBM i probes.

Usage (inside the "tests" container):
    nox -s probe -- [reachability|connect|sysinfo|libraries|packages|features|
                     string_limits|extract|queries|listagg|trunc|durations|in_subquery|
                     tuple_in|tuple_lookups|compound_parts|selected_predicates|catalog|all] ...
    nox -s probe -- fetch_errors | mapping_errors | long_string_params |
                    numeric_params | constraint_errors | drop_column | alter_table |
                    alter_column
                                       (own connection attributes, run alone)
    nox -s probe -- session

Probes run sequentially and share at most one ODBC connection per run.
A probe with its own connection attributes (``connection_attributes()``) must
run alone and is not part of "all".
Results are printed and stored as JSON under test-results/probes/.
"""

from __future__ import annotations

import contextlib
import sys

import qtemp_alter_column
import qtemp_alter_table
import qtemp_catalog
import qtemp_compound_parts
import qtemp_connect
import qtemp_constraint_errors
import qtemp_drop_column
import qtemp_durations
import qtemp_extract
import qtemp_features
import qtemp_fetch_errors
import qtemp_in_subquery
import qtemp_libraries
import qtemp_listagg
import qtemp_long_string_params
import qtemp_mapping_errors
import qtemp_numeric_params
import qtemp_packages
import qtemp_queries
import qtemp_reachability
import qtemp_selected_predicates
import qtemp_session
import qtemp_string_limits
import qtemp_system_info
import qtemp_trunc
import qtemp_tuple_in
import qtemp_tuple_lookups
from _common import ProbeError, Settings, connect, write_result

PROBES = {
    "reachability": qtemp_reachability,
    "connect": qtemp_connect,
    "sysinfo": qtemp_system_info,
    "libraries": qtemp_libraries,
    "session": qtemp_session,
    "packages": qtemp_packages,
    "features": qtemp_features,
    "string_limits": qtemp_string_limits,
    "extract": qtemp_extract,
    "queries": qtemp_queries,
    "listagg": qtemp_listagg,
    "trunc": qtemp_trunc,
    "durations": qtemp_durations,
    "fetch_errors": qtemp_fetch_errors,
    "mapping_errors": qtemp_mapping_errors,
    "long_string_params": qtemp_long_string_params,
    "in_subquery": qtemp_in_subquery,
    "tuple_in": qtemp_tuple_in,
    "tuple_lookups": qtemp_tuple_lookups,
    "compound_parts": qtemp_compound_parts,
    "selected_predicates": qtemp_selected_predicates,
    "numeric_params": qtemp_numeric_params,
    "constraint_errors": qtemp_constraint_errors,
    "drop_column": qtemp_drop_column,
    "alter_table": qtemp_alter_table,
    "alter_column": qtemp_alter_column,
    "catalog": qtemp_catalog,
}
USAGE = f"usage: run.py [{'|'.join(PROBES)}|all] ..."


def _own_connection(module) -> bool:
    return hasattr(module, "connection_attributes")


def main(argv: list[str]) -> int:
    names = argv or ["all"]
    if "all" in names:
        names = [name for name, module in PROBES.items() if not _own_connection(module)]
    unknown = [name for name in names if name not in PROBES]
    if unknown:
        print(f"unknown probe(s): {', '.join(unknown)}\n{USAGE}", file=sys.stderr)
        return 1
    if len(names) > 1 and any(_own_connection(PROBES[name]) for name in names):
        print("probes with their own connection attributes must run alone", file=sys.stderr)
        return 1

    conn = None
    try:
        settings = Settings.from_env(
            need_credentials=any(PROBES[name].NEEDS_CONNECTION for name in names)
        )
        for name in names:
            module = PROBES[name]
            print(f"\n=== probe: {name} ===")
            if module.NEEDS_CONNECTION and conn is None:
                if _own_connection(module):
                    conn = connect(
                        settings, module.connection_attributes(settings), module.AUTOCOMMIT
                    )
                else:
                    conn = connect(settings)
            result = module.run(settings, conn)
            print(f"\nresult saved to {write_result(name, result, settings)}")
    except ProbeError as exc:
        print(f"\nPROBE FAILED [{exc.category}]: {exc}", file=sys.stderr)
        return exc.exit_code
    finally:
        if conn is not None:
            # A probe may have closed it already (one connection at a time).
            with contextlib.suppress(Exception):
                conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
