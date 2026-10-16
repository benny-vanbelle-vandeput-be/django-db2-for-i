"""Run read-only IBM i probes.

Usage (inside the "tests" container):
    nox -s probe -- [reachability|connect|sysinfo|libraries|all] ...

Probes run sequentially and share at most one ODBC connection per run.
Results are printed and stored as JSON under test-results/probes/.
"""

from __future__ import annotations

import sys

import p00_reachability
import p01_connect
import p02_system_info
import p03_libraries
from _common import ProbeError, Settings, connect, write_result

PROBES = {
    "reachability": p00_reachability,
    "connect": p01_connect,
    "sysinfo": p02_system_info,
    "libraries": p03_libraries,
}
USAGE = f"usage: run.py [{'|'.join(PROBES)}|all] ..."


def main(argv: list[str]) -> int:
    names = argv or ["all"]
    if "all" in names:
        names = list(PROBES)
    unknown = [name for name in names if name not in PROBES]
    if unknown:
        print(f"unknown probe(s): {', '.join(unknown)}\n{USAGE}", file=sys.stderr)
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
