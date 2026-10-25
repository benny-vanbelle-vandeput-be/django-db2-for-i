`supports_foreign_keys`: migrations create a foreign key constraint for every
`ForeignKey` and `OneToOneField`, as a separate `ALTER TABLE ... ADD
CONSTRAINT` statement. Violations raise `IntegrityError`. Introspection
(`inspectdb`, the schema editor) does not report a foreign key that Db2 for i
no longer enforces. See Known limitations for exact type matching (SQL0538),
fixtures that refer to rows loaded later, and constraint checks that can't be
switched off.
