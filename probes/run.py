"""Run read-only IBM i probes.

Usage (inside the "tests" container):
    nox -s probe -- [reachability|connect|sysinfo|libraries|packages|features|
                     string_limits|extract|all] ...
    nox -s probe -- session

Probes run sequentially and share at most one ODBC connection per run.
A probe with its own connection attributes (``connection_attributes()``) must
run alone and is not part of "all".
Results are printed and stored as JSON under test-results/probes/.
"""

from __future__ import annotations

import sys

import p00_reachability
import p01_connect
import p02_system_info
import p03_libraries
import p04_session
import p05_packages
import p06_features
import p07_string_limits
import p08_extract
from _common import ProbeError, Settings, connect, write_result

PROBES = {
    "reachability": p00_reachability,
    "connect": p01_connect,
    "sysinfo": p02_system_info,
    "libraries": p03_libraries,
    "session": p04_session,
    "packages": p05_packages,
    "features": p06_features,
    "string_limits": p07_string_limits,
    "extract": p08_extract,
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
            conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
