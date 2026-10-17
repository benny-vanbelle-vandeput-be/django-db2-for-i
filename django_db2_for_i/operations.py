"""DatabaseOperations: SQL generation helpers (quoting, casts, dates, pagination).

Implemented in phase 1; extended in later phases. Behaviour notes are backed
by probes (docs/IBMI_NOTES.md, ``w03_operations``).

Identifiers: Db2 for i folds unquoted names to uppercase. ``quote_name()``
uppercases and quotes every name, so ``"basic_article"`` becomes
``"BASIC_ARTICLE"``, the same object as the unquoted name. Introspection
converts names back to lowercase (``identifier_converter``). Consequence:
mixed-case ``db_table`` / ``db_column`` names are not preserved.

Date/time values are passed to the driver as ``date`` / ``time`` /
``datetime`` objects, not strings. There is no time zone aware timestamp
type: with ``USE_TZ`` aware datetimes are stored as naive values in the
connection's time zone (UTC unless the database's ``TIME_ZONE`` is set) and
made aware again when read.
"""

import uuid
from collections import defaultdict
from collections.abc import Iterable

from django.conf import settings
from django.db import NotSupportedError
from django.db.backends.base.operations import BaseDatabaseOperations
from django.db.backends.utils import truncate_name
from django.utils import timezone


