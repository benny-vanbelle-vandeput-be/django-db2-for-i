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

Database functions
------------------
Where Db2 for i differs from Django's default SQL (probe ``db_functions``):

- ``Length``: ``LENGTH`` counts UTF-16 code units (an emoji is 2);
  ``CHARACTER_LENGTH`` counts characters.
- ``Log(a, b)``: Db2 for i's ``LOG`` takes one argument, so ``LN(b) / LN(a)``.
- ``Concat``: ``CONCAT`` takes two arguments (Django's ``ConcatPair`` gives it
  two) and is NULL when either is; Django's ``Concat`` treats NULL as empty
  text, so each argument that can be NULL (all but a non-NULL ``Value`` and an
  inner ``ConcatPair``) is wrapped in ``COALESCE(<arg>, '')``.
- ``ATan2(y, x)``: Db2 for i's ``ATAN2`` takes x first, so the arguments are
  swapped.
- ``MD5``, ``SHA1``, ``SHA256``, ``SHA512``: ``HASH_MD5`` ... ``HASH_SHA512``
  over the text as UTF-8, ``LOWER(HEX(HASH_<x>(CAST(<expr> AS CLOB(2G) CCSID
  1208))))``, which gives Python's ``hashlib`` result, also for an ``NCLOB``
  (probe ``db_function_args``).
- ``LPad``, ``RPad``, ``Repeat``: a ``Value(None)`` argument is an untyped
  NULL, which they refuse (SQL0171); it is cast to NVARCHAR (the text) or
  INTEGER (``Repeat``'s number).
- ``Cast`` of a number to a ``DecimalField`` with ``decimal_places``: Db2 for
  i's ``CAST`` cuts off (2.55 to 2.5, probe ``db_functions``), Django rounds,
  so the number is rounded first: ``CAST(ROUND(<x>, <places>) AS DECIMAL(p,
  s))``, a DOUBLE through ``DECFLOAT(34)`` (``ROUND`` of a DOUBLE stays binary,
  and the cast then cuts -1.92999... to -1.92; probe ``db_function_args``).
  ``ROUND`` takes halves away from zero, as Django expects without
  ``rounds_to_even``.
- ``Cast`` of a float to text: Db2 for i writes a DOUBLE as ``3E0``; through
  ``DECFLOAT(16)`` plus 0 (the exponent becomes 0) it is ``3``, ``4.5`` and
  ``300``, as on Django's other backends, with 16 significant digits (probe
  ``float_text``).
- ``Reverse``,``SHA224``, ``SHA384``: Db2 for i has no ``REVERSE``,
  ``HASH_SHA224`` or ``HASH_SHA384`` (SQL0204), so they raise
  NotSupportedError rather than a workaround that could give other results.

Window functions
----------------
Probe ``window``: every window function, partitions and frames work, but

- ``Lag`` / ``Lead``: the offset must be a constant (a marker is SQL0104, a
  typed one SQL0199), so a whole-number ``Value`` is written as a literal;
- ``NthValue``: the position takes a plain marker but not a typed one
  (SQL0171), and ``Value`` writes typed markers, so it is a literal too;
