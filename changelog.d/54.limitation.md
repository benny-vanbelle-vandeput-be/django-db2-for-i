A bare `%s` in `RawSQL()` is an untyped parameter marker, which Db2 for i
rejects in the select list (SQL0418); cast it in the SQL, e.g.
`RawSQL("CAST(%s AS NVARCHAR(20))", [value])` (see
docs/user/Known-Limitations.md).