class DatabaseOperations(BaseDatabaseOperations):
    def max_name_length(self) -> int:
        return self.connection.capabilities.max_name_length

    def quote_name(self, name: str) -> str:
        if name.startswith('"') and name.endswith('"'):
            return name  # Already quoted.
        name = truncate_name(name, self.max_name_length()).upper()
        return '"{}"'.format(name.replace('"', '""'))

    # --- Inserts ------------------------------------------------------------------

    def last_insert_id(self, cursor, table_name: str, pk_name: str) -> int | None:
        """The identity value of the last INSERT on this connection.

        Only reliable directly after a single-row ``INSERT ... VALUES``:
        IDENTITY_VAL_LOCAL() returns the last row's value after a multi-row
        insert and the explicit value when the key was given. Returning
        columns (``FINAL TABLE``) replace this in phase 5.
        """
        cursor.execute("SELECT IDENTITY_VAL_LOCAL() FROM SYSIBM.SYSDUMMY1")
        value = cursor.fetchone()[0]
        # IDENTITY_VAL_LOCAL() is DECIMAL(31, 0).
        return None if value is None else int(value)

    # --- Pagination -----------------------------------------------------------------

    def no_limit_value(self) -> None:
        # An offset without a limit is "OFFSET n ROWS" without FETCH FIRST.
        return None

    def limit_offset_sql(self, low_mark: int | None, high_mark: int | None) -> str:
        """``OFFSET n ROWS`` and/or ``FETCH FIRST m ROWS ONLY``."""
        if not self.connection.capabilities.has_offset_fetch:
            raise NotSupportedError("Pagination needs OFFSET/FETCH FIRST (has_offset_fetch).")
        limit, offset = self._get_limit_offset_params(low_mark, high_mark)
        return " ".join(
            sql
            for sql in (
                f"OFFSET {offset} ROWS" if offset else None,
                f"FETCH FIRST {limit} ROWS ONLY" if limit else None,
            )
            if sql
        )

    # --- Date/time values -------------------------------------------------------------

    def adapt_datefield_value(self, value):
        return value

    def adapt_datetimefield_value(self, value):
        if value is None or hasattr(value, "resolve_expression"):
            return value
        if timezone.is_aware(value):
            if not settings.USE_TZ:
                raise ValueError(
                    "Db2 for i backend does not support timezone-aware datetimes when "
                    "USE_TZ is False."
                )
            value = timezone.make_naive(value, self.connection.timezone)
        return value

    def adapt_timefield_value(self, value):
        """A ``time`` without microseconds.

        Db2 for i ``TIME`` has no fractional seconds and drops them silently
        (docs/DECISIONS.md). Truncating here makes saving and lookups such as
        ``filter(t=value)`` consistent with what is stored.
        """
        if value is None or hasattr(value, "resolve_expression"):
            return value
        if timezone.is_aware(value):
            raise ValueError("Django does not support timezone-aware times.")
        return value.replace(microsecond=0)

    def get_db_converters(self, expression):
        converters = super().get_db_converters(expression)
        internal_type = expression.output_field.get_internal_type()
        if internal_type == "DateTimeField" and settings.USE_TZ:
            converters.append(self.convert_datetimefield_value)
        elif internal_type == "UUIDField":
            converters.append(self.convert_uuidfield_value)
        return converters

    def convert_datetimefield_value(self, value, expression, connection):
        if value is not None:
            value = timezone.make_aware(value, self.connection.timezone)
        return value

    def convert_uuidfield_value(self, value, expression, connection):
        if value is not None:
            value = uuid.UUID(value)
        return value

    # --- Identity reset ----------------------------------------------------------

    def sequence_reset_sql(self, style, model_list):
        """Restart each model's identity at ``MAX(pk) + 1`` (1 for an empty table).

        ``GENERATED BY DEFAULT`` identities do not advance past explicit key
        values (e.g. from fixtures), so the next generated key would collide.
        ``RESTART WITH`` needs a constant, so the maximum is queried first.
        """
        from django.db import models

        statements = []
        for model in model_list:
            for field in model._meta.local_fields:
                if isinstance(field, models.AutoField):
                    table, column = model._meta.db_table, field.column
                    statements.append(
                        "{} {} {} {} {}".format(
                            style.SQL_KEYWORD("ALTER TABLE"),
                            style.SQL_TABLE(self.quote_name(table)),
                            style.SQL_KEYWORD("ALTER COLUMN"),
                            style.SQL_FIELD(self.quote_name(column)),
                            style.SQL_KEYWORD(
                                f"RESTART WITH {self._next_identity_value(table, column)}"
                            ),
                        )
                    )
                    break  # Only one AutoField per model.
        return statements

    def _next_identity_value(self, table: str, column: str) -> int:
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"SELECT COALESCE(MAX({self.quote_name(column)}), 0) + 1 "
                f"FROM {self.quote_name(table)}"
            )
            return int(cursor.fetchone()[0])

    # --- Flush ----------------------------------------------------------------------

    def sql_flush(self, style, tables, *, reset_sequences=False, allow_cascade=False):
        """Empty ``tables``.

        ``TRUNCATE`` is refused for a table referenced by a foreign key
        (SQ20356, even when the child is empty), so those tables are emptied
        with ``DELETE`` after their children, and their identity is restarted
        with ``ALTER TABLE ... ALTER COLUMN ... RESTART WITH <start>``.
        Other tables use ``TRUNCATE TABLE ... [RESTART IDENTITY]``.
        """
        if not tables:
            return []
        names = {table.upper(): table for table in tables}
        references, identities = self._flush_metadata(list(names))

        def table_sql(name: str) -> str:
            return style.SQL_FIELD(self.quote_name(names[name]))

        parents = {parent for _, parent in references}
        statements = [
            "{} {}{}".format(
                style.SQL_KEYWORD("TRUNCATE TABLE"),
                table_sql(name),
                style.SQL_KEYWORD(" RESTART IDENTITY") if reset_sequences else "",
            )
            for name in names
            if name not in parents
        ]
        for name in _children_first(parents, references):
            statements.append(f"{style.SQL_KEYWORD('DELETE FROM')} {table_sql(name)}")
            if reset_sequences and name in identities:
                column, start = identities[name]
                statements.append(
                    "{} {} {} {} {}".format(
                        style.SQL_KEYWORD("ALTER TABLE"),
                        table_sql(name),
                        style.SQL_KEYWORD("ALTER COLUMN"),
                        style.SQL_FIELD(self.quote_name(column)),
                        style.SQL_KEYWORD(f"RESTART WITH {start}"),
                    )
                )
        return statements

    def _flush_metadata(
        self, tables: list[str]
    ) -> tuple[set[tuple[str, str]], dict[str, tuple[str, int]]]:
        """Foreign keys among ``tables`` and their identity columns.

        Returns ``({(child, parent), ...}, {table: (identity column, start)})``
        with uppercase names, for tables in the connection's current schema.
        """
        placeholders = ", ".join(["%s"] * len(tables))
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT C.TABLE_NAME, P.TABLE_NAME "
                "FROM QSYS2.SYSREFCST R "
                "JOIN QSYS2.SYSCST C ON C.CONSTRAINT_SCHEMA = R.CONSTRAINT_SCHEMA "
                "AND C.CONSTRAINT_NAME = R.CONSTRAINT_NAME "
                "JOIN QSYS2.SYSCST P ON P.CONSTRAINT_SCHEMA = R.UNIQUE_CONSTRAINT_SCHEMA "
                "AND P.CONSTRAINT_NAME = R.UNIQUE_CONSTRAINT_NAME "
                f"WHERE P.TABLE_SCHEMA = CURRENT SCHEMA AND P.TABLE_NAME IN ({placeholders})",
                tables,
            )
            references = {(child.rstrip(), parent.rstrip()) for child, parent in cursor.fetchall()}
            cursor.execute(
                "SELECT TABLE_NAME, COLUMN_NAME, IDENTITY_START FROM QSYS2.SYSCOLUMNS "
                "WHERE TABLE_SCHEMA = CURRENT SCHEMA AND IS_IDENTITY = 'YES' "
                f"AND TABLE_NAME IN ({placeholders})",
                tables,
            )
            identities = {
                table.rstrip(): (column.rstrip(), int(start))
                for table, column, start in cursor.fetchall()
            }
        return references, identities


def _children_first(tables: Iterable[str], references: set[tuple[str, str]]) -> list[str]:
    """Order ``tables`` so that a table comes before the tables it references.

    Self-references are ignored (one DELETE removes all rows). Cycles are
    broken in name order; such a DELETE may then fail on a constraint.
    """
    remaining = set(tables)
    children_of: dict[str, set[str]] = defaultdict(set)
    for child, parent in references:
        if child != parent and child in remaining and parent in remaining:
            children_of[parent].add(child)
    ordered: list[str] = []
    while remaining:
        # Ready: no child of this table is still waiting to be emptied.
        ready = sorted(t for t in remaining if not (children_of[t] & remaining))
        ready = ready or [min(remaining)]
        ordered.extend(ready)
        remaining.difference_update(ready)
    return ordered
