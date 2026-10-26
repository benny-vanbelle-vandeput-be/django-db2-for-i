`db_index=True` on a `TextField` or `BinaryField` no longer fails with
SQL0350: Db2 for i cannot index a LOB column, so the index is skipped, as
Django's Oracle and MySQL backends do.
