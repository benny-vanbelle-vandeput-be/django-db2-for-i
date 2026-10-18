`supports_select_union`: `union()` querysets. An ordered union is written as
`SELECT * FROM LATERAL (<union>) ORDER BY ...` (Db2 for i accepts no
expressions, such as the NULL ordering emulation, in the ORDER BY of a
union; LATERAL keeps outer references of a correlated subquery visible).
