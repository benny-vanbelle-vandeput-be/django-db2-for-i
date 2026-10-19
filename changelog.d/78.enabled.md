`supports_tuple_lookups`: lookups on a multi-column relation
(`ForeignObject`) use row values: `(a, b) = (x, y)` and
`(a, b) IN (subquery)`. `exclude()` by such a relation now leaves out rows with
a NULL in one of its columns, as on other backends (it returned them before).
IN lists and `>`, `>=`, `<`, `<=` keep the expanded form, which Db2 for i
needs.
