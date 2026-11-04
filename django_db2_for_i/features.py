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
REASON_CHECK_LIKE_COLUMN_PATTERN = (
    "Db2 for i rejects a CHECK condition with LIKE against a pattern built from a column (SQL0546)"
)
REASON_MERGE_RETURNS_NO_ROWS = (
    "bulk_create(update_conflicts=True) is a MERGE, which returns no rows (FINAL TABLE takes "
    "only INSERT): the objects get no primary keys"
)
REASON_FINAL_TABLE_NOT_RETURNING = (
    "the test looks for RETURNING in the SQL; Db2 for i returns columns with FINAL TABLE"
)
REASON_LOWERCASE_NAME_IN_SQL = (
    "the test looks for a lowercase column name in the SQL; names are uppercase on Db2 for i"
)
REASON_NO_SUCH_FUNCTION = (
    "Db2 for i has no such function (REVERSE, HASH_SHA224, HASH_SHA384: SQL0204); the backend "
    "raises NotSupportedError"
)
REASON_TIME_ZONE_CONVERSION = (
    "converting datetimes to another time zone in SQL is not supported yet: Db2 for i has no "
    "time zone database; the backend raises NotSupportedError"
)
REASON_EXTRACT_IN_SQL = (
    "the test counts the word EXTRACT in the SQL; Db2 for i writes YEAR(...) and the like"
)
REASON_TRUNC_KIND_REFUSED = (
    "an unknown Trunc kind raises ValueError before any SQL is sent; the test accepts only a "
    "database error or no rows"
)
REASON_TRUNC_NULL_ZONEINFO = (
    "before Django 6.1, Trunc of a NULL datetime with USE_TZ raises ValueError when "
    "has_zoneinfo_database is off; 6.1 lets the backend keep the NULL"
)
REASON_SINGLE_BYTE_CHR = (
    "CHR and ASCII on Db2 for i work on single-byte characters; a non-ASCII character gives a "
    "substitute character (probes db_functions, db_function_args)"
)

