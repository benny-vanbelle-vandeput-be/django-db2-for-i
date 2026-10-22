"""Drop leftover test objects of crashed runs from our own test libraries.

    bin/ibmi-cleanup [--yes]       (scripts/pub400.sh ibmi_cleanup [--yes])

The standing approval of CLAUDE.md (2026-10-21, phase 4 decision 16) covers
exactly this, and nothing else:

- only the libraries of the IBM i test settings (``default``, and ``other``
  when configured): the two ``.env`` libraries;
- only a library that contains the ``DJDB2I_TEST_MARKER`` table; any other is
  refused, so a wrong ``.env`` can never touch a real library;
- only objects on the cleanup list (``DB2I_TABLE_LIST``, written by test runs
  before each ``CREATE``, tests/table_registry.py) that still exist, never one
  in the marker's snapshot, never the marker itself; indexes and views go with
  their tables (the backend's own drop, creation.py);
- without ``--yes`` it only lists. Objects that are not on the list are
  reported, never dropped: dropping them needs the maintainer's approval.

What was dropped goes to ``test-results/cleanup/<UTC time>.txt``; list entries
of objects that no longer exist are pruned. One connection per library, under
the PUB400 lock (scripts/pub400.sh). No connection details are printed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests import table_registry  # noqa: E402

RESULTS = ROOT / "test-results" / "cleanup"


def plan(entries, library, inventory, snapshot, marker_table):
    """``(drop, unlisted)`` for one library: what may go, and what is only reported."""
    listed = {e.name for e in entries if e.library == library}
    leftovers = set(inventory) - set(snapshot) - {marker_table}
    return sorted(leftovers & listed), sorted(leftovers - listed)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--yes", action="store_true", help="drop (otherwise only list)")
    args = parser.parse_args(argv)
    path = table_registry.list_path()
    if path is None:
        print(f"refused: {table_registry.ENV} is not set; run through scripts/pub400.sh")
        return 2
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.django_settings.settings_pub400")
    import django

    django.setup()
    from django.db import connections

    from django_db2_for_i.creation import MARKER_TABLE

    entries = table_registry.read(path)
    dropped, refused, remaining, visited = [], False, set(), set()
    for alias in connections:
        connection = connections[alias]
        library = (connection.settings_dict.get("TEST", {}).get("NAME") or "").upper()
        if connection.vendor != "db2_for_i" or not library:
            continue
        creation = connection.creation
        visited.add(library)
        with connection.cursor() as cursor:
            inventory = creation._inventory(cursor, library)
            if MARKER_TABLE not in inventory:
                listed = sorted({e.name for e in entries if e.library == library} & set(inventory))
                if listed:
                    print(
                        f"{library}: no {MARKER_TABLE} table: refused, nothing dropped "
                        f"(listed objects present: {', '.join(listed)})"
                    )
                    refused = True
                else:
                    print(f"{library}: no {MARKER_TABLE} table and no listed objects: clean")
                remaining |= {(library, name) for name in inventory}
                continue
            snapshot = creation._read_marker(cursor, library).snapshot
            drop, unlisted = plan(entries, library, inventory, snapshot, MARKER_TABLE)
            print(
                f"{library}: {len(drop)} leftover object(s) on the list: {', '.join(drop) or '-'}"
            )
            if unlisted:
                print(
                    f"{library}: not on the list, not dropped (needs approval): "
                    f"{', '.join(unlisted)}"
                )
            if args.yes and drop:
                creation._drop(cursor, library, drop, inventory)
                dropped += [f"{inventory[name]}\t{library}\t{name}" for name in drop]
                inventory = creation._inventory(cursor, library)
            remaining |= {(library, name) for name in inventory}
        connection.close()
    if dropped:
        RESULTS.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
        (RESULTS / f"{stamp}.txt").write_text("\n".join(dropped) + "\n")
        print(f"dropped {len(dropped)} object(s); written to test-results/cleanup/{stamp}.txt")
    elif not args.yes:
        print("nothing dropped: without --yes bin/ibmi-cleanup only lists")
    # Only the libraries checked here: entries of others stay on the list.
    kept = [e for e in entries if e.library not in visited or (e.library, e.name) in remaining]
    if len(kept) != len(entries):
        table_registry.write(path, kept)
        print(f"pruned {len(entries) - len(kept)} list entr(ies) of objects that no longer exist")
    return 1 if refused else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
