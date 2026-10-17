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
- Tables that existed before the journal was created are **not** journaled
  automatically; start journaling for them with `STRJRNPF`.

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

## Network

The database host server must be reachable: port **9471** (TLS, default) or
**8471** (without TLS).

> **Not documented yet:** whether other host server ports (server mapper 449,
> sign-on 8476/9476) must be reachable too; so far only setups where they were
> open have been tested.
