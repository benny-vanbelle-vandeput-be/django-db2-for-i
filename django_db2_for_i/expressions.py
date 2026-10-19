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
  ``max_length``: ``NVARCHAR(max_length)``, or the bucket of the value's own
  length when it is longer (never cut short). Longer than 16370 units: refused
  (no rule for longer casts yet; NVARCHAR(16382) and up fail with SQL0901);
- integers whose type was inferred: ``INTEGER``, ``BIGINT`` outside the
  INTEGER range, ``DECIMAL(n, 0)`` outside the BIGINT range;
- Decimal without ``max_digits``: ``DECIMAL(p, s)`` from the value's digits;
- ``None`` with a known output_field: ``CAST(NULL AS <type>)``; without one:
  plain ``NULL``, there is no type to cast to;
- booleans, other integer fields, floats, dates, times, datetimes, UUIDs,
  durations, IP addresses: the field's cast type (BOOLEAN, ..., DOUBLE, DATE,
  TIME, TIMESTAMP(6), CHAR(32), BIGINT microseconds, VARCHAR(39));
- a ForeignKey or OneToOneField: its target field's type, recursively.

Any other type (bytes, JSON, ...) raises NotSupportedError;
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
and as a selected value (compiler.py: Db2 for i's NOT is TRUE for a NULL value).

Boolean values as conditions
----------------------------
Django writes a BOOLEAN value used as a condition as the bare value or ``NOT
value``: ``filter(flag=True)`` / ``filter(flag=False)`` through Exact's
boolean shortcut, ``filter(<boolean annotation>=False)``, ``filter(~F("flag"))``.
Db2 for i evaluates a BOOLEAN value used as a predicate two-valued (NULL as
false), so ``NOT flag`` matches NULL rows (probes ``queries``,
``selected_predicates``). Such conditions are written as comparisons,
``<value> = TRUE`` / ``<value> = FALSE``, which are three-valued in every
position and can use an index on the column; a negated value is unwrapped
(``~F("flag")`` as a condition is ``flag = FALSE``).

Durations
---------
A DurationField is a BIGINT of microseconds. Adding it to a timestamp uses
labeled durations, split into whole days and the remaining microseconds:
``ts + INTEGER(d / 86400000000) DAYS + MOD(d, 86400000000) MICROSECONDS``. A
single ``d MICROSECONDS`` silently gives NULL from 10**15 microseconds (about
31.7 years) on; the split is exact from year 1 to 9999 (probe ``durations``).
A DATE is cast to TIMESTAMP(6) first (``TIMESTAMP(<date>)`` drops the
microseconds); a TIME goes through a timestamp on 2000-01-01 and wraps at 24
hours. A duration times or divided by a number is BIGINT arithmetic.

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

Tuple lookups
-------------
With ``supports_tuple_lookups``, Django writes lookups on a multi-column
relation as row values. Db2 for i accepts ``(a, b) = (x, y)`` and ``(a, b) IN
(subquery)``, but rejects a row-value IN list (``(a, b) IN ((x, y), ...)``,
SQL0104) and row-value ``>``, ``>=``, ``<``, ``<=`` (SQL0115; probe
``tuple_lookups``). For those, ``TupleIn`` with values and the tuple
comparisons use Django's expanded form (``a = x AND b = y OR ...``, ``a > x OR
(a = x AND b > y)``), which is how SQL defines row-value comparisons, so the
result is the same, NULLs included. Against a subquery they go through
Django's own SQL (native IN; comparisons raise NotSupportedError, as
``supports_tuple_comparison_against_subquery`` is off).
"""

from __future__ import annotations

import copy
import re
from decimal import Decimal

from django.core.exceptions import FieldError
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
    Col,
    Combinable,
    DurationExpression,
    Exists,
    Expression,
    ExpressionWrapper,
    NegatedExpression,
    OrderBy,
    RawSQL,
    Value,
)
from django.db.models.fields.tuple_lookups import (
    TupleGreaterThan,
    TupleGreaterThanOrEqual,
    TupleIn,
    TupleLessThan,
    TupleLessThanOrEqual,
)
from django.db.models.functions import Cast
from django.db.models.lookups import (
    Exact,
    GreaterThan,
    GreaterThanOrEqual,
    In,
    IsNull,
    LessThan,
    LessThanOrEqual,
    Lookup,
)
from django.db.models.sql.query import Query
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
        "DurationField",
        "GenericIPAddressField",
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


def _concrete_field(output_field):
    """The field whose SQL type a relation's value has: a ForeignKey or
    OneToOneField takes its target field's type, recursively (a key to a key)."""
    seen = set()
    while getattr(output_field, "is_relation", False) and id(output_field) not in seen:
        seen.add(id(output_field))
        target = getattr(output_field, "target_field", None)
        if target is None:
            break
        output_field = target
    return output_field


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
    output_field = _concrete_field(output_field)
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
        if isinstance(value, str) and utf16_length(value) > max_length:
            # Longer than the field: never cast it shorter (the driver refuses it
            # with CWB0111; probe long_string_params), so its own bucket.
            return string_type(utf16_length(value))
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


