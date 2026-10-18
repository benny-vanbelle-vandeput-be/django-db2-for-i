"""SQL compiler overrides, only where Db2 for i syntax requires them.

``DatabaseOperations.compiler_module`` points here. The insert, update,
delete and aggregate compilers are Django's, combined with this module's
``SQLCompiler`` (the pattern of Django's MySQL backend).

SELECT DISTINCT with emulated NULL ordering
-------------------------------------------
Db2 for i has no ``NULLS FIRST`` / ``NULLS LAST``, so Django orders by
``<expr> IS [NOT] NULL, <expr>`` instead. With ``SELECT DISTINCT``, Db2 for i
requires every ORDER BY expression in the select list (SQL0214), and an
expression that contains parameter markers never matches a selected one,
even with the same text (probe ``queries``, docs/IBMI_NOTES.md). So for
DISTINCT queries this compiler selects the predicate and the expression as
hidden columns (Django already does so for ORDER BY expressions that are not
selected) and orders by their positions: ``ORDER BY 4 ASC, 3 DESC``. Hidden
columns are trimmed from the results by Django (``has_extra_select``). The
predicate depends only on an expression that is selected too, so it never
changes which rows are distinct.

Exists() outside a search condition
-----------------------------------
Db2 for i accepts ``EXISTS (...)`` only directly as a search condition of
WHERE / HAVING: not in the select list, GROUP BY or ORDER BY, and not inside
``CASE WHEN`` (also not in a WHERE clause; probe ``queries``). There this
compiler renders ``Exists()`` as ``((<subquery>) IS NOT NULL)``: Django's
Exists subquery is ``SELECT 1 ... FETCH FIRST 1 ROWS ONLY``, so it stops at
the first row like EXISTS. A ``WhereNode`` is a search condition when it is
the query's WHERE / HAVING / QUALIFY, or a WhereNode directly inside one;
``NOT`` and Django's ``Exact(<condition>, True)`` wrapper of
``filter(<condition>)`` keep the context. Any other expression (a select column, ``When``, a
lookup, ...) switches the context off for everything below it.

Predicates as select columns
----------------------------
``supports_boolean_expr_in_select_clause`` is on (BOOLEAN results), but a
select-list predicate with an untyped parameter marker fails with SQL0418
(``SELECT X < ?``; probe ``queries``), e.g. ``annotate(b=Q(pages__lt=100))``.
A lookup or ``Q`` compiled directly by the compiler (a select column, a
GROUP BY item, an UPDATE value) is therefore written as ``CASE WHEN
<predicate> THEN TRUE ELSE FALSE END``, still a BOOLEAN value. Nested
predicates and search conditions are not wrapped; ``Exists()`` needs no
wrapper (its first-row form has no untyped marker).
"""

from __future__ import annotations

from django.db.models import IntegerField
from django.db.models.expressions import (
    Exists,
    ExpressionWrapper,
    NegatedExpression,
    OrderBy,
    RawSQL,
    Ref,
)
from django.db.models.lookups import Exact, IsNull, Lookup
from django.db.models.sql import compiler
from django.db.models.sql.where import WhereNode

# Exists() as a value: the first-row subquery, NULL when there is no row.
EXISTS_AS_VALUE = "((%(subquery)s) IS NOT NULL)"


def _exists_selecting_literal(node: Exists) -> Exists:
    """A copy of ``node`` whose subquery selects ``1``, not a parameter marker.

    Django's Exists subquery selects Value(1), which the backend renders as
    ``CAST(? AS INTEGER)``; a parameter marker in the select list of an EXISTS
    subquery fails in the IBM i host server ("Error in host server data
    stream", 30187; probe ``queries``).
    """
    node = node.copy()  # also clones the query
    if "a" in node.query.annotations:
        node.query.annotations["a"] = RawSQL("1", (), output_field=IntegerField())
    return node


def _emulated_nulls_predicate(order_by, sql: str, inner_sql: str) -> bool | None:
    """IsNull's rhs if ``sql`` starts with Django's NULL ordering emulation."""
    if not isinstance(order_by, OrderBy):
        return None
    if sql.startswith(f"{inner_sql} IS NULL, "):
        return True
    if sql.startswith(f"{inner_sql} IS NOT NULL, "):
        return False
    return None


