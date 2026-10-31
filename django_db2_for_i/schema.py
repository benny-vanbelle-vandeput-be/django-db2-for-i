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
- Inquiry message CPA32B2 (DROP COLUMN, narrowing, SET NOT NULL) is
  suppressed for the job while a field is removed or altered, until the
  outermost schema editor exits (inquiry.py). A narrowing change that would
  truncate or round a value is refused first (narrowing_check()): with
  CPA32B2 out of the way Db2 for i would change the value silently.
"""

import contextlib
import datetime
import math
import re
from decimal import Decimal

from django.db import (
    DatabaseError,
    DataError,
    IntegrityError,
    NotSupportedError,
    OperationalError,
    models,
)
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

from . import inquiry
from .expressions import NVARCHAR_MAX


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


# Narrowing checks (narrowing_check()), in the units Db2 for i measures in
# (probe qaqqini_lifecycle): LENGTH of a graphic string (NCHAR, NVARCHAR,
# NCLOB) counts UTF-16 code units (an emoji is 2), of a single-byte string
# (CHAR, VARCHAR, CLOB) bytes in its CCSID (UTF-8 for CCSID 1208: an emoji
# is 4). A conversion to fewer decimals or to an integer truncates (DOUBLE
# 0.29 becomes DECIMAL 0.28), and an overflowing CAST gives NULL instead of
# an error, so the bounds are checked before the CAST.
GRAPHIC_TYPES = frozenset({"NCHAR", "NVARCHAR", "NCLOB", "GRAPHIC", "VARGRAPHIC", "DBCLOB"})
SINGLE_BYTE_TYPES = frozenset({"CHAR", "VARCHAR", "CLOB"})
FIXED_LENGTH_TYPES = frozenset({"CHAR", "NCHAR", "GRAPHIC"})
LOB_TYPES = frozenset({"CLOB", "NCLOB", "DBCLOB", "BLOB"})
# A long form of each type, for measuring a value converted to it: VARCHAR and
# NVARCHAR as probe string_limits casts them, the fixed-length types at their
# documented maximum.
MAX_LENGTHS = {
    "CHAR": 32766,
    "VARCHAR": 32000,
    "NCHAR": 16383,
    "NVARCHAR": NVARCHAR_MAX,
    "GRAPHIC": 16383,
    "VARGRAPHIC": NVARCHAR_MAX,
}
INTEGER_RANGES = {
    "SMALLINT": (-32768, 32767),
    "INTEGER": (-2147483648, 2147483647),
    "BIGINT": (-9223372036854775808, 9223372036854775807),
}
# Digits of the largest value: a DECIMAL needs that many integer digits.
INTEGER_DIGITS = {"SMALLINT": 5, "INTEGER": 10, "BIGINT": 19}
_LENGTH = re.compile(r"\(\s*(\d+)\s*\)")
_PRECISION = re.compile(r"\(\s*(\d+)\s*,\s*(\d+)\s*\)")
_CCSID = re.compile(r"\bCCSID\s+(\d+)", re.IGNORECASE)


def _length(sql_type: str) -> int | None:
    match = _LENGTH.search(sql_type)
    return int(match.group(1)) if match else None


def _precision(sql_type: str) -> tuple[int, int]:
    """``(9, 2)`` for ``DECIMAL(9, 2)``; Db2 for i's default for ``DECIMAL`` is (5, 0)."""
    match = _PRECISION.search(sql_type)
    if match:
        return int(match.group(1)), int(match.group(2))
    length = _length(sql_type)
    return (length, 0) if length is not None else (5, 0)


def _ccsid(sql_type: str) -> str | None:
    match = _CCSID.search(sql_type)
    return match.group(1) if match else None


def narrowing_check(column: str, old_type: str, new_type: str) -> tuple[str, str] | None:
    """A condition that is true for a value ALTER COLUMN ... SET DATA TYPE
    from ``old_type`` to ``new_type`` would truncate or round, and what it
    finds; None when no value can change (widening, or not checked).

    ``column`` is the quoted column name. Strings are measured as Db2 for i
    measures them (UTF-16 code units, or bytes in the column's CCSID);
    numbers fail on any value that would change: out of range, or with
    digits after the target's decimals. A change to DOUBLE is not checked
    (rounding to the nearest double, as on other databases).
    """
    old, new = base_type(old_type), base_type(new_type)
    if old_type == new_type:
        return None
    if old in CHARACTER_TYPES | GRAPHIC_TYPES | SINGLE_BYTE_TYPES and new in MAX_LENGTHS:
        return _string_check(column, old, new, old_type, new_type)
    if old in NUMERIC_TYPES and new in NUMERIC_TYPES:
        return _numeric_check(column, old, new, old_type, new_type)
    if old == "BLOB" and new in {"CHAR", "VARCHAR"} and _length(new_type) is not None:
        limit = _length(new_type)
        return f"LENGTH({column}) > {limit}", f"a value longer than {limit} bytes"
    return None


