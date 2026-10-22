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

## SQL0545 (-545): "... not allowed by CHECK constraint"

```
IntegrityError: [HY000] ... SQL0545 - INSERT, UPDATE, or MERGE not allowed by CHECK constraint. (-545)
```

**Cause:** a row violates a CHECK constraint, for example a negative value
in a `PositiveIntegerField` column or a model `CheckConstraint`.

The driver reports the generic SQLSTATE `HY000` instead of `23513`; the
backend raises `IntegrityError` by SQLCODE, as for other constraint
violations (duplicate key SQL0803, NOT NULL SQL0407).

**Fix:** correct the value; validate the model (`full_clean()`) to catch it
before saving.

## ALTER TABLE cancelled (CPA32B2, HY008)

```
OperationalError: Db2 for i cancelled this ALTER TABLE because it may lose data
(inquiry message CPA32B2, default reply C; job log CPD32CE). ...
```

The driver itself only reports `[HY008] ... Operation cancelled. (30071)`; the
backend checks the job log and replaces it with this explanation.

**Cause:** `DROP COLUMN` or a narrowing column change (also on an empty
table) sends inquiry message CPA32B2, and its default reply cancels the
change.

**Fix:** an administrator adds `ADDRPYLE SEQNBR(<free number>) MSGID(CPA32B2)
RPY('I')`, and the database settings set `OPTIONS["inquiry_message_reply"] =
"*SYSRPYL"`, see [IBM i requirements](IBM-i-Requirements.md#alter-table-that-may-lose-data).
If the message says the connection already uses `*SYSRPYL`, the reply list
entry is missing or does not match.

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

## 22018: "CWBNL0107 - Converted ... errors found"

A string parameter contains a character the target column's CCSID cannot
hold, for example `€` or an emoji in a `VARCHAR` column in CCSID 273. Django
creates `NVARCHAR`/`NCLOB` columns, which hold any character; the error comes
from columns created outside Django. See
[Known limitations](Known-Limitations.md#text-outside-the-job-ccsid).

## Garbled column names or error messages

Log message: *"The process locale is not UTF-8 (...): the IBM i Access ODBC
driver garbles non-ASCII characters in result column names and error
messages"*.

Non-ASCII characters in result column names or error messages are garbled
when the Python process does not run in a UTF-8 locale, for example with
`LC_ALL=C`. Data values are not affected. Run with a UTF-8 locale:
`LANG=C.UTF-8` with `LC_ALL` unset, or `LC_ALL=C.UTF-8` (for a service, set
it in its environment, e.g. `Environment=LANG=C.UTF-8` in a systemd unit).
See [Known limitations](Known-Limitations.md#run-in-a-utf-8-locale).

## Columns not in the order of the model's fields

**Not an error.** A table's columns follow the order of the model's fields in
Django (`Model._meta.local_fields`), and the backend writes `CREATE TABLE`
in exactly that order. Django orders fields by the order in which the field
objects were created, not by the order of the base classes: fields inherited
from an abstract base class or a mixin are copies that keep their original
position, so they usually come **before** the model's own fields, in the
order the bases were defined in their modules. For example:

```python
class TimestampedMixin(models.Model):
    created = models.DateTimeField(null=True)
    class Meta:
        abstract = True

class TitledBase(models.Model):
    title = models.CharField(max_length=50)
    class Meta:
        abstract = True

class Article(TimestampedMixin, TitledBase):
    body = models.CharField(max_length=100)
```

gives the columns `ID, CREATED, TITLE, BODY`. A field added later with a
migration (`AddField`) is appended at the end of the table, as `ALTER TABLE
... ADD COLUMN` always appends on Db2 for i. Code that needs a fixed column
order should name the columns (`SELECT ID, TITLE ...`), not rely on
`SELECT *`.

## More errors

> **Not documented yet.** Further entries (sign-on failures, TLS certificate
> problems, `22001` string too long) will be added as they are verified.
