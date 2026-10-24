`RenameModel` / `AlterModelTable` (`RENAME TABLE`) and `RenameIndex`
(`RENAME INDEX`, `can_rename_index`) work, and so do identity changes in
`AlterField`: AutoField to IntegerField drops the identity, IntegerField to
AutoField adds it and continues after the largest key, and AutoField to
BigAutoField widens it. Renaming a column raises `NotSupportedError`: Db2 for
i has no statement for it; keep the column with `db_column` (Known
limitations).
