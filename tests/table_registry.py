"""The list of objects test runs create on IBM i, read by bin/ibmi-cleanup.

Phase 4 decision 16: ``bin/ibmi-cleanup`` drops only objects on this list.
``install()`` (called by the IBM i test settings) adds an execute wrapper to
every connection of this backend; before a statement runs, a ``CREATE TABLE``,
``CREATE VIEW`` or ``CREATE ALIAS`` appends its object to the list and the line
is flushed to disk, so a crash during the create still leaves it on the list.

A ``RENAME TABLE`` of a table on the list updates that entry to the new name,
also before the statement runs (and back if the statement fails), so the list
always names the table as it is; a table that is not on the list is never
added by a rename (CLAUDE.md, standing approval of ``bin/ibmi-cleanup``).

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
RENAMED = re.compile(
    rf"^\s*RENAME\s+TABLE\s+(?:(?P<library>{_IDENT})\s*\.\s*)?(?P<old>{_IDENT})"
    rf"\s+TO\s+(?P<new>{_IDENT})",
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


def parse_rename(sql: str, default_library: str) -> tuple[str, str, str] | None:
    """``(library, old name, new name)`` of a ``RENAME TABLE``; the new name is
    unqualified on Db2 for i (it stays in the library)."""
    match = RENAMED.match(sql)
    if not match:
        return None
    library = _identifier(match["library"]) if match["library"] else default_library.upper()
    return library, _identifier(match["old"]), _identifier(match["new"])


def rename(path: Path, library: str, old: str, new: str) -> bool:
    """Rename the TABLE entry ``library.old`` to ``new``; False (and no change)
    when it is not on the list. The entry keeps its creation time."""
    entries = read(path)
    for index, entry in enumerate(entries):
        if (entry.kind, entry.library, entry.name) == ("TABLE", library, old):
            entries[index] = dataclasses.replace(entry, name=new)
            write(path, entries)
            return True
    return False


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
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write("".join(entry.line() for entry in entries))
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def list_path() -> Path | None:
    value = os.environ.get(ENV)
    return Path(value) if value else None


def wrapper(execute, sql, params, many, context):
    path = list_path()
    if path is not None and isinstance(sql, str):
        connection = context["connection"]
        library = connection.settings_dict["NAME"] or ""
        entry = parse(sql, library)
        if entry is not None:
            record(path, entry)
        renamed = parse_rename(sql, library)
        if renamed is not None and rename(path, *renamed):
            library, old, new = renamed
            try:
                return execute(sql, params, many, context)
            except Exception:
                rename(path, library, new, old)
                raise
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
