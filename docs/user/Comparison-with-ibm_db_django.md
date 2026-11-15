# Comparison with ibm_db_django

> **This comparison reflects the state on 2026-11-15.** Both projects change
> over time, so check the sources below before you rely on a row.
>
> - **django-db2-for-i** 0.1.0b4: its `DatabaseFeatures` flags
>   ([feature flags](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/blob/main/docs/FEATURES.md)).
> - **[ibm_db_django](https://github.com/ibmdb/python-ibmdb-django)** 1.6.0.0:
>   the latest commit, `838265d` (2026-02-15). Its flags come from the
>   `DatabaseFeatures` class in `ibm_db_django/base.py`.

[ibm_db_django](https://github.com/ibmdb/python-ibmdb-django) is IBM's
Django backend for Db2. This page compares the two backends: first in
general, then flag by flag.

## In general

| | django-db2-for-i | ibm_db_django |
|---|---|---|
| **Database** | Db2 for i (IBM i 7.5 and later) | Db2 for Linux, Unix and Windows 11.5 or later. Its README lists IBM i ("Remote connections to i5/OS (iSeries)") under "Future Supported Databases". A few introspection queries already have an IBM i variant. |
| **Driver** | pyodbc with the IBM i Access ODBC Driver ([ODBC driver setup](ODBC-Driver-Setup.md)) | `ibm_db`. According to the [ibm_db README](https://github.com/ibmdb/python-ibmdb#Licenserequirements), connecting to Db2 for i from Linux, Unix, Windows or macOS needs a Db2 Connect license, on the client or on the server. |
| **Django** | 5.2 LTS, 6.0, 6.1 | 5.2 (release 1.6.0.0); older releases for Django 2.2 to 4.2 |
| **Python** | 3.12, 3.13, 3.14; 3.15 with Django 6.1.3 or later | up to 3.13 (its README) |
| **How it is tested** | Django's own test modules and the project's own tests, against a real IBM i 7.5, for every supported Django version ([test status](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/blob/main/docs/TEST_STATUS.md)) | The repository has no tests and publishes no test results. |
| **Releases** | Signed tags on GitHub; not on PyPI | PyPI (`ibm-db-django`) |
| **Status** | beta | 1.6.0.0, released 2026-02-15 |
| **License** | BSD-3-Clause | Apache-2.0 |

## Feature flags on Django 5.2

Django reads a backend's `DatabaseFeatures` flags to know what the backend
can do. Django's test suite also skips the tests of a feature that is off.
The table below compares the flags on Django 5.2, the only Django version
both backends support.

**How to read the comparison**

- **A flag that is on is a claim, not a test result.** For django-db2-for-i,
  every flag that is on passes the related Django tests on IBM i 7.5. For
  ibm_db_django, a flag that is on says only what the backend claims.
  Whether it works on Db2 for i was not tested for this page.
- **Defaults:** ¹ marks a flag that ibm_db_django does not set itself. It
  then has Django 5.2's default value.
- **Older attributes:** ibm_db_django also sets 14 attributes that Django
  5.2 no longer reads, such as `can_introspect_null` and
  `uses_custom_query_class`. They are left out here.

| On Django 5.2 | Number of flags |
|---|---|
| on in both | 41 |
| on in django-db2-for-i only | 26 |
| on in ibm_db_django only | 11 |
| off in both | 46 |

### The main differences

**On in django-db2-for-i only:**
- window functions (`supports_over_clause`, `supports_frame_range_fixed_distance`);
- `JSONField` (`supports_json_field`);
- inserts that return the primary key and defaults in the same statement
  (`can_return_columns_from_insert`, `can_return_rows_from_bulk_insert`);
- `bulk_create()` with many rows per statement (`has_bulk_insert`), also with
  `ignore_conflicts` and `update_conflicts`;
- `select_for_update(of=...)` and `skip_locked=True`;
- partial indexes, and unique constraints that accept several NULLs;
- several column changes in one `ALTER TABLE`, and `RenameIndex` in place.

**On in ibm_db_django only (11 flags):**
- **9 flags describe Db2 for LUW features that Db2 for i does not have.**
  Our probes on IBM i 7.5 showed this, and the reason for each is in
  [feature flags](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/blob/main/docs/FEATURES.md#intentionally-off-50):
  - tablespaces;
  - virtual generated columns;
  - `NULLS FIRST` / `NULLS LAST`;
  - expressions as column defaults;
  - an index on a LOB column;
  - case-insensitive `LIKE`;
  - comparing a condition with `=`;
  - comments containing any Unicode text;
  - JSON introspection.
- **`supports_primitives_in_json_field`:** has no effect in ibm_db_django,
  because it has `supports_json_field` off.
- **`atomic_transactions`:** describes how a transaction behaves after an
  error; it is not a feature.

## Every flag

### On in django-db2-for-i (67)

| Flag | What it means | django-db2-for-i | ibm_db_django |
|---|---|---|---|
| `allow_sliced_subqueries_with_in` | A sliced queryset (`qs[:n]`, also with an offset) can be used in `__in`. | ✅ | ✅ ¹ |
| `allows_auto_pk_0` | An `AutoField` primary key may be 0. | ✅ | ✅ ¹ |
| `allows_group_by_lob` | `TextField` and `BinaryField` columns can be grouped by. | ✅ | ✅ ¹ |
| `can_create_inline_fk` | A foreign key column added by a migration gets its constraint in the same `ALTER TABLE ... ADD COLUMN`. | ✅ | ❌ |
| `can_introspect_check_constraints` | `inspectdb` and introspection find CHECK constraints. | ✅ | ✅ ¹ |
| `can_introspect_default` | Introspection reads column defaults. | ✅ | ✅ ¹ |
| `can_introspect_foreign_keys` | Introspection finds foreign keys. | ✅ | ✅ ¹ |
| `can_release_savepoints` | Savepoints are released after a nested `atomic()` block that succeeded. | ✅ | ❌ ¹ |
| `can_rename_index` | `RenameIndex` renames an index in place instead of dropping and recreating it. | ✅ | ❌ ¹ |
| `can_return_columns_from_insert` | Inserted rows return their primary key and defaults in one statement. | ✅ | ❌ ¹ |
| `can_return_rows_from_bulk_insert` | `bulk_create()` sets the primary keys of the created objects. | ✅ | ❌ ¹ |
| `can_rollback_ddl` | Schema changes inside a transaction are rolled back with it: a migration that fails halfway leaves nothing behind. | ✅ | ✅ |
| `can_use_chunked_reads` | `QuerySet.iterator()` fetches rows in chunks from an open cursor while other queries run. | ✅ | ✅ |
| `delete_can_self_reference_subquery` | A delete whose filter has a subquery on the same table runs as one statement. | ✅ | ✅ ¹ |
| `has_bulk_insert` | `bulk_create()` inserts many rows in one statement. | ✅ | ❌ |
| `has_json_object_function` | JSON objects can be built in SQL (`JSONObject`). | ✅ | ✅ ¹ |
| `has_real_datatype` | The database has a single-precision `REAL` type besides `DOUBLE`. | ✅ | ❌ ¹ |
| `has_select_for_update` | `select_for_update()` locks the selected rows. | ✅ | ✅ |
| `has_select_for_update_of` | `select_for_update(of=...)` locks rows of the named tables only. | ✅ | ❌ ¹ |
| `has_select_for_update_skip_locked` | `select_for_update(skip_locked=True)` skips locked rows. | ✅ | ❌ ¹ |
| `ignores_table_name_case` | Table names that differ only in case are the same table (names are uppercase). | ✅ | ✅ |
| `ignores_unnecessary_order_by_in_subqueries` | Django may leave an `ORDER BY` in a subquery; the database accepts and ignores it. | ✅ | ✅ ¹ |
| `implied_column_null` | Columns are nullable unless `NOT NULL` is written; no bare `NULL` keyword in DDL. | ✅ | ❌ ¹ |
| `indexes_foreign_keys` | Foreign key columns get an index (on Db2 for i Django's own: the constraint creates none). | ✅ | ✅ ¹ |
| `nulls_order_largest` | NULL sorts as the largest value: last in ascending order, first in descending. | ✅ | ✅ |
| `requires_compound_order_by_subquery` | An ordered `union()` / `intersection()` / `difference()` is wrapped in a subquery to order it. | ✅ | ❌ ¹ |
| `requires_literal_defaults` | Column defaults in DDL are written as literals, not parameters. | ✅ | ✅ |
| `select_for_update_of_column` | `select_for_update(of=...)` is written with column names, not table names. | ✅ | ❌ ¹ |
| `supports_boolean_expr_in_select_clause` | Conditions such as `Exists()` or `Q()` can be selected and grouped by. | ✅ | ✅ ¹ |
| `supports_cast_with_precision` | `Cast()` to a type with a length or precision, e.g. `DecimalField(max_digits=...)`. | ✅ | ✅ ¹ |
| `supports_column_check_constraints` | CHECK constraints on a single column (e.g. `PositiveIntegerField`) are enforced by the database. | ✅ | ✅ ¹ |
| `supports_combined_alters` | Several column changes are written as one `ALTER TABLE` statement. | ✅ | ❌ ¹ |
| `supports_date_lookup_using_string` | Lookups such as `__startswith` with a string on a date or datetime column. | ✅ | ✅ ¹ |
| `supports_default_in_lead_lag` | `Lead()` / `Lag()` with a `default`. | ✅ | ✅ ¹ |
| `supports_default_keyword_in_bulk_insert` | `bulk_create()` writes `DEFAULT` for fields with a `db_default`. | ✅ | ✅ ¹ |
| `supports_default_keyword_in_insert` | An insert writes `DEFAULT` for fields with a `db_default`. | ✅ | ✅ ¹ |
| `supports_expression_indexes` | Indexes on expressions (`Index(Lower('name'))`). | ✅ | ✅ ¹ |
| `supports_foreign_keys` | Foreign keys are enforced by the database. | ✅ | ✅ ¹ |
| `supports_frame_range_fixed_distance` | Window `RANGE` frames with a fixed distance (`ValueRange(start=-5)`). | ✅ | ❌ ¹ |
| `supports_functions_in_partial_indexes` | Functions in the `condition` of a partial index. | ✅ | ✅ ¹ |
| `supports_ignore_conflicts` | `bulk_create(ignore_conflicts=True)`. | ✅ | ❌ |
| `supports_index_column_ordering` | Index columns can be ordered `DESC` (`Index(fields=["-field"])`). | ✅ | ✅ ¹ |
| `supports_json_field` | `JSONField`. | ✅ | ❌ |
| `supports_nullable_unique_constraints` | Unique constraints on nullable columns allow several NULLs. | ✅ | ❌ |
| `supports_over_clause` | Window functions (`Window`, `OVER (...)`). | ✅ | ❌ ¹ |
| `supports_paramstyle_pyformat` | Raw SQL may use `%(name)s` parameters with a dict. | ✅ | ❌ |
| `supports_parentheses_in_compound` | Parts of a compound query may have their own `ORDER BY` / slice. | ✅ | ✅ ¹ |
| `supports_partial_indexes` | Indexes and unique constraints with a `condition`. | ✅ | ❌ |
| `supports_partially_nullable_unique_constraints` | Multi-column unique constraints where some columns are NULL. | ✅ | ❌ |
| `supports_regex_backreferencing` | `regex` / `iregex` lookups support backreferences (ICU regular expressions). | ✅ | ✅ |
| `supports_select_difference` | `QuerySet.difference()` (`EXCEPT`). | ✅ | ✅ ¹ |
| `supports_select_for_update_with_limit` | `select_for_update()` on a sliced queryset. | ✅ | ✅ ¹ |
| `supports_select_intersection` | `QuerySet.intersection()` (`INTERSECT`). | ✅ | ✅ ¹ |
| `supports_select_union` | `QuerySet.union()` (`UNION` / `UNION ALL`). | ✅ | ✅ ¹ |
| `supports_sequence_reset` | `sqlsequencereset` and `TransactionTestCase.reset_sequences` restart identity values. | ✅ | ✅ |
| `supports_slicing_ordering_in_compound` | Slicing and ordering of the parts of a compound query. | ✅ | ❌ ¹ |
| `supports_subqueries_in_group_by` | A subquery can be used in `GROUP BY`. | ✅ | ❌ |
| `supports_table_check_constraints` | Model `CheckConstraint`s are enforced by the database. | ✅ | ✅ ¹ |
| `supports_temporal_subtraction` | Subtracting dates, times and datetimes gives an exact `timedelta`. | ✅ | ✅ |
| `supports_transactions` | Transactions with commit and rollback (on journaled tables). | ✅ | ✅ |
| `supports_tuple_lookups` | Lookups on several columns at once (composite keys, multi-column relations). | ✅ | ✅ ¹ |
| `supports_update_conflicts` | `bulk_create(update_conflicts=True)` (upsert). | ✅ | ❌ ¹ |
| `supports_update_conflicts_with_target` | `bulk_create(update_conflicts=True, unique_fields=...)`: an upsert on named columns. | ✅ | ❌ ¹ |
| `test_db_allows_multiple_connections` | The test database may be used by several connections at once. | ✅ | ✅ ¹ |
| `truncates_names` | Names longer than the database allows are shortened with a hash, the same way everywhere. | ✅ | ❌ ¹ |
| `update_can_self_select` | An update whose filter has a subquery on the same table runs as one statement. | ✅ | ✅ ¹ |
| `uses_savepoints` | Nested `atomic()` blocks use savepoints. | ✅ | ✅ |

### Off on purpose in django-db2-for-i (41)

Why each one is off: [feature flags](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/blob/main/docs/FEATURES.md#intentionally-off-50).

| Flag | What it means | django-db2-for-i | ibm_db_django |
|---|---|---|---|
| `allows_group_by_select_index` | `GROUP BY 1`: grouping by the position of a selected column. | ❌ | ❌ |
| `allows_group_by_selected_pks` | Grouping by a model's primary key alone also groups by its other selected columns. | ❌ | ❌ ¹ |
| `allows_multiple_constraints_on_same_fields` | Several constraints on the same columns. | ❌ | ❌ |
| `atomic_transactions` | An error inside a transaction aborts the whole transaction. | ❌ | ✅ ¹ |
| `can_clone_databases` | The test database can be cloned for parallel test runs (`--parallel`). | ❌ | ❌ ¹ |
| `can_defer_constraint_checks` | Constraint checks can be deferred to the end of the transaction. | ❌ | ❌ |
| `can_introspect_json_field` | Introspection recognizes a `JSONField` column. | ❌ | ✅ ¹ |
| `can_introspect_materialized_views` | `inspectdb --include-views` also finds materialized views. | ❌ | ❌ ¹ |
| `greatest_least_ignores_nulls` | `Greatest()` / `Least()` skip NULL arguments instead of returning NULL. | ❌ | ❌ ¹ |
| `has_case_insensitive_like` | `LIKE` matches regardless of case (`'a' LIKE 'A'`). | ❌ | ✅ |
| `has_native_duration_field` | `DurationField` is a native interval column. | ❌ | ❌ ¹ |
| `has_native_json_field` | `JSONField` is a native JSON column type. | ❌ | ❌ ¹ |
| `has_native_uuid_field` | `UUIDField` is a native UUID column. | ❌ | ❌ ¹ |
| `has_select_for_update_nowait` | `select_for_update(nowait=True)` fails instead of waiting for a lock. | ❌ | ❌ ¹ |
| `has_zoneinfo_database` | The database has its own time zone database. | ❌ | ❌ |
| `order_by_nulls_first` | NULL sorts first in ascending order. | ❌ | ❌ ¹ |
| `rounds_to_even` | `Round()` rounds halves to even. | ❌ | ❌ ¹ |
| `supports_aggregate_filter_clause` | Aggregates with a `filter` are written with SQL `FILTER (WHERE ...)`. | ❌ | ❌ ¹ |
| `supports_collation_on_charfield` | `CharField(db_collation=...)`. | ❌ | ❌ |
| `supports_collation_on_textfield` | `TextField(db_collation=...)`. | ❌ | ❌ |
| `supports_comments` | `db_comment` and `db_table_comment` are stored as column and table comments. | ❌ | ✅ |
| `supports_comments_inline` | Column comments are written in the `ADD COLUMN` statement itself. | ❌ | ❌ |
| `supports_comparing_boolean_expr` | Conditions can be compared or tested with `IS NULL` (`WHERE (price > 0) IS NOT NULL`). | ❌ | ✅ ¹ |
| `supports_covering_indexes` | Indexes and unique constraints with `include` (covering indexes). | ❌ | ❌ ¹ |
| `supports_deferrable_unique_constraints` | `UniqueConstraint(deferrable=...)`. | ❌ | ❌ ¹ |
| `supports_explaining_query_execution` | `QuerySet.explain()`. | ❌ | ? |
| `supports_expression_defaults` | `db_default` can be an expression, not only a constant. | ❌ | ✅ ¹ |
| `supports_forward_references` | Rows may reference rows inserted later in the same transaction (deferred constraints). | ❌ | ❌ |
| `supports_frame_exclusion` | Window frames with `exclusion` (`EXCLUDE ...`). | ❌ | ❌ ¹ |
| `supports_index_on_text_field` | Indexes on `TextField` columns. | ❌ | ✅ ¹ |
| `supports_json_field_contains` | `JSONField` `contains` / `contained_by` lookups. | ❌ | ❌ |
| `supports_logical_xor` | `Q(...) ^ Q(...)` is written with a native `XOR` operator. | ❌ | ❌ ¹ |
| `supports_non_deterministic_collations` | Non-deterministic (for example case-insensitive) collations in `db_collation`. | ❌ | ❌ |
| `supports_nulls_distinct_unique_constraints` | `UniqueConstraint(nulls_distinct=...)`. | ❌ | ❌ ¹ |
| `supports_order_by_nulls_modifier` | `NULLS FIRST` / `NULLS LAST` in `ORDER BY` (`F('x').asc(nulls_first=True)`). | ❌ | ✅ ¹ |
| `supports_primitives_in_json_field` | `JSONField` holds a plain number, string or boolean at the top level, not only objects and arrays. | ❌ | ✅ ¹ |
| `supports_stored_generated_columns` | `GeneratedField(db_persist=True)`, stored generated columns. | ❌ | ❌ |
| `supports_tablespaces` | `db_tablespace` on models, fields and indexes. | ❌ | ✅ |
| `supports_timezones` | Datetimes are stored with their time zone. | ❌ | ❌ |
| `supports_unlimited_charfield` | `CharField` without `max_length`. | ❌ | ❌ ¹ |
| `supports_virtual_generated_columns` | `GeneratedField(db_persist=False)`, virtual generated columns. | ❌ | ✅ |

### Not applicable to Db2 for i (16)

These describe another database (PostgreSQL, MySQL, Oracle, SQLite, SQL Server).

| Flag | What it means | django-db2-for-i | ibm_db_django |
|---|---|---|---|
| `can_distinct_on_fields` | `distinct(*fields)` (`DISTINCT ON`). | ❌ | ❌ |
| `collate_as_index_expression` | A collation in an index is written as an index expression. | ❌ | ❌ ¹ |
| `connection_persists_old_columns` | A connection must be reset after a schema change to see the new columns. | ❌ | ❌ ¹ |
| `for_update_after_from` | Row locks are written right after `FROM`. | ❌ | ❌ ¹ |
| `gis_enabled` | GeoDjango spatial fields. | ❌ | ❌ ¹ |
| `has_json_operators` | JSON is queried with operators (`->`, `->>`). | ❌ | ❌ ¹ |
| `has_select_for_no_key_update` | `select_for_update(no_key=True)`. | ❌ | ❌ ¹ |
| `interprets_empty_strings_as_nulls` | Empty strings are stored as NULL. | ❌ | ❌ |
| `json_key_contains_list_matching_requires_list` | `contains` on a JSON key needs a list to match an element of a list. | ❌ | ❌ ¹ |
| `only_supports_unbounded_with_preceding_and_following` | Window `RANGE` frames take only unbounded or current-row bounds. | ❌ | ❌ ¹ |
| `related_fields_match_type` | A foreign key column must have exactly the type of the column it references. | ❌ | ❌ ¹ |
| `requires_casted_case_in_updates` | `CASE` expressions in updates are cast to the column type. | ❌ | ❌ ¹ |
| `requires_explicit_null_ordering_when_grouping` | A grouped query gets an explicit `ORDER BY NULL` to avoid sorting. | ❌ | ❌ ¹ |
| `schema_editor_uses_clientside_param_binding` | The schema editor binds DDL parameters in the client. | ❌ | ❌ ¹ |
| `supports_callproc_kwargs` | `cursor.callproc()` with keyword parameters. | ❌ | ❌ ¹ |
| `supports_unspecified_pk` | A model can be saved without a primary key value. | ❌ | ❌ ¹ |

### Only in Django 6.0 and 6.1 (20)

ibm_db_django does not support Django 6.0 or 6.1, so it has none of these.

| Flag | What it means | django-db2-for-i (Django 6.1) |
|---|---|---|
| `has_native_boolean_field` | `BooleanField` is a native `BOOLEAN` column (IBM i 7.5). | ✅ |
| `pattern_lookup_needs_param_pattern` | `contains`, `startswith` and friends are written with `LIKE` patterns. | ✅ |
| `supports_aggregate_distinct_multiple_argument` | `StringAgg(..., distinct=True)` with a delimiter (`distinct` with several arguments). | ✅ |
| `supports_aggregate_order_by_clause` | `StringAgg(..., order_by=...)` and other ordered aggregates. | ✅ |
| `supports_any_value` | The `AnyValue` aggregate (one value of a column per group). | ✅ |
| `supports_inspectdb` | `manage.py inspectdb` generates models from existing tables. | ✅ |
| `supports_on_delete_db_cascade` | `on_delete=DB_CASCADE`: the database deletes related rows (Django 6.1+). | ✅ |
| `supports_on_delete_db_default` | `on_delete=DB_SET_DEFAULT` (Django 6.1+). | ✅ |
| `supports_on_delete_db_null` | `on_delete=DB_SET_NULL` (Django 6.1+). | ✅ |
| `supports_uuid4_function` | The `UUID4()` database function (Django 6.1+), through `GENERATE_UUID()`; detected at connect, as it needs IBM i 7.5 Db2 PTF Group level 8. | ✅ |
| `can_return_rows_from_update` | Saving an existing object reads back database-computed fields from the same `UPDATE` (Django 6.0+). | ❌ |
| `supports_alter_generated_column_data_type` | The type of a `GeneratedField` column can be changed in place (Django 6.1+). | ❌ |
| `supports_bit_aggregations` | The `BitAnd`, `BitOr` and `BitXor` aggregates (Django 6.1+). | ❌ |
| `supports_default_in_bit_aggregations` | Bit aggregates with a `default` (Django 6.1+). | ❌ |
| `supports_json_negative_indexing` | `JSONField` key transforms with a negative array index (Django 6.0+). | ❌ |
| `supports_no_precision_decimalfield` | `DecimalField` without `max_digits` and `decimal_places` (Django 6.1+). | ❌ |
| `supports_tuple_comparison_against_subquery` | Composite fields compared with `>`, `<` against a subquery. | ❌ |
| `supports_uuid4_function_in_default` | `db_default=UUID4()` (Django 6.1+). | ❌ |
| `supports_uuid7_function` | The `UUID7()` database function (Django 6.1+). | ❌ |
| `supports_uuid7_function_shift` | `UUID7(shift=...)` (Django 6.1+). | ❌ |
