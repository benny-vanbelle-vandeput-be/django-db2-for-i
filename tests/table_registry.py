"""The list of objects test runs create on IBM i, read by bin/ibmi-cleanup.

Phase 4 decision 16: ``bin/ibmi-cleanup`` drops only objects on this list.
``install()`` (called by the IBM i test settings) adds an execute wrapper to
every connection of this backend; before a statement runs, a ``CREATE TABLE``,
``CREATE VIEW`` or ``CREATE ALIAS`` appends its object to the list and the line
is flushed to disk, so a crash during the create still leaves it on the list.

The list is ``DB2I_TABLE_LIST``, set by ``scripts/pub400.sh`` to a file in the
state directory outside every checkout (next to the PUB400 lock), so it does
not depend on the worktree a run came from. Without it nothing is recorded,
and ``bin/ibmi-cleanup`` then reports such tables instead of dropping them.

One line per object: ``<kind>\\t<library>\\t<name>\\t<UTC time>``. The list
holds names, never data or connection details.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import os
import re
from pathlib import Path

ENV = "DB2I_TABLE_LIST"
VENDOR = "db2_for_i"
_IDENT = r'(?:"(?:[^"]|"")+"|[A-Za-z_$#@][\w$#@]*)'
CREATED = re.compile(
    rf"^\s*CREATE\s+(?:OR\s+REPLACE\s+)?(?P<kind>TABLE|VIEW|ALIAS)\s+"
    rf"(?:(?P<library>{_IDENT})\s*\.\s*)?(?P<name>{_IDENT})",
    re.IGNORECASE,
)


@dataclasses.dataclass(frozen=True)
class Entry:
    kind: str  # TABLE, VIEW or ALIAS
    library: str
    name: str
    created: str = ""

    def line(self) -> str:
        return f"{self.kind}\t{self.library}\t{self.name}\t{self.created}\n"


def _identifier(text: str) -> str:
    """The catalog name: a quoted identifier as written, an ordinary one uppercased."""
    if text.startswith('"'):
        return text[1:-1].replace('""', '"')
    return text.upper()


def parse(sql: str, default_library: str) -> Entry | None:
    match = CREATED.match(sql)
    if not match:
        return None
    library = _identifier(match["library"]) if match["library"] else default_library.upper()
    return Entry(match["kind"].upper(), library, _identifier(match["name"]))


def record(path: Path, entry: Entry) -> None:
    stamped = dataclasses.replace(
        entry, created=dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(stamped.line())
        handle.flush()
        os.fsync(handle.fileno())


def read(path: Path) -> list[Entry]:
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) == 4:
            entries.append(Entry(*parts))
    return entries


def write(path: Path, entries: list[Entry]) -> None:
    """Replace the list (atomically): bin/ibmi-cleanup prunes objects that are gone."""
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text("".join(entry.line() for entry in entries), encoding="utf-8")
    temporary.replace(path)


def list_path() -> Path | None:
    value = os.environ.get(ENV)
    return Path(value) if value else None


def wrapper(execute, sql, params, many, context):
    path = list_path()
    if path is not None and isinstance(sql, str):
        connection = context["connection"]
        entry = parse(sql, connection.settings_dict["NAME"] or "")
        if entry is not None:
            record(path, entry)
    return execute(sql, params, many, context)


def _on_connection_created(sender, connection, **kwargs) -> None:
    if connection.vendor == VENDOR and wrapper not in connection.execute_wrappers:
        connection.execute_wrappers.append(wrapper)


def install() -> None:
    """Record the objects of every connection of this backend (IBM i test settings)."""
    from django.db.backends.signals import connection_created

    connection_created.connect(
        _on_connection_created, weak=False, dispatch_uid="db2i-table-registry"
    )
