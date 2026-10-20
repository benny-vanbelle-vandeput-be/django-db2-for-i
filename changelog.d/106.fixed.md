A CHECK constraint violation (SQL0545, e.g. a negative value in a
`PositiveIntegerField`) raised `DatabaseError` because the driver reports
the generic SQLSTATE `HY000`; it now raises `IntegrityError`, like the other
constraint violations.
