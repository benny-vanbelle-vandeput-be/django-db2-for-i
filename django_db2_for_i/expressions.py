"""Db2 for i SQL for Django expressions.

Uses Django's documented extension point for third-party backends: an
``as_<vendor>()`` method monkey patched onto the expression class
(docs/ref/models/expressions.txt, "Adding support in third-party database
backends"). Imported by ``base.py``, so it is active whenever the backend is.

Value
-----
Db2 for i rejects untyped parameter markers (and an untyped NULL) in the
select list, in ``CASE ... THEN ? ELSE ?``, in ``COALESCE(col, ?)`` and in
``? + ?`` (SQL0418). Every ``Value`` is therefore rendered as a typed marker,
``CAST(? AS <type>)``. Plain filter parameters (``filter(x=1)``) are not
``Value`` expressions and stay ``?``.

Type rules (output_field, explicit or resolved from the Python value):

- string without ``max_length``: ``NVARCHAR(<length>)``, the value's length in
  UTF-16 code units (minimum 1); with ``max_length``: ``NVARCHAR(max_length)``;
- integer: ``INTEGER``, ``BIGINT`` outside the INTEGER range, ``DECIMAL(n, 0)``
  outside the BIGINT range;
- Decimal without ``max_digits``: ``DECIMAL(p, s)`` from the value's digits;
  with ``max_digits`` / ``decimal_places``: those;
- ``None`` with a known output_field: ``CAST(NULL AS <type>)`` (for strings and
  decimals without length/precision: ``NVARCHAR(1)`` / ``DECIMAL(31, 0)``);
  ``None`` without one: plain ``NULL``, there is no type to cast to;
- everything else: the field's cast type (BOOLEAN, DATE, TIME, TIMESTAMP(6),
  DOUBLE, CHAR(32) for UUIDs, ...).
"""

from __future__ import annotations

from decimal import Decimal

from django.db.models import CharField, DecimalField, IntegerField
from django.db.models.expressions import Value

INTEGER_RANGE = (-(2**31), 2**31 - 1)
BIGINT_RANGE = (-(2**63), 2**63 - 1)


def utf16_length(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def decimal_type(value: Decimal) -> str:
    """``DECIMAL(precision, scale)`` that holds ``value`` exactly."""
    _sign, digits, exponent = value.as_tuple()
    if not isinstance(exponent, int):  # NaN / Infinity: let Db2 reject them
        return "DECIMAL(31, 0)"
    scale = max(-exponent, 0)
    integer_digits = max(len(digits) + exponent, 0)
    return f"DECIMAL({max(integer_digits + scale, 1)}, {scale})"


def value_cast_type(value, output_field, connection) -> str:
    """The SQL type for a ``Value`` holding ``value`` (already prepared)."""
    if isinstance(output_field, CharField) and output_field.max_length is None:
        return f"NVARCHAR({max(utf16_length(value), 1) if value is not None else 1})"
    if isinstance(output_field, DecimalField) and output_field.max_digits is None:
        return decimal_type(Decimal(value)) if value is not None else "DECIMAL(31, 0)"
    if type(output_field) is IntegerField and isinstance(value, int):
        if INTEGER_RANGE[0] <= value <= INTEGER_RANGE[1]:
            return "INTEGER"
        if BIGINT_RANGE[0] <= value <= BIGINT_RANGE[1]:
            return "BIGINT"
        return f"DECIMAL({len(str(abs(value)))}, 0)"
    return output_field.cast_db_type(connection)


def value_as_db2_for_i(self, compiler, connection, **extra_context):
    sql, params = self.as_sql(compiler, connection, **extra_context)
    if sql not in ("%s", "NULL"):
        return sql, params  # a field's own placeholder SQL: leave it alone
    output_field = self._output_field_or_none
    if output_field is None:
        return sql, params  # untyped NULL: nothing to cast to
    value = params[0] if params else None
    return f"CAST({sql} AS {value_cast_type(value, output_field, connection)})", params


Value.as_db2_for_i = value_as_db2_for_i