def _is_condition_wrapper(node) -> bool:
    """Nodes that render a condition as a condition: ``NOT <condition>``, and
    Django's filter(<condition>) form ``Exact(<condition>, True/False)``
    (rendered as ``<condition>`` or ``NOT <condition>``)."""
    if isinstance(node, NegatedExpression):
        return True
    return (
        isinstance(node, Exact)
        and isinstance(node.rhs, bool)
        and getattr(node.lhs, "conditional", False)
    )


def _is_value_predicate(node) -> bool:
    """A lookup or Q (or a wrapper around one): a predicate that may hold untyped markers."""
    if isinstance(node, (Lookup, WhereNode)):
        return True
    # NegatedExpression is an ExpressionWrapper too.
    if isinstance(node, ExpressionWrapper):
        return _is_value_predicate(node.expression)
    return False


class SQLCompiler(compiler.SQLCompiler):
    # True while compiling a search condition of WHERE / HAVING / QUALIFY.
    _in_condition = False
    # Nesting depth of compile(): 0 for what the compiler compiles directly.
    _depth = 0

    def compile(self, node):
        if isinstance(node, Exists):
            node = _exists_selecting_literal(node)
            if not self._in_condition:
                return node.as_sql(self, self.connection, template=EXISTS_AS_VALUE)
        outer = self._in_condition
        self._in_condition = (outer and _is_condition_wrapper(node)) or (
            isinstance(node, WhereNode) and (outer or self._is_query_condition(node))
        )
        as_value = self._depth == 0 and not self._in_condition and _is_value_predicate(node)
        self._depth += 1
        try:
            sql, params = super().compile(node)
        finally:
            self._in_condition = outer
            self._depth -= 1
        if as_value:
            return f"CASE WHEN {sql} THEN TRUE ELSE FALSE END", params
        return sql, params

    def _is_query_condition(self, node) -> bool:
        conditions = (
            getattr(self, "where", None),
            getattr(self, "having", None),
            getattr(self, "qualify", None),
            self.query.where,
        )
        return any(node is condition for condition in conditions)

    def pre_sql_setup(self, with_col_aliases=False):
        self._null_ordering_positions = {}
        extra_select, order_by, group_by = super().pre_sql_setup(with_col_aliases)
        if self._null_ordering_positions:
            order_by = [self._by_position(item) for item in order_by]
        return extra_select, order_by, group_by

    def _by_position(self, item):
        expr, (_sql, _params, is_ref) = item
        positions = self._null_ordering_positions.get(id(expr))
        if positions is None:
            return item
        predicate, value = positions
        direction = "DESC" if expr.descending else "ASC"
        return expr, (f"{predicate} ASC, {value} {direction}", [], is_ref)

    def get_extra_select(self, order_by, select):
        if not self.query.distinct or self.query.distinct_fields:
            return super().get_extra_select(order_by, select)
        extra_select = []
        selected = [t[1] for t in select]

        def position(expression, sql, params):
            """1-based select list position of (sql, params); added if missing."""
            if (sql, params) not in selected:
                selected.append((sql, params))
                extra_select.append((expression, (sql, params), None))
            return selected.index((sql, params)) + 1

        for expr, (sql, params, is_ref) in order_by:
            inner_sql, inner_params = self.compile(expr.expression)
            is_null = _emulated_nulls_predicate(expr, sql, inner_sql)
            if is_null is None:
                # Django's rule: the expression without its direction.
                without_ordering = self.ordering_parts.search(sql)[1]
                if not is_ref:
                    position(expr, without_ordering, params)
                continue
            source = expr.expression
            if isinstance(source, Ref):
                source = source.source  # group by the expression, not the alias
            keyword = "IS NULL" if is_null else "IS NOT NULL"
            self._null_ordering_positions[id(expr)] = (
                position(IsNull(source, is_null), f"{inner_sql} {keyword}", inner_params),
                position(source, inner_sql, inner_params),
            )
        return extra_select


class SQLInsertCompiler(compiler.SQLInsertCompiler, SQLCompiler):
    pass


class SQLDeleteCompiler(compiler.SQLDeleteCompiler, SQLCompiler):
    pass


class SQLUpdateCompiler(compiler.SQLUpdateCompiler, SQLCompiler):
    pass


class SQLAggregateCompiler(compiler.SQLAggregateCompiler, SQLCompiler):
    pass
