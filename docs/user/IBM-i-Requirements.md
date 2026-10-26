# IBM i requirements

## Release

IBM i **7.5** or later. The backend refuses older releases. A release newer
than the backend knows about works with the newest known capabilities and
logs a warning.

## Journaling (required)

Every table Django writes to must be **journaled**. The backend runs all data
changes under commitment control (also in autocommit mode, see
`TRUEAUTOCOMMIT` in [Configuration](Configuration.md)), and Db2 for i only
allows that on journaled tables. Without a journal you get **SQL7008**, see
[Troubleshooting](Troubleshooting.md).

- A library created with SQL `CREATE SCHEMA` has a `QSQJRN` journal, and new
  SQL tables in it are journaled automatically.
- A library created with `CRTLIB` has no journal. Create one named `QSQJRN`;
  SQL tables created afterwards are journaled automatically:

  ```
  CRTJRNRCV JRNRCV(MYLIB/QSQJRN0001) THRESHOLD(100000) TEXT('Journal receiver')
  CRTJRN JRN(MYLIB/QSQJRN) JRNRCV(MYLIB/QSQJRN0001) MNGRCV(*SYSTEM) DLTRCV(*YES) TEXT('Journal')
  ```

  `MNGRCV(*SYSTEM) DLTRCV(*YES)` lets the system attach new receivers and
  delete old ones. Check this against your backup and recovery policy:
  deleting receivers may not be acceptable on production systems.
- Instead of a `QSQJRN` journal, the library itself can be journaled with
  `STRJRNLIB`, to a journal of any name. With the default inherit rules
  (`INHRULES`), new tables in it start journaling to that journal. This rests
  on IBM's STRJRNLIB documentation and is not yet tested on IBM i; the
  `QSQJRN` journal above is.
- Tables that existed before the journal was created are **not** journaled
  automatically; start journaling for them with `STRJRNPF`.
