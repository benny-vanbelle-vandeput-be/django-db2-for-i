"""DatabaseFeatures: optional Django features, conservative by default.

Every optional flag starts as False and is enabled only when backed by
passing Django tests. Flags ask ServerCapabilities, never compare versions.

Every flag that Django 6.1 defaults to True is listed here explicitly, so
enabling one is a visible one-line change.
"""

from django.db.backends.base.features import BaseDatabaseFeatures
from django.utils.functional import cached_property

from django_db2_for_i import compat

# Fixed reasons for skips and expected failures, so related entries can be
# found and counted (docs/DECISIONS.md).
REASON_TIME_FRACTIONS = "Db2 for i TIME has no fractional seconds"
REASON_IDENTITY_RESTART_DEFERRED = "identity restart deferred in TestCase (SQL0910)"
REASON_UNTYPED_NULL = "Db2 for i rejects an untyped NULL as an expression (SQL0206)"
REASON_TYPED_PARAMETER_MARKERS = (
    "parameter markers are typed: untyped markers on both sides of a comparison "
    "compare wrongly on Db2 for i"
)


REASON_UNTYPED_RAW_SQL_PARAMETER = (
    "a bare %s in RawSQL or extra() is an untyped parameter marker, which Db2 for i rejects in the "
    "select list (SQL0418); cast it in the SQL"
)
REASON_PENDING_ROW_CHANGES = (
    "null=True to null=False with a default sets the NULLs (UPDATE) and then runs SET NOT NULL "
    "in the same transaction; Db2 for i refuses an ALTER TABLE on a table with row changes in "
    "the transaction (SQL0910)"
)
REASON_NO_COLUMN_RENAME = "Db2 for i has no statement to rename a column (IBM i 7.5 and 7.6)"
REASON_TYPE_NOT_IN_PLACE = "Db2 for i cannot change this column type in place (SQL0190)"


