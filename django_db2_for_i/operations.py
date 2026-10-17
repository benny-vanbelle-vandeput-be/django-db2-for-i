"""DatabaseOperations: SQL generation helpers (quoting, casts, dates, pagination).

Implemented in phase 1; extended in later phases.

Identifiers: Db2 for i folds unquoted names to uppercase. ``quote_name()``
uppercases and quotes every name, so ``"basic_article"`` becomes
``"BASIC_ARTICLE"``, the same object as the unquoted name. Introspection
converts names back to lowercase (``identifier_converter``). Consequence:
mixed-case ``db_table`` / ``db_column`` names are not preserved.

Planned for phase 1, step 4:
- ``last_insert_id()`` via ``IDENTITY_VAL_LOCAL()`` (returning columns are
  off, and the ``basic`` module needs the new primary key).
- ``USE_TZ`` (default True since Django 5.0, also in the test suite): there is
  no time zone aware timestamp type, so aware datetimes are converted to
  naive UTC (the connection's time zone) in ``adapt_datetimefield_value()``,
  and read values made aware again by a converter in ``get_db_converters()``.
- Pagination with ``OFFSET ... ROWS FETCH FIRST ... ROWS ONLY``, from
  capabilities.
"""

from django.db.backends.base.operations import BaseDatabaseOperations
from django.db.backends.utils import truncate_name


class DatabaseOperations(BaseDatabaseOperations):
    def max_name_length(self) -> int:
        return self.connection.capabilities.max_name_length

    def quote_name(self, name: str) -> str:
        if name.startswith('"') and name.endswith('"'):
            return name  # Already quoted.
        name = truncate_name(name, self.max_name_length()).upper()
        return '"{}"'.format(name.replace('"', '""'))
