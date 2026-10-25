AddField of a NOT NULL field without any default no longer fails with
SQL0109 ("NOT NULL clause not allowed"). The column is added with the type's
system default, which is dropped right after. A table that already has rows
is refused with `IntegrityError` instead of silently giving those rows the
system default, as on PostgreSQL. In a migration's transaction the table is
locked during the check.
