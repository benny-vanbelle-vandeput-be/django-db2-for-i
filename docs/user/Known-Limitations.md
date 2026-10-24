# Known limitations

## TimeField has no fractional seconds

Db2 for i `TIME` stores whole seconds only. The backend removes microseconds
before saving and in lookups, so `filter(t=value)` matches what was stored.
Use a `DateTimeField` (`TIMESTAMP(6)`, microseconds kept) if you need
sub-second precision.

## Emoji count as two characters in CharField

`CharField(max_length=n)` is `NVARCHAR(n)` (UTF-16). `n` counts UTF-16 code
units, which equals Django's character count for all common characters
(including accented ones), but characters outside the Basic Multilingual
Plane, such as emoji, use **two** units. A value that passes Django's
`max_length` validation can then be rejected by the database with
SQLSTATE `22001` ("Input data is too big to fit into field"); it is never
silently truncated. Example: 6 emoji fit `max_length=10` in Django but not in
`NVARCHAR(10)`.

## Text outside the job CCSID

Statement text and string parameters travel as Unicode (UTF-8), so any
character can appear in SQL and in `NVARCHAR`, `NCHAR` and `NCLOB` columns
(every `CharField` and `TextField`). Limits come from the IBM i job CCSID
(273 on PUB400; see `QSYS2.ACTIVE_JOB_INFO`):

- **`VARCHAR` / `CHAR` columns in the job CCSID** (tables not created by
  Django): a character the CCSID cannot hold, such as `€` in CCSID 273 or an
  emoji, is refused with SQLSTATE `22018`, never replaced.
- **Names**: table, column and alias names must use characters of the job
  CCSID; others fail with `SQL0104`.
- **Comments** (`COMMENT ON`, used once `db_comment` is supported): the text
  must use characters of the job CCSID; others fail with `SQL0104`.

### Run in a UTF-8 locale

In a process locale that is not UTF-8, the IBM i Access ODBC driver garbles
non-ASCII characters in **result column names and error messages**. Data
values (literals, parameters, results) stay correct. The backend logs a
warning on the `django_db2_for_i` logger at the first connection when the
locale is not UTF-8.

Python uses UTF-8 by default, also in the plain `C`/`POSIX` locale (PEP
538), but an explicit `LC_ALL=C` (or another non-UTF-8 locale) switches it
off. **Fix:** run with a UTF-8 locale, for example `LANG=C.UTF-8` with
`LC_ALL` unset, or `LC_ALL=C.UTF-8`. pyodbc's metadata decoding
(`setdecoding(SQL_WMETADATA, ...)`) cannot repair it: the driver returns the
text already broken.

## Parameters in RawSQL and extra() must be cast

