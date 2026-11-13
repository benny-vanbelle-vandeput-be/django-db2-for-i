- `supports_paramstyle_pyformat`: raw SQL may use `%(name)s` placeholders
  with a dict of parameters (`cursor.execute()`, `executemany()`,
  `Model.objects.raw()`), as on PostgreSQL.
- `supports_date_lookup_using_string`: text lookups such as
  `published__startswith="2005"` on date, datetime and time fields, which
  compare the ISO text of the value.
