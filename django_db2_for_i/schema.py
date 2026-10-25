"""DatabaseSchemaEditor: DDL generation for models and migrations.

Implemented in phase 1 (CREATE/DROP TABLE); completed in phase 4.

- Foreign keys are created without an ON DELETE clause: Db2's default
  NO ACTION (checked at the end of the statement), never RESTRICT, so a
  self-referencing table can be emptied with one DELETE (docs/DECISIONS.md).
- Defaults are written as literals (``requires_literal_defaults``): DDL is
  not parameterized. A column DEFAULT on Db2 for i accepts only a bare
  constant or a special register: no CAST, no parentheses, no expression
  (probe ``probe_defaults``, docs/IBMI_NOTES.md). Both ``default`` (a Python
  default written while a migration adds a column) and ``db_default`` go
  through ``prepare_default()``, which has an explicit rule per type.
"""

import datetime
import math
import re
from decimal import Decimal

from django.db import DatabaseError, IntegrityError, NotSupportedError, OperationalError, models
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

from . import inquiry


def string_literal(value: str) -> str:
    """``'abc'`` for printable ASCII without quotes, else ``UX'<UTF-16 hex>'``.

    In a column DEFAULT, Db2 for i stores an escaped quote wrongly ('O''Brien'
    becomes O''Brien in NVARCHAR, a garbled value in CHAR/VARCHAR), N'...'
    truncates CHAR values. The UTF-16 hex constant is stored correctly in
    every string column type (probe ``probe_defaults``, docs/IBMI_NOTES.md),
    whatever the statement encoding; non-ASCII text uses it too, so the DDL
    stays ASCII.
    """
    if all(" " <= char <= "~" and char != "'" for char in value):
        return f"'{value}'"
    return f"UX'{value.encode('utf-16-be').hex().upper()}'"


def default_literal(value) -> str:
    """The SQL constant for a column DEFAULT; NotSupportedError without a rule.

    ``None`` is not handled here: a NULL default is no default (see
    DatabaseSchemaEditor.prepare_default).
    """
    # bool before int: bool is a subclass of int.
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise NotSupportedError(f"Db2 for i has no DEFAULT constant for {value!r}.")
        return format(value, "f")
    if isinstance(value, float):
        if not math.isfinite(value):
            raise NotSupportedError(f"Db2 for i has no DEFAULT constant for {value!r}.")
        # An E in the constant makes it a floating-point constant.
        return repr(value).upper() if "e" in repr(value) else f"{value!r}E0"
    if isinstance(value, str):
        return string_literal(value)
    # datetime before date: datetime is a subclass of date.
    if isinstance(value, datetime.datetime):
        if value.tzinfo is not None:
            raise NotSupportedError(
                "A time zone aware datetime cannot be a column DEFAULT: Db2 for i "
                "TIMESTAMP has no time zone."
            )
        return f"'{value.isoformat(sep=' ')}'"
    if isinstance(value, datetime.date):
        return f"'{value.isoformat()}'"
    if isinstance(value, datetime.time):
        if value.tzinfo is not None:
            raise NotSupportedError(
                "A time zone aware time cannot be a column DEFAULT: Db2 for i TIME has "
                "no time zone."
            )
        return f"'{value.isoformat()}'"
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"BX'{bytes(value).hex().upper()}'"
    raise NotSupportedError(
        f"No DEFAULT literal rule for {type(value).__name__} values ({value!r})."
    )


# Which base types ALTER COLUMN ... SET DATA TYPE converts in place (probe
# qtemp_type_changes, docs/IBMI_NOTES.md): within the numeric types and within
# the character types (narrowing or to DOUBLE is cancelled by CPA32B2), and BLOB
# to CHAR / VARCHAR (CPA32B2). Every other change between two of these base
# types is refused (SQL0190); a type not listed here is not checked.
NUMERIC_TYPES = frozenset({"SMALLINT", "INTEGER", "BIGINT", "DECIMAL", "DOUBLE"})
CHARACTER_TYPES = frozenset({"CHAR", "VARCHAR", "NVARCHAR", "NCLOB"})
KNOWN_TYPES = NUMERIC_TYPES | CHARACTER_TYPES | {"BLOB", "BOOLEAN", "DATE", "TIME", "TIMESTAMP"}


