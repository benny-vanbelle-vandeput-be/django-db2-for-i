"""DatabaseSchemaEditor: DDL generation for models and migrations.

Implemented in phase 1 (CREATE/DROP TABLE); completed in phase 4.

- Foreign keys are created without an ON DELETE clause: Db2's default
  NO ACTION (checked at the end of the statement), never RESTRICT, so a
  self-referencing table can be emptied with one DELETE (docs/DECISIONS.md).
- Defaults are written as literals (``requires_literal_defaults``): DDL is
  not parameterized.
"""

import datetime
from decimal import Decimal

from django.db.backends.base.schema import BaseDatabaseSchemaEditor


class DatabaseSchemaEditor(BaseDatabaseSchemaEditor):
    def quote_value(self, value) -> str:
        """An SQL literal for ``value`` (used for collected SQL and defaults)."""
        if value is None:
            return "NULL"
        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        if isinstance(value, (int, float, Decimal)):
            return str(value)
        if isinstance(value, str):
            return "'{}'".format(value.replace("'", "''"))
        if isinstance(value, datetime.datetime):
            return f"'{value.isoformat(sep=' ')}'"
        if isinstance(value, (datetime.date, datetime.time)):
            return f"'{value.isoformat()}'"
        if isinstance(value, (bytes, bytearray, memoryview)):
            return f"BX'{bytes(value).hex().upper()}'"
        raise ValueError(f"Cannot quote parameter value {value!r} of type {type(value)}")

    def prepare_default(self, value) -> str:
        # The literal ends up in SQL that is executed with (empty) params, so
        # "%" must be escaped for the %s -> ? conversion.
        return self.quote_value(value).replace("%", "%%")