- ``PercentRank``, ``CumeDist``: Db2 for i gives a DECFLOAT, which the driver
  fetches as text, so the window is cast to DOUBLE (Django's ``FloatField``).

JSONField
---------
An NCLOB holding the JSON text (no CHECK: ``IS JSON`` is refused there, probe
``lib_json_check``). The lookups follow Django's Oracle code with Db2 for i's
functions (probe ``json_lookups``):

- ``data__key``: ``JSON_QUERY(<col>, '<path>')``, the key's JSON text, strings
  with their quotes, which ``JSONField.from_db_value`` decodes; NULL for JSON
  null and a missing key. ``KT()``: ``JSON_QUERY ... OMIT QUOTES``. The path is
  an SQL literal, not a marker, so the select list and GROUP BY match.
- ``has_key``, ``has_keys``, ``has_any_keys``, ``key__isnull``: ``JSON_EXISTS``.
- ``key__exact``, ``key__in``: the right-hand side's JSON through
  ``JSON_QUERY(JSON_OBJECT('value' VALUE ? FORMAT JSON), '$.value')``, so both
  sides are compact JSON text; JSON null as "the key exists and JSON_QUERY is
  NULL".
- ``key__lt`` and the other comparisons with a number: ``JSON_VALUE(...
  RETURNING DECFLOAT(34))`` (JSON text compares as text).
- ``JSONObject``, ``JSONArray``: ``JSON_OBJECT`` / ``JSON_ARRAY`` returning an
  NCLOB, JSON values with ``FORMAT JSON``, NULL elements kept as JSON null.
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
    JSONField,
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
    Func,
    NegatedExpression,
    OrderBy,
    RawSQL,
    Value,
    Window,
)
from django.db.models.fields.json import (
    HasKeyLookup,
    HasKeyOrArrayIndex,
    KeyTextTransform,
    KeyTransform,
    KeyTransformExact,
    KeyTransformGt,
    KeyTransformGte,
    KeyTransformIn,
    KeyTransformIsNull,
    KeyTransformLt,
    KeyTransformLte,
)
from django.db.models.fields.tuple_lookups import (
    TupleGreaterThan,
    TupleGreaterThanOrEqual,
    TupleIn,
    TupleLessThan,
    TupleLessThanOrEqual,
)
from django.db.models.functions import (
    MD5,
    SHA1,
    SHA224,
    SHA256,
    SHA384,
    SHA512,
    ATan2,
    Cast,
    Coalesce,
    ConcatPair,
    CumeDist,
    JSONArray,
    JSONObject,
    Lag,
    Lead,
    Length,
    Log,
    LPad,
    NthValue,
    PercentRank,
    Repeat,
    Reverse,
    RPad,
)
from django.db.models.lookups import (
    Exact,
    GreaterThan,
    GreaterThanOrEqual,
    In,
    IsNull,
    LessThan,
    LessThanOrEqual,
    Lookup,
    Range,
)
from django.db.models.sql.query import Query
from django.db.models.sql.where import WhereNode

from .compat import DJANGO_CHECKS_TUPLE_SUBQUERY_COMPARISON, JSONIn, StringAgg

SMALLINT_RANGE = (-(2**15), 2**15 - 1)
INTEGER_RANGE = (-(2**31), 2**31 - 1)
BIGINT_RANGE = (-(2**63), 2**63 - 1)
# DECIMAL(64, 0) fails with SQL0604 on Db2 for i 7.5 (probe numeric_params).
DECIMAL_MAX_PRECISION = 63
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
        "JSONField",
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
    """``DECIMAL(precision, scale)`` that holds ``value`` exactly (never rounded)."""
    precision, scale = decimal_digits(value)
    return f"DECIMAL({precision}, {scale})"


def decimal_digits(value: Decimal) -> tuple[int, int]:
    """(precision, scale) that hold ``value`` exactly, from its digits and exponent.

    Trailing zeros count as given (``1.50`` has scale 2); only when that needs
    more than DECIMAL_MAX_PRECISION digits are they dropped (exact, the same
    number). NaN, infinities and values that need more digits raise
    NotSupportedError: never rounded or truncated.
    """
    if not value.is_finite():
        raise NotSupportedError(
            f"Db2 for i backend: Decimal('{value}') is not a number DECIMAL can hold; "
            "NaN and infinities cannot be stored or compared."
        )
    _sign, digits, exponent = value.as_tuple()
    precision, scale = _digits_and_scale(digits, exponent)
    if precision > DECIMAL_MAX_PRECISION:
        digits = digits[: len(digits) - _trailing_zeros(digits)] or (0,)
        exponent = exponent + (len(value.as_tuple().digits) - len(digits))
        precision, scale = _digits_and_scale(digits, exponent)
    if precision > DECIMAL_MAX_PRECISION:
        raise NotSupportedError(
            f"Db2 for i backend: the value {value} needs {precision} digits; DECIMAL holds at "
            f"most {DECIMAL_MAX_PRECISION}. It is never rounded or truncated "
            "(docs/user/Known-Limitations.md, 'Numbers with more than 63 digits')."
        )
    return precision, scale


def _digits_and_scale(digits: tuple[int, ...], exponent: int) -> tuple[int, int]:
    if not any(digits):  # zero, also 0E-70 or -0.0: one digit holds it
        return 1, 0
    scale = max(-exponent, 0)
    integer_digits = max(len(digits) + exponent, 0)
    return max(integer_digits + scale, 1), scale


