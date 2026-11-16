# Upgrading

The backend is in beta: settings and behaviour may change between releases.
This page lists what can matter for an existing project, release by release.
The full list of changes is in the
[CHANGELOG](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/blob/main/CHANGELOG.md).

## How to upgrade

1. Read the sections below from the release after yours up to the new one.
2. Install the new release from its tag:

   ```sh
   pip install "django-db2-for-i @ git+https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i.git@v<version>"
   ```

3. Run your tests, then `python manage.py check --database default` and
   `python manage.py migrate` as usual. Optional: run the smoke set against
   your IBM i ([Check your own IBM i](Installation.md#check-your-own-ibm-i)).

## 0.1.0b5 (2026-11-16)

- **Comments are stored now:** `db_comment` and `db_table_comment` become
  `COMMENT ON COLUMN` / `COMMENT ON TABLE` in migrations, and introspection
  and `inspectdb` read them back. Before, the backend ignored them. No new
  migration is needed. A comment is written when a migration creates the
  table or field, or changes the comment, so tables that already exist keep
  no comment until then.
- **Only printable ASCII in a comment.** Any other character (an accent, €,
  an emoji) raises `NotSupportedError` before the migration changes anything,
  and `manage.py check` reports it as `django_db2_for_i.E006`. Change such a
  comment to plain ASCII before you upgrade. See
  [Known limitations](Known-Limitations.md#comments).
- **A `JSONField` whose whole value is a number, a string, `true`, `false`
  or JSON null** is now found by `=`, `__in` and (Django 6.1) `JSONNull()`.
  Before, such rows were stored and read back, but these lookups did not
  match them, so a query may now return rows it did not return before.

## 0.1.0b4 (2026-11-14)

- **New warning in migrations: `RecordFormatChanged` (`django_db2_for_i.W003`).**
  A migration that adds, drops, changes or copies a column warns once per
  table: RPG and CL programs compiled over that table must be compiled
  again. Nothing to change if no programs use your tables; otherwise see
  [Known limitations](Known-Limitations.md#programs-over-a-changed-table).
- **Renaming a column is possible, opt-in:** `OPTIONS["column_rename"] = "copy"`
  ([Configuration](Configuration.md)). Without it a rename is refused, as
  before.
- **Migrations write slightly different SQL:** a foreign key column added
  by `AddField` gets its constraint in the same `ALTER TABLE`, and several
  changes to one column are one statement. Only `sqlmigrate` output
  differs from earlier releases; the tables that result are the same.
- **Removing a field also drops an index or view on its column** (newly
  documented, not changed): Db2 for i's default is `CASCADE`. See
  [Known limitations](Known-Limitations.md#removing-a-field-drops-what-depends-on-its-column).
- `Chr` and `Ord` now work beyond ASCII.
- **Fixed: a table stayed locked after some migrations.** In 0.1.0b3 and
  earlier, after a migration that adds a `NOT NULL` column without a default
  or narrows a column, other jobs could neither read nor write that table
  (SQL0913) until the migrating connection closed. If you added
  `connection.close()` after `call_command("migrate")` as a workaround, it
  is no longer needed (it does no harm). `manage.py migrate` released the
  lock when it ended.
- **Newly documented, not changed:** `bulk_create(ignore_conflicts=True)`,
  and `add()` / `set()` of a `ManyToManyField`, skip a row as soon as another job has inserted the same
  key, before that job commits. If that job then rolls back, neither row is
  in the table. See [Known limitations](Known-Limitations.md#bulk_create-with-ignore_conflicts-or-update_conflicts).

## 0.1.0b3 (2026-11-11)

New: window functions, `JSONField`, the database functions and, on Django
6.1, DB-level `on_delete`. Where the database functions differ from what
you may expect from other databases:

- `Length` counts characters, `Concat` treats NULL as empty text, and
  `Cast()` of a number to a decimal rounds (halves away from zero) instead of
  cutting off.
- `Reverse`, `SHA224` and `SHA384` raise `NotSupportedError`: Db2 for i has
  no such functions.
- `Chr` and `Ord` work on ASCII only.

## 0.1.0b2 (2026-11-02)

- **`m2m.add()`, `m2m.set()` and `bulk_create(ignore_conflicts=True)` use a
  `MERGE`.** When two jobs insert the same row at the same moment it can
  raise `IntegrityError` (SQL0803) or `OperationalError` (SQL0913); retry
  inside `transaction.atomic()`. The code is in
  [Known limitations](Known-Limitations.md#errors-when-two-jobs-insert-the-same-row-at-the-same-time).
- **`bulk_create()`** inserts many rows per statement, and splits batches
  with `TextField` or `BinaryField` columns into smaller ones (at most 512
  parameter markers for those columns). A larger `batch_size` is reduced;
  nothing to change in your code.
- `save()` and `create()` read the key and `db_default` values from the
  insert itself instead of a second query.
- A nullable `unique=True` field, `unique_together` and
  `UniqueConstraint(fields=...)` accept several NULLs.

## 0.1.0b1 (2026-10-29)

- **Migrations can drop columns, narrow them and make them `NOT NULL`
  without a system reply list entry** (new option
  `suppress_inquiry_messages`, default `True`). If you set
  `inquiry_message_reply` to `"*SYSRPYL"` only for migrations, you can
  remove it; it stays the fallback where `QSYS2.OVERRIDE_QAQQINI` is not
  allowed. See
  [IBM i requirements](IBM-i-Requirements.md#alter-table-that-may-lose-data).
- A narrowing change that would truncate a string or round a number is now
  refused with `DataError` before anything changes; fix the data first
  ([Narrowing a column](Known-Limitations.md#narrowing-a-column)).
- An `AlterField` to a type Db2 for i cannot convert in place (for example
  text to a date) raises `NotSupportedError` before any SQL is sent; the
  workaround is a new field plus a data migration
  ([Known limitations](Known-Limitations.md#changing-a-column-to-an-incompatible-type)).

## From an alpha (0.1.0a1 to 0.1.0a4)

Read every section above. The alphas were early development releases; their
changes are in the CHANGELOG.
