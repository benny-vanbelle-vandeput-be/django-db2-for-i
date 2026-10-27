A column default containing `%` (`default` or `db_default`) was stored
with the `%` doubled when a migration created the table or added the
column (`DEFAULT '100%%'` for `"100%"`), and a one-character default `"%"`
failed with SQL0574. `sqlmigrate` showed the doubled `%` too. Changing a
default with `AlterField` was not affected.