def _trailing_zeros(digits: tuple[int, ...]) -> int:
    count = 0
    for digit in reversed(digits):
        if digit:
            break
        count += 1
    return count


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
    if internal == "JSONField":
        # The JSON text (JSONField.get_db_prep_value), as for a TextField.
        return string_type(utf16_length(value) if value is not None else 0)
    if isinstance(output_field, DecimalField) and output_field.max_digits is None:
        return decimal_type(Decimal(value)) if value is not None else "DECIMAL(31, 0)"
    if not explicit and type(output_field) is IntegerField and isinstance(value, int):
        if INTEGER_RANGE[0] <= value <= INTEGER_RANGE[1]:
            return "INTEGER"
        if BIGINT_RANGE[0] <= value <= BIGINT_RANGE[1]:
            return "BIGINT"
        return decimal_type(Decimal(value))
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


class TypedNull(Expression):
    """``CAST(NULL AS <type>)``: SQL NULL with a type. Not ``Value(None,
    output_field=...)``, which a JSONField writes as JSON ``null``."""

    def __init__(self, output_field):
        super().__init__(output_field=output_field)

    def as_sql(self, compiler, connection):
        cast_type = value_cast_type(None, self.output_field, connection, explicit=True)
        return f"CAST(NULL AS {cast_type})", ()


def _is_untyped_null(expression) -> bool:
    """An expression that compiles to a bare NULL: ``Value(None)`` without an
    output_field, or a function of only such values (``Coalesce(None, None)``)."""
    if isinstance(expression, Value):
        return expression.value is None and explicit_output_field(expression) is None
    if isinstance(expression, Func):
        sources = expression.get_source_expressions()
        return bool(sources) and all(_is_untyped_null(source) for source in sources)
    return False


def case_as_db2_for_i(self, compiler, connection, **extra_context):
    """A CASE whose results are all a bare NULL is refused (SQL0580), as in
    ``bulk_update()`` of a field to ``Value(None)``: then each result gets the
    CASE's type. A bare NULL next to a typed result is accepted and stays."""
    output_field = self._output_field_or_none
    *cases, default = self.get_source_expressions()
    results = [when.get_source_expressions()[1] for when in cases]
    if output_field is not None and cases and all(map(_is_untyped_null, [*results, default])):
        typed = []
        for when in cases:
            condition, _result = when.get_source_expressions()
            when = when.copy()
            when.set_source_expressions([condition, TypedNull(output_field)])
            typed.append(when)
        clone = self.copy()
        clone.set_source_expressions([*typed, TypedNull(output_field)])
        self = clone
    sql, params = self.as_sql(compiler, connection, **extra_context)
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
SIZED_COMPARISONS = (Exact, In, Range, GreaterThan, GreaterThanOrEqual, LessThan, LessThanOrEqual)
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


_NUMERIC_COLUMN = re.compile(
    r"^(?P<kind>SMALLINT|INTEGER|BIGINT|DECIMAL|NUMERIC)"
    r"(?:\((?P<precision>\d+)(?:,\s*(?P<scale>\d+))?\))?",
    re.IGNORECASE,
)
_INTEGER_COLUMN_RANGES = {
    "SMALLINT": SMALLINT_RANGE,
    "INTEGER": INTEGER_RANGE,
    "BIGINT": BIGINT_RANGE,
}


def _is_number(value) -> bool:
    return isinstance(value, Decimal) or (isinstance(value, int) and not isinstance(value, bool))


def _numeric_fits(lhs, connection):
    """A function telling whether a number fits the left-hand side's marker, or
    None for a column whose numbers always fit (DOUBLE, REAL, ...).

    The driver sizes an untyped marker by the column (probe numeric_params):
    SMALLINT / INTEGER / BIGINT by their range, DECIMAL(p, s) by p - s integer
    digits and s decimals (a value with more decimals, trailing zeros included,
    does not fit). For an expression the size is not known: Decimals never
    count as fitting, integers only within the INTEGER range.
    """
    if not isinstance(lhs, Col):
        return lambda value: (
            not isinstance(value, Decimal) and INTEGER_RANGE[0] <= value <= INTEGER_RANGE[1]
        )
    match = _NUMERIC_COLUMN.match(lhs.output_field.db_type(connection) or "")
    if not match:
        return None
    kind = match["kind"].upper()
    if kind in _INTEGER_COLUMN_RANGES:
        low, high = _INTEGER_COLUMN_RANGES[kind]

        def fits_integer(value) -> bool:
            if isinstance(value, Decimal) and value != value.to_integral_value():
                return False
            return low <= value <= high

        return fits_integer
    precision = int(match["precision"] or 5)
    scale = int(match["scale"] or 0)

    def fits(value) -> bool:
        number = Decimal(value)
        if not number.is_finite():
            return False
        digits, value_scale = decimal_digits(number)
        return value_scale <= scale and digits - value_scale <= precision - scale

    return fits


