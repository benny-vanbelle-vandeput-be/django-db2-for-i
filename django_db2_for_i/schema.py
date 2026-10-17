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
from decimal import Decimal

from django.db import NotSupportedError
from django.db.backends.base.schema import BaseDatabaseSchemaEditor


def string_literal(value: str) -> str:
    """``'abc'`` for printable ASCII without quotes, else ``UX'<UTF-16 hex>'``.

    In a column DEFAULT, Db2 for i stores an escaped quote wrongly ('O''Brien'
    becomes O''Brien in NVARCHAR, a garbled value in CHAR/VARCHAR), N'...'
    truncates CHAR values, and any non-ASCII character in the statement text
    fails in the ODBC driver (memory allocation error). The UTF-16 hex
    constant is stored correctly in every string column type (probe
    ``probe_defaults``, docs/IBMI_NOTES.md).
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


class DatabaseSchemaEditor(BaseDatabaseSchemaEditor):
    def quote_value(self, value) -> str:
        """An SQL literal for ``value`` (used for collected SQL)."""
        if value is None:
            return "NULL"
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
            yield part
