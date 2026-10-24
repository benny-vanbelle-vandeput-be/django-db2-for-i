`AlterField` changes that widen a column (a longer `max_length`, a larger
integer or decimal type), make it nullable or change its default work on
Db2 for i: the schema editor writes `ALTER COLUMN ... SET DATA TYPE`. The
CPA32B2 error for narrowing changes and `NOT NULL` now names `NOT NULL` and
points to the documentation; Known limitations explains that a cancelled
change to `NOT NULL` can leave NULLs set to the default.