def _oversized_type(value, string_capacity, numeric_fits) -> str | None:
    """The SQL type for a comparison value that does not fit its marker, or None."""
    if isinstance(value, str):
        if string_capacity is None or _length(value, string_capacity[1]) > string_capacity[0]:
            if utf16_length(value) > NVARCHAR_MAX:
                raise NotSupportedError(
                    f"Db2 for i backend: a comparison value of {utf16_length(value)} UTF-16 "
                    "units is longer than the largest supported comparison value "
                    f"({NVARCHAR_MAX}); it is never truncated (docs/user/Known-Limitations.md, "
                    "'Comparison values longer than 16370 characters')."
                )
            return string_type(utf16_length(value))
        return None
    if _is_number(value) and numeric_fits is not None:
        if isinstance(value, Decimal) and not value.is_finite():
            decimal_digits(value)  # raises a clear error
        if not numeric_fits(value):
            return decimal_type(Decimal(value))  # raises beyond 63 digits
    return None


def with_typed_oversized_values(lookup, connection):
    """A copy of ``lookup`` that types its values that do not fit, or None.

    The driver sizes an untyped marker by the column, so a longer string
    (CWB0111), an integer out of the column's range or a Decimal with more
    digits than DECIMAL(p, s) fails (30018, 30160, 30126; probes
    long_string_params, numeric_params). Only the markers of those values get a
    type of their own: ``CAST(? AS NVARCHAR(<bucket>))`` for a string,
    ``CAST(? AS DECIMAL(p, s))`` with the value's own digits for a number, so
    Db2 for i compares exactly (never rounded or truncated). Values that fit,
    also the other elements of an IN list or a range, keep their untyped
    markers and SQL. (Value objects in an IN list would make Django type every
    element.) A string counts as too long in the column's unit (UTF-16 code
    units for NVARCHAR, bytes for VARCHAR) or when the left-hand side is not a
    plain column (size unknown).
    """
    if not isinstance(lookup, SIZED_COMPARISONS) or not lookup.rhs_is_direct_value():
        return None
    values = list(lookup.rhs) if isinstance(lookup, (In, Range)) else [lookup.rhs]
    string_capacity = _column_capacity(lookup.lhs, connection)
    numeric_fits = _numeric_fits(lookup.lhs, connection)

    def oversized(value) -> str | None:
        return _oversized_type(value, string_capacity, numeric_fits)

    if not any(oversized(value) for value in values):
        return None
    process_rhs = lookup.process_rhs

    def typed(marker: str, param) -> str:
        sql_type = oversized(param)
        return f"CAST({marker} AS {sql_type})" if sql_type and marker == "%s" else marker

    def typed_process_rhs(compiler, connection):
        sql, params = process_rhs(compiler, connection)
        params = list(params)
        if isinstance(sql, (list, tuple)):  # range: one marker per bound
            if len(sql) != len(params):
                return sql, params
            return [typed(marker, param) for marker, param in zip(sql, params, strict=True)], params
        parts = sql.split("%s")
        if len(parts) - 1 != len(params):  # not one marker per value: leave it
            return sql, params
        result = parts[0]
        for param, rest in zip(params, parts[1:], strict=True):
            result += typed("%s", param) + rest
        return result, params

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
    typed = with_typed_oversized_values(self, connection)
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
        if (
            not DJANGO_CHECKS_TUPLE_SUBQUERY_COMPARISON
            and self.rhs.subquery
            and not isinstance(self, TupleIn)
        ):  # as Django 6.0+ refuses it (row-value comparisons give SQL0115)
            raise NotSupportedError(
                f'"{self.lookup_name}" cannot be used to target composite fields '
                "through subqueries on this backend"
            )
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


