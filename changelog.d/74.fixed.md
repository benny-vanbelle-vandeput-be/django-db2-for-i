Filtering a multi-column relation (`ForeignObject`) by a subquery
(`account__in=<queryset>`) failed with SQL0216: the IN (subquery) rewrite
from #71 also reached `(a, b) IN (subquery)` in WHERE, and it compared one
column with a tuple. In WHERE the condition is no longer rewritten; outside a
search condition (XOR, a selected `Q`) the rewrite now has one column per
tuple element, and stays exactly three-valued.
