A selected value that cannot be converted, or divides by zero (e.g.
`Cast("text", IntegerField())` on non-numeric text), is NULL on Db2 for i,
without an error or a driver warning; in filters the same raises SQL0802.
See docs/user/Known-Limitations.md.