if StringAgg is not None:  # Django 6.0+ (compat.py)
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


# --- Database functions -------------------------------------------------------------------


def length_as_db2_for_i(self, compiler, connection, **extra_context):
    return self.as_sql(compiler, connection, function="CHARACTER_LENGTH", **extra_context)


Length.as_db2_for_i = length_as_db2_for_i


def log_as_db2_for_i(self, compiler, connection, **extra_context):
    base, number = self.get_source_expressions()
    base_sql, base_params = compiler.compile(base)
    number_sql, number_params = compiler.compile(number)
    return f"(LN({number_sql}) / LN({base_sql}))", (*number_params, *base_params)


Log.as_db2_for_i = log_as_db2_for_i


def concat_pair_as_db2_for_i(self, compiler, connection, **extra_context):
    clone = self.copy()
    clone.set_source_expressions(
        [
            expression
            if isinstance(expression, ConcatPair)
            or (isinstance(expression, Value) and expression.value is not None)
            else Coalesce(expression, Value(""))
            for expression in clone.get_source_expressions()
        ]
    )
    return clone.as_sql(compiler, connection, **extra_context)


ConcatPair.as_db2_for_i = concat_pair_as_db2_for_i


def _not_supported(function: str):
    def as_db2_for_i(self, compiler, connection, **extra_context):
        raise NotSupportedError(
            f"Db2 for i backend: {function} is not supported (Db2 for i has no such function)."
        )

    return as_db2_for_i


Reverse.as_db2_for_i = _not_supported("Reverse")
SHA224.as_db2_for_i = _not_supported("SHA224")
SHA384.as_db2_for_i = _not_supported("SHA384")


def atan2_as_db2_for_i(self, compiler, connection, **extra_context):
    clone = self.copy()
    clone.set_source_expressions(self.get_source_expressions()[::-1])
    return clone.as_sql(compiler, connection, **extra_context)


ATan2.as_db2_for_i = atan2_as_db2_for_i


def _hash(function: str):
    template = f"LOWER(HEX({function}(CAST(%(expressions)s AS CLOB(2G) CCSID 1208))))"

    def as_db2_for_i(self, compiler, connection, **extra_context):
        return self.as_sql(compiler, connection, template=template, **extra_context)

    return as_db2_for_i


MD5.as_db2_for_i = _hash("HASH_MD5")
SHA1.as_db2_for_i = _hash("HASH_SHA1")
SHA256.as_db2_for_i = _hash("HASH_SHA256")
SHA512.as_db2_for_i = _hash("HASH_SHA512")


def _typed_nulls(*fields):
    """``as_db2_for_i`` that casts an untyped ``Value(None)`` argument to the
    field of its position, which the function refuses otherwise (SQL0171)."""

    def as_db2_for_i(self, compiler, connection, **extra_context):
        expressions = self.get_source_expressions()
        typed = [
            Value(None, output_field=field)
            if field is not None
            and isinstance(expression, Value)
            and expression.value is None
            and expression._output_field_or_none is None
            else expression
            for expression, field in zip(
                expressions, (*fields, *[None] * len(expressions))[: len(expressions)], strict=True
            )
        ]
        if typed == expressions:
            return self.as_sql(compiler, connection, **extra_context)
        clone = self.copy()
        clone.set_source_expressions(typed)
        return clone.as_sql(compiler, connection, **extra_context)

    return as_db2_for_i


LPad.as_db2_for_i = _typed_nulls(CharField())
RPad.as_db2_for_i = _typed_nulls(CharField())
Repeat.as_db2_for_i = _typed_nulls(CharField(), IntegerField())


NUMERIC_TYPES = frozenset({"FloatField", "DecimalField"})