REASON_NO_JSON_CHECK = (
    "Db2 for i refuses CHECK (C IS JSON) on an NCLOB (SQL0546, probe lib_json_check), so "
    "invalid JSON written past Django's encoder is stored"
)
REASON_JSON_KEY_ORDER_AS_TEXT = (
    "ordering by a JSON key compares its JSON text, as on Oracle and MariaDB (JSON_QUERY; "
    "probe json_lookups)"
)
REASON_JSON_KEY_DOUBLE_QUOTE = (
    "a Db2 for i JSON path cannot hold a key with a double quote in any form (probe "
    "json_lookups); the backend raises NotSupportedError"
)


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
    # GROUP BY, DISTINCT and ORDER BY an NCLOB or a BLOB (probe phase6_flags).
    allows_group_by_lob = True
    allows_group_by_select_index = False
    # An UPDATE / DELETE whose subquery reads the same table runs as one
    # statement, without materializing the subquery first (probe qtemp_cursors).
    update_can_self_select = True
    delete_can_self_reference_subquery = True
    # IN (SELECT ... FETCH FIRST n ROWS ONLY), also with OFFSET (probe queries).
    allow_sliced_subqueries_with_in = True
    # A scalar subquery in GROUP BY works (probe queries).
    supports_subqueries_in_group_by = True
    # ANY_VALUE aggregate (probe queries).
    supports_any_value = True
    # StringAgg(order_by=...) as LISTAGG(...) WITHIN GROUP (ORDER BY ...) (probe listagg).
    supports_aggregate_order_by_clause = True
    # ORDER BY in an IN, FROM or EXISTS subquery is accepted (probe phase6_flags).
    ignores_unnecessary_order_by_in_subqueries = True
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
    # LISTAGG(DISTINCT x, ',') (probes listagg, phase6_flags).
    supports_aggregate_distinct_multiple_argument = True
    supports_bit_aggregations = False
    supports_default_in_bit_aggregations = False
    # Cast to a length or precision; a number cast to a DecimalField is rounded
    # first, as Db2 for i's CAST cuts off (expressions.py, probe db_functions).
    supports_cast_with_precision = True
    # ROUND takes halves away from zero: 2.5 to 3, -2.5 to -3 (probe db_functions).
    rounds_to_even = False
    # REAL is a single-precision float (probe phase6_flags).
    has_real_datatype = True
    # Window functions: every one, partitions, ROWS and RANGE frames; a LAG / LEAD
    # offset and NTH_VALUE's position are written as constants, PERCENT_RANK and
    # CUME_DIST cast to DOUBLE (expressions.py, probe window).
    supports_over_clause = True
    # A typed default: LAG(V, 1, CAST(? AS DOUBLE)) (probe window).
    supports_default_in_lead_lag = True
    # RANGE 5 PRECEDING on a number; on a date it is refused (SQL0182, probe window).
    supports_frame_range_fixed_distance = True
    # EXCLUDE ... is refused (SQL0104, probe window).
    supports_frame_exclusion = False
    # Predicates are valid in the select list and GROUP BY on 7.5 (BOOLEAN);
    # Exists() is rendered as a first-row subquery there (compiler.py).
    supports_boolean_expr_in_select_clause = True
    supports_comparing_boolean_expr = False
    # Row values: (a, b) = (x, y) and (a, b) IN (subquery); IN lists and
    # >, >=, <, <= in Django's expanded form (expressions.py, probe tuple_lookups).
    supports_tuple_lookups = True
    supports_tuple_comparison_against_subquery = False

    # Inserts and fetching
    # SELECT ... FROM FINAL TABLE (INSERT ...) returns the key and the column
    # defaults of the inserted row (probe qtemp_returning, compiler.py).
    can_return_columns_from_insert = True
    # bulk_create() as one multi-row INSERT; with returning, FINAL TABLE gives the
    # rows back in input order (ORDER BY INPUT SEQUENCE, probe qtemp_returning).
    # The batch size stays below the statement limits (operations.bulk_batch_size).
    can_return_rows_from_bulk_insert = True
    # QuerySet.iterator() keeps its cursor open and fetches in chunks while
    # other statements run on the connection (probe qtemp_cursors; with
    # commitment control: tests/ibmi/test_queries.py).
    can_use_chunked_reads = True
    has_bulk_insert = True
    # An explicit 0 in an identity column is a normal key (probe qtemp_returning).
    allows_auto_pk_0 = True
    # DEFAULT in VALUES, also with several rows (probe qtemp_returning).
    supports_default_keyword_in_insert = True
    supports_default_keyword_in_bulk_insert = True
    # bulk_create(ignore_conflicts / update_conflicts) as a MERGE (compiler.py,
    # probe qtemp_merge); update_conflicts needs its unique_fields as the ON.
    supports_ignore_conflicts = True
    supports_update_conflicts = True
    supports_update_conflicts_with_target = True

    # Schema and constraints
    # NULLs in a UNIQUE constraint are distinct: several NULLs, also in part of
    # a multi-column key (probe lib_unique_catalog, #213). Unique indexes use
    # UNIQUE WHERE NOT NULL for the same (schema.sql_create_unique_index).
    supports_nullable_unique_constraints = True
    supports_partially_nullable_unique_constraints = True
    # Identities restart at IDENTITY_START (sequence_reset_by_name_sql); in
    # TestCase, sequence_reset_sql is deferred to the commit (SQL0910).
    supports_sequence_reset = True
    # Names over 128 characters (SQL0107, probe qtemp_later_flags) are shortened
    # with Django's truncate_name() in quote_name(), so Django does the same
    # when it looks up constraint columns and skips its name length check.
    truncates_names = True
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
    # CREATE [UNIQUE] INDEX ... WHERE, also with functions, and indexes on
    # expressions (probe qtemp_indexes); Django's sql_create_index fits as is.
    # No INCLUDE (supports_covering_indexes).
    supports_partial_indexes = True
    supports_functions_in_partial_indexes = True
    supports_expression_indexes = True
    allows_multiple_constraints_on_same_fields = False
    supports_collation_on_charfield = False
    supports_collation_on_textfield = False
    supports_non_deterministic_collations = False
    supports_alter_generated_column_data_type = False
    # DB-level on_delete (Django 6.1: DB_CASCADE, DB_SET_NULL, DB_SET_DEFAULT):
    # Django writes ON DELETE CASCADE / SET NULL / SET DEFAULT into the foreign
    # key; each works as IBM documents, also in a transaction, and SYSREFCST
    # names the rule (probe lib_on_delete, #220). SET DEFAULT refuses to delete
    # the parent the default points to (SQL0532, an IntegrityError).
    supports_on_delete_db_cascade = True
    supports_on_delete_db_default = True
    supports_on_delete_db_null = True
    # RENAME INDEX (probe 24). Combined alters stay off: Db2 for i accepts
    # several clauses in one ALTER TABLE only without commas, and Django joins
    # them with ", ".
    can_rename_index = True

    # Introspection
    can_introspect_default = True
    can_introspect_foreign_keys = True
    can_introspect_check_constraints = True
    # CREATE INDEX ... (a DESC, b ASC) (probe alter_table); introspection reads
    # QSYS2.SYSKEYS.ORDERING into get_constraints()' "orders".
    supports_index_column_ordering = True
    # inspectdb (phase 4 step D). quote_name() writes every name in
    # uppercase, so a table name's case is lost: "PascalCase" and "pascalcase"
    # are the same table, and introspection reports it in lowercase.
    supports_inspectdb = True
    ignores_table_name_case = True

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

    # JSON: an NCLOB with Db2 for i's JSON functions (expressions.py, probes
    # json_functions, json_lookups), where the server has them.
    @cached_property
    def supports_json_field(self) -> bool:
        return self.connection.capabilities.has_json_functions

    # JSON_OBJECT with typed markers, keys and nesting (probe json_functions).
    @cached_property
    def has_json_object_function(self) -> bool:
        return self.connection.capabilities.has_json_functions

    # CHECK (C IS JSON) is refused on an NCLOB (SQL0546, probe lib_json_check),
    # so introspection sees a plain LOB.
    can_introspect_json_field = False
    # A root scalar is stored and read back, but JSON_QUERY and JSON_VALUE
    # cannot reach it (NULL; probe json_functions).
    supports_primitives_in_json_field = False
    # No containment function; path filters returned false (probe json_functions).
    supports_json_field_contains = False
    # $.d[-1] gives NULL without an error (probe json_functions).
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
        REASON_NO_SUCH_FUNCTION: {
            "db_functions.text.test_reverse.ReverseTests.test_basic",
            "db_functions.text.test_reverse.ReverseTests.test_expressions",
            "db_functions.text.test_reverse.ReverseTests.test_null",
            "db_functions.text.test_reverse.ReverseTests.test_transform",
            "db_functions.text.test_sha224.SHA224Tests.test_basic",
            "db_functions.text.test_sha224.SHA224Tests.test_transform",
            "db_functions.text.test_sha384.SHA384Tests.test_basic",
            "db_functions.text.test_sha384.SHA384Tests.test_transform",
        },
    }
    expected_failures: dict[str, set[str]] = {
        # Subtracts from a TimeField stored with microseconds (TIME has none).
        REASON_TIME_FRACTIONS: {
            "expressions.tests.FTimeDeltaTests.test_time_subtraction",
            # Cast and Trunc to a TimeField.
            "db_functions.comparison.test_cast.CastTests.test_cast_from_db_datetime_to_time",
            "db_functions.datetime.test_extract_trunc.DateFunctionTests.test_trunc_time_func",
            "db_functions.datetime.test_extract_trunc.DateFunctionWithTimeZoneTests.test_trunc_time_func",
        },
        REASON_TIME_ZONE_CONVERSION: {
            "db_functions.datetime.test_extract_trunc.DateFunctionWithTimeZoneTests.test_extract_func_explicit_timezone_priority",
            "db_functions.datetime.test_extract_trunc.DateFunctionWithTimeZoneTests.test_extract_func_with_timezone",
            "db_functions.datetime.test_extract_trunc.DateFunctionWithTimeZoneTests.test_extract_func_with_timezone_minus_no_offset",
            "db_functions.datetime.test_extract_trunc.DateFunctionWithTimeZoneTests.test_trunc_func_with_timezone",
            "db_functions.datetime.test_extract_trunc.DateFunctionWithTimeZoneTests.test_trunc_timezone_applied_before_truncation",
        },
        # str(qs.query).count("extract") with a year lookup against an expression.
        REASON_EXTRACT_IN_SQL: {
            "db_functions.datetime.test_extract_trunc.DateFunctionTests.test_extract_year_exact_lookup",
            "db_functions.datetime.test_extract_trunc.DateFunctionTests.test_extract_year_greaterthan_lookup",
            "db_functions.datetime.test_extract_trunc.DateFunctionTests.test_extract_year_lessthan_lookup",
            "db_functions.datetime.test_extract_trunc.DateFunctionWithTimeZoneTests.test_extract_year_exact_lookup",
            "db_functions.datetime.test_extract_trunc.DateFunctionWithTimeZoneTests.test_extract_year_greaterthan_lookup",
            "db_functions.datetime.test_extract_trunc.DateFunctionWithTimeZoneTests.test_extract_year_lessthan_lookup",
        },
        REASON_TRUNC_KIND_REFUSED: {
            "db_functions.datetime.test_extract_trunc.DateFunctionTests.test_trunc_lookup_name_sql_injection",
            "db_functions.datetime.test_extract_trunc.DateFunctionWithTimeZoneTests.test_trunc_lookup_name_sql_injection",
        },
        # On Django 5.2 and 6.0 only (compat.py).
        REASON_TRUNC_NULL_ZONEINFO: set(compat.TRUNC_NULL_FAILING),
        # Chr(ord("É")) and Ord on "Élena".
        REASON_SINGLE_BYTE_CHR: {
            "db_functions.text.test_chr.ChrTests.test_non_ascii",
            "db_functions.text.test_ord.OrdTests.test_basic",
        },
        # sequence_reset_sql() inside TestCase's transaction: the restart waits
        # for a commit that never comes (operations.py, SQL0910).
        REASON_IDENTITY_RESTART_DEFERRED: {
            "backends.tests.SequenceResetTest.test_generic_relation",
        },
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
            # AlterField null=True to null=False with a db_default, on a table with NULLs.
            "migrations.test_operations.OperationTests.test_alter_field_change_blank_nullable_database_default_to_not_null",
            "migrations.test_operations.OperationTests.test_alter_field_change_nullable_to_database_default_not_null",
            "migrations.test_operations.OperationTests.test_alter_field_change_nullable_to_decimal_database_default_not_null",
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
            # RenameField, a renamed or repointed m2m (the through table's
            # columns), an AlterField to a new column name.
            "migrations.test_operations.OperationTests.test_alter_fk_non_fk",
            "migrations.test_operations.OperationTests.test_alter_id_pk_to_uuid_pk",
            "migrations.test_operations.OperationTests.test_alter_model_table_m2m_field",
            "migrations.test_operations.OperationTests.test_rename_field",
            "migrations.test_operations.OperationTests.test_rename_field_add_non_nullable_field_with_composite_pk",
            "migrations.test_operations.OperationTests.test_rename_field_index_together",
            "migrations.test_operations.OperationTests.test_rename_field_reloads_state_on_fk_target_changes",
            "migrations.test_operations.OperationTests.test_rename_field_unique_together",
            "migrations.test_operations.OperationTests.test_rename_m2m_model_after_rename_field",
            "migrations.test_operations.OperationTests.test_rename_m2m_target_model",
            "migrations.test_operations.OperationTests.test_rename_model_with_db_table_rename_m2m",
            "migrations.test_operations.OperationTests.test_rename_model_with_m2m",
            "migrations.test_operations.OperationTests.test_rename_model_with_m2m_models_in_different_apps_with_same_name",
            "migrations.test_operations.OperationTests.test_rename_model_with_self_referential_m2m",
            "migrations.test_operations.OperationTests.test_repoint_field_m2m",
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
            # A primary key or to_field target between INTEGER and NVARCHAR;
            # no table rebuild (docs/DECISIONS.md).
            "migrations.test_executor.ExecutorTests.test_alter_id_type_with_fk",
            "migrations.test_operations.OperationTests.test_alter_field_pk_fk_char_to_int",
            "migrations.test_operations.OperationTests.test_alter_field_reloads_state_fk_with_to_field_related_name_target_type_change",
            "migrations.test_operations.OperationTests.test_alter_field_reloads_state_on_fk_with_to_field_target_type_change",
        },
        # ~Q(surname__startswith=F("name")): LIKE REPLACE(...("NAME")...) || '%'.
        # The other subtests pass on a clean system (docs/IBMI_NOTES.md: PUB400
        # currently refuses the constraint name "CONSTRAINT" with SQL0601).
        REASON_CHECK_LIKE_COLUMN_PATTERN: {
            "migrations.test_operations.OperationTests.test_add_constraint_percent_escaping",
            "migrations.test_operations.OperationTests.test_create_model_constraint_percent_escaping",
        },
        # sql.rfind("headline") on the CREATE INDEX of a partial index, which
        # quotes "HEADLINE"; the index itself is covered by the golden
        # ddl/add_index_partial and tests/ibmi/test_schema.py.
        # assertIsNotNone(instance.pk) after an upsert; the rows themselves are
        # right (probe qtemp_merge, Known Limitations).
        REASON_MERGE_RETURNS_NO_ROWS: {
            "bulk_create.tests.BulkCreateTests.test_update_conflicts_two_fields_unique_fields_both",
            "bulk_create.tests.BulkCreateTests.test_update_conflicts_two_fields_unique_fields_first",
            "bulk_create.tests.BulkCreateTests.test_update_conflicts_two_fields_unique_fields_second",
            "bulk_create.tests.BulkCreateTests.test_update_conflicts_unique_fields",
            "bulk_create.tests.BulkCreateTests.test_update_conflicts_unique_fields_update_fields_db_column",
            "bulk_create.tests.BulkCreateTests.test_update_conflicts_unique_two_fields_unique_fields_both",
            "bulk_create.tests.BulkCreateTests.test_update_conflicts_unique_two_fields_unique_fields_one",
        },
        REASON_LOWERCASE_NAME_IN_SQL: {
            "indexes.tests.PartialIndexTests.test_multiple_conditions",
        },
        REASON_NO_JSON_CHECK: {
            "model_fields.test_jsonfield.JSONFieldTests.test_db_check_constraints",
        },
        REASON_JSON_KEY_ORDER_AS_TEXT: {
            "model_fields.test_jsonfield.TestQuerying.test_ordering_by_transform",
        },
        REASON_JSON_KEY_DOUBLE_QUOTE: {
            "model_fields.test_jsonfield.TestQuerying.test_key_sql_injection_escape",
            "model_fields.test_jsonfield.TestQuerying.test_lookups_special_chars_double_quotes",
        },
        # assertIn("RETURNING ...", sql). The other tests of the module read the returned
        # values, and pass.
        REASON_FINAL_TABLE_NOT_RETURNING: {
            "queries.test_db_returning.ReturningValuesTests.test_insert_returning",
            "queries.test_db_returning.ReturningValuesTests.test_insert_returning_multiple",
        },
    }
    # Per Django version: the entries above that pass on the running version
    # (compat.PASSING_ON_THIS_VERSION) are left out, since an expected failure
    # that passes fails the run.
    django_test_expected_failures: set[str] = (
        set().union(*expected_failures.values()) - compat.PASSING_ON_THIS_VERSION
    )