# --- String values longer than the column -------------------------------------------------

# Comparisons whose untyped marker the driver describes with the size of the
# other side: a longer value fails on the client with CWB0111 ("Input data is
# too big to fit into field"), it is never truncated (probe long_string_params).
# LIKE and UPPER(...) = UPPER(?) are not affected.
SIZED_COMPARISONS = (Exact, In, GreaterThan, GreaterThanOrEqual, LessThan, LessThanOrEqual)
_STRING_COLUMN = re.compile(
    r"^(?P<kind>NVARCHAR|NCHAR|VARGRAPHIC|GRAPHIC|VARCHAR|CHAR)\((?P<size>\d+)\)", re.IGNORECASE
)


def _column_capacity(lhs, connection) -> tuple[int, str] | None:
    """(size, unit) of a column's string type; None when the size is not known.

    Only a plain column has a known size: the driver sizes an expression's
    marker by the expression's result (``SUBSTR(NAME, 1, 3)`` is 3, whatever
    the field says), so an expression counts as unknown.
    """
    if not isinstance(lhs, Col):
        return None
    match = _STRING_COLUMN.match(lhs.output_field.db_type(connection) or "")
    if not match:
        return None
    kind = match["kind"].upper()
    unit = "bytes" if kind in ("VARCHAR", "CHAR") else "utf-16"  # VARCHAR: CCSID 1208
    return int(match["size"]), unit


def _length(value: str, unit: str) -> int:
    return len(value.encode("utf-8")) if unit == "bytes" else utf16_length(value)


def with_typed_long_strings(lookup, connection):
    """A copy of ``lookup`` that types its too-long string values, or None.

    A value is too long when it exceeds the column in the column's unit (UTF-16
    code units for NVARCHAR, so an emoji counts twice; bytes for VARCHAR), or
    when the left-hand side is not a plain column (size unknown). Only the
    markers of those values become ``CAST(? AS NVARCHAR(<bucket>))``; values
    that fit, also the other elements of an IN list, keep their untyped markers
    and SQL. (Value objects in an IN list would make Django type every element.)
    """
    if not isinstance(lookup, SIZED_COMPARISONS) or not lookup.rhs_is_direct_value():
        return None
    values = list(lookup.rhs) if isinstance(lookup, In) else [lookup.rhs]
    capacity = _column_capacity(lookup.lhs, connection)

    def too_long(value) -> bool:
        if not isinstance(value, str):
            return False
        return capacity is None or _length(value, capacity[1]) > capacity[0]

    if not any(too_long(value) for value in values):
        return None
    for value in values:
        if too_long(value) and utf16_length(value) > NVARCHAR_MAX:
            raise NotSupportedError(
                f"Db2 for i backend: a comparison value of {utf16_length(value)} UTF-16 units "
                f"is longer than the largest supported comparison value ({NVARCHAR_MAX}); "
                "it is never truncated (docs/user/Known-Limitations.md, 'Comparison values "
                "longer than 16370 characters')."
            )
    process_rhs = lookup.process_rhs

    def typed_process_rhs(compiler, connection):
        sql, params = process_rhs(compiler, connection)
        params = list(params)
        parts = sql.split("%s")
        if len(parts) - 1 != len(params):  # not one marker per value: leave it
            return sql, params
        typed = parts[0]
        for param, rest in zip(params, parts[1:], strict=True):
            marker = f"CAST(%s AS {string_type(utf16_length(param))})" if too_long(param) else "%s"
            typed += marker + rest
        return typed, params

    clone = copy.copy(lookup)
    clone.process_rhs = typed_process_rhs
    return clone


def _is_boolean_value_condition(lookup) -> bool:
    """Django's ``Exact(<value>, True/False)`` for a BOOLEAN value used as a
    condition (``filter(flag=False)``, ``filter(~F("flag"))``, a boolean
    annotation in ``filter()``), which it would write as ``value`` / ``NOT value``."""
    return (
        isinstance(lookup, Exact)
        and isinstance(lookup.rhs, bool)
        and getattr(lookup.lhs, "conditional", False)
        and not renders_as_predicate(lookup.lhs)
        # A conditional RawSQL is trusted to be a condition (as Django's own
        # conditional_expression_supported_in_where_clause does): left as it is.
        and not isinstance(lookup.lhs, RawSQL)
    )