def cast_as_db2_for_i(self, compiler, connection, **extra_context):
    output_field = self.output_field
    (source,) = self.get_source_expressions()
    if (
        isinstance(output_field, DecimalField)
        and output_field.decimal_places is not None
        and _internal_type_or_none(source) in NUMERIC_TYPES
    ):
        source_sql, source_params = compiler.compile(source)
        if _internal_type_or_none(source) == "FloatField":
            # ROUND of a DOUBLE stays binary: -1.93 is -1.92999..., cut to -1.92.
            source_sql = f"CAST({source_sql} AS DECFLOAT(34))"
        cast_type = output_field.cast_db_type(connection)
        sql = f"CAST(ROUND({source_sql}, {int(output_field.decimal_places)}) AS {cast_type})"
        return sql, source_params
    if isinstance(output_field, (CharField, TextField)) and _internal_type_or_none(source) == (
        "FloatField"
    ):
        # A DOUBLE as text is 3E0; through DECFLOAT(16) it is 3, 4.5, 0.1, and
        # adding 0 sets the exponent to 0, so 300 is not 3E+2 (probe float_text).
        source_sql, source_params = compiler.compile(source)
        cast_type = output_field.cast_db_type(connection)
        return f"CAST(CAST({source_sql} AS DECFLOAT(16)) + 0 AS {cast_type})", source_params
    return self.as_sql(compiler, connection, **extra_context)


Cast.as_db2_for_i = cast_as_db2_for_i


# --- Window functions ---------------------------------------------------------------------


class IntegerLiteral(Expression):
    """A whole number written into the SQL, where Db2 for i takes only a constant."""

    def __init__(self, value: int):
        super().__init__(output_field=IntegerField())
        self.value = int(value)

    def as_sql(self, compiler, connection):
        return str(self.value), ()


def _literal_argument(position: int):
    """``as_db2_for_i`` writing the whole-number ``Value`` at ``position`` as a literal."""

    def as_db2_for_i(self, compiler, connection, **extra_context):
        sources = self.get_source_expressions()
        argument = sources[position]
        if (
            isinstance(argument, Value)
            and isinstance(argument.value, int)
            and not isinstance(argument.value, bool)
        ):
            clone = self.copy()
            sources[position] = IntegerLiteral(argument.value)
            clone.set_source_expressions(sources)
            return clone.as_sql(compiler, connection, **extra_context)
        return self.as_sql(compiler, connection, **extra_context)

    return as_db2_for_i


Lag.as_db2_for_i = _literal_argument(1)
Lead.as_db2_for_i = _literal_argument(1)
NthValue.as_db2_for_i = _literal_argument(1)


def window_as_db2_for_i(self, compiler, connection, template=None):
    sql, params = self.as_sql(compiler, connection, template=template)
    if isinstance(self.source_expression, (PercentRank, CumeDist)):
        sql = f"CAST({sql} AS DOUBLE)"
    return sql, params


Window.as_db2_for_i = window_as_db2_for_i


# --- JSONField ---------------------------------------------------------------------------


def _json_path_sql(path: str) -> tuple[str, tuple]:
    """A JSON path as SQL: a string literal where it can be one (the select list
    and GROUP BY then match), a marker for characters above U+FFFE and U+FFFF,
    which a literal in the statement loses (probe json_lookups). ``%`` doubled
    for the placeholder conversion."""
    if any(ord(char) >= 0xFFFF for char in path):
        return "%s", (path,)
    return "'" + path.replace("'", "''").replace("%", "%%") + "'", ()


def _key_transform_parts(transform, compiler, connection):
    lhs, params, key_transforms = transform.preprocess_lhs(compiler, connection)
    path_sql, path_params = _json_path_sql(connection.ops.compile_json_path(key_transforms))
    return lhs, (*params, *path_params), path_sql


def key_transform_as_db2_for_i(self, compiler, connection):
    """``data__key``: the key's JSON text (strings keep their quotes), which
    JSONField.from_db_value decodes; NULL for JSON null and a missing key
    (probe json_lookups)."""
    lhs, params, path = _key_transform_parts(self, compiler, connection)
    return f"JSON_QUERY({lhs}, {path})", params


def key_text_transform_as_db2_for_i(self, compiler, connection):
    """``KT("data__key")``: a string without its quotes, other values as JSON text."""
    lhs, params, path = _key_transform_parts(self, compiler, connection)
    # An NCLOB, not JSON_QUERY's CLOB: LISTAGG refuses a CLOB with an NVARCHAR
    # separator (SQL0171; probe json_lookups).
    return f"JSON_QUERY({lhs}, {path} RETURNING NCLOB(1M) OMIT QUOTES)", params


