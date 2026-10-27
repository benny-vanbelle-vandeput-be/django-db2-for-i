`supports_inspectdb` and `ignores_table_name_case`: `manage.py inspectdb`
writes models for existing tables (also with `NUMERIC` and `CLOB` columns,
which are now introspected as `DecimalField` and `TextField`), and a
`db_table` that differs only in case is the same table.
