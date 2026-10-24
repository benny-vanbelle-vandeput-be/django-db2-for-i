`bin/ibmi-cleanup` also finds a test table that a crashed run had renamed:
a `RENAME TABLE` of a table on the cleanup list updates its entry to the
new name before the statement runs.
