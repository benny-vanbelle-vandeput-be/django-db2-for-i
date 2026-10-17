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
"""

from __future__ import annotations

from django.db.models.expressions import OrderBy, Ref
from django.db.models.lookups import IsNull
from django.db.models.sql import compiler


def _emulated_nulls_predicate(order_by, sql: str, inner_sql: str) -> bool | None:
    """IsNull's rhs if ``sql`` starts with Django's NULL ordering emulation."""
    if not isinstance(order_by, OrderBy):
        return None
    if sql.startswith(f"{inner_sql} IS NULL, "):
        return True
    if sql.startswith(f"{inner_sql} IS NOT NULL, "):
        return False
    return None


class SQLCompiler(compiler.SQLCompiler):
    def pre_sql_setup(self, with_col_aliases=False):
        self._null_ordering_positions = {}
        extra_select, order_by, group_by = super().pre_sql_setup(with_col_aliases)
        if self._null_ordering_positions:
            order_by = [self._by_position(item) for item in order_by]
        return extra_select, order_by, group_by

    def _by_position(self, item):
        expr, (sql, params, is_ref) = item
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
