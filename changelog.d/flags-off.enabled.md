- `supports_paramstyle_pyformat`: raw SQL may use `%(name)s` placeholders
  with a dict of parameters (`cursor.execute()`, `executemany()`,
  `Model.objects.raw()`), as on PostgreSQL.
