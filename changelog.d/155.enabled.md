- Check constraints (`supports_column_check_constraints`,
  `supports_table_check_constraints`): model `CheckConstraint`s are created
  in `CREATE TABLE` and by `AddConstraint` / `RemoveConstraint`, and a
  violation raises `IntegrityError` (SQL0545). Tables need a journal for
  constraints (SQL7008 otherwise; IBM i requirements).
