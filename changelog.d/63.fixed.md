`iexact` returned no rows for values containing `_`, `%` or `\`: the value
was escaped for LIKE, although `iexact` compares with `UPPER(column) =
UPPER(value)`. It is now compared as it is (as on PostgreSQL and Oracle).
