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

## More errors

> **Not documented yet.** Further entries (sign-on failures, TLS certificate
> problems, `22001` string too long) will be added as they are verified.
