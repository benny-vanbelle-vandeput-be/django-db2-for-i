Grouping by an annotation whose SQL contains a value
(`annotate(b=Q(pages__lt=100)).values("b").annotate(n=Count("id"))`,
`values(m=Mod("pages", 10))`, a subquery or `Exists()` that filters with a
value), or by an expression used inside another selected expression, failed
on Db2 for i (30101 / SQL0122). Such grouped expressions are computed in a
`LATERAL` derived table and grouped by its columns; other grouping keeps
its SQL.
