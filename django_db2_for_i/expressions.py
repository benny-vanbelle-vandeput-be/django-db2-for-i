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

An explicit ``output_field`` always takes precedence over the type inferred
from the Python value. Type rules:

- strings (CharField, TextField) without ``max_length``: ``NVARCHAR(<bucket>)``,
  the value's UTF-16 length rounded up to 32, 256, 1024, 4000 or 16370, so
  values of different lengths share one SQL text (statement cache); with
  ``max_length``: ``NVARCHAR(max_length)``. Longer than 16370 units: refused
  (no rule for longer casts yet; NVARCHAR(16382) and up fail with SQL0901);
- integers whose type was inferred: ``INTEGER``, ``BIGINT`` outside the
  INTEGER range, ``DECIMAL(n, 0)`` outside the BIGINT range;
- Decimal without ``max_digits``: ``DECIMAL(p, s)`` from the value's digits;
- ``None`` with a known output_field: ``CAST(NULL AS <type>)``; without one:
  plain ``NULL``, there is no type to cast to;
- booleans, other integer fields, floats, dates, times, datetimes, UUIDs: the
  field's cast type (BOOLEAN, ..., DOUBLE, DATE, TIME, TIMESTAMP(6), CHAR(32)).

Any other type (bytes, timedelta, JSON, ...) raises NotSupportedError;
its rule comes with the field support in a later phase.