def boolean_value_condition(lookup, compiler):
    """``<value> = TRUE`` / ``<value> = FALSE``: three-valued, where Db2 for i's
    ``NOT <value>`` is TRUE for NULL (see the module docstring). A negated value
    is unwrapped with the truth flipped: ``~F("flag")`` becomes ``flag = FALSE``."""
    value, truth = lookup.lhs, lookup.rhs
    while isinstance(value, NegatedExpression) and not renders_as_predicate(value.expression):
        value, truth = value.expression, not truth
    sql, params = compiler.compile(value)
    return f"{sql} = {'TRUE' if truth else 'FALSE'}", params


def lookup_as_db2_for_i(self, compiler, connection):
    if _is_boolean_value_condition(self):
        return boolean_value_condition(self, compiler)
    typed = with_typed_long_strings(self, connection)
    if typed is not None:
        return typed.as_sql(compiler, connection)
    if getattr(self.lhs, "conditional", False) and getattr(self.rhs, "conditional", False):
        operands = [_as_operand(operand) for operand in (self.lhs, self.rhs)]
        if any(isinstance(operand, (PredicateValue, NegatedValue)) for operand in operands):
            return type(self)(*operands).as_sql(compiler, connection)
    return self.as_sql(compiler, connection)


Lookup.as_db2_for_i = lookup_as_db2_for_i


def tuple_expanded_as_db2_for_i(self, compiler, connection):
    """Row-value IN lists and comparisons in Django's expanded form (see the
    module docstring); against a subquery, Django's own SQL."""
    if isinstance(self.rhs, Query):
        return lookup_as_db2_for_i(self, compiler, connection)
    return self.get_fallback_sql(compiler, connection)


for _tuple_lookup in (
    TupleIn,
    TupleGreaterThan,
    TupleGreaterThanOrEqual,
    TupleLessThan,
    TupleLessThanOrEqual,
):
    _tuple_lookup.as_db2_for_i = tuple_expanded_as_db2_for_i


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


# --- Durations ----------------------------------------------------------------------------

DAY_MICROSECONDS = 86_400_000_000
TEMPORAL_TYPES = frozenset({"DateField", "DateTimeField", "TimeField"})


def _internal_type_or_none(expression) -> str | None:
    try:
        return expression.output_field.get_internal_type()
    except FieldError:
        return None


def duration_expression_as_db2_for_i(self, compiler, connection):
    connection.ops.check_expression_support(self)
    lhs_type, rhs_type = _internal_type_or_none(self.lhs), _internal_type_or_none(self.rhs)
    temporal = (
        self.lhs if lhs_type in TEMPORAL_TYPES else self.rhs if rhs_type in TEMPORAL_TYPES else None
    )
    if temporal is not None and self.connector in (Combinable.ADD, Combinable.SUB):
        duration = self.rhs if temporal is self.lhs else self.lhs
        temporal_sql, temporal_params = compiler.compile(temporal)
        duration_sql, duration_params = compiler.compile(duration)
        kind = _internal_type_or_none(temporal)
        if kind == "DateField":
            temporal_sql = f"CAST({temporal_sql} AS TIMESTAMP(6))"
        elif kind == "TimeField":
            temporal_sql = f"TIMESTAMP(DATE('2000-01-01'), {temporal_sql})"
        sign = "-" if self.connector == Combinable.SUB else "+"
        sql = (
            f"{temporal_sql} {sign} INTEGER(({duration_sql}) / {DAY_MICROSECONDS}) DAYS "
            f"{sign} MOD(({duration_sql}), {DAY_MICROSECONDS}) MICROSECONDS"
        )
        if kind == "TimeField":
            sql = f"TIME({sql})"
        return f"({sql})", (*temporal_params, *duration_params, *duration_params)
    lhs_sql, lhs_params = compiler.compile(self.lhs)
    rhs_sql, rhs_params = compiler.compile(self.rhs)
    sql = connection.ops.combine_expression(self.connector, [lhs_sql, rhs_sql])
    if self.connector in (Combinable.MUL, Combinable.DIV):
        sql = f"BIGINT({sql})"  # microseconds stay a whole number
    return f"({sql})", (*lhs_params, *rhs_params)


DurationExpression.as_db2_for_i = duration_expression_as_db2_for_i