def _string_check(column, old, new, old_type, new_type):
    limit = _length(new_type)
    if limit is None:
        return None
    units = (
        "UTF-16 code units"
        if new in GRAPHIC_TYPES
        else "bytes (UTF-8)"
        if _ccsid(new_type) == "1208"
        else "bytes"
    )
    found = f"a value longer than {limit} {units}"
    same_units = (old in GRAPHIC_TYPES) == (new in GRAPHIC_TYPES) and _ccsid(old_type) == _ccsid(
        new_type
    )
    source_length = None if old in LOB_TYPES else _length(old_type)
    if same_units and source_length is not None and source_length <= limit:
        return None
    # A fixed-length value's trailing blanks are padding, not data.
    value = f"RTRIM({column})" if old in FIXED_LENGTH_TYPES else column
    if same_units:
        return f"LENGTH({value}) > {limit}", found
    # Measured in the new type's units: converted to its longest form first.
    widest = _LENGTH.sub(f"({MAX_LENGTHS[new]})", new_type, count=1)
    return (
        f"CASE WHEN LENGTH({value}) > {MAX_LENGTHS[new]} THEN 1 "
        f"WHEN LENGTH(CAST({value} AS {widest})) > {limit} THEN 1 ELSE 0 END = 1",
        found,
    )