- Constraints need the journal too: a primary key, a unique constraint, a
  foreign key and a CHECK constraint (the check of a positive integer field,
  a model's `CheckConstraint`) fail with **SQL7008** on a table that is not
  journaled, both in `CREATE TABLE` and in `ALTER TABLE ... ADD CONSTRAINT`,
  also in autocommit mode. A migration that adds a check constraint to an
  existing table (`AddConstraint`, or `AlterField` to a positive integer
  field) therefore needs that table journaled, for example with `STRJRNPF`
  for a table created before the journal.

### System check `django_db2_for_i.W001`

Django's database checks (`migrate`, `manage.py check --database <alias>`)
warn when new tables in a library of a checked alias would not be journaled:
the library given as `NAME` and the one given as `TEST["NAME"]`. A library is
fine when it has a `QSQJRN` journal, or when it is journaled with `STRJRNLIB`
and new objects inherit that. The check only reads catalog services
(`QSYS2.LIBRARY_INFO`, `QSYS2.OBJECT_STATISTICS`), and needs `*READ` authority
to the library. A library that does not exist is not reported. It does not
look at tables that already exist (see `STRJRNPF` above).

| Id | Meaning |
|---|---|
| `django_db2_for_i.W001` | New tables in the library would not be journaled. |
| `django_db2_for_i.W002` | The journaling state could not be read (the warning shows the error). |

`migrate` checks only the alias it migrates; to check several aliases, name
each one: `manage.py check --database default --database other`. To silence
a check, add its id to `SILENCED_SYSTEM_CHECKS`; with W001 silenced the
backend does not query the journaling state at all:

```python
SILENCED_SYSTEM_CHECKS = ["django_db2_for_i.W001"]
```

## Test library

Django's test runner needs an existing library for tests (see
[Configuration](Configuration.md#test-database-test)): journaled as above,
and holding nothing but test data. A fresh library created with `CRTLIB` plus
a `QSQJRN` journal is fine.

When the first constraint (for example a primary key) is created in a library,
Db2 for i adds SQL catalog views to it (`SYSCST`, `SYSKEYCST`, `SYSREFCST`,
`SYSCHKCST`, `SYSCSTCOL`, `SYSCSTDEP`). They belong to the system; the backend
ignores them and never drops them.

## Authorities

> **Partly documented.** What has been verified so far:

- The user profile needs to read the catalog views in `QSYS2` (for example
  `QSYS2.SYSTABLES`, `QSYS2.SYSCOLUMNS`, `QSYS2.SYSCST`, `QSYS2.SYSREFCST`).
- To run migrations, it needs the authority to create, alter and drop tables
  and indexes in the library given as `NAME`.
- Creating the journal in a library you own works for a normal user profile
  (verified on a public test system).

Still to be documented: authorities for creating test schemas, and the
minimum object authorities for an application that only reads and writes data.

## ALTER TABLE that may lose data

`DROP COLUMN`, narrowing column changes (for example a shorter
`max_length`, or `IntegerField` to `SmallIntegerField`) and making a column
`NOT NULL` (`null=True` to `null=False`) make Db2 for i send
the inquiry message **CPA32B2** ("Change of file may cause data to be lost"),
also for an empty table. Its default reply is "cancel". Widening changes (a
longer `max_length`, a larger integer or decimal type), making a column
nullable, changing its default and adding columns are not affected.

**Migrations need nothing extra: no reply list entry and no administrator.**
While a migration (or your own schema editor) removes or alters a field, the
backend sets the query option `SUPPRESS_INQUIRY_MESSAGES` to `*YES` for its
own job, so Db2 for i does not send CPA32B2. It does this with
`QSYS2.OVERRIDE_QAQQINI`, which keeps a copy of the job's query options in
`QTEMP`. When the outermost schema editor is done, it discards that copy, and
CPA32B2 is back for everything else.

- This needs IBM i 7.5 or later: the option and `OVERRIDE_QAQQINI` are part
  of the base release. The user profile needs no special authority (verified
  on a public test system with a profile without special authorities).
- Only the job of the connection is affected: no system value, no reply list
  entry, nothing outside `QTEMP`. Other query options of the job stay as they
  were.
- CPA32B2 stays a safety net outside field changes: an `ALTER TABLE` in
  `RunSQL` or on a cursor of your own is still cancelled (see
  [Troubleshooting](Troubleshooting.md#alter-table-cancelled-cpa32b2-hy008)).
- With CPA32B2 out of the way, Db2 for i would truncate a longer string or
  round away decimals silently. So before a narrowing change the backend
  looks for a value that would change and refuses the migration with
  `DataError` if it finds one (see
  [Known limitations](Known-Limitations.md#narrowing-a-column)).
- If the copy cannot be discarded on a connection that still works, the
  backend closes that connection, so the suppression can never reach an
  `ALTER TABLE` outside migrations.

**To keep CPA32B2 for migrations too**, turn the suppression off:

```python
"OPTIONS": {"suppress_inquiry_messages": False}
```

Then such migrations fail with an explanation, unless the system reply list
answers CPA32B2:

1. An administrator adds a system reply list entry once (pick a free
   sequence number, see `WRKRPYLE`):

   ```
   ADDRPYLE SEQNBR(<free number>) MSGID(CPA32B2) RPY('I')
   ```

   The entry answers CPA32B2 with "ignore" for every job that uses the system
   reply list, so check which jobs on your system run with
   `INQMSGRPY(*SYSRPYL)` first. An entry with comparison data (`CMPDTA`) can
   limit it, for example to one library.
2. The database settings use the system reply list:

   ```python
   "OPTIONS": {"inquiry_message_reply": "*SYSRPYL"}
   ```

   The backend changes the job's `INQMSGRPY` when it connects (it reads the
   current value first and refuses to change anything if it cannot) and
   restores that value when the connection closes. For a single migration you
   can also call `connection.set_inquiry_message_reply("*SYSRPYL")` and
   `connection.restore_inquiry_message_reply()` yourself.

The user profile needs no special authority to change its own job's
`INQMSGRPY` (verified on a public test system). The check for values that
would change runs on this path too.

## Network

The database host server must be reachable: port **9471** (TLS, default) or
**8471** (without TLS).

> **Not documented yet:** whether other host server ports (server mapper 449,
> sign-on 8476/9476) must be reachable too; so far only setups where they were
> open have been tested.
