"""Renaming a column by copying it (``OPTIONS["column_rename"] = "copy"``, #258 F).

Db2 for i has no statement to rename a column (SQL0199, IBM i 7.5 and 7.6). With the
option, the schema editor adds a column with the new name in the old one's place
(``ADD COLUMN ... BEFORE``), copies the values, rebuilds what was on the old column
and drops it. The order comes from probes ``qtemp_column_copy`` and
``lib_column_copy`` (docs/IBMI_NOTES.md):

1. Checks, before any statement: what Django cannot rebuild refuses the rename
   (triggers, column masks and row permissions on the column, column authorities, a
   field procedure, a hidden or generated column, an identity GENERATED ALWAYS).
2. Every foreign key *to* the table is dropped (and added again at the end): while one
   exists, the copy is SQL0910. Then the primary key, unique and check constraints,
   foreign keys and indexes on the column; an identity loses it on the old column.
3. ``ADD COLUMN <new> [FOR COLUMN <system name>] <type> BEFORE <old>``.
4. ``UPDATE ... SET <new> = <old> WITH NC``: under commitment control a changed row
   makes every later ALTER TABLE of the table SQL0910; the copied values are only in
   the new column, which a rollback removes.
5. NOT NULL and the default from the catalog, the identity's restart, the constraints
   and indexes again (same names, column names replaced in check clauses and index
   conditions), the column heading, text and comment.
6. At the end of the schema editor (deferred SQL): the foreign keys to the table again,
   then ``DROP COLUMN <old> RESTRICT``. RESTRICT refuses an index or view that still
   uses the old column (SQL0196), so nothing Django did not rebuild is dropped quietly.

Everything runs in the migration's transaction: a failure rolls it all back.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from django.db import DatabaseError, NotSupportedError
from django.db.backends.ddl_references import Statement, Table

from . import fields

OPTION = "column_rename"
COPY = "copy"
REFUSE = "refuse"
VALUES = (COPY, REFUSE)

COLUMN_SQL = (
    "SELECT IS_NULLABLE, COLUMN_DEFAULT, IS_IDENTITY, IDENTITY_GENERATION, HIDDEN, "
    "HAS_FLDPROC, COLUMN_EXPRESSION, COLUMN_HEADING, COLUMN_TEXT, LONG_COMMENT "
    "FROM QSYS2.SYSCOLUMNS WHERE TABLE_SCHEMA = CURRENT SCHEMA AND TABLE_NAME = %s "
    "AND COLUMN_NAME = %s"
)
# What uses the column and cannot be rebuilt: the number of each.
BLOCKERS = (
    (
        "a trigger",
        "SELECT COUNT(*) FROM QSYS2.SYSTRIGCOL WHERE TABLE_SCHEMA = CURRENT SCHEMA "
        "AND TABLE_NAME = %s AND COLUMN_NAME = %s",
    ),
    (
        "column authorities (GRANT ... ON COLUMN)",
        "SELECT COUNT(*) FROM QSYS2.SYSCOLAUTH WHERE TABLE_SCHEMA = CURRENT SCHEMA "
        "AND TABLE_NAME = %s AND COLUMN_NAME = %s",
    ),
    (
        "a column mask",
        "SELECT COUNT(*) FROM QSYS2.SYSCONTROLS WHERE TABLE_SCHEMA = CURRENT SCHEMA "
        "AND TABLE_NAME = %s AND COLUMN_NAME = %s",
    ),
)
PERMISSIONS_SQL = (
    "SELECT RULETEXT FROM QSYS2.SYSCONTROLS WHERE TABLE_SCHEMA = CURRENT SCHEMA "
    "AND TABLE_NAME = %s AND CONTROL_TYPE = 'R'"
)
# Foreign keys of other tables (or this one) that reference this table.
INCOMING_SQL = (
    "SELECT C.TABLE_SCHEMA, C.TABLE_NAME, R.CONSTRAINT_SCHEMA, R.CONSTRAINT_NAME, "
    "R.UPDATE_RULE, R.DELETE_RULE, R.UNIQUE_CONSTRAINT_SCHEMA, R.UNIQUE_CONSTRAINT_NAME "
    "FROM QSYS2.SYSREFCST R JOIN QSYS2.SYSCST C "
    "ON C.CONSTRAINT_SCHEMA = R.CONSTRAINT_SCHEMA AND C.CONSTRAINT_NAME = R.CONSTRAINT_NAME "
    "JOIN QSYS2.SYSCST P "
    "ON P.CONSTRAINT_SCHEMA = R.UNIQUE_CONSTRAINT_SCHEMA "
    "AND P.CONSTRAINT_NAME = R.UNIQUE_CONSTRAINT_NAME "
    "WHERE P.TABLE_SCHEMA = CURRENT SCHEMA AND P.TABLE_NAME = %s "
    "ORDER BY R.CONSTRAINT_SCHEMA, R.CONSTRAINT_NAME"
)
KEY_COLUMNS_SQL = (
    "SELECT COLUMN_NAME FROM QSYS2.SYSKEYCST WHERE CONSTRAINT_SCHEMA = %s "
    "AND CONSTRAINT_NAME = %s ORDER BY ORDINAL_POSITION"
)
# The constraints of the table with their kind and, for a check, its clause.
CONSTRAINTS_SQL = (
    "SELECT C.CONSTRAINT_SCHEMA, C.CONSTRAINT_NAME, C.CONSTRAINT_TYPE, H.CHECK_CLAUSE, "
    "R.UPDATE_RULE, R.DELETE_RULE, R.UNIQUE_CONSTRAINT_SCHEMA, R.UNIQUE_CONSTRAINT_NAME "
    "FROM QSYS2.SYSCST C "
    "LEFT JOIN QSYS2.SYSCHKCST H "
    "ON H.CONSTRAINT_SCHEMA = C.CONSTRAINT_SCHEMA AND H.CONSTRAINT_NAME = C.CONSTRAINT_NAME "
    "LEFT JOIN QSYS2.SYSREFCST R "
    "ON R.CONSTRAINT_SCHEMA = C.CONSTRAINT_SCHEMA AND R.CONSTRAINT_NAME = C.CONSTRAINT_NAME "
    "WHERE C.TABLE_SCHEMA = CURRENT SCHEMA AND C.TABLE_NAME = %s "
    "ORDER BY C.CONSTRAINT_NAME"
)
CHECK_COLUMNS_SQL = (
    "SELECT COLUMN_NAME FROM QSYS2.SYSCSTCOL WHERE CONSTRAINT_SCHEMA = %s AND CONSTRAINT_NAME = %s"
)
REFERENCED_TABLE_SQL = (
    "SELECT TABLE_SCHEMA, TABLE_NAME FROM QSYS2.SYSCST WHERE CONSTRAINT_SCHEMA = %s "
    "AND CONSTRAINT_NAME = %s"
)
INDEXES_SQL = (
    "SELECT INDEX_SCHEMA, INDEX_NAME, IS_UNIQUE, SYSTEM_INDEX_NAME, SEARCH_CONDITION "
    "FROM QSYS2.SYSINDEXES WHERE TABLE_SCHEMA = CURRENT SCHEMA AND TABLE_NAME = %s "
    "ORDER BY INDEX_NAME"
)
INDEX_KEYS_SQL = (
    "SELECT COLUMN_NAME, ORDERING, COLUMN_IS_EXPRESSION FROM QSYS2.SYSKEYS "
    "WHERE INDEX_SCHEMA = %s AND INDEX_NAME = %s ORDER BY ORDINAL_POSITION"
)
# QSYS2.SYSINDEXES.IS_UNIQUE: duplicates allowed, unique, unique where not null.
INDEX_KINDS = {"D": "INDEX", "U": "UNIQUE INDEX", "V": "UNIQUE WHERE NOT NULL INDEX"}

_LITERAL = re.compile(r"('(?:[^']|'')*')")


def rename_in(text: str, old: str, new: str) -> str:
    """``text`` (a check clause or index condition from the catalog) with the column
    ``old`` renamed to ``new``, quoted or not; string constants stay as they are."""
    bare = re.compile(rf'(?<![\w$#@"]){re.escape(old)}(?![\w$#@"])', re.IGNORECASE)
    quoted = f'"{old}"'
    parts = _LITERAL.split(text)
    for index in range(0, len(parts), 2):  # the parts outside string constants
        parts[index] = bare.sub(f'"{new}"', parts[index].replace(quoted, f'"{new}"'))
    return "".join(parts)


def _mentions(text: str | None, column: str) -> bool:
    return bool(text) and rename_in(text, column, "\0") != text


@dataclass
class Plan:
    """The statements of one column copy, in their order."""

    before: list[str] = field(default_factory=list)  # drops, before the copy
    add: str = ""
    copy: str = ""
    after: list[str] = field(default_factory=list)  # rebuild, right after the copy
    deferred: list[str] = field(default_factory=list)  # at the end of the editor


class DeferredFieldChange(Statement):
    """A deferred statement of a column copy, run with CPA32B2 suppressed (a field
    change). Its tables follow a later table rename of the same schema editor, as
    Django's own deferred statements do; its column names never follow a column
    rename (the old column is meant, also after Django renamed references to it)."""

    def __init__(self, template: str, quote_name, **tables: str):
        super().__init__(template, **{key: Table(name, quote_name) for key, name in tables.items()})

    def references_column(self, table, column):
        return False

    def rename_column_references(self, table, old_column, new_column):
        pass


class DropOldColumn(DeferredFieldChange):
    """The deferred DROP COLUMN ... RESTRICT of a copied column."""


class Skip(str):
    """A statement the schema editor does not run (the copy replaced it)."""


def _drop(editor, table_name: str, column: str) -> DropOldColumn:
    return DropOldColumn(
        f"ALTER TABLE %(table)s DROP COLUMN {editor.quote_name(column)} RESTRICT",
        editor.quote_name,
        table=table_name,
    )


def _catalog_name(table_name: str, cursor) -> tuple[str, str]:
    """(schema, table) of ``table_name`` as the catalog names them."""
    library, table = table_name.split('"."', 1) if '"."' in table_name else ("", table_name)
    if not library:
        cursor.execute("VALUES CURRENT SCHEMA")
        library = cursor.fetchone()[0]
    return library.strip().upper(), table.strip().upper()


def _clean(value) -> str:
    return "" if value is None else str(value).rstrip()


def _text_constant(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def plan(editor, table_name: str, old_field, new_field, old_type: str) -> Plan:
    """The statements that copy ``old_field``'s column of ``table_name`` to
    ``new_field.column``. ``table_name`` is the table as it is now: Django may have
    renamed it already (an m2m table that is repointed)."""
    q = editor.quote_name
    table = q(table_name)
    old = old_field.column.upper()
    new = new_field.column.upper()
    system = fields.system_name(new_field)
    for_column = f" FOR COLUMN {system}" if system and system != new else ""
    result = Plan()
    if editor.collect_sql:
        # sqlmigrate: no catalog to read. The constraints, indexes and foreign keys
        # are rebuilt from the catalog when the migration runs.
        result.before.append(
            "-- Db2 for i: the column is copied; constraints, indexes, labels and the "
            "foreign keys to the table are rebuilt from the catalog when it runs"
        )
        result.add = (
            f"ALTER TABLE {table} ADD COLUMN {q(new)}{for_column} {old_type} BEFORE {q(old)}"
        )
        result.copy = f"UPDATE {table} SET {q(new)} = {q(old)} WITH NC"
        if not old_field.null:
            result.after.append(f"ALTER TABLE {table} ALTER COLUMN {q(new)} SET NOT NULL")
        result.deferred.append(_drop(editor, table_name, old))
        return result

    from .introspection import _in_library  # introspection imports schema.py

    with editor.connection.cursor() as cursor:

        def rows(sql: str, extra: tuple = ()) -> list:
            query, params = _in_library(sql, table_name)
            cursor.execute(query, [*params, *extra])
            return cursor.fetchall()

        def fetch(sql: str, params: list) -> list:
            cursor.execute(sql, params)
            return cursor.fetchall()

        found = rows(COLUMN_SQL, (old,))
        if not found:
            raise NotSupportedError(f"Column {old} of table {table} was not found in the catalog.")
        (
            nullable,
            default,
            identity,
            generation,
            hidden,
            fldproc,
            expression,
            heading,
            text,
            comment,
        ) = found[0]
        problems = []
        if _clean(hidden) not in ("", "N"):
            problems.append("it is a hidden column")
        if _clean(fldproc) == "Y":
            problems.append("it has a field procedure (FIELDPROC)")
        if expression is not None:
            problems.append("it is a generated column")
        if _clean(identity) == "YES" and _clean(generation) == "ALWAYS":
            problems.append("it is an identity GENERATED ALWAYS")
        for what, sql in BLOCKERS:
            if rows(sql, (old,))[0][0]:
                problems.append(f"{what} uses it")
        if any(_mentions(rule, old) for (rule,) in rows(PERMISSIONS_SQL)):
            problems.append("a row permission uses it")
        if problems:
            raise NotSupportedError(
                f"Db2 for i cannot rename column {old} of table {table} by copying it: "
                f"{'; '.join(problems)}. Rebuild those yourself, or keep the column name "
                f'with db_column={old_field.column!r}. See "Renaming a column" in '
                "docs/user/Known-Limitations.md."
            )

        def keys(schema, name) -> list[str]:
            return [_clean(c) for (c,) in fetch(KEY_COLUMNS_SQL, [_clean(schema), _clean(name)])]

        def renamed(columns: list[str]) -> str:
            return ", ".join(q(new if c == old else c) for c in columns)

        # Every foreign key to the table: dropped now, added again at the end.
        for (
            child_schema,
            child,
            schema,
            name,
            update_rule,
            delete_rule,
            parent_schema,
            parent_key,
        ) in rows(INCOMING_SQL):
            child_table = f"{q(_clean(child_schema))}.{q(_clean(child))}"
            constraint = f"{q(_clean(schema))}.{q(_clean(name))}"
            columns = keys(schema, name)
            parent_columns = keys(parent_schema, parent_key)
            result.before.append(f"ALTER TABLE {child_table} DROP CONSTRAINT {constraint}")
            sql = (
                f"ALTER TABLE %(child)s ADD CONSTRAINT {constraint} FOREIGN KEY "
                f"({renamed(columns)}) REFERENCES %(table)s ({renamed(parent_columns)}) "
                f"ON DELETE {_clean(delete_rule)} ON UPDATE {_clean(update_rule)}"
            )
            child_name = f'{_clean(child_schema)}"."{_clean(child)}'
            if (_clean(child_schema), _clean(child)) == _catalog_name(table_name, cursor):
                child_name = table_name  # a foreign key of the table to itself
            result.deferred.append(DeferredFieldChange(sql, q, child=child_name, table=table_name))

        # The constraints on the column.
        for schema, name, kind, clause, update_rule, delete_rule, parent_schema, parent_key in rows(
            CONSTRAINTS_SQL
        ):
            kind = _clean(kind)
            constraint = f"{q(_clean(schema))}.{q(_clean(name))}"
            if kind == "CHECK":
                columns = [
                    _clean(c) for (c,) in fetch(CHECK_COLUMNS_SQL, [_clean(schema), _clean(name)])
                ]
                if old not in columns:
                    continue
                body = f"CHECK ({rename_in(_clean(clause), old, new)})"
            else:
                columns = keys(schema, name)
                if old not in columns:
                    continue
                if kind == "FOREIGN KEY":
                    if (_clean(schema), _clean(name)) in {
                        (_clean(r[2]), _clean(r[3])) for r in rows(INCOMING_SQL)
                    }:
                        continue  # a foreign key of the table to itself: handled above
                    target_schema, target = fetch(
                        REFERENCED_TABLE_SQL, [_clean(parent_schema), _clean(parent_key)]
                    )[0]
                    body = (
                        f"FOREIGN KEY ({renamed(columns)}) REFERENCES "
                        f"{q(_clean(target_schema))}.{q(_clean(target))} "
                        f"({renamed(keys(parent_schema, parent_key))}) "
                        f"ON DELETE {_clean(delete_rule)} ON UPDATE {_clean(update_rule)}"
                    )
                else:  # PRIMARY KEY, UNIQUE
                    body = f"{kind} ({renamed(columns)})"
            result.before.append(f"ALTER TABLE {table} DROP CONSTRAINT {constraint}")
            result.after.append(f"ALTER TABLE {table} ADD CONSTRAINT {constraint} {body}")

        # The indexes with the column as a key.
        for schema, name, unique, system_index, condition in rows(INDEXES_SQL):
            index_keys = fetch(INDEX_KEYS_SQL, [_clean(schema), _clean(name)])
            if not any(_clean(c) == old and _clean(e) != "Y" for c, _o, e in index_keys):
                continue  # an expression or condition on the column: RESTRICT refuses
            kind = INDEX_KINDS.get(_clean(unique))
            if kind is None or any(_clean(e) == "Y" for _c, _o, e in index_keys):
                raise NotSupportedError(
                    f"Db2 for i cannot rename column {old} of table {table} by copying it: "
                    f"index {_clean(name)} on it cannot be rebuilt (an expression key or "
                    "an index kind Django does not create). Drop it first."
                )
            index = f"{q(_clean(schema))}.{q(_clean(name))}"
            columns = ", ".join(
                f"{q(new if _clean(c) == old else _clean(c))} "
                f"{'DESC' if _clean(o) == 'D' else 'ASC'}"
                for c, o, _e in index_keys
            )
            system_clause = (
                f" FOR SYSTEM NAME {_clean(system_index)}"
                if len(_clean(name)) > 10 and _clean(system_index)
                else ""
            )
            where = f" WHERE {rename_in(_clean(condition), old, new)}" if _clean(condition) else ""
            result.before.append(f"DROP INDEX {index}")
            result.after.append(
                f"CREATE {kind} {index}{system_clause} ON {table} ({columns}){where}"
            )

    is_identity = _clean(identity) == "YES"
    if is_identity:
        result.before.append(f"ALTER TABLE {table} ALTER COLUMN {q(old)} DROP IDENTITY")
    if _clean(nullable) == "N":
        result.before.append(f"ALTER TABLE {table} ALTER COLUMN {q(old)} DROP NOT NULL")
    not_null = " NOT NULL" if is_identity else ""
    result.add = (
        f"ALTER TABLE {table} ADD COLUMN {q(new)}{for_column} {old_type}{not_null} BEFORE {q(old)}"
    )
    result.copy = f"UPDATE {table} SET {q(new)} = {q(old)} WITH NC"
    alterations = []
    if _clean(nullable) == "N" and not is_identity:
        alterations.append("SET NOT NULL")
    if default is not None and not is_identity:
        alterations.append(f"SET DEFAULT {_clean(default)}")
    if alterations:
        result.after.insert(0, f"ALTER TABLE {table} ALTER COLUMN {q(new)} {' '.join(alterations)}")
    if is_identity:
        result.after.insert(
            0,
            editor.sql_restart_identity
            % {
                "table": table,
                "column": q(new),
                "table_text": table.replace("'", "''"),
                "column_text": q(new).replace("'", "''"),
            },
        )
    if _clean(heading):
        result.after.append(
            f"LABEL ON COLUMN {table}.{q(new)} IS {_text_constant(_clean(heading))}"
        )
    if _clean(text):
        result.after.append(
            f"LABEL ON COLUMN {table}.{q(new)} TEXT IS {_text_constant(_clean(text))}"
        )
    if _clean(comment):
        result.after.append(
            f"COMMENT ON COLUMN {table}.{q(new)} IS {_text_constant(_clean(comment))}"
        )
    result.deferred.append(_drop(editor, table_name, old))
    return result


SQL0910 = -910
SQL0196 = -196


def sqlcode(exc: Exception) -> int | None:
    return getattr(exc.__cause__, "sqlcode", None)


def run(editor, table_name: str, old_field, new_field, old_type: str) -> None:
    """Copy the column now and defer what has to wait (see the module docstring)."""
    steps = plan(editor, table_name, old_field, new_field, old_type)
    for sql in steps.before:
        editor.execute(sql)
    editor.execute(steps.add)
    try:
        editor.execute(steps.copy)
    except DatabaseError as exc:
        if sqlcode(exc) != SQL0910:
            raise
        raise NotSupportedError(
            f"Db2 for i cannot copy column {old_field.column!r} of table "
            f"{table_name!r} in this migration: the table has a pending change "
            "(SQL0910) from an earlier operation on it. Put the field rename in a "
            "migration of its own."
        ) from exc
    for sql in steps.after:
        editor.execute(sql)
    editor.deferred_sql.extend(steps.deferred)


def explain_restrict(sql: str, exc: Exception) -> Exception | None:
    """A clear error for the deferred DROP COLUMN ... RESTRICT that Db2 for i refused."""
    if isinstance(sql, DropOldColumn) and sqlcode(exc) == SQL0196:
        return NotSupportedError(
            f"Db2 for i refused the last step of a column rename, {sql}: an index or view "
            "Django does not know about (for example on an expression of the column) "
            "still uses the old column (SQL0196). The migration was rolled back. Drop or "
            "change that object first."
        )
    return None
