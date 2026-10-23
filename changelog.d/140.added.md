Introspection finds foreign keys: `get_relations()` reads them from the `QSYS2`
catalog (on Django 6.1 with the delete rule as `db_on_delete`), and
`can_introspect_foreign_keys` is on.
