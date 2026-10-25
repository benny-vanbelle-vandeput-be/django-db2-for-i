- Foreign key violations (SQL0530, SQL0531, SQL0532) now raise
  `IntegrityError` instead of `DatabaseError`: Db2 for i reports them with
  the generic SQLSTATE `HY000`, so they are classified by SQLCODE, as CHECK
  violations are. This matters for foreign key constraints that exist in the
  database already, such as on tables not managed by Django migrations.
- A CHECK constraint that existing rows violate (SQL0544, for example
  `AlterField` to a `PositiveIntegerField` over negative values) now raises
  `IntegrityError` instead of `DatabaseError`.
