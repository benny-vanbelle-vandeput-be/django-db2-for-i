`supports_comments`: `db_comment` and `db_table_comment` are stored as
`COMMENT ON COLUMN` / `COMMENT ON TABLE` and read back by introspection and
`inspectdb`. Only printable ASCII is accepted. Other characters raise
`NotSupportedError` before the migration changes anything, and
`manage.py check` reports them as `django_db2_for_i.E006`. Db2 for i stores
only characters of the job CCSID, and replaces or refuses the others.
