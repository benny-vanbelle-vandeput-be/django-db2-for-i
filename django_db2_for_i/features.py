"""DatabaseFeatures: optional Django features, conservative by default.

Every optional flag starts as False and is enabled only when backed by
passing Django tests. Flags ask ServerCapabilities, never compare versions.

Every flag that Django 6.1 defaults to True is listed here explicitly, so
enabling one is a visible one-line change.
"""

from django.db.backends.base.features import BaseDatabaseFeatures
from django.utils.functional import cached_property

# Fixed reasons for skips and expected failures, so related entries can be
# found and counted (docs/DECISIONS.md).
REASON_TIME_FRACTIONS = "Db2 for i TIME has no fractional seconds"
REASON_IDENTITY_RESTART_DEFERRED = "identity restart deferred in TestCase (SQL0910)"


class DatabaseFeatures(BaseDatabaseFeatures):
    minimum_database_version = (7, 5)

    # --- Facts about Db2 for i (not optional features) -----------------------

    # Never let Django's default cached_property run: it creates a test table
    # to find out. Commitment control works on journaled tables (see
    # docs/IBMI_NOTES.md).
    supports_transactions = True
    # DDL inside a transaction is not rolled back until a probe shows it is.
    can_rollback_ddl = False
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
    allow_sliced_subqueries_with_in = False
    supports_subqueries_in_group_by = False
    ignores_unnecessary_order_by_in_subqueries = False
    supports_regex_backreferencing = False
    supports_date_lookup_using_string = False
    supports_order_by_nulls_modifier = False
    supports_select_union = False
    supports_select_intersection = False
    supports_select_difference = False
    supports_parentheses_in_compound = False
    supports_select_for_update_with_limit = False
    supports_aggregate_distinct_multiple_argument = False
    supports_bit_aggregations = False
    supports_default_in_bit_aggregations = False
    supports_cast_with_precision = False
    supports_default_in_lead_lag = False
    supports_boolean_expr_in_select_clause = False
    supports_comparing_boolean_expr = False
    supports_tuple_lookups = False
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
    supports_foreign_keys = False
    can_create_inline_fk = False
    indexes_foreign_keys = False
    supports_column_check_constraints = False
    supports_table_check_constraints = False
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

    # Introspection
    can_introspect_default = False
    can_introspect_foreign_keys = False
    can_introspect_check_constraints = False
    supports_index_column_ordering = False
    supports_inspectdb = False

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
    django_test_skips: dict[str, set[str]] = {}
    expected_failures: dict[str, set[str]] = {
        REASON_TIME_FRACTIONS: set(),
        REASON_IDENTITY_RESTART_DEFERRED: set(),
    }
    django_test_expected_failures: set[str] = set().union(*expected_failures.values())