Predicates as operands
----------------------
Db2 for i rejects a predicate as a comparison operand: ``(a < b) = (c < d)``,
``bool_col = (x < y)`` and ``(pred) = TRUE`` fail with SQL0104 (probe
``queries``). When a lookup compares two conditional expressions, each
operand that renders as a predicate (a lookup, a ``Q`` / WhereNode,
``Exists``, or an ExpressionWrapper / NegatedExpression around one) is
written as ``CASE WHEN <predicate> THEN TRUE ELSE FALSE END``, a BOOLEAN
value; Django's Oracle backend does the same in ``Lookup.as_oracle``.
Boolean columns and values are never wrapped, and ``filter(<cond>=True)``
(rendered by Django as just the condition) is unchanged. ``NOT <BOOLEAN
value>`` (``~Value(False)``, ``~F("flag")``) is written as ``CASE <value> WHEN
TRUE THEN FALSE WHEN FALSE THEN TRUE END`` (``NegatedValue``), as an operand
and everywhere else (compiler.py: Db2 for i's NOT is TRUE for a NULL value).

Aggregates
----------
``AVG`` of an INTEGER returns an INTEGER on Db2 for i (``AVG`` of 3, 1, 2 is
2; probe ``queries``), while Django's ``Avg`` of an integer is a FloatField.
When the output is a FloatField and the argument is not one already, the
argument is cast to DOUBLE. ``Avg`` over a DecimalField stays DECIMAL, which
keeps its precision.

Case collapsed to an untyped NULL
---------------------------------
When every ``When`` of a ``Case`` matches nothing (``filter=Q(pk__in=[])`` on
an aggregate, which Django emulates as ``CASE WHEN <filter> THEN <arg>
END``), Django compiles just the default, a plain ``NULL`` when the default
is ``None``. Db2 for i rejects an untyped NULL as an argument (``COUNT(NULL)``
fails with SQL0171; probe ``queries``), so it is cast to the Case's type:
``COUNT(CAST(NULL AS INTEGER))``.

StringAgg
---------
Db2 for i has no ``STRING_AGG``; its ``LISTAGG`` aggregates strings (probe
``listagg``). The result type follows the argument: VARCHAR(4000) for a
VARCHAR, 2000 characters for an NVARCHAR (our CharField), a 1M character LOB
for a LOB. A longer result fails with SQL0802 (no truncation). ``StringAgg``
is a TextField, so the argument is cast to NCLOB (unless it is one already):
``LISTAGG(CAST(<expr> AS NCLOB), CAST(? AS NVARCHAR(32)))``, which allows
results up to 1M characters. The separator is a typed marker (a ``Value``);
an untyped string constant as separator fails with LOB arguments longer than
4K (SQL0171).

``LISTAGG`` over no values is NULL in Db2 for i, but the IBM i Access ODBC
driver returns it as an empty string when it is fetched (probe ``listagg``).
``CASE WHEN COUNT(<expr>) = 0 THEN NULL ELSE LISTAGG(...) END`` is fetched as
NULL, and keeps a real empty string (one empty value) as it is.

``StringAgg(..., order_by=...)`` becomes ``LISTAGG(...) WITHIN GROUP (ORDER BY
...)``. Django's NULL ordering emulation (``<expr> IS NULL, <expr>``) is not
valid there (SQL0199), so ``nulls_first`` / ``nulls_last`` items are ordered by
``CASE WHEN <expr> IS NULL THEN 0 ELSE 1 END`` first (probe ``listagg``).
"""

from __future__ import annotations

from decimal import Decimal

from django.db import NotSupportedError
from django.db.models import (
    Avg,
    BooleanField,
    CharField,
    Count,
    DecimalField,
    FloatField,
    IntegerField,
    StringAgg,
    TextField,
    When,
)
from django.db.models.expressions import (
    Case,
    Exists,
    Expression,
    ExpressionWrapper,
    NegatedExpression,
    OrderBy,
    Value,
)
from django.db.models.functions import Cast
from django.db.models.lookups import IsNull, Lookup
from django.db.models.sql.where import WhereNode

INTEGER_RANGE = (-(2**31), 2**31 - 1)
BIGINT_RANGE = (-(2**63), 2**63 - 1)
# Largest NVARCHAR(n) a cast accepts with a value of that length (probe
# string_limits: NVARCHAR(16382) and up fail with SQL0901).
NVARCHAR_MAX = 16370
STRING_BUCKETS = (32, 256, 1024, 4000, NVARCHAR_MAX)

SUPPORTED_TYPES = frozenset(
    {
        "CharField",
        "TextField",
        "BooleanField",
        "SmallIntegerField",
        "IntegerField",
        "BigIntegerField",
        "PositiveSmallIntegerField",
        "PositiveIntegerField",
        "PositiveBigIntegerField",
        "SmallAutoField",
        "AutoField",
        "BigAutoField",
        "FloatField",
        "DecimalField",
        "DateField",
        "DateTimeField",
        "TimeField",
        "UUIDField",
    }
)


def utf16_length(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def string_type(length: int) -> str:
    for bucket in STRING_BUCKETS:
        if length <= bucket:
            return f"NVARCHAR({bucket})"
    raise NotSupportedError(
        f"Db2 for i backend: a string Value of {length} UTF-16 units is longer than "
        f"NVARCHAR({NVARCHAR_MAX}); longer strings cannot be used as expression values yet."
    )


def decimal_type(value: Decimal) -> str:
    """``DECIMAL(precision, scale)`` that holds ``value`` exactly."""
    _sign, digits, exponent = value.as_tuple()
    if not isinstance(exponent, int):  # NaN / Infinity: let Db2 reject them
        return "DECIMAL(31, 0)"
    scale = max(-exponent, 0)
    integer_digits = max(len(digits) + exponent, 0)
    return f"DECIMAL({max(integer_digits + scale, 1)}, {scale})"


def _internal_type(output_field) -> str:
    if isinstance(output_field, (CharField, TextField)):
        return "TextField" if isinstance(output_field, TextField) else "CharField"
    return output_field.get_internal_type()


def value_cast_type(
    value, output_field, connection, *, explicit: bool, python_type: str | None = None
) -> str:
    """The SQL type for a ``Value`` holding ``value`` (already prepared).

    ``explicit``: the output_field was given, not inferred from the value.
    ``python_type``: the original value's type name, for error messages.
    """
    internal = _internal_type(output_field)
    if internal not in SUPPORTED_TYPES:
        raise NotSupportedError(
            f"Db2 for i backend: Value of type {python_type or type(value).__name__} with "
            "output field "
            f"{output_field.__class__.__name__} is not supported yet."
        )
    if internal in ("CharField", "TextField"):
        max_length = getattr(output_field, "max_length", None)
        if max_length is None or internal == "TextField":
            return string_type(utf16_length(value) if value is not None else 0)
        if max_length > NVARCHAR_MAX:
            return string_type(max_length)  # raises
        return f"NVARCHAR({max_length})"
    if isinstance(output_field, DecimalField) and output_field.max_digits is None:
        return decimal_type(Decimal(value)) if value is not None else "DECIMAL(31, 0)"
    if not explicit and type(output_field) is IntegerField and isinstance(value, int):
        if INTEGER_RANGE[0] <= value <= INTEGER_RANGE[1]:
            return "INTEGER"
        if BIGINT_RANGE[0] <= value <= BIGINT_RANGE[1]:
            return "BIGINT"
        return f"DECIMAL({len(str(abs(value)))}, 0)"
    return output_field.cast_db_type(connection)


def explicit_output_field(expression: Value):
    """The output_field passed to ``Value(...)``, or None if it was inferred."""
    args, kwargs = getattr(expression, "_constructor_args", ((), {}))
    return kwargs.get("output_field", args[1] if len(args) > 1 else None)


def value_as_db2_for_i(self, compiler, connection, **extra_context):
    sql, params = self.as_sql(compiler, connection, **extra_context)
    if sql not in ("%s", "NULL"):
        return sql, params  # a field's own placeholder SQL: leave it alone
    output_field = self._output_field_or_none
    value = params[0] if params else None
    if output_field is None:
        if value is not None:
            raise NotSupportedError(
                f"Db2 for i backend: Value of type {type(self.value).__name__} has no SQL type; "
                "pass output_field."
            )
        return sql, params  # untyped NULL: nothing to cast to
    cast_type = value_cast_type(
        value,
        output_field,
        connection,
        explicit=explicit_output_field(self) is not None,
        python_type=type(self.value).__name__,
    )
    return f"CAST({sql} AS {cast_type})", params


Value.as_db2_for_i = value_as_db2_for_i


def case_as_db2_for_i(self, compiler, connection, **extra_context):
    sql, params = self.as_sql(compiler, connection, **extra_context)
    output_field = self._output_field_or_none
    if sql == "NULL" and not params and output_field is not None:
        cast_type = value_cast_type(None, output_field, connection, explicit=True)
        return f"CAST(NULL AS {cast_type})", params
    return sql, params


Case.as_db2_for_i = case_as_db2_for_i

# --- Predicates as operands ---------------------------------------------------------------


def renders_as_predicate(expression) -> bool:
    """True if ``expression`` compiles to a predicate (not a BOOLEAN value)."""
    if isinstance(expression, (Lookup, WhereNode, Exists)):
        return True
    # NegatedExpression is an ExpressionWrapper too.
    if isinstance(expression, ExpressionWrapper):
        return renders_as_predicate(expression.expression)
    return False


class PredicateValue(Expression):
    """``CASE WHEN <predicate> THEN TRUE ELSE FALSE END``: a predicate as a BOOLEAN value."""

    output_field = BooleanField()

    def __init__(self, predicate):
        super().__init__(output_field=BooleanField())
        self.predicate = predicate

    def get_source_expressions(self):
        return [self.predicate]

    def set_source_expressions(self, exprs):
        (self.predicate,) = exprs

    def as_sql(self, compiler, connection):
        sql, params = compiler.compile(self.predicate)
        return f"CASE WHEN {sql} THEN TRUE ELSE FALSE END", params


class NegatedValue(Expression):
    """``NOT <BOOLEAN value>`` as a BOOLEAN value: NULL stays NULL."""

    output_field = BooleanField()

    def __init__(self, value):
        super().__init__(output_field=BooleanField())
        self.value = value

    def get_source_expressions(self):
        return [self.value]

    def set_source_expressions(self, exprs):
        (self.value,) = exprs

    def as_sql(self, compiler, connection):
        sql, params = compiler.compile(self.value)
        return f"CASE {sql} WHEN TRUE THEN FALSE WHEN FALSE THEN TRUE END", params


def _as_operand(operand):
    if isinstance(operand, NegatedExpression) and not renders_as_predicate(operand.expression):
        return NegatedValue(operand.expression)
    return PredicateValue(operand) if renders_as_predicate(operand) else operand


def lookup_as_db2_for_i(self, compiler, connection):
    if getattr(self.lhs, "conditional", False) and getattr(self.rhs, "conditional", False):
        operands = [_as_operand(operand) for operand in (self.lhs, self.rhs)]
        if any(isinstance(operand, (PredicateValue, NegatedValue)) for operand in operands):
            return type(self)(*operands).as_sql(compiler, connection)
    return self.as_sql(compiler, connection)


Lookup.as_db2_for_i = lookup_as_db2_for_i


# --- Aggregates ---------------------------------------------------------------------------


def avg_as_db2_for_i(self, compiler, connection, **extra_context):
    source, *rest = self.get_source_expressions()
    if isinstance(self.output_field, FloatField) and not isinstance(
        source.output_field, FloatField
    ):
        clone = self.copy()
        clone.set_source_expressions([Cast(source, FloatField()), *rest])
        return clone.as_sql(compiler, connection, **extra_context)
    return self.as_sql(compiler, connection, **extra_context)


Avg.as_db2_for_i = avg_as_db2_for_i


# LISTAGG's ordering, as Oracle writes it (Django's StringAgg.as_oracle).
WITHIN_GROUP_TEMPLATE = (
    "%(function)s(%(distinct)s%(expressions)s) WITHIN GROUP (%(order_by)s)%(filter)s"
)


def _null_ranked(order_by):
    """``order_by`` with each nulls_first / nulls_last item ordered by a NULL rank
    first (``CASE WHEN <expr> IS NULL ...``) instead of Django's emulation."""
    items = []
    for item in order_by.get_source_expressions():
        if isinstance(item, OrderBy) and (item.nulls_first or item.nulls_last):
            null, other = (0, 1) if item.nulls_first else (1, 0)
            rank = Case(When(IsNull(item.expression, True), then=Value(null)), default=Value(other))
            items += [OrderBy(rank), OrderBy(item.expression, descending=item.descending)]
        else:
            items.append(item)
    clone = order_by.copy()
    clone.set_source_expressions(items)
    return clone


def string_agg_as_db2_for_i(self, compiler, connection, **extra_context):
    clone = self.copy()
    source, delimiter, aggregate_filter, order_by = clone.get_source_expressions()
    expression = source
    if not isinstance(source.output_field, TextField):
        expression = Cast(source, TextField())
    if order_by is not None:
        order_by = _null_ranked(order_by)
        extra_context.setdefault("template", WITHIN_GROUP_TEMPLATE)
    clone.set_source_expressions([expression, delimiter, aggregate_filter, order_by])
    sql, params = clone.as_sql(compiler, connection, function="LISTAGG", **extra_context)
    condition = aggregate_filter.condition if aggregate_filter is not None else None
    count_sql, count_params = compiler.compile(Count(source, filter=condition))
    return f"CASE WHEN {count_sql} = 0 THEN NULL ELSE {sql} END", (*count_params, *params)


StringAgg.as_db2_for_i = string_agg_as_db2_for_i
