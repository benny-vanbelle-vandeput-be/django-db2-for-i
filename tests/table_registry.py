"""The list of objects test runs create on IBM i, read by bin/ibmi-cleanup.

Phase 4 decision 16: ``bin/ibmi-cleanup`` drops only objects on this list.
``install()`` (called by the IBM i test settings) adds an execute wrapper to
every connection of this backend; before a statement runs, a ``CREATE TABLE``,
``CREATE VIEW`` or ``CREATE ALIAS`` appends its object to the list and the line
is flushed to disk, so a crash during the create still leaves it on the list.

A ``RENAME TABLE`` of a table on the list updates that entry, never adding
one: before the statement runs it holds the new name and, as ``renamed_from``,
every name the table had since the last commit, so a crash during the rename
leaves them all and ``bin/ibmi-cleanup`` drops whichever exists. The pending
names are cleared once the rename is committed: in a transaction
(``atomic()``, with can_rollback_ddl) only after it commits (``on_commit``;
Django drops the callbacks of a savepoint that is rolled back, and after a
rollback the entry keeps every name); in autocommit (``atomic = False``)
after the statement succeeds. If the statement fails, the entry is set back
as it was (CLAUDE.md, standing approval of ``bin/ibmi-cleanup``). A table
that is not on the list is never added by a rename.

The list is ``DB2I_TABLE_LIST``, set by ``scripts/pub400.sh`` to a file in the
state directory outside every checkout (next to the PUB400 lock), so it does
not depend on the worktree a run came from. Without it nothing is recorded,
and ``bin/ibmi-cleanup`` then reports such tables instead of dropping them.

One line per object: ``<kind>\\t<library>\\t<name>\\t<UTC time>``, plus
``\\t<old name>`` per pending name while a rename is not committed. The list
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
    # The names the table had since the last commit, while a RENAME TABLE is
    # not committed.
    renamed_from: tuple[str, ...] = ()

    def line(self) -> str:
        pending = "".join(f"\t{name}" for name in self.renamed_from)
        return f"{self.kind}\t{self.library}\t{self.name}\t{self.created}{pending}\n"

    @property
    def names(self) -> set[str]:
        """The names this object may have now: all of them while a rename is pending."""
        return {self.name, *self.renamed_from}


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


def _update(path: Path, library: str, name: str, change, *, pending: bool = True) -> Entry | None:
    """Replace the TABLE entry of ``library.name`` with ``change(entry)`` (the
    newest, if a name was created more than once: the table that exists now).
    With ``pending`` a pending name matches too. Returns the entry as it was,
    or None (and no change) when it is not on the list. The entry keeps its
    creation time."""
    entries = read(path)
    for index in reversed(range(len(entries))):
        entry = entries[index]
        names = entry.names if pending else {entry.name}
        if (entry.kind, entry.library) == ("TABLE", library) and name in names:
            entries[index] = change(entry)
            write(path, entries)
            return entry
    return None


def rename_pending(path: Path, library: str, old: str, new: str) -> Entry | None:
    """Before a RENAME TABLE: the entry holds ``new`` and keeps ``old`` (and
    every name not committed yet) as renamed_from. Returns the entry as it was."""

    def change(entry: Entry) -> Entry:
        names = dict.fromkeys((*entry.renamed_from, entry.name, old))
        names.pop(new, None)
        return dataclasses.replace(entry, name=new, renamed_from=tuple(names))

    return _update(path, library, old, change)


def rename_committed(path: Path, library: str, new: str) -> None:
    """The RENAME TABLE is committed: only the new name, if the entry still
    holds it (a later rename in a rolled-back savepoint leaves every name)."""
    _update(path, library, new, lambda e: dataclasses.replace(e, renamed_from=()), pending=False)


def rename_failed(path: Path, library: str, new: str, before: Entry) -> None:
    """The RENAME TABLE failed: the entry as it was before."""
    _update(path, library, new, lambda e: before, pending=False)


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
        if len(parts) >= 4:
            entries.append(Entry(*parts[:4], renamed_from=tuple(parts[4:])))
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
        before = rename_pending(path, *renamed) if renamed is not None else None
        if before is not None:
            library, _old, new = renamed
            try:
                result = execute(sql, params, many, context)
            except Exception:
                rename_failed(path, library, new, before)
                raise
            if connection.in_atomic_block:
                connection.on_commit(lambda: rename_committed(path, library, new))
            elif connection.get_autocommit():
                rename_committed(path, library, new)
            # In manual transaction management the names stay pending.
            return result
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