def _numeric_check(column, old, new, old_type, new_type):
    if new in INTEGER_RANGES:
        low, high = INTEGER_RANGES[new]
        out_of_range = f"{column} < {low} OR {column} > {high}"
        if old in INTEGER_RANGES:
            if INTEGER_DIGITS[old] <= INTEGER_DIGITS[new]:
                return None
            return out_of_range, f"a value outside the {new} range"
        return (
            f"CASE WHEN {out_of_range} THEN 1 "
            f"WHEN {column} <> CAST({column} AS {new}) THEN 1 ELSE 0 END = 1",
            f"a value outside the {new} range or with decimals",
        )
    if new == "DECIMAL":
        precision, scale = _precision(new_type)
        integer_digits = precision - scale
        if old == "DECIMAL":
            old_precision, old_scale = _precision(old_type)
            if scale >= old_scale and integer_digits >= old_precision - old_scale:
                return None
        elif old in INTEGER_DIGITS and integer_digits >= INTEGER_DIGITS[old]:
            return None
        # 10 ** integer_digits as an exact constant (DECIMAL holds 63 digits).
        bound = "1" + "0" * integer_digits if integer_digits < 63 else "1E63"
        return (
            f"CASE WHEN ABS({column}) >= {bound} THEN 1 "
            f"WHEN {column} <> CAST({column} AS DECIMAL({precision}, {scale})) THEN 1 "
            "ELSE 0 END = 1",
            f"a value with more than {integer_digits} integer digits or more than {scale} decimals",
        )
    return None


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
    # A UniqueConstraint with a condition or expressions is a unique index. A
    # plain unique index treats NULLs as equal; UNIQUE WHERE NOT NULL treats
    # them as distinct, as a UNIQUE constraint does and Django assumes, also
    # with a WHERE condition and expression keys (probes lib_unique_catalog,
    # qtemp_unique_nulls). %(nulls_distinct)s stays empty: no NULLS [NOT]
    # DISTINCT on Db2 for i (supports_nulls_distinct_unique_constraints).
    sql_create_unique_index = (
        "CREATE UNIQUE WHERE NOT NULL INDEX %(name)s ON %(table)s "
        "(%(columns)s)%(include)s%(nulls_distinct)s%(condition)s"
    )
    # A column that becomes an identity numbers from 1, below the keys it
    # already holds; RESTART WITH takes only a constant, so a dynamic compound
    # statement reads MAX() itself (also for collected SQL, qtemp_renames).
    sql_restart_identity = (
        "BEGIN DECLARE NEXT_ID BIGINT; "
        "SET NEXT_ID = (SELECT COALESCE(MAX(%(column)s), 0) + 1 FROM %(table)s); "
        "EXECUTE IMMEDIATE 'ALTER TABLE %(table_text)s ALTER COLUMN %(column_text)s "
        "RESTART WITH ' CONCAT VARCHAR(NEXT_ID); END"
    )

    # Field changes in progress (remove_field(), alter_field()): their ALTER
    # TABLE statements run with CPA32B2 suppressed. Counted, since
    # alter_field() can call other methods that are counted too.
    _field_changes = 0
    # This editor counts in the connection's open schema editors.
    _counted = False
    # Why CPA32B2 is not suppressed (inquiry.py), None when it is.
    _suppression = inquiry.NOT_IN_FIELD_CHANGE

    def __enter__(self):
        editor = super().__enter__()
        if not self.collect_sql:
            self.connection._schema_editor_depth += 1
            self._counted = True
        return editor

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            result = self._exit(exc_type, exc_value, traceback)
        except BaseException as error:
            self._leave(error)
            raise
        self._leave(exc_value)
        return result

    def _leave(self, error):
        """The outermost schema editor of the connection ends the CPA32B2
        suppression, after its transaction has ended (OVERRIDE_QAQQINI is not
        transactional)."""
        if not self._counted:
            return
        self._counted = False
        self.connection._schema_editor_depth -= 1
        if self.connection._schema_editor_depth == 0:
            self.connection.end_cpa32b2_suppression(error)

    def _exit(self, exc_type, exc_value, traceback):
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

    @contextlib.contextmanager
    def _field_change(self):
        self._field_changes += 1
        try:
            yield
        finally:
            self._field_changes -= 1

    def execute(self, sql, params=()):
        """Suppress CPA32B2 for the ALTER TABLE of a field change, and explain
        an ALTER TABLE that Db2 for i cancelled anyway (see inquiry.py).

        A statement without parameters runs as is (``params=None``), as
        Django already runs create_model(), add_field(), add_constraint() and
        deferred SQL: a literal ``%`` (in a DEFAULT, which prepare_default()
        writes unescaped) is never taken for a placeholder, neither by the
        cursor nor in collected SQL.
        """
        if not params:
            params = None
        is_alter = inquiry.is_alter_table(str(sql))
        if is_alter and self._field_changes and not self.collect_sql:
            self._suppression = self.connection.suppress_cpa32b2()
        try:
            return super().execute(sql, params)
        except DatabaseError as exc:
            if is_alter and self._cancelled_by_inquiry(str(sql), exc):
                active = self.connection._inquiry_reply_active
                suppression = (
                    self._suppression if self._field_changes else inquiry.NOT_IN_FIELD_CHANGE
                )
                raise OperationalError(
                    inquiry.cancelled_ddl_message(active, suppression or inquiry.SUPPRESSION_FAILED)
                ) from exc
            raise

    def remove_field(self, model, field):
        with self._field_change():
            return super().remove_field(model, field)

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

    def _field_should_be_indexed(self, model, field):
        """No index on a LOB column (TextField, BinaryField): Db2 for i refuses
        it with SQL0350, so db_index=True is skipped there, as the Oracle and
        MySQL backends do for their limited types (supports_index_on_text_field)."""
        if base_type(field.db_type(self.connection)) in LOB_TYPES:
            return False
        return super()._field_should_be_indexed(model, field)

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
        if old_type and new_type and old_field.column and not self.collect_sql:
            self._refuse_changed_values(model, old_field, new_field, old_type, new_type)
        with self._field_change(), self._lob_without_db_index(old_field, new_field):
            return super().alter_field(model, old_field, new_field, strict=strict)

    @contextlib.contextmanager
    def _lob_without_db_index(self, *fields):
        """Django's alter_field() adds and drops the db_index index without
        asking _field_should_be_indexed(): a LOB field counts as db_index=False
        there, so no index is created on it, and a field that leaves a LOB type
        gets its index."""
        lobs = [
            field
            for field in fields
            if field.db_index and base_type(field.db_type(self.connection)) in LOB_TYPES
        ]
        for field in lobs:
            field.db_index = False
        try:
            yield
        finally:
            for field in lobs:
                field.db_index = True

    def _refuse_changed_values(self, model, old_field, new_field, old_type, new_type):
        """DataError if the type change would truncate or round a value
        (narrowing_check()). In a transaction the table is locked first, so
        no such value can arrive before the ALTER TABLE."""
        check = narrowing_check(self.quote_name(old_field.column), old_type, new_type)
        if check is None:
            return
        condition, found = check
        table = self.quote_name(model._meta.db_table)
        if self.connection.in_atomic_block:
            self.execute(self.sql_lock_table % {"table": table})
        with self.connection.cursor() as cursor:
            cursor.execute(f"SELECT 1 FROM {table} WHERE {condition} FETCH FIRST 1 ROW ONLY")
            changed = cursor.fetchone() is not None
        if changed:
            raise DataError(
                f"Cannot change {model._meta.label}.{new_field.name} ({table}."
                f"{self.quote_name(old_field.column)}) from {old_type} to {new_type}: the "
                f"table has {found}, which Db2 for i would truncate or round without an "
                "error. Change those values first (a data migration), then change the field. "
                'See "Narrowing a column" in docs/user/Known-Limitations.md.'
            )

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
        # Not escaped for "%s" placeholders: DDL without parameters runs as
        # is (execute()).
        return "NULL" if value is None else default_literal(value)

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
