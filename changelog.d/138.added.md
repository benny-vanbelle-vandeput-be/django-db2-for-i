Introspection reads constraints and indexes: `get_constraints()` returns the
primary key, unique, foreign key and check constraints and the indexes of a
table (with the column order of each index) from the `QSYS2` catalog, and
`get_primary_key_column()` follows from it.