def base_type(sql_type: str) -> str:
    """``DECIMAL`` for ``DECIMAL(9, 2)``, ``INTEGER`` for an identity column."""
    match = re.match(r"\s*([A-Za-z]+)", sql_type or "")
    return match.group(1).upper() if match else ""


def converts_in_place(old_type: str, new_type: str) -> bool:
    old, new = base_type(old_type), base_type(new_type)
    if old == new or old not in KNOWN_TYPES or new not in KNOWN_TYPES:
        return True
    if (old in NUMERIC_TYPES and new in NUMERIC_TYPES) or (
        old in CHARACTER_TYPES and new in CHARACTER_TYPES
    ):
        return True
    return old == "BLOB" and new in {"CHAR", "VARCHAR"}


class DatabaseSchemaEditor(BaseDatabaseSchemaEditor):
    # The same DROP COLUMN on every supported Django version (Django 5.2 adds
    # CASCADE, 6.0+ does not): Db2 for i's default for dependent objects is not
    # known yet (probe 23, docs/IBMI_NOTES.md), so the SQL does not depend on it.
    sql_delete_column = "ALTER TABLE %(table)s DROP COLUMN %(column)s"
    # Db2 for i knows only SET DATA TYPE, not Django's TYPE (SQL0199, probe 24).
    # Widening keeps the data, also with an index or identity on the column;
    # narrowing is cancelled by CPA32B2 (qtemp_alter_column, docs/IBMI_NOTES.md).
    # The NULL and DEFAULT templates of the base class are Db2 for i syntax.
    sql_alter_column_type = "ALTER COLUMN %(column)s SET DATA TYPE %(type)s%(collation)s"
    # Db2 for i renames tables and indexes with RENAME, not ALTER ... RENAME TO
    # (SQL0199, probe 24). It has no statement to rename a column (see
    # _rename_field_sql()).
    sql_rename_table = "RENAME TABLE %(old_table)s TO %(new_table)s"
    # Held until the migration's transaction ends: no row can be added between
    # the check for rows and the ADD COLUMN of a NOT NULL column (add_field()).
    sql_lock_table = "LOCK TABLE %(table)s IN EXCLUSIVE MODE"
    sql_rename_index = "RENAME INDEX %(old_name)s TO %(new_name)s"
    # A column that becomes an identity numbers from 1, below the keys it
    # already holds; RESTART WITH takes only a constant, so a dynamic compound
    # statement reads MAX() itself (also for collected SQL, qtemp_renames).
    sql_restart_identity = (
        "BEGIN DECLARE NEXT_ID BIGINT; "
        "SET NEXT_ID = (SELECT COALESCE(MAX(%(column)s), 0) + 1 FROM %(table)s); "
        "EXECUTE IMMEDIATE 'ALTER TABLE %(table_text)s ALTER COLUMN %(column_text)s "
        "RESTART WITH ' CONCAT VARCHAR(NEXT_ID); END"
    )

    def __exit__(self, exc_type, exc_value, traceback):
        """Roll the migration's transaction back when a deferred statement fails.

        Django runs the deferred SQL (indexes, foreign keys) before it leaves
        the atomic block, so an error there skips ``atomic.__exit__``: with
        can_rollback_ddl the transaction stays open and the connection stays
        in an atomic block (Django's test teardown then closes it, and every
        later statement fails with "Attempt to use a closed connection").
        """
        if exc_type is None and self.atomic_migration:
            try:
                for sql in self.deferred_sql:
                    self.execute(sql, None)
            except BaseException as error:
                self.atomic.__exit__(type(error), error, error.__traceback__)
                raise
            self.deferred_sql = []
        return super().__exit__(exc_type, exc_value, traceback)

    def execute(self, sql, params=()):
        """Explain an ALTER TABLE that Db2 for i cancelled (CPA32B2, see inquiry.py)."""
        try:
            return super().execute(sql, params)
        except DatabaseError as exc:
            if self._cancelled_by_inquiry(str(sql), exc):
                active = self.connection._inquiry_reply_active
                raise OperationalError(inquiry.cancelled_ddl_message(active)) from exc
            raise

    def _cancelled_by_inquiry(self, sql: str, exc: DatabaseError) -> bool:
        """HY008 on ALTER TABLE, with CPA32B2/CPD32CE in the job log."""
        sqlstate = getattr(exc.__cause__, "sqlstate", "")
        if not inquiry.is_alter_table(sql) or sqlstate != inquiry.CANCELLED_SQLSTATE:
            return False
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(inquiry.JOB_LOG_SQL)
                messages = {str(row[0]).strip() for row in cursor.fetchall()}
        except DatabaseError:
            return False
        return bool(messages & set(inquiry.CANCEL_MESSAGES))

    def add_field(self, model, field):
        """A NOT NULL column without any default: Db2 for i needs a DEFAULT with
        NOT NULL (SQL0109, probe add_column_default), so the column gets a bare
        DEFAULT (the type's system default), which is dropped right after.

        Existing rows would silently get that system default, so a table with
        rows is refused, as PostgreSQL refuses it; in a transaction the table is
        locked first, so no row can arrive in between. Collected SQL
        (sqlmigrate) has no database to ask: it shows the DEFAULT form.
        """
        if not self._needs_temporary_default(field):
            return super().add_field(model, field)
        table = self.quote_name(model._meta.db_table)
        if not self.collect_sql:
            if self.connection.in_atomic_block:
                self.execute(self.sql_lock_table % {"table": table})
            with self.connection.cursor() as cursor:
                cursor.execute(f"SELECT 1 FROM {table} FETCH FIRST 1 ROW ONLY")
                has_rows = cursor.fetchone() is not None
            if has_rows:
                raise IntegrityError(
                    f"Cannot add NOT NULL column {self.quote_name(field.column)} without a "
                    f"default to table {table}: the table has rows. Give the field a default "
                    "or db_default, or add it with null=True first and fill it."
                )
        self._bare_default_field = field
        try:
            super().add_field(model, field)
        finally:
            self._bare_default_field = None
        changes, params = self._alter_column_default_sql(model, None, field, drop=True)
        self.execute(self.sql_alter_column % {"table": table, "changes": changes}, params)

    _bare_default_field = None

    def _needs_temporary_default(self, field) -> bool:
        """A NOT NULL column for which Django writes no DEFAULT at all."""
        if field.column is None or field.many_to_many or field.null or field.generated:
            return False
        if "AS IDENTITY" in (field.db_parameters(connection=self.connection)["type"] or ""):
            return False
        return not field.has_db_default() and self.effective_default(field) is None

    def alter_field(self, model, old_field, new_field, strict=False):
        """Refuse a type change Db2 for i cannot make in place (SQL0190) before
        any statement runs: Django drops foreign keys, unique constraints and
        indexes of the column first, and without can_rollback_ddl a later
        error would leave them dropped."""
        old_type = old_field.db_parameters(connection=self.connection)["type"]
        new_type = new_field.db_parameters(connection=self.connection)["type"]
        if old_type and new_type and not converts_in_place(old_type, new_type):
            raise NotSupportedError(
                f"Db2 for i cannot change {model._meta.label}.{new_field.name} "
                f"({model._meta.db_table}.{new_field.column}) from {base_type(old_type)} to "
                f"{base_type(new_type)} in place (SQL0190). Add a new field with the new "
                "type, copy the data in a data migration, then remove the old field. See "
                '"Changing a column to an incompatible type" in docs/user/Known-Limitations.md.'
            )
        return super().alter_field(model, old_field, new_field, strict=strict)

    def _alter_column_type_sql(
        self, model, old_field, new_field, new_type, old_collation, new_collation
    ):
        """Identity changes need more than SET DATA TYPE (probe qtemp_renames).

        - From an AutoField to another field: SET DATA TYPE keeps the identity,
          so DROP IDENTITY first, then set the type.
        - To an AutoField from another field: SET DATA TYPE ... AS IDENTITY
          works, then the identity restarts after the largest key.
        Between AutoFields the base class's SET DATA TYPE ... AS IDENTITY is
        right (widening keeps the numbering; narrowing is cancelled by CPA32B2).
        """
        fragment, other_actions = super()._alter_column_type_sql(
            model, old_field, new_field, new_type, old_collation, new_collation
        )
        old_auto = isinstance(old_field, models.AutoField)
        new_auto = isinstance(new_field, models.AutoField)
        table = self.quote_name(model._meta.db_table)
        column = self.quote_name(new_field.column)
        if old_auto and not new_auto:
            set_type = self.sql_alter_column % {"table": table, "changes": fragment[0]}
            return (f"ALTER COLUMN {column} DROP IDENTITY", []), [
                (set_type, fragment[1]),
                *other_actions,
            ]
        if new_auto and not old_auto:
            restart = self.sql_restart_identity % {
                "table": table,
                "column": column,
                "table_text": table.replace("'", "''"),
                "column_text": column.replace("'", "''"),
            }
            return fragment, [*other_actions, (restart, [])]
        return fragment, other_actions

    def _rename_field_sql(self, table, old_field, new_field, new_type):
        """Db2 for i has no statement to rename a column (IBM i 7.5 and 7.6)."""
        raise NotSupportedError(
            f"Db2 for i cannot rename column {old_field.column!r} of table {table!r} to "
            f"{new_field.column!r}: IBM i has no statement for it (SQL0199). Keep the "
            f"column name with db_column={old_field.column!r} on the renamed field. See "
            '"Renaming a column" in docs/user/Known-Limitations.md.'
        )

    def quote_value(self, value) -> str:
        """An SQL literal for ``value`` (collected SQL, COMMENT ON).

        Strings are plain ``'...'`` constants with doubled quotes: statement
        text is UTF-8 (drivers/pyodbc.py), and COMMENT ON accepts only a plain
        string constant (``UX'...'`` fails with SQL0104). Column DEFAULTs use
        default_literal() instead, see string_literal().
        """
        if value is None:
            return "NULL"
        if isinstance(value, str):
            return "'" + value.replace("'", "''") + "'"
        try:
            return default_literal(value)
        except NotSupportedError:
            raise ValueError(
                f"Cannot quote parameter value {value!r} of type {type(value)}"
            ) from None

    def prepare_default(self, value) -> str:
        """The literal for a DEFAULT clause; ``None`` means no default.

        Django only asks for non-NULL Python defaults; ``db_default=None``
        is dropped from CREATE/ADD COLUMN in ``_iter_column_sql()`` and
        becomes ``SET DEFAULT NULL`` in ALTER COLUMN, which is the same.
        """
        literal = "NULL" if value is None else default_literal(value)
        # The literal ends up in SQL that is executed with (empty) params, so
        # "%" must be escaped for the %s -> ? conversion.
        return literal.replace("%", "%%")

    def db_default_sql(self, field):
        """``db_default`` as a bare constant, never compiled to CAST(? AS ...).

        Value expressions are prepared like the field's own values (e.g. a
        UUID becomes its 32-character hex string). Other expressions are not
        supported (``supports_expression_defaults = False``).
        """
        from django.db.models.expressions import Value

        db_default = field._db_default_expression
        if not isinstance(db_default, Value):
            raise NotSupportedError(
                f"{field.model._meta.label}.{field.name}: Db2 for i accepts only constants "
                f"as a column DEFAULT, not {db_default!r}."
            )
        value = db_default.value
        if value is not None:
            value = db_default.output_field.get_db_prep_save(value, self.connection)
        return self._column_default_sql(field) % self.prepare_default(value), []

    def _iter_column_sql(self, column_db_type, params, model, field, *args, **kwargs):
        for part in super()._iter_column_sql(column_db_type, params, model, field, *args, **kwargs):
            # db_default=None: no default, rather than DEFAULT NULL (which a
            # NOT NULL column would reject).
            if part == "DEFAULT NULL":
                continue
            # A NOT NULL column without a default (add_field()): the type's
            # system default, dropped right after the ADD COLUMN.
            if part == "NOT NULL" and field is self._bare_default_field:
                yield "DEFAULT"
            yield part
