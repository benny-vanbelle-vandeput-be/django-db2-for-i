`IN (subquery)` inside Django's XOR emulation (`Q(pk__in=...) ^ Q(...)`) or a
selected `Q(...__in=<subquery>)` failed with SQL0115: Db2 for i accepts IN
(subquery) only as a search condition. There it is written as an exact
three-valued expression of first-row subqueries, also when negated.