A bare `%s` in `RawSQL()` or in `extra(select=..., select_params=...)` (and
`extra(where=..., params=...)`) becomes an untyped parameter marker.
Db2 for i rejects untyped markers in the select list (SQL0418, "Use of
parameter marker, NULL, or UNKNOWN not valid"), and two untyped markers
compared with each other give wrong results. The backend types the values
of Django's own expressions, but it does not rewrite your SQL. Cast the
parameter in the SQL instead:

```python
# Fails with SQL0418:
Company.objects.annotate(foo=RawSQL("%s", ["value"]))
# Works:
Company.objects.annotate(foo=RawSQL("CAST(%s AS NVARCHAR(20))", ["value"]))
```

The same applies to `extra()`:

```python
# Fails with SQL0418:
Item.objects.extra(select={"foo": "%s"}, select_params=(1,))
# Works:
Item.objects.extra(select={"foo": "CAST(%s AS INTEGER)"}, select_params=(1,))
```

Use the SQL type of the value: `NVARCHAR(n)` for strings, `INTEGER`,
`DECIMAL(p, s)`, `DATE`, `TIMESTAMP(6)`, `BOOLEAN`, ...

## Custom SQL with a bare NULL

Db2 for i does not accept an untyped `NULL` as an expression (`WHERE NULL IS
NULL` fails with SQL0206). Custom expressions, transforms or `RawSQL` that
produce a bare `NULL` must cast it, e.g. `CAST(NULL AS INTEGER)`. Django's
own expressions do this already on this backend.

## One statement per execute, without a closing `;`

Db2 for i runs one statement per call and rejects a `;` at its end
(`SQL0104 - Token ; was not valid`). The backend removes **one** trailing `;`
(and the whitespace after it) from every statement, as Django's Oracle backend
does, so `cursor.execute("SELECT ... ;")` works. A second `;`, or several
statements in one string, still fail with `SQL0104`: run them one by one.

## Table and column names are uppercase

Names are created in uppercase (`basic_article` becomes `BASIC_ARTICLE`).
Mixed-case `db_table` / `db_column` names are not preserved.

## Case-insensitive lookups do not use normal indexes

`iexact`, `icontains`, `istartswith` and `iendswith` compare
`UPPER(column)` with `UPPER(value)`. A normal index on the column cannot be
used for `UPPER(column)`, so these lookups scan the table. (`icontains` and
`iendswith` cannot use an index anyway, as with every `LIKE '%...'`.) Options
for a later version: a derived index on `UPPER(column)`, or a case-insensitive
sort sequence for the connection; neither is implemented yet.

## Time zones

There is no time zone aware timestamp type. With `USE_TZ = True` (Django's
default), aware datetimes are stored as naive values in the connection's time
zone (UTC unless the database's `TIME_ZONE` is set) and made aware again when
read. With `USE_TZ = False`, aware datetimes raise `ValueError`.

**Date functions need the database's time zone.** Lookups and functions
that work in a time zone (`__year`, `__week_day`, `__hour`, `__date`, `Extract()`,
`Trunc()`, `TruncDate()`, `dates()`, `datetimes()`, ...)
run in the zone the database stores datetimes in. With `USE_TZ = True`, the
current time zone (Django's `TIME_ZONE`, `timezone.activate()`, or a
`tzinfo` argument) must equal the database's `TIME_ZONE` (UTC if not set);
otherwise they raise `NotSupportedError` naming both zones. Converting
between zones is not supported yet: a fixed UTC offset would be wrong across
daylight saving time changes.

Choosing the zone:

- **New tables:** UTC is safest. Leave the database's `TIME_ZONE` unset and set
  Django's `TIME_ZONE = "UTC"` if you use date lookups.
- **Existing IBM i tables with local times** (written by RPG or COBOL programs,
  for example): set the database's `TIME_ZONE` and Django's `TIME_ZONE` to that
  zone, e.g. both `"Europe/Brussels"`:

  ```python
  TIME_ZONE = "Europe/Brussels"
  DATABASES = {"default": {"ENGINE": "django_db2_for_i", ..., "TIME_ZONE": "Europe/Brussels"}}
  ```

- Local time with daylight saving time has an **ambiguous hour every autumn**:
  when the clock goes back, the times of that hour occur twice and a naive
  `TIMESTAMP` cannot tell them apart. Django reads them as the first
  occurrence. UTC has no such hour.

## Identity values after loading fixtures in TestCase

Primary keys are identity columns (`GENERATED BY DEFAULT AS IDENTITY`). They
do not move past explicit key values, so after loading data with explicit
keys the backend restarts them at the next free value. Db2 for i refuses that
restart inside a transaction that already changed the table (SQL0910), so it
is done after the commit. In Django's `TestCase` the transaction is never
committed: a test that loads fixtures with explicit keys and then creates an
object without a key can get an `IntegrityError` (duplicate key). Workaround:
give such objects explicit keys, or use `TransactionTestCase` (expected to
work because `loaddata` commits there; not verified yet).

## Dropping a table also drops what depends on it

On Db2 for i, `DROP TABLE` without an option behaves like `DROP TABLE ...
CASCADE`: it also drops the views that select from the table and the foreign
keys in other tables that reference it, and the referencing tables lose those
constraints without notice. `RESTRICT` would refuse instead (SQL0478).

The backend's schema editor drops tables this way, so **removing a Django
model (for example with a migration that deletes it) also drops non-Django
views and foreign keys that depend on its table**, including objects created
outside Django. Check for dependent objects before deleting a model whose
table is used by other applications.

## Dropping, narrowing or making a column NOT NULL needs a reply list entry

`RemoveField` (`ALTER TABLE ... DROP COLUMN`), changes that narrow a column
(a shorter `max_length`, a smaller integer type) and `AlterField` from
`null=True` to `null=False` make Db2 for i send inquiry
message CPA32B2 ("Change of file may cause data to be lost"), also on an empty
table. Its default reply cancels the change, and the backend raises
`OperationalError` with an explanation. To allow such changes, an
administrator adds a system reply list entry and the database settings set
`OPTIONS["inquiry_message_reply"] = "*SYSRPYL"`, see
[IBM i requirements](IBM-i-Requirements.md#alter-table-that-may-lose-data).

**A cancelled change to `NOT NULL` can still change rows.** For a field that
goes from `null=True` to `null=False` with a `default` or `db_default`,
Django first sets the existing NULLs to that default (`UPDATE ... WHERE ...
IS NULL`), then sends `SET NOT NULL`. Migrations on Db2 for i do not run in a
transaction yet (`can_rollback_ddl` is off), so when CPA32B2 cancels
`SET NOT NULL` the column stays nullable but the NULLs have already been
replaced by the default. Run such a migration only where the reply list entry
is in place, or check for NULLs first.

The backend writes `DROP COLUMN` without `CASCADE` or `RESTRICT` on every
Django version (Django 5.2's own text adds `CASCADE`). What Db2 for i does
with views or indexes that depend on the column is not verified yet: on a
system without the reply list entry the statement is always cancelled first.

## Differences between the supported Django versions

The backend behaves the same on Django 5.2, 6.0 and 6.1, except:

- `StringAgg` requires Django 6.0 or later (see "StringAgg results are limited
  to 1M characters"). `AnyValue` and ordered aggregates
  (`Aggregate(order_by=...)`) are Django 6.0 features as well.
- Database-level `on_delete` (Django 6.1) is not supported yet on any version.
- Generated SQL differs in small ways between versions (Django 5.2 and 6.0
  leave subquery aliases unquoted, which Db2 for i reads the same way).

## Tables must be in the library given as NAME

Unqualified constraint names (such as the names of foreign key constraints
Django adds) resolve to the connection's current schema, which is the library
given as `NAME`. Db2 for i requires a constraint to be in the same schema as
its table, so creating a constraint on a table in another library fails with
`SQL5051 - Qualifier ... not same as name ...`. Models whose `db_table` points
to another library are therefore **not supported yet**; planned, see
[#124](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/124).
(Verified for foreign key constraints; index names in another library have not
been tested yet.)

## Strings longer than 1M characters are refused

String parameters longer than **1,048,576 UTF-16 units** (1M; an emoji
counts as two) are refused with `NotSupportedError`, before anything is
sent. 1M characters is the capacity of a `TextField` column (`NCLOB`, which
is `NCLOB(1M)`), so a longer value could not be stored there anyway.

Why a limit at all: up to it, the backend sends every string in one piece
(pyodbc `maxwrite`). Above it pyodbc would send the value in chunks again,
and chunked strings lose characters in the IBM i Access ODBC driver (fixed
after 0.1.0a1 for everything up to the limit; before, strings over 8184
characters were refused). Columns declared larger than `NCLOB(1M)` by hand
cannot receive longer values through this backend yet.

Not limited: bytes (`BinaryField`, `BLOB`). Above 4 MiB they are sent in
chunks, which is safe for binary data. Reading long values is not limited.

## Database defaults must be constants

`db_default` accepts constants only (strings, numbers, booleans, dates,
times, naive datetimes, bytes), written into the table definition as
literals. Expressions such as `db_default=Now()` raise `NotSupportedError`,
and so do time zone aware datetimes, because Db2 for i `TIMESTAMP` has no
time zone. `db_default=None` means "no default".

## Regular expressions use the ICU dialect

As on every Django backend, `regex` and `iregex` use the database's regular
expression dialect, not Python's `re`. Db2 for i evaluates them with the
`REGEXP_LIKE` predicate, which uses ICU (International Components for
Unicode) regular expressions; see IBM's "REGEXP_LIKE predicate" and
"Regular expression control characters" in the Db2 for i SQL reference.

- `iregex` adds the `i` flag (case-insensitive, also for non-ASCII
  letters); no other flags are set: `.` does not match line terminators and
  `^` / `$` match only at the start and end of the whole value.
- Backreferences (`(ab)\1`), character classes, `\d`, `\w` and Unicode
  characters in patterns work.
- The pattern is sent as `NVARCHAR(16370)`, so patterns longer than 16370
  characters fail.
- `NULL` values never match (also not `^$`).
- Non-string columns (e.g. an `IntegerField`) are converted to text by Db2
  for i before matching.
- The ICU option of IBM i must be installed (standard on IBM i 7.5);
  without it the predicate fails with SQL0204.

## StringAgg results are limited to 1M characters

`StringAgg` uses Db2 for i's `LISTAGG`. The result holds up to 1M
(1048576) characters; a longer result fails with SQL0802 ("Data conversion
or data mapping error") instead of being truncated. `StringAgg(...,
distinct=True)` is not supported yet (Django raises NotSupportedError).

`StringAgg` requires Django 6.0 or later: on Django 5.2 it exists only in
`django.contrib.postgres`, which works with PostgreSQL only.

## Numbers with more than 63 digits

A filter value that does not fit its column (an integer out of a
`SmallIntegerField`'s range in an `__in` list or a `__range`, a `Decimal` with
more digits than `max_digits` / `decimal_places`) works and is compared
exactly: it matches what exact arithmetic says, and is never rounded or
truncated. Db2 for i's `DECIMAL` holds at most 63 digits, so a value that
needs more (for example `Decimal(10**63)`, or `Decimal("1E-70")` with 70
decimal places) cannot be compared and raises `NotSupportedError`. Trailing
zeros do not count against the limit. `Decimal("NaN")` and infinities are
refused by Django's `DecimalField` itself.

## Conversion errors in selected values give NULL

When a selected value cannot be converted, or divides by zero, Db2 for i
returns NULL for that row instead of raising an error, and the driver gives
no warning. For example, `Cast("text", IntegerField())` on a row whose text is
not a number gives `None` for that row; other rows convert normally. In a
filter (`WHERE`), the same conversion raises SQL0802 ("Data conversion or
data mapping error"). Validate or clean such data before casting, or check
for unexpected `None` values.

## Comparison values longer than 16370 characters

A filter value longer than its column (for example a search term longer than
a `CharField`'s `max_length`) works and simply matches nothing; it is never
truncated. Values longer than 16370 UTF-16 code units (an emoji counts as
two) cannot be compared and raise `NotSupportedError`; no column can hold a
value that long except a `TextField`, whose lookups are not affected.

## Durations

A `DurationField` is stored as a BIGINT of microseconds, as on MySQL and
SQLite. The largest value is 2^63 - 1 microseconds (106,751,991 days 4:00:54);
Python's `timedelta.max` (999,999,999 days) does not fit. A `timedelta`
outside that range is refused with a `ValueError` before anything is sent,
in saves, filters and `Value()`.

**Results outside years 1 to 9999 become NULL, silently.** Adding a duration
to a date, time or datetime gives NULL instead of an error when the result
falls outside the timestamp range. In an update this **writes NULL**:

```python
# A deadline near 9999-12-31 plus 30 days: DEADLINE becomes NULL, no error.
Task.objects.update(deadline=F("deadline") + timedelta(days=30))
```

Validate ranges in the application before such updates (for example, filter
out rows whose result would pass year 9999, or check the duration first).

`TimeField + DurationField` wraps at 24 hours, as on PostgreSQL, and has no
fractional seconds (see "TimeField has no fractional seconds").

## Features not available yet

The backend is in early development; these are switched off for now and
enabled one at a time: foreign key constraints in the database, bulk insert,
returning columns, check constraints, JSONField, window functions, `select_for_update`,
`inspectdb`, and creating test schemas (tests
run in an existing library, see [Configuration](Configuration.md#test-database-test)).