class DatabaseFeatures(BaseDatabaseFeatures):
    minimum_database_version = (7, 5)

    # --- Facts about Db2 for i (not optional features) -----------------------

    # Never let Django's default cached_property run: it creates a test table
    # to find out. Commitment control works on journaled tables (see
    # docs/IBMI_NOTES.md).
    supports_transactions = True
    # ROLLBACK undoes every DDL form the schema editor writes, none commits
    # implicitly, and a transaction stays usable after a CPA32B2 cancel
    # (probe lib_rollback_ddl, phase 4 item 11a): an atomic migration runs in
    # one transaction and leaves nothing behind when it fails.
    can_rollback_ddl = True
    # An error does not abort the transaction (unlike PostgreSQL).
    atomic_transactions = False
    # SELECT without FROM is not allowed.
    bare_select_suffix = " FROM SYSIBM.SYSDUMMY1"
    # LIKE is used for pattern lookups.
    pattern_lookup_needs_param_pattern = True
    # Datetimes are stored naive (no TIMESTAMP WITH TIME ZONE type); see
    # DatabaseOperations for the UTC conversion with USE_TZ.
    supports_timezones = False
    has_zoneinfo_database = False
    # Constraints are checked per statement; nothing is deferrable.
    supports_forward_references = False
    # Django's %s placeholders are converted to ?; dict params are refused.
    supports_paramstyle_pyformat = False
    # PUB400 limits connections per client.
    test_db_allows_multiple_connections = False
    # DDL is not parameterized: defaults are written as literals.
    requires_literal_defaults = True
    # Columns are nullable unless NOT NULL is given; no bare NULL keyword.
    implied_column_null = True

    @cached_property
    def has_native_boolean_field(self) -> bool:
        return self.connection.capabilities.has_boolean_type

    # --- Optional features, all off until backed by passing Django tests -----

    # Savepoints (nested atomic()): SAVEPOINT ... ON ROLLBACK RETAIN CURSORS,
    # RELEASE SAVEPOINT, ROLLBACK TO SAVEPOINT (probe probe_savepoints).
    uses_savepoints = True
    can_release_savepoints = True

    # Queries
    allows_group_by_lob = False
    allows_group_by_select_index = False
    update_can_self_select = False
    delete_can_self_reference_subquery = False
    # IN (SELECT ... FETCH FIRST n ROWS ONLY), also with OFFSET (probe queries).
    allow_sliced_subqueries_with_in = True
    # A scalar subquery in GROUP BY works (probe queries).
    supports_subqueries_in_group_by = True
    # ANY_VALUE aggregate (probe queries).
    supports_any_value = True
    # StringAgg(order_by=...) as LISTAGG(...) WITHIN GROUP (ORDER BY ...) (probe listagg).
    supports_aggregate_order_by_clause = True
    ignores_unnecessary_order_by_in_subqueries = False
    # REGEXP_LIKE (ICU) supports backreferences (probe queries).
    supports_regex_backreferencing = True
    supports_date_lookup_using_string = False
    supports_order_by_nulls_modifier = False
    # NULL sorts as the largest value: last ascending, first descending (probe
    # queries). order_by_nulls_first stays False (NULLs are not first ascending).
    nulls_order_largest = True
    # UNION / UNION ALL (probe queries).
    supports_select_union = True
    # Exact date/time/datetime subtraction in microseconds (operations.py, probe durations).
    supports_temporal_subtraction = True
    # The ORDER BY of a compound query accepts only result columns, not
    # expressions such as Django's NULL ordering emulation (SQL0214); an
    # ordered compound query is wrapped: SELECT * FROM (<compound>) ORDER BY.
    requires_compound_order_by_subquery = True
    # INTERSECT / EXCEPT (without ALL, which Db2 for i rejects; Django uses neither ALL).
    supports_select_intersection = True
    supports_select_difference = True
    # Parts of a compound query in parentheses, each with its own ORDER BY and
    # OFFSET / FETCH FIRST, also inside subqueries and nested (probes queries,
    # compound_parts).
    supports_parentheses_in_compound = True
    supports_slicing_ordering_in_compound = True
    supports_select_for_update_with_limit = False
    supports_aggregate_distinct_multiple_argument = False
    supports_bit_aggregations = False
    supports_default_in_bit_aggregations = False
    supports_cast_with_precision = False
    supports_default_in_lead_lag = False
    # Predicates are valid in the select list and GROUP BY on 7.5 (BOOLEAN);
    # Exists() is rendered as a first-row subquery there (compiler.py).
    supports_boolean_expr_in_select_clause = True
    supports_comparing_boolean_expr = False
    # Row values: (a, b) = (x, y) and (a, b) IN (subquery); IN lists and
    # >, >=, <, <= in Django's expanded form (expressions.py, probe tuple_lookups).
    supports_tuple_lookups = True
    supports_tuple_comparison_against_subquery = False

    # Inserts and fetching
    can_use_chunked_reads = False
    has_bulk_insert = False
    allows_auto_pk_0 = False
    supports_default_keyword_in_insert = False
    supports_default_keyword_in_bulk_insert = False
    supports_ignore_conflicts = False

    # Schema and constraints
    supports_nullable_unique_constraints = False
    supports_partially_nullable_unique_constraints = False
    supports_sequence_reset = False
    # Foreign keys (phase 4 step C): separate ALTER TABLE ... ADD CONSTRAINT
    # statements (decision 4), violations SQL0530-0532 -> IntegrityError
    # (drivers/base.py), the column types must match exactly (SQL0538), and a
    # SET DATA TYPE on a foreign key's column silently stops enforcing it, so
    # Django's drop and re-add around a type change matters (IBMI_NOTES,
    # "Foreign keys through the schema editor"). Nothing is deferrable.
    supports_foreign_keys = True
    can_create_inline_fk = False
    # A foreign key column ends up with an index: Db2 for i creates none for
    # the constraint, so the index is Django's own (decision 5, amended
    # 2026-10-25). Django reads this flag only in its tests.
    indexes_foreign_keys = True
    # CHECK constraints (phase 4 item 11): the column check of the positive
    # integer fields and model CheckConstraints. A violation is SQL0545 with
    # SQLSTATE HY000, mapped to IntegrityError by its SQLCODE (#96).
    supports_column_check_constraints = True
    supports_table_check_constraints = True
    supports_expression_defaults = False
    supports_index_on_text_field = False
    supports_partial_indexes = False
    supports_functions_in_partial_indexes = False
    supports_expression_indexes = False
    allows_multiple_constraints_on_same_fields = False
    supports_collation_on_charfield = False
    supports_collation_on_textfield = False
    supports_non_deterministic_collations = False
    supports_alter_generated_column_data_type = False
    supports_on_delete_db_cascade = False
    supports_on_delete_db_default = False
    supports_on_delete_db_null = False
    # RENAME INDEX (probe 24). Combined alters stay off: Db2 for i accepts
    # several clauses in one ALTER TABLE only without commas, and Django joins
    # them with ", ".
    can_rename_index = True

    # Introspection
    can_introspect_default = True
    can_introspect_foreign_keys = True
    can_introspect_check_constraints = True
    supports_index_column_ordering = False
    supports_inspectdb = False

    @cached_property
    def introspected_field_types(self) -> dict[str, str]:
        """What introspection finds for a field the backend created: no unsigned
        types (Positive*), DurationField as BIGINT, the IP fields as VARCHAR."""
        return {
            **super().introspected_field_types,
            "DurationField": "BigIntegerField",
            "GenericIPAddressField": "CharField",
            "PositiveBigIntegerField": "BigIntegerField",
            "PositiveIntegerField": "IntegerField",
            "PositiveSmallIntegerField": "SmallIntegerField",
        }

    # JSON
    supports_json_field = False
    can_introspect_json_field = False
    supports_primitives_in_json_field = False
    supports_json_field_contains = False
    has_json_object_function = False
    supports_json_negative_indexing = False

    # Known failures of Django's own test suite, grouped by one fixed reason
    # string each (see the REASON_* constants). Filled from real runs (phase 1,
    # step 9).
    # Skipped, not expected failures, on every supported Django version.
    django_test_skips: dict[str, set[str]] = {
        # Repointing an m2m renames the through table's column (tagm2mtest_id
        # to uniquetest_id). As expected failures they still error: the
        # tearDown drops the through table the test never created (SQL0204),
        # and unittest then drops the expected failure. They become expected
        # failures again if the table-rebuild decision (phase 4, step C) ever
        # adds column renames.
        REASON_NO_COLUMN_RENAME: {
            "schema.tests.SchemaTests.test_m2m_repoint",
            "schema.tests.SchemaTests.test_m2m_repoint_custom",
            "schema.tests.SchemaTests.test_m2m_repoint_inherited",
        },
    }
    expected_failures: dict[str, set[str]] = {
        # Subtracts from a TimeField stored with microseconds (TIME has none).
        REASON_TIME_FRACTIONS: {
            "expressions.tests.FTimeDeltaTests.test_time_subtraction",
        },
        REASON_IDENTITY_RESTART_DEFERRED: set(),
        # A custom transform with template "NULL" gives WHERE NULL IS NULL.
        REASON_UNTYPED_NULL: {
            "lookup.tests.LookupTests.test_exact_none_transform",
        },
        # Asserts the SQL text "2 > 1"; the backend casts both values
        # (CAST(? AS INTEGER) > CAST(? AS INTEGER)), see docs/DECISIONS.md.
        REASON_TYPED_PARAMETER_MARKERS: {
            "lookup.tests.LookupTests.test_lookup_direct_value_rhs_unwrapped",
        },
        # RawSQL("%s", ["value"]): user SQL the backend does not rewrite.
        REASON_UNTYPED_RAW_SQL_PARAMETER: {
            "expressions.tests.BasicExpressionsTests.test_annotate_values_filter",
            # extra(select={"foo": "%s"}, select_params=(1,)).
            "queries.tests.Queries1Tests.test_tickets_1878_2939",
            # RawSQL("%s", ...) annotation.
            "queries.test_query.TestQueryNoModel.test_rawsql_annotation",
        },
        # Formerly cancelled by CPA32B2, which is now suppressed in migrations.
        REASON_PENDING_ROW_CHANGES: {
            "schema.tests.SchemaTests.test_alter_field_default_dropped",
            "schema.tests.SchemaTests.test_alter_null_to_not_null",
            "schema.tests.SchemaTests.test_alter_null_with_default_value_deferred_constraints",
            "schema.tests.SchemaTests.test_alter_text_field_to_not_null_with_default_value",
        },
        # RenameField / a new db_column: NotSupportedError (schema.py).
        REASON_NO_COLUMN_RENAME: {
            "schema.tests.SchemaTests.test_alter_pk_with_self_referential_field",
            # A column author becomes ForeignKey author (column author_id).
            "schema.tests.SchemaTests.test_alter_to_fk",
            "schema.tests.SchemaTests.test_autofield_to_o2o",
            "schema.tests.SchemaTests.test_m2m_rename_field_in_target_model",
            "schema.tests.SchemaTests.test_referenced_field_without_constraint_rename_inside_atomic_block",
            "schema.tests.SchemaTests.test_rename",
            "schema.tests.SchemaTests.test_rename_column_renames_deferred_sql_references",
            "schema.tests.SchemaTests.test_rename_keep_db_default",
            "schema.tests.SchemaTests.test_rename_keep_null_status",
            "schema.tests.SchemaTests.test_rename_field_with_check_to_truncated_name",
            "schema.tests.SchemaTests.test_rename_referenced_field",
            "schema.tests.SchemaTests.test_unique",
        },
        # Text to a date or time, AutoField to and from CharField: NotSupportedError.
        REASON_TYPE_NOT_IN_PLACE: {
            "schema.tests.SchemaTests.test_alter_auto_field_to_char_field",
            "schema.tests.SchemaTests.test_alter_text_field_to_date_field",
            "schema.tests.SchemaTests.test_alter_text_field_to_datetime_field",
            "schema.tests.SchemaTests.test_alter_text_field_to_time_field",
            "schema.tests.SchemaTests.test_char_field_pk_to_auto_field",
            # CharField to a ForeignKey to an AutoField (NVARCHAR to BIGINT).
            "schema.tests.SchemaTests.test_char_field_with_db_index_to_fk",
        },
    }
    # Per Django version: the entries above that pass on the running version
    # (compat.PASSING_ON_THIS_VERSION) are left out, since an expected failure
    # that passes fails the run.
    django_test_expected_failures: set[str] = (
        set().union(*expected_failures.values()) - compat.PASSING_ON_THIS_VERSION
    )