KeyTransform.as_db2_for_i = key_transform_as_db2_for_i
KeyTextTransform.as_db2_for_i = key_text_transform_as_db2_for_i


def _has_key_paths(lookup, compiler, connection):
    """Django's HasKeyLookup._as_sql_parts with this backend's path keys (Django
    json.dumps the final key, which a Db2 for i path does not read)."""
    if isinstance(lookup.lhs, KeyTransform):
        lhs_sql, lhs_params, lhs_keys = lookup.lhs.preprocess_lhs(compiler, connection)
    else:
        (lhs_sql, lhs_params), lhs_keys = lookup.process_lhs(compiler, connection), []
    keys = lookup.rhs if isinstance(lookup.rhs, (list, tuple)) else [lookup.rhs]
    for key in keys:
        if isinstance(key, KeyTransform):
            *_, rhs_keys = key.preprocess_lhs(compiler, connection)
        else:
            rhs_keys = [key]
        *rhs_keys, final_key = rhs_keys
        path = connection.ops.compile_json_path([*lhs_keys, *rhs_keys])
        if isinstance(lookup, HasKeyOrArrayIndex):
            path += connection.ops.compile_json_path([final_key], include_root=False)
        else:
            path += connection.ops.compile_json_path_key(str(final_key))
        yield lhs_sql, tuple(lhs_params), path


def has_key_lookup_as_db2_for_i(self, compiler, connection, template=None):
    parts, params = [], []
    for lhs_sql, lhs_params, path in _has_key_paths(self, compiler, connection):
        path_sql, path_params = _json_path_sql(path)
        parts.append(f"JSON_EXISTS({lhs_sql}, {path_sql})")
        params.extend((*lhs_params, *path_params))
    return self._combine_sql_parts(parts), tuple(params)


HasKeyLookup.as_db2_for_i = has_key_lookup_as_db2_for_i


def key_transform_isnull_as_db2_for_i(self, compiler, connection):
    """``data__key__isnull=False`` is has_key; ``=True`` is "no such key, or no
    document" (as Django's Oracle code)."""
    sql, params = HasKeyOrArrayIndex(self.lhs.lhs, self.lhs.key_name).as_db2_for_i(
        compiler, connection
    )
    if not self.rhs:
        return sql, params
    lhs, lhs_params, _ = self.lhs.preprocess_lhs(compiler, connection)
    return f"(NOT {sql} OR {lhs} IS NULL)", (*params, *lhs_params)


KeyTransformIsNull.as_db2_for_i = key_transform_isnull_as_db2_for_i


def _normalized_json(param: str) -> str:
    """The JSON text of a marker as JSON_QUERY writes it (compact), so it
    compares equal to a key's JSON_QUERY (probe json_lookups)."""
    cast = string_type(utf16_length(param))
    return f"JSON_QUERY(JSON_OBJECT('value' VALUE CAST(%s AS {cast}) FORMAT JSON), '$.value')"


def _normalized_rhs(rhs: str, rhs_params) -> str:
    if rhs.count("%s") != len(rhs_params) or not all(isinstance(p, str) for p in rhs_params):
        return rhs
    return rhs % tuple(_normalized_json(param) for param in rhs_params)


def key_transform_exact_as_db2_for_i(self, compiler, connection):
    if isinstance(self.rhs, KeyTransform):
        return self.as_sql(compiler, connection)
    lhs, lhs_params = self.process_lhs(compiler, connection)
    rhs, rhs_params = self.process_rhs(compiler, connection)
    if tuple(rhs_params) == ("null",):
        # JSON null: the key exists and JSON_QUERY gives NULL for it.
        has_key = HasKeyOrArrayIndex(self.lhs.lhs, self.lhs.key_name)
        has_key_sql, has_key_params = has_key.as_db2_for_i(compiler, connection)
        # Unknown, not false, without the key (as on PostgreSQL), so that
        # exclude(data__key=None) leaves out documents without it too.
        return (
            f"CASE WHEN {has_key_sql} THEN 1 END = 1 AND {lhs} IS NULL",
            (*has_key_params, *lhs_params),
        )
    return f"{lhs} = {_normalized_rhs(rhs, rhs_params)}", (*lhs_params, *rhs_params)


KeyTransformExact.as_db2_for_i = key_transform_exact_as_db2_for_i


