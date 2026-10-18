Comparing a boolean column with a negated boolean value
(`filter(flag=~Value(False))`, `filter(flag=F("negated_annotation"))`) failed
with SQL0199: `NOT <value>` is a predicate, which Db2 for i rejects as an
operand. It is written as `CASE <value> WHEN TRUE THEN FALSE WHEN FALSE THEN
TRUE END`, which keeps NULL as NULL.
