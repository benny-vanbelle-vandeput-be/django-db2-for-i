# Troubleshooting

Errors are listed by SQLCODE (the negative number in parentheses at the end of
the driver message, e.g. `(-7008)`). The SQLSTATE alone is often the generic
`HY000`.

## SQL7008 (-7008): "... not valid for operation"

```
[HY000] ... SQL7008 - MYTABLE in MYLIB not valid for operation. (-7008)
The table's library needs a QSQJRN journal: ...
```

**Cause:** the table is not journaled. All data changes run under commitment
control, which needs journaled tables.

**Fix:** create a `QSQJRN` journal in the library and journal the table, see
[IBM i requirements](IBM-i-Requirements.md#journaling-required). Libraries
created with `CREATE SCHEMA` are journaled already.

## SQL0910 (-910): "... has a pending change"

```
[HY000] ... SQL0910 - Object MYTABLE in MYLIB type *FILE has a pending change. (-910)
```

**Cause:** a DDL statement (for example `ALTER TABLE ... RESTART WITH` to
reset an identity) ran in a transaction that has uncommitted changes on the
same table.

The backend avoids this for its own identity restarts (flush, `loaddata`) by
running them after the commit. You can still hit it with your own DDL inside
`transaction.atomic()`, or in a `TestCase` (see
[Known limitations](Known-Limitations.md#identity-values-after-loading-fixtures-in-testcase)).

**Fix:** run the DDL outside the transaction, or commit first.

## Test library refused

Raised as `TestDatabaseRefused` before or after a test run. Before the tests,
nothing has been changed when it is raised.

| Message starts with | Cause and fix |
|---|---|
| "Test library ... does not exist" | Create the library; the backend never creates schemas. |
| "... has no QSQJRN journal" / "... is not active" | Create or start the journal, see [IBM i requirements](IBM-i-Requirements.md#journaling-required). |
| "... contains objects that do not belong to the Django models under test" | The library holds other tables or views. Use a library for tests only. |
| "... contains tables of the Django models under test ... but no DJDB2I_TEST_MARKER table" | The library looks like an application library. Use an empty library; drop the tables yourself only if you are sure they hold no data you need. |
| "Could not drop ... object(s)" | Cleanup failed; the marker is kept so the next run (with `--noinput`) can finish the cleanup. |

## More errors

> **Not documented yet.** Further entries (sign-on failures, TLS certificate
> problems, `22001` string too long) will be added as they are verified.
