`delete()` of a queryset filtered by a subquery on its own table (for
example `Book.objects.filter(pk__in=Book.objects.filter(...).values("pk"))`)
failed with SQL0115. Django rewrites such a delete as
`pk IN (SELECT * FROM (...) subquery)` in a new outer query, whose WHERE
the compiler did not recognise as a search condition: it wrapped the IN in
`CASE WHEN ... THEN TRUE ELSE FALSE END`, where Db2 for i rejects IN
(subquery).