def key_transform_in_as_db2_for_i(self, compiler, connection):
    lhs, lhs_params = self.process_lhs(compiler, connection)
    rhs, rhs_params = self.process_rhs(compiler, connection)
    return f"{lhs} IN {_normalized_rhs(rhs, rhs_params)}", (*lhs_params, *rhs_params)


KeyTransformIn.as_db2_for_i = key_transform_in_as_db2_for_i


def json_in_as_db2_for_i(self, compiler, connection):
    """``data__in=[...]`` on the whole document (Django 6.1): both sides as
    compact JSON text, so whitespace in a stored document does not matter."""
    if isinstance(self.lhs, KeyTransform):
        return key_transform_in_as_db2_for_i(self, compiler, connection)
    lhs, lhs_params = self.process_lhs(compiler, connection)
    rhs, rhs_params = self.process_rhs(compiler, connection)
    lhs = f"JSON_QUERY({lhs}, '$')"
    return f"{lhs} IN {_normalized_rhs(rhs, rhs_params)}", (*lhs_params, *rhs_params)


if JSONIn is not None:
    JSONIn.as_db2_for_i = json_in_as_db2_for_i


def _is_number(value) -> bool:
    return isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)


def key_transform_numeric_as_db2_for_i(self, compiler, connection):
    """``data__key__lt=2``: the key as a number (DECFLOAT(34); NULL for any other
    value), as JSON text would compare as text (probe json_lookups)."""
    rhs, rhs_params = self.process_rhs(compiler, connection)
    if not (rhs_params and all(_is_number(param) for param in rhs_params)):
        return self.as_sql(compiler, connection)
    lhs, lhs_params, path = _key_transform_parts(self.lhs, compiler, connection)
    lhs = f"JSON_VALUE({lhs}, {path} RETURNING DECFLOAT(34))"
    operator = connection.operators[self.lookup_name] % rhs
    return f"{lhs} {operator}", (*lhs_params, *rhs_params)


for _lookup in (KeyTransformLt, KeyTransformLte, KeyTransformGt, KeyTransformGte):
    _lookup.as_db2_for_i = key_transform_numeric_as_db2_for_i


def _json_value_sql(expression, compiler) -> tuple[str, tuple]:
    """A JSONObject value or JSONArray element; JSON (a JSONField, a nested
    JSONObject or JSONArray) with FORMAT JSON, else it would be a string."""
    sql, params = compiler.compile(expression)
    if isinstance(expression._output_field_or_none, JSONField):
        sql += " FORMAT JSON"
    return sql, tuple(params)


def json_object_as_db2_for_i(self, compiler, connection, **extra_context):
    """``JSON_OBJECT((<key>) VALUE <value>, ... RETURNING NCLOB(1M))``; SQL NULL
    values are JSON null, Db2 for i's default (probe json_lookups)."""
    if not connection.features.has_json_object_function:
        return self.as_sql(compiler, connection, **extra_context)  # raises
    sources = self.get_source_expressions()
    parts, params = [], []
    for key, value in zip(sources[::2], sources[1::2], strict=True):
        key_sql, key_params = compiler.compile(key)
        value_sql, value_params = _json_value_sql(value, compiler)
        parts.append(f"({key_sql}) VALUE {value_sql}")
        params += [*key_params, *value_params]
    body = f"{', '.join(parts)} " if parts else ""
    return f"JSON_OBJECT({body}RETURNING NCLOB(1M))", tuple(params)


def json_array_as_db2_for_i(self, compiler, connection, **extra_context):
    """``JSON_ARRAY(<element>, ... NULL ON NULL RETURNING NCLOB(1M))``: Db2 for
    i leaves out NULL elements by default, Django keeps them as JSON null."""
    if not connection.features.supports_json_field:
        return self.as_sql(compiler, connection, **extra_context)  # raises
    parts, params = [], []
    for element in self.get_source_expressions():
        sql, element_params = _json_value_sql(element, compiler)
        parts.append(sql)
        params += element_params
    body = f"{', '.join(parts)} NULL ON NULL " if parts else ""
    return f"JSON_ARRAY({body}RETURNING NCLOB(1M))", tuple(params)


JSONObject.as_db2_for_i = json_object_as_db2_for_i
JSONArray.as_db2_for_i = json_array_as_db2_for_i
