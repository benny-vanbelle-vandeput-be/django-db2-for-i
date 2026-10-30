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
<predicate> THEN TRUE WHEN NOT (<predicate>) THEN FALSE END``, still a BOOLEAN
value, and NULL when the predicate is UNKNOWN (as on PostgreSQL; issue #75).
The predicate's parameters are sent twice. ``NOT (<predicate>)`` is
three-valued because a BOOLEAN value used as a condition is always a
comparison (``flag = TRUE``, expressions.py); probe ``selected_predicates``
checked the form for every kind of predicate, with subqueries evaluated
twice. Nested predicates and search conditions are not wrapped; ``Exists()``
needs no wrapper (its first-row form has no untyped marker).

GROUP BY an expression with parameters, or nested in a select expression
----------------------------------------------------------------------
Db2 for i matches a grouped expression only when it is selected as a whole
and has no parameter marker: ``SELECT MOD(X, ?) ... GROUP BY MOD(X, ?)``
fails (30101, markers never match), and so does ``SELECT X + X + 1 ... GROUP
BY X + X`` (SQL0122) or ``LEAST(MIN(X), <grouped>)``; ``GROUP BY`` an alias or
a position is not allowed (probe ``queries``). For such grouped expressions
this compiler computes them per row in a LATERAL derived table and groups by
its columns::

    SELECT G.G1, COUNT(*) FROM <tables and joins>
    CROSS JOIN LATERAL (SELECT MOD(X, ?) AS G1 FROM SYSIBM.SYSDUMMY1) AS G
    WHERE ... GROUP BY G.G1

Everything else (joins, WHERE, aggregates, HAVING, ORDER BY) stays as it
is; wherever the grouped expression is compiled it becomes ``G.G1``.
Grouping by columns, and by expressions without parameters that are only
selected as a whole, keeps its SQL.

Conditions of constraints and indexes
-------------------------------------
For a ``CheckConstraint`` (and a condition of a ``UniqueConstraint`` or an
``Index``) Django builds a WhereNode on a ``Query(alias_cols=False)`` and
calls its ``as_sql()`` directly, so its predicates reach ``compile()`` at
depth 0, where they would be wrapped as select-list values. They are search
conditions (``CHECK (<search condition>)``), and their parameters are
inlined as literals, so they stay predicates: at depth 0 of such a query
the compiler is in a search condition. Db2 for i has no generated columns
with an expression, the other schema use of these queries.
"""

from __future__ import annotations

from django.db import NotSupportedError
from django.db.models import IntegerField
from django.db.models.constants import OnConflict
from django.db.models.expressions import (
    Col,
    ColPairs,
    Exists,
    ExpressionWrapper,
    NegatedExpression,
    OrderBy,
    RawSQL,
    Ref,
)
from django.db.models.lookups import Exact, In, IsNull, Lookup
from django.db.models.sql import compiler
from django.db.models.sql.query import Query
from django.db.models.sql.where import WhereNode

from .expressions import NegatedValue, renders_as_predicate

# Exists() as a value: the first-row subquery, NULL when there is no row.
EXISTS_AS_VALUE = "((%(subquery)s) IS NOT NULL)"
# Django's wrapper of an ordered compound query, and ours.
COMPOUND_WRAPPER = "SELECT * FROM ( "
LATERAL_COMPOUND_WRAPPER = "SELECT * FROM LATERAL ( "
# The LATERAL derived table of grouped expressions, and its columns G1, G2, ...
GROUPING_TABLE = "DJDB2I_GROUPING"
# The derived table of a rewritten IN (subquery) (_in_subquery_as_value).
IN_TABLE = '"DJDB2I_IN"'


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


def _is_in_subquery(node) -> bool:
    return isinstance(node, In) and isinstance(node.rhs, Query)


def _single_in_subquery(node) -> bool:
    """``Q(x__in=<subquery>)``: a WhereNode holding just that lookup."""
    return (
        isinstance(node, WhereNode)
        and not node.negated
        and len(node.children) == 1
        and _is_in_subquery(node.children[0])
    )


def _hashable(node) -> bool:
    try:
        hash(node)
    except TypeError:
        return False
    return True


class SQLCompiler(compiler.SQLCompiler):
    # True while compiling a search condition of WHERE / HAVING / QUALIFY.
    _in_condition = False
    # Nesting depth of compile(): 0 for what the compiler compiles directly.
    _depth = 0
    # Grouped expression -> its column in the LATERAL grouping table.
    _grouping_columns: dict = {}
    # The lookup being compiled as a search condition, while it renders.
    _condition_lookup = None

    def compile(self, node):
        if self._grouping_columns and _hashable(node) and node in self._grouping_columns:
            return self._grouping_columns[node], []
        # A lookup that renders as another lookup on the same lhs (RelatedIn as
        # TupleIn for a multi-column relation) keeps the search condition.
        # The condition of a constraint or index (module docstring).
        schema_condition = self._depth == 0 and not self.query.alias_cols
        in_condition = (
            self._in_condition
            or schema_condition
            or (
                isinstance(node, Lookup)
                and self._condition_lookup is not None
                and node.lhs is self._condition_lookup.lhs
            )
        )
        if _is_in_subquery(node) and not in_condition:
            if self._depth == 0:  # selected as it is: the three-valued BOOLEAN itself
                return self._in_subquery_case(node)
            return self._in_subquery_as_value(node)
        if isinstance(node, NegatedExpression) and not renders_as_predicate(node.expression):
            # NOT <BOOLEAN value> is TRUE for NULL on Db2 for i (also in WHERE).
            node = NegatedValue(node.expression)
        if isinstance(node, Exists):
            node = _exists_selecting_literal(node)
            if not in_condition:
                return node.as_sql(self, self.connection, template=EXISTS_AS_VALUE)
        outer, outer_lookup = self._in_condition, self._condition_lookup
        self._in_condition = (in_condition and _is_condition_wrapper(node)) or (
            isinstance(node, WhereNode) and (in_condition or self._is_query_condition(node))
        )
        self._condition_lookup = node if in_condition and isinstance(node, Lookup) else None
        as_value = (
            self._depth == 0
            and not self._in_condition
            and not schema_condition
            and _is_value_predicate(node)
        )
        if as_value and _single_in_subquery(node):
            # Q(x__in=<subquery>) as a value: the rewrite's BOOLEAN is the value
            # (its subqueries once, not twice through CASE WHEN p ... NOT (p)).
            self._in_condition, self._condition_lookup = outer, outer_lookup
            return self._in_subquery_case(node.children[0])
        self._depth += 1
        try:
            sql, params = super().compile(node)
        finally:
            self._in_condition, self._condition_lookup = outer, outer_lookup
            self._depth -= 1
        if as_value:
            # NULL when the predicate is UNKNOWN (no ELSE); NOT of a predicate is
            # three-valued (boolean values are comparisons by now, expressions.py).
            return f"CASE WHEN {sql} THEN TRUE WHEN NOT ({sql}) THEN FALSE END", [*params, *params]
        return sql, params

    def _in_subquery_as_value(self, lookup: In):
        """``x IN (subquery)`` outside a search condition, where Db2 for i rejects
        it (inside CASE WHEN: SQL0115; probes ``in_subquery``, ``tuple_in``): the
        three-valued BOOLEAN of ``_in_subquery_case`` compared with TRUE."""
        sql, params = self._in_subquery_case(lookup)
        return f"{sql} = TRUE", params

    def _in_subquery_case(self, lookup: In):
        """The three-valued BOOLEAN of ``x IN (subquery)``.

        TRUE if a row matches on every column; else NULL if a row has no
        column that is definitely unequal (equal, or NULL on either side);
        else FALSE. ``x`` is one column, or the columns of a multi-column
        relation (``(a, b) IN (subquery)``)."""
        if isinstance(lookup.lhs, ColPairs):
            xs = [self.compile(col) for col in lookup.lhs]
        else:
            xs = [lookup.process_lhs(self, self.connection)]
        subquery, subquery_params = lookup.process_rhs(self, self.connection)
        names = [f"V{number}" for number in range(1, len(xs) + 1)]
        rows = f"LATERAL {subquery} AS {IN_TABLE} ({', '.join(names)})"
        equal, maybe = [], []
        equal_params, maybe_params = [], []
        for name, (x, x_params) in zip(names, xs, strict=True):
            v = f"{IN_TABLE}.{name}"
            equal.append(f"{v} = {x}")
            equal_params.extend(x_params)
            maybe.append(f"({v} = {x} OR {v} IS NULL OR {x} IS NULL)")
            maybe_params.extend((*x_params, *x_params))
        match = f"(SELECT 1 FROM {rows} WHERE {' AND '.join(equal)} FETCH FIRST 1 ROWS ONLY)"
        unknown = f"(SELECT 1 FROM {rows} WHERE {' AND '.join(maybe)} FETCH FIRST 1 ROWS ONLY)"
        sql = (
            f"(CASE WHEN {match} IS NOT NULL THEN TRUE "
            f"WHEN {unknown} IS NOT NULL THEN NULL ELSE FALSE END)"
        )
        return sql, (*subquery_params, *equal_params, *subquery_params, *maybe_params)

    def as_sql(self, with_limits=True, with_col_aliases=False):
        sql, params = super().as_sql(with_limits, with_col_aliases)
        if self.query.combinator and sql.startswith(COMPOUND_WRAPPER):
            sql = LATERAL_COMPOUND_WRAPPER + sql.removeprefix(COMPOUND_WRAPPER)
        return sql, params

    def _is_query_condition(self, node) -> bool:
        conditions = (
            getattr(self, "where", None),
            getattr(self, "having", None),
            getattr(self, "qualify", None),
            self.query.where,
            getattr(self, "outer_where", None),
        )
        return any(node is condition for condition in conditions)

    def pre_sql_setup(self, with_col_aliases=False):
        self._null_ordering_positions = {}
        self._grouping_columns = {}
        self._grouping_columns = self._laterally_grouped()
        extra_select, order_by, group_by = super().pre_sql_setup(with_col_aliases)
        if self._null_ordering_positions:
            order_by = [self._by_position(item) for item in order_by]
        return extra_select, order_by, group_by

    def _laterally_grouped(self) -> dict:
        """The grouped expressions to compute in the LATERAL grouping table."""
        if self.query.group_by is None:
            return {}
        annotations = list(self.query.annotation_select.values())
        # Django groups by query.group_by (values().annotate()) and by every
        # selected non-aggregate annotation (get_group_by()).
        candidates = list(self.query.group_by) if isinstance(self.query.group_by, tuple) else []
        for annotation in annotations:
            if not annotation.contains_aggregate:
                candidates.extend(annotation.get_group_by_cols())
        grouped = []
        for expr in candidates:
            if not hasattr(expr, "as_sql"):
                expr = self.query.resolve_ref(expr)
            source = expr.source if isinstance(expr, Ref) else expr
            if not isinstance(source, Col) and _hashable(source) and source not in grouped:
                grouped.append(source)
        lateral = [
            source
            for source in grouped
            if not source.contains_aggregate
            and (self.compile(source)[1] or self._nested(source, annotations))
        ]
        table = self.connection.ops.quote_name(GROUPING_TABLE)
        return {
            source: f"{table}.{self.connection.ops.quote_name(f'G{number}')}"
            for number, source in enumerate(lateral, start=1)
        }

    @staticmethod
    def _nested(source, annotations) -> bool:
        """True if ``source`` is part of another selected expression."""
        for annotation in annotations:
            if annotation is source or annotation == source:
                continue
            if any(node is not annotation and node == source for node in annotation.flatten()):
                return True
        return False

    def get_from_clause(self):
        result, params = super().get_from_clause()
        if self._grouping_columns:
            columns, saved = [], self._grouping_columns
            self._grouping_columns = {}  # compile the expressions themselves
            try:
                for source, column in saved.items():
                    sql, source_params = self.compile(source)
                    columns.append(f"{sql} AS {column.rsplit('.', 1)[1]}")
                    params.extend(source_params)
            finally:
                self._grouping_columns = saved
            table = self.connection.ops.quote_name(GROUPING_TABLE)
            result.append(
                f"CROSS JOIN LATERAL (SELECT {', '.join(columns)} FROM SYSIBM.SYSDUMMY1) AS {table}"
            )
        return result, params

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
    _assembled = None

    def assemble_as_sql(self, fields, value_rows):
        """Django's placeholders and parameters, kept for _merge_sql(): the
        columns Django leaves out (6.1 drops a db_default column that is
        DEFAULT in every row) are already gone here, on every version."""
        placeholder_rows, param_rows = super().assemble_as_sql(fields, value_rows)
        self._assembled = (fields, placeholder_rows, param_rows)
        return placeholder_rows, param_rows

    def as_sql(self):
        """Db2 for i has no ``INSERT ... RETURNING``: the insert is wrapped in
        ``SELECT <columns> FROM FINAL TABLE (INSERT ...)``, which returns the
        inserted rows, generated identities and column defaults included
        (probe ``qtemp_returning``). Several rows come back in input order
        with ``ORDER BY INPUT SEQUENCE``. ``DatabaseOperations`` returns an
        empty returning clause, so Django builds the plain ``INSERT`` here.
        ``bulk_create()`` with ignore_conflicts / update_conflicts is a
        ``MERGE`` instead (_merge_sql())."""
        if self.query.on_conflict:
            return self._merge_sql()
        statements = super().as_sql()
        if not (self.returning_fields and self.connection.features.can_return_columns_from_insert):
            return statements
        ((sql, params),) = statements
        qn = self.connection.ops.quote_name
        columns = ", ".join(qn(field.column) for field in self.returning_fields)
        order = " ORDER BY INPUT SEQUENCE" if len(self.query.objs) > 1 else ""
        return [(f"SELECT {columns} FROM FINAL TABLE ({sql}){order}", params)]

    def execute_sql(self, returning_fields=None):
        """A MERGE returns no rows (FINAL TABLE takes only INSERT, probe
        qtemp_merge): bulk_create(update_conflicts=True) leaves the keys of
        the objects unset, which Django accepts for a conflict insert."""
        if not self.query.on_conflict:
            return super().execute_sql(returning_fields)
        self.returning_fields = None
        with self.connection.cursor() as cursor:
            for sql, params in self.as_sql():
                cursor.execute(sql, params)
        return []

    def _merge_sql(self):
        """``MERGE INTO <table> AS TGT USING (VALUES ...) AS SRC (<columns>) ON <key
        match> [WHEN MATCHED THEN UPDATE SET ...] WHEN NOT MATCHED THEN
        INSERT ...`` (probe qtemp_merge). Db2 for i has no ON CONFLICT.

        The source's parameter markers are cast (untyped ones: SQL0584).
        ignore_conflicts matches every unique key whose columns are inserted
        (OR); update_conflicts matches its unique_fields. A key with a NULL
        never matches, as NULLs in a unique key are distinct (step D). The
        same key twice in one batch is refused (SQL0803 / SQL0788), where
        PostgreSQL skips it."""
        self.returning_fields = None
        (plain,) = super().as_sql()
        fields, placeholder_rows, param_rows = self._assembled
        if fields == [None]:
            return [plain]
        qn = self.connection.ops.quote_name
        opts = self.query.get_meta()
        columns = [field.column for field in fields]
        if self.query.on_conflict == OnConflict.UPDATE:
            keys = [[field.column for field in self.query.unique_fields]]
        else:
            keys = [key for key in self._unique_keys(opts) if set(key) <= set(columns)]
        if not keys:
            return [plain]
        rows = ", ".join(
            "(%s)" % ", ".join(self._cast(field, sql) for field, sql in zip(fields, row))
            for row in placeholder_rows
        )
        on = " OR ".join(
            "(%s)" % " AND ".join(f"TGT.{qn(c)} = SRC.{qn(c)}" for c in key) for key in keys
        )
        names = ", ".join(qn(c) for c in columns)
        sql = f"MERGE INTO {qn(opts.db_table)} AS TGT USING (VALUES {rows}) AS SRC ({names}) ON {on}"
        if self.query.on_conflict == OnConflict.UPDATE:
            assignments = ", ".join(
                f"TGT.{qn(field.column)} = SRC.{qn(field.column)}" for field in self.query.update_fields
            )
            sql += f" WHEN MATCHED THEN UPDATE SET {assignments}"
        values = ", ".join(f"SRC.{qn(c)}" for c in columns)
        sql += f" WHEN NOT MATCHED THEN INSERT ({names}) VALUES ({values})"
        return [(sql, tuple(p for row in param_rows for p in row))]

    def _cast(self, field, sql):
        if sql == "DEFAULT":
            raise NotSupportedError(
                "Db2 for i backend: bulk_create() with ignore_conflicts or update_conflicts "
                "cannot write DEFAULT for a db_default field (MERGE takes no DEFAULT in its "
                "source); give the field a value."
            )
        return f"CAST({sql} AS {field.cast_db_type(self.connection)})"

    @staticmethod
    def _unique_keys(opts):
        """The column sets of the model's unconditional unique keys."""
        keys = [[field.column for field in getattr(opts.pk, "fields", None) or [opts.pk]]]
        keys += [[field.column] for field in opts.local_concrete_fields if field.unique]
        keys += [
            [opts.get_field(name).column for name in fields] for fields in opts.unique_together
        ]
        keys += [
            [opts.get_field(name).column for name in constraint.fields]
            for constraint in opts.total_unique_constraints
        ]
        unique = []
        for key in keys:
            if key not in unique:
                unique.append(key)
        return unique


class SQLDeleteCompiler(compiler.SQLDeleteCompiler, SQLCompiler):
    outer_where = None

    def _as_sql(self, query):
        # A delete that references its own table compiles the WHERE of a new
        # outer query (pk IN (SELECT * FROM (...) subquery)): a search
        # condition too, not a value.
        self.outer_where = query.where
        return super()._as_sql(query)


class SQLUpdateCompiler(compiler.SQLUpdateCompiler, SQLCompiler):
    pass


class SQLAggregateCompiler(compiler.SQLAggregateCompiler, SQLCompiler):
    pass
