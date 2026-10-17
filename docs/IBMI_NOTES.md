# IBM i notes

IBM i quirks and probe findings. Every claim here is backed by a probe in
`probes/` or by a cited IBM source, with the date it was checked.

## IBM i Access ODBC Driver for Linux

Checked 2026-10-16 against IBM's repository
(`https://public.dhe.ibm.com/software/ibmi/products/odbc/debs/dists/1.1.0/`):

- Package `ibm-iaccess`, latest version `1.1.0.29-1.0` (amd64).
  Depends on `libodbc2, libodbcinst2, odbcinst, libstdc++6`.
- Architectures published: **amd64, i386, ppc64el. No arm64.** Apple Silicon
  hosts must run the `full` image as `linux/amd64` (emulated).
- The repository is **unsigned** (no `Release.gpg` / `InRelease`); IBM's own
  `.list` file uses `[trusted=yes]`. We pin the `.deb` by SHA256 instead.
- The package's postinst registers drivers from
  `/opt/ibm/iaccess/unixodbcregistration`:
  - `IBM i Access ODBC Driver`: `Driver=/opt/ibm/iaccess/lib/libcwbodbc.so`
    (32-bit path, not shipped in the amd64 package) and
    `Driver64=/opt/ibm/iaccess/lib64/libcwbodbc.so`;
  - `IBM i Access ODBC Driver 64-bit`: `Driver=/opt/ibm/iaccess/lib64/libcwbodbc.so`.
  - Both with `Threading = 0`, `DontDLClose = 1`.
- The package ships its license at `/opt/ibm/iaccess/doc/license.txt`.

## Test system: PUB400

Terms of use reviewed by the project owner on 2026-10-16 before any live probe.

Probes run 2026-10-16/17 (UTC) with `ibm-iaccess` 1.1.0.29 from the `tests` container.
User profile, library names and client IP are not recorded here; libraries
follow PUB400's naming pattern `<USER>1`, `<USER>2`, `<USER>B`.

### Reachability and TLS (`probe -- reachability`)
- TCP open: 449 (as-svrmap), 8471 (as-database), 8476 (as-signon),
  9471 (as-database-s), 9476 (as-signon-s).
- TLS on 9471 and 9476: TLS 1.3, certificate `CN=pub400.com` issued by
  Sectigo Public Server Authentication CA DV E36, valid until 2027-04-18.
  **Trusted by the Debian CA store in the container** (no extra CA needed), so
  `DB2I_SSL=1` works as is.

### Connection (`probe -- connect`)
- `SELECT 1 FROM SYSIBM.SYSDUMMY1` returns 1 over TLS.
- SQLGetInfo: `SQL_DBMS_NAME` = `DB2/400 SQL`, `SQL_DBMS_VER` = `07.05.0015`,
  `SQL_DRIVER_NAME` = `libcwbodbc.so`, `SQL_DRIVER_VER` = `07.01.029`,
  `SQL_DRIVER_ODBC_VER` = `03.51`, `SQL_SERVER_NAME` = `PUB400.COM`.
- Server job: `nnnnnn/QUSER/QZDASSINIT` (the TLS database server job);
  `QSYS2.NETSTAT_JOB_INFO` confirms local port 9471 (`as-database-s`).
- With SQL naming (`NAM=0`) and no `DBQ`, `CURRENT SCHEMA` is the user profile
  name, which is **not** one of the user's libraries. The backend must set the
  schema explicitly.
- Wrong password: SQLSTATE `28000`, driver message
  `Communication link failure. comm rc=8002 - CWBSY0002 - Password for user ... is not correct, Password length = <n>, ...`.
  The message contains the **password length**; probes redact it. The backend
  must do the same in its error mapping (phase 1).

### OS release, TR level, Db2 PTF Group level, CCSID (`probe -- sysinfo`)
- OS release: **IBM i 7.5** (`SYSIBMADM.ENV_SYS_INFO`: `OS_VERSION` 7, `OS_RELEASE` 5).
- TR level and Db2 PTF Group level: **unavailable**. `QSYS2.GROUP_PTF_INFO`
  fails with `SQL0443 - NOT AUTHORIZED TO COMMAND WRKPTFGRP` for a normal
  PUB400 user. Consequence for `capabilities.py`: features that depend on TR or
  PTF level must be detected with targeted feature probes or configured via
  `OPTIONS`, not by reading PTF groups.
- System values (`QSYS2.SYSTEM_VALUE_INFO`): `QCCSID` = **273** (EBCDIC
  Germany/Austria), `QLANGID` = `ENU`, `QCNTRYID` = `US`, `QTIMZON` = `Q0000UTC`,
  `QUTCOFFSET` = `+0000`.
- Job CCSID of the database server job: `CCSID` = 273, `DEFAULT_CCSID` = 273
  (`QSYS2.ACTIVE_JOB_INFO`). Not 65535.
- Catalog facts found on the way: `QSYS2.GET_JOB_INFO` has no CCSID column;
  `CCSID` and `DEFAULT_CCSID` are output columns of `QSYS2.ACTIVE_JOB_INFO`
  (specific name `QSQACTJOB`), per `QSYS2.SYSPARMS`.

### Libraries and journaling (`probe -- libraries`)
The user owns three libraries (found via `QSYS2.OBJECT_OWNERSHIP`), all
visible as SQL schemas:

| Library | Text | Existing tables | `QSQJRN` | Journal receivers | `QDFTJRN` |
|---|---|---|---|---|---|
| `<USER>1` | "*CURLIB your current library" | 208 | no | none | no |
| `<USER>2` | "second library" | 0 | no | none | no |
| `<USER>B` | "for backup data" | 0 | no | none | no |

**None of the libraries is journaled.** Tables created there are not journaled,
so commitment control (transactions) will not work until a journal exists.
Creating a journal receiver and `QSQJRN` journal changes the system and is a
separate proposal that needs approval.

### Journal setup in the `default` library (`nox -s setup_journal -- --execute`)
Approved by the project owner and run 2026-10-16 23:49 UTC against `<USER>2`
(the `default` library). The `other` library is not journaled yet (phase 1
configures only `default`). Commands, via `CALL QSYS2.QCMDEXC(?)` on a
connection with SQL naming and `CMT=0`:

```
CRTJRNRCV JRNRCV(<USER>2/QSQJRN0001) THRESHOLD(100000) TEXT('django-db2-for-i test journal')
CRTJRN JRN(<USER>2/QSQJRN) JRNRCV(<USER>2/QSQJRN0001) MNGRCV(*SYSTEM) DLTRCV(*YES) TEXT('django-db2-for-i test journal')
```

- A normal PUB400 user **is authorized** to run `CRTJRNRCV` and `CRTJRN` in
  their own library; both completed without messages.
- Effective receiver settings (`QSYS2.JOURNAL_RECEIVER_INFO`):
  **`THRESHOLD` = 100000** (as requested, KB), `RECEIVER_MAXIMUM_SIZE` =
  `*MAXOPT2`, status `ATTACHED`, `SIZE` = 2628 directly after creation.
- Effective journal settings (`QSYS2.JOURNAL_INFO`): `JOURNAL_STATE` = `*ACTIVE`,
  `MANAGE_RECEIVER_OPTION` = `*SYSTEM` (delay 10), `DELETE_RECEIVER_OPTION` =
  `YES` (delay 10), `REMOVE_INTERNAL_ENTRIES` = `YES`, `MESSAGE_QUEUE` =
  `QSYSOPR`, `JOURNALED_OBJECT_LIMIT` = `*MAX250K`.
- Verification: `CREATE TABLE <USER>2.DJJRNCHK (ID INTEGER)` was **journaled
  automatically** to `<USER>2/QSQJRN` (`QSYS2.OBJECT_STATISTICS`: `JOURNALED` =
  `YES`), without `STRJRNPF` or a `QDFTJRN` data area. The table was dropped
  afterwards.
- Removal (not run): `nox -s setup_journal -- --undo [--execute]` runs `DLTJRN`
  and then `DLTJRNRCV ... DLTOPT(*IGNINQMSG)` for every `QSQJRN*` receiver.
  `DLTJRN` fails while tables are still journaled to `QSQJRN`.

### Session behaviour (`probe -- session`)
Run 2026-10-16 23:56 UTC (read-only). Connection attributes: `NAM=0`,
`DBQ=<default library>`, `CMT=1`, `DFT=5`, `TFT=2`, autocommit off.

- **Default schema:** with `DBQ` set, `CURRENT SCHEMA` is the `DBQ` library and
  `CURRENT PATH` is `"QSYS","QSYS2","SYSPROC","SYSIBMADM","<library>"`.
- **Date/time types:** pyodbc returns `datetime.date`, `datetime.time` and
  `datetime.datetime` (microseconds included) for `DATE`, `TIME`, `TIMESTAMP`.
  The `DFT`/`TFT` formats only affect string renderings: `CHAR(CURRENT DATE)` =
  `2026-10-16`, `CHAR(CURRENT TIME)` = `23.56.08` (ISO time on IBM i uses
  dots), `CHAR(CURRENT TIMESTAMP)` = `2026-10-16-23.56.08.587941`.
- **String to date/time:** `CAST` accepts `13.45.30` and `13:45:30` for `TIME`,
  and both `2026-10-17 13:45:30.123456` and `2026-10-17-13.45.30.123456` for
  `TIMESTAMP`, as literals and as parameters.
- **Isolation level:** `CURRENT ISOLATION` does not exist (`SQL0104`).
  `QSYS2.DB_TRANSACTION_INFO WHERE JOB_NAME = QSYS2.JOB_NAME` works and shows
  `DEFAULT_LOCK_LEVEL` = `*CS` for `CMT=1`, `LOCK_SCOPE` = `*ACTGRP`,
  commitment definition `*DFTACTGRP`.
- **Unicode (casts of parameters):** length checks happen **in the ODBC driver**,
  before the server: too-long input fails with SQLSTATE `22001`
  (`CWB0111 - Input data is too big to fit into field`), not with silent
  truncation. Characters that the target CCSID cannot represent fail with
  `22018` (`CWBNL0107`).

  | Input | `NVARCHAR(10)` | `VARCHAR(10) CCSID 1208` | `VARCHAR(10) CCSID 273` |
  |---|---|---|---|
  | `é` × 10 | ok, 10 chars | `22001` (20 bytes) | ok |
  | `é` × 11 | `22001` | `22001` | `22001` |
  | emoji × 1 | ok | ok (4 bytes) | `22018` |
  | emoji × 5 | ok (10 UTF-16 units), `CHARACTER_LENGTH` = 5 | `22001` | `22018` |
  | emoji × 10 | `22001` (20 UTF-16 units) | `22001` | `22018` |
  | `aé` + emoji | ok, 3 chars | ok, 3 chars | `22018` |

  So `NVARCHAR(n)` counts UTF-16 code units: it matches Django's `max_length`
  for every BMP character, while a non-BMP character (emoji) uses 2 of the
  `n` units. `VARCHAR(n) CCSID 1208` counts bytes. The `INSERT` behaviour
  into real columns is covered by write probe `w01_commitment.py`.

### Commitment control on an unjournaled table, Unicode columns (`probe_write`)
Approved by the project owner and run 2026-10-17 00:01 UTC with
`w01_commitment.py` against `<USER>B` (no `QSQJRN`). Connection `NAM=0`,
`CMT=1` (*CS). Table `DJPROBE (ID INTEGER NOT NULL, NV NVARCHAR(10),
V8 VARCHAR(10) CCSID 1208)`, created (not journaled, `JOURNALED` = `NO`) and
dropped again.

| Step | Result |
|---|---|
| *CS, autocommit **on**: `INSERT`, then `UPDATE` | both **ok** |
| *CS, autocommit **off**: `INSERT` | **`SQL7008`** (`DJPROBE in <USER>B not valid for operation`), SQLSTATE `HY000` |
| autocommit on, `INSERT ... WITH NC` | ok |

- So with `CMT=1`, **autocommit statements do not need a journaled table**;
  only real transactions (autocommit off, i.e. Django's `atomic()`) do. The
  driver's mechanism for this (e.g. the `TrueAutoCommit` keyword) has not been
  probed yet; do not rely on it until it is.
- `SQL7008` arrives with the generic SQLSTATE `HY000`; error mapping must look
  at the SQL code (`-7008`), not only the SQLSTATE.

Unicode `INSERT` (with `WITH NC`) into real columns behaves exactly like the
casts in the session probe: the ODBC driver rejects too-long values with
`22001` (`CWB0111`), nothing is truncated, and every accepted value round-trips
unchanged.

| Input | `NVARCHAR(10)` | `VARCHAR(10) CCSID 1208` |
|---|---|---|
| `é` × 10 | ok (`LENGTH` 10, `CHARACTER_LENGTH` 10) | `22001` |
| `é` × 11 | `22001` | `22001` |
| emoji × 1 | ok (`LENGTH` 2, `CHARACTER_LENGTH` 1) | ok (`LENGTH` 4, `CHARACTER_LENGTH` 1) |
| emoji × 5 | ok (`LENGTH` 10, `CHARACTER_LENGTH` 5) | `22001` |
| emoji × 6 | `22001` | `22001` |
| emoji × 10 | `22001` | `22001` |

For `NVARCHAR`, `LENGTH` counts UTF-16 code units and `CHARACTER_LENGTH`
counts characters (code points).

### Statement atomicity in autocommit mode (`probe_autocommit`)
Requested by the project owner; run 2026-10-17 00:07 UTC with
`w02_autocommit.py` on a journaled table in `<USER>2` (`DJAUTOC (ID INTEGER NOT
NULL PRIMARY KEY)`, created and dropped). Connection `NAM=0`, `CMT=1`,
autocommit on, one connection per run. After seeding `ID=1`, the statement
`INSERT ... VALUES (2), (3), (1)` fails with `SQL0803` (duplicate key,
SQLSTATE `23000`) in both runs.

| `TRUEAUTOCOMMIT` | Rows after the failed statement | `NUMBER_COMMITS` / `NUMBER_ROLLBACKS` |
|---|---|---|
| `0` (driver default) | `1, 2, 3`: **not atomic**, rows 2 and 3 stay | 0 / 1 |
| `1` | `1`: **atomic** | 2 / 2 |

- With `TRUEAUTOCOMMIT=0` the driver runs autocommit statements outside
  commitment control (no commits are counted), even with `CMT=1` and a
  journaled table. This also explains why autocommit `INSERT`/`UPDATE` worked
  on the unjournaled table in `probe_write`.
- With `TRUEAUTOCOMMIT=1` each autocommit statement runs under commitment
  control and is committed or rolled back as a whole.
- Not probed yet: `TRUEAUTOCOMMIT=1` on an unjournaled table. Expected
  `SQL7008` (commitment control needs a journal), to be confirmed.

### ODBC connection string keywords (IBM documentation)
Checked 2026-10-17 in IBM's
[Connection string keywords](https://www.ibm.com/docs/en/i/7.4?topic=details-connection-string-keywords)
(IBM i 7.4 docs; no 7.5-specific page found):

| Keyword (ODBC.INI name) | Values | Driver default |
|---|---|---|
| `NAM` (`Naming`) | 0 = *SQL, 1 = *SYS | 0 |
| `DBQ` (`DefaultLibraries`) | library list | `QGPL` |
| `CMT` (`CommitMode`) | 0 *NONE, 1 *CS, 2 *CHG, 3 *ALL, 4 *RR | **2** (*CHG) |
| `TRUEAUTOCOMMIT` (`TrueAutoCommit`) | 0 = autocommit under *NONE, 1 = under the connection's level | 0 |
| `DFT` (`DateFormat`) | 5 = *ISO | 5 |
| `TFT` (`TimeFormat`) | 2 = *ISO (`hh.mm.ss`) | 0 (*HMS) |
| `XDYNAMIC` (`ExtendedDynamic`) | 0 = off, 1 = on | **1** |
| `DFTPKGLIB` (`DefaultPkgLibrary`) | package library; only with `XDYNAMIC=1` | `QGPL` |
| `PKG` (`DefaultPackage`) | `A/DEFAULT(IBM),x,0,y,z,0`; only with `XDYNAMIC=1` | `A/DEFAULT(IBM),2,0,1,0,512` |
| `SSL` | 0 = password only, 1 = all traffic | 0 |

- The `TRUEAUTOCOMMIT` description matches `probe_autocommit`.
- The page says `SSL` is supported only on Windows. **That remark is outdated**:
  with the Linux driver (`ibm-iaccess` 1.1.0.29), `SSL=1` connections use TLS
  1.3 on port 9471 (`as-database-s`), verified by `probe -- reachability` and
  `probe -- connect` (`QSYS2.NETSTAT_JOB_INFO` local port 9471).
- Only `CMT=1` → *CS has been verified by a probe; the other `CMT` values are
  taken from this page.

### Extended dynamic SQL packages (`probe -- packages`)
Read-only, 2026-10-17 07:37 UTC. Lists `*SQLPKG` objects owned by the current
user and those in the `default` and `other` libraries.

- Before `XDYNAMIC=0` was set: the earlier probe runs (driver default
  `XDYNAMIC=1`) had created **`QGPL/PYTHONANBI`** (`*SQLPKG`, owned by the
  PUB400 user, 196608 bytes), created 2026-10-16 23:56:08 UTC (first
  `probe -- session` run, the first probe with parameter markers), last
  changed 23:56:37. No packages in `<USER>2` or `<USER>B`. So a normal PUB400
  user can create packages in `QGPL`.
- After setting `XDYNAMIC=0` in the probes and the driver, a new
  `probe -- session` run followed by `probe -- packages` (07:38 UTC) shows no
  new package and `QGPL/PYTHONANBI` unchanged. That run repeated already-seen
  statements, so it is weak evidence; the check is repeated after the first
  Django test run.
- Removal, approved by the project owner on the condition that the package is
  ours: on 2026-10-17 `QSYS2.OBJECT_STATISTICS` showed `OBJOWNER` and
  `OBJDEFINER` = the PUB400 user and `OBJCREATED` 23:56:08 UTC, during the
  first `probe -- session` run (ended 23:56:09; the change at 23:56:37 matches
  the second run). `CALL QSYS2.QCMDEXC('DLTSQLPKG SQLPKG(QGPL/PYTHONANBI)')`
  succeeded (not locked); the package no longer exists.
- Note: `QGPL` is shared on PUB400 and package names derive from the
  application name (`PYTHON...`), so other Python users may have packages
  with similar names there. Never delete a package without checking
  `OBJOWNER` and `OBJCREATED` first.

### SQL features for the capability profiles (`probe -- features`)
Read-only, 2026-10-17 07:55 UTC on PUB400 (IBM i 7.5, TR level not readable).
Evidence for the `"7.5"` profile in `capabilities.py`.

| Capability | Checks | Result |
|---|---|---|
| `has_boolean_type` | `TRUE`/`FALSE` literals, `CAST(1 AS BOOLEAN)`, `CAST(NULL AS BOOLEAN)`, `CAST(? AS BOOLEAN)` with Python `True`/`False`, `WHERE CAST(? AS BOOLEAN) IS TRUE` | all ok; pyodbc returns Python **`bool`** (and `None` for NULL) |
| `has_limit_offset` | `ORDER BY ... LIMIT 1 OFFSET 0`, and `LIMIT ? OFFSET ?` | ok |
| `has_offset_fetch` | `OFFSET 0 ROWS FETCH FIRST 1 ROWS ONLY`, and with parameters | ok |
| `has_json_functions` | `JSON_OBJECT('a' VALUE 1)` (returns `{"a":1}`), `JSON_VALUE(... RETURNING INTEGER)`, `JSON_TABLE` | ok |

SQLGetInfo limits as reported by the driver: `SQL_MAX_SCHEMA_NAME_LEN` 130,
`SQL_MAX_TABLE_NAME_LEN` 128, `SQL_MAX_COLUMN_NAME_LEN` 128,
`SQL_MAX_IDENTIFIER_LEN` **18**, `SQL_MAX_INDEX_SIZE` 2000,
`SQL_MAX_ROW_SIZE` **32740**, `SQL_MAX_STATEMENT_LEN` 2097152.

- `SQL_MAX_IDENTIFIER_LEN` 18 contradicts the 128-character table/column
  limits reported alongside it; it is not used.
- `SQL_MAX_ROW_SIZE` 32740 differs from the 32,766-byte row length used in
  DECISIONS.md (NVARCHAR decision). The real limit is to be verified with a
  DDL probe (phase 4) before anything depends on the exact value.
- Repeated 2026-10-17 08:16 UTC after the first Django run (`nox -s pub400`,
  Django `connection.cursor()` with new statement texts and parameter
  markers, `XDYNAMIC=0`): **no `*SQLPKG` objects** owned by the user or in
  the test libraries. This is the confirmation promised above.

### Operations behaviour (`probe_operations`)
Run 2026-10-17 08:31 UTC with `w03_operations.py` on two temporary tables in
`<USER>2` (journaled), dropped afterwards. Connection as the backend's:
`NAM=0`, `CMT=1`, `TRUEAUTOCOMMIT=1`, `XDYNAMIC=0`, autocommit on. (The JSON
result file was not written because of a serialization bug in the probe,
fixed afterwards; the findings below are from the console output.)

**TIME has no fractional seconds; microseconds are dropped silently.**
- `CAST(? AS TIME)` with `time(13, 45, 30, 123456)` returns `13:45:30`, and
  inserting that value into a `TIME` column stores `13:45:30`. No error, no
  warning.
- `CAST('13.45.30.123456' AS TIME)` returns **NULL** (no error).
- `TIMESTAMP(6)` keeps microseconds (`2026-10-17 13:45:30.123456`), via casts
  and columns.

**`IDENTITY_VAL_LOCAL()`** returns `Decimal`:
- single-row `INSERT ... VALUES`: the generated value (1, then 2);
- multi-row `INSERT ... VALUES (..), (..)`: the **last** row's value (4);
- `INSERT` with an explicit key (100): **the explicit value** (100);
- `INSERT ... SELECT` (one row): the generated value (5).
- `GENERATED BY DEFAULT` identities do **not** advance past explicit values:
  after inserting 100, the next generated value was 5. Explicit keys below the
  counter will therefore collide later (relevant for fixtures and sequence
  reset).

**Pagination:** `ORDER BY ... OFFSET n ROWS` (no FETCH), `OFFSET n ROWS FETCH
FIRST m ROWS ONLY` and `FETCH FIRST m ROWS ONLY` all work. (The `pub400` tier
also runs `limit_offset_sql()` output against the server.)

**TRUNCATE:**
- `TRUNCATE TABLE <child> RESTART IDENTITY` works, also inside a transaction
  (autocommit off), and restarts the identity (next value 1).
- `TRUNCATE TABLE <parent> RESTART IDENTITY` on a table referenced by a
  foreign key fails with `SQ20356 - Table ... cannot be truncated` (SQLCODE
  -20356, SQLSTATE `HY000`), **even when the child table is empty**, with and
  without `IMMEDIATE`.
- Fallback works: `DELETE FROM <parent>` then `ALTER TABLE <parent> ALTER
  COLUMN ID RESTART WITH 1`; the next generated value is 1.

**Catalog columns** (read-only, `QSYS2.SYSCOLUMNS` of the views themselves):
`QSYS2.SYSCOLUMNS` has `IS_IDENTITY`, `IDENTITY_GENERATION`, `IDENTITY_START`,
`DATETIME_PRECISION`, `CCSID`, `HAS_DEFAULT`, `COLUMN_DEFAULT`, `HIDDEN`;
`QSYS2.SYSREFCST` links a foreign key (`CONSTRAINT_SCHEMA/NAME`) to the
referenced key (`UNIQUE_CONSTRAINT_SCHEMA/NAME`); `QSYS2.SYSCST` gives each
constraint's `TABLE_SCHEMA/TABLE_NAME` and `CONSTRAINT_TYPE`.

### Identity restart inside a transaction: SQL0910 (`pub400` tier)
Found 2026-10-17 by the `pub400` schema tests: `ALTER TABLE t ALTER COLUMN id
RESTART WITH n` fails with `SQL0910 - Object T in <library> type *FILE has a
pending change` (SQLCODE -910, SQLSTATE `HY000`) when the same transaction
already changed rows of `t` (e.g. `DELETE FROM t` in Django's
`execute_sql_flush()` atomic block, or rows inserted by `loaddata`).
Confirmed by `probe_sequence` (baseline step).

### SEQUENCE objects as key generator (`probe_sequence`)
Requested by the project owner; run 2026-10-17 09:00 UTC with
`w04_sequence.py` on a sequence and two tables in `<USER>2` (journaled), all
dropped afterwards. One connection, backend settings, autocommit off for the
transaction steps.

- **`DEFAULT NEXT VALUE FOR <sequence>` is not supported** in a column
  definition: `SQL0199 - Keyword VALUE not expected` (SQLSTATE `42000`). The
  probe fell back to inserting `NEXT VALUE FOR <sequence>` explicitly in the
  `VALUES` list.
- **`ALTER SEQUENCE ... RESTART WITH 101` works inside a transaction that has
  pending row changes** on the table (no SQL0910); the next generated value was
  101.
- `PREVIOUS VALUE FOR <sequence>` returns a Python `int`: the last value this
  job generated (1 after the first insert; still 1 after an insert with an
  explicit key 100; 101 after the restart; the **last** row's value, 123,
  after a multi-row insert).
- **Rollback** removed the rows but **not the restart**: the next value after
  the rollback was 121, not 2. `ALTER SEQUENCE` is not undone by a rollback,
  and the default `CACHE 20` makes the job skip the rest of its cached values
  (102-120) after the restart.
- Catalog: `QSYS2.SYSSEQUENCES` (`DATA_TYPE` INTEGER, `START` 1, `INCREMENT`
  1, `CACHE` 20, `CYCLE` NO, `ORDER` NO). Sequences are `*DTAARA` objects.

### DROP TABLE with foreign keys and views (`probe_drop`)
Requested by the project owner; run 2026-10-17 12:11 UTC with `w05_drop.py`
on temporary objects in `<USER>2` (journaled), dropped afterwards.

| Statement | Result |
|---|---|
| `DROP TABLE parent RESTRICT` (child has a foreign key to it) | refused: `SQL0478 - Object ... of type FILE cannot be dropped` |
| `DROP TABLE parent` (no option) | parent dropped, **the child's foreign key is dropped too**, child stays |
| `DROP TABLE parent CASCADE` | same as without option |
| `DROP TABLE child` (no option) while a view selects from it | child and **the view** are dropped |

So `DROP TABLE` without an option behaves like `CASCADE`. Test database
cleanup still drops views first, then tables children first, so each object
is dropped explicitly; an object already gone (SQLCODE -204) is not an error.

Also found on the way: `ALTER TABLE lib.t ADD CONSTRAINT c ...` with an
**unqualified** constraint name fails with `SQL5051 - Qualifier <x> not same
as name <lib>` when the connection's current schema is not the table's
library: an unqualified constraint name takes the current schema, and a
constraint must be in its table's schema. The backend connects with
`DBQ = NAME` (and `NAME` is the test library during tests), so its own
constraints are in the right schema.

### SQL catalog views in a library (`pub400` tier)
Found 2026-10-17: the default library contained six views nobody had created
explicitly: `SYSCHKCST`, `SYSCST`, `SYSCSTCOL`, `SYSCSTDEP`, `SYSKEYCST`,
`SYSREFCST` (`QSYS2.SYSTABLES`: `TABLE_TYPE` = `V`, `FILE_TYPE` = `D`,
`SYSTEM_TABLE` = `Y`; object attribute `LF`, text "SQL catalog view", owned by
the library's owner). They were created at 2026-10-17 00:07:25 UTC, when
`probe_autocommit` created the first table with a primary key in this
`CRTLIB` library; the `other` library (never had constraints) has none. Db2
for i adds these constraint catalog views to a library with its first
constraint. Catalog queries that list a library's tables must filter
`SYSTEM_TABLE = 'N'` (introspection and test database creation do).

### Long strings: NVARCHAR limit and LOB parameter truncation (`probe -- string_limits`)
Read-only (casts on `SYSIBM.SYSDUMMY1`), 2026-10-17, one connection with
the probes' settings (pyodbc, `ibm-iaccess` 1.1.0.29).

**Maximum NVARCHAR length in a cast:**
- `CAST(? AS NVARCHAR(n))` with a one-character parameter is accepted up to
  n = 16381; from n = 16382 on (also 16384, 32739, 32740) the server fails with
  **`SQL0901 - SQL system error`** (an internal error, not a clean refusal).
- `CAST(? AS NVARCHAR(16370))` round-trips parameters of up to 16370
  characters exactly (ASCII and `é`); 16371 characters fail cleanly with
  `22001` (`CWB0111`). An earlier run of `NVARCHAR(16381)` with a
  16381-character parameter failed with `SQL0302 - Conversion error`.
- So **16370** is the verified usable maximum.

**LOB-typed parameters lose characters (data loss, not fixed):**
- Through `CAST(? AS DBCLOB(1M))`, `NCLOB(1M)` or `CLOB(1M) CCSID 1208`, the
  server sees **one character less than was sent from 8185 characters on**:
  8184 characters arrive intact, 8185 arrive as 8184, 16370 as 16369, 24555
  as 24553 (two lost), 32768 as 32766. No error, no warning.
- The same lengths through `NVARCHAR(16370)` or `VARCHAR(32000) CCSID 1208`
  arrive intact.
- 8184 characters are 16368 bytes in UTF-16; the loss looks like an
  off-by-one in how pyodbc and the IBM i Access driver pass long LOB
  parameters (data at execution, in chunks). Not investigated further yet.
- Consequence: writing more than 8184 characters into an `NCLOB` column
  (Django `TextField`) very likely loses characters. To be confirmed with a
  write probe and fixed before `TextField` is supported (see
  docs/user/Known-Limitations.md).
- **Not affected** (read-only checks, 2026-10-17): bytes parameters through
  `CAST(? AS BLOB(1M))` (8184 to 70,000 bytes) and `VARBINARY(32000)` arrive
  intact; reading server-built `NCLOB` and `BLOB` values (built by
  concatenating LOB pieces, up to 300,000 characters/bytes) returns them
  intact. (`REPEAT()` results above about 32K are NULL, so large test values
  must be concatenated.) The loss is on the write path for strings only.
- **Guard:** the pyodbc driver refuses every string parameter longer than 8184
  UTF-16 units with NotSupportedError (pyodbc chooses LOB or NVARCHAR binding
  from the driver's parameter description, which the backend cannot see).

### Column DEFAULT constants (`nox -s probe_defaults`)
2026-10-17, one connection, only `DECLARE GLOBAL TEMPORARY TABLE SESSION.x`
(QTEMP, gone at disconnect), one `INSERT` per table and reading the stored
value back. Found because Django's `basic` tests failed during setup with
`DEFAULT CAST(1 AS INTEGER)` (SQL0574).

**Accepted forms:** bare constants and special registers only.
- Accepted, and stored as written: `1`, `-1`, `9223372036854775807`, `1.50`
  (DECIMAL), `1.5E0` (DOUBLE), `'abc'`, `''`, `'100%'`, `TRUE` (BOOLEAN),
  `'2026-01-02'` (DATE), `CURRENT_TIMESTAMP`, `BX'01AB'` (BLOB, via the
  `pub400` goldens).
- Rejected: `CAST(<constant> AS <type>)` for every type tried (**SQL0574**),
  `(1)` and `1 + 1` (**SQL0104**).

**String constants are stored wrongly in two cases (no error):**
- An escaped quote: `DEFAULT 'O''Brien'` stores `O''Brien` in NVARCHAR and
  NCLOB, `O'Brie ` in VARCHAR(10), `O'Brie n  ` in CHAR(10).
- `N'...'` stores the quote correctly in NVARCHAR, VARCHAR and NCLOB, but
  truncates CHAR values: `N'<32 hex digits>'` in CHAR(32) keeps 16 characters,
  `N'O''Brien'` in CHAR(10) gives `O'Bri`.
- Any non-ASCII character in the statement text (`é`, `€`, emoji; with or
  without `N`) fails in the ODBC driver with **`HY001` "Memory allocation
  error" (30027)**. An emoji-only `'😀'` was stored as `'=\x00'`. Whether this
  also affects non-ASCII text outside DEFAULT clauses is not verified yet (the
  backend sends values as parameters).
- **`UX'<UTF-16 hex>'`** is stored correctly in NVARCHAR, NCHAR, NCLOB, CHAR and
  VARCHAR (quotes, `€`, emoji, empty string). VARCHAR (single-byte CCSID)
  replaces characters it cannot represent with SUB (`x1A`), as for any value.

**Backend rule** (`schema.string_literal()`): printable ASCII without a quote
is written as `'...'`; anything else as `UX'...'`.

**ALTER TABLE ... DROP COLUMN** on a table with rows was cancelled with
**`HY008` "Operation cancelled" (30071)** in the `pub400` tier (2026-10-17);
the cause is the CPA32B2 inquiry message, see "ALTER TABLE cancelled by
CPA32B2" below.

### ALTER TABLE cancelled by CPA32B2 (`probe_inquiry`, `probe_job_reuse`)
2026-10-17. `probe_inquiry` changes only QTEMP and its own job (every job
attribute it changes is set back and read back); `probe_job_reuse` changes
only its own job and uses two connections, strictly one after the other.

**What happens:**
- `ALTER TABLE ... DROP COLUMN` sends inquiry message **CPA32B2** ("Change of
  file &1 may cause data to be lost. (C I)"), **also on an empty table**. Its
  default reply is **`C`** (`QSYS2.MESSAGE_FILE_DATA`). Job log: CPD32CC
  "Change to field B may result in data loss", CPD32CE "Change of file ...
  canceled", CPF7304 "File ... not changed"; the driver reports **`HY008`
  "Operation cancelled" (30071)**. CPA32B2 itself does not appear in the job
  log.
- Narrowing type changes are cancelled the same way, also when every value
  fits: INTEGER -> SMALLINT, VARCHAR(10) -> VARCHAR(5), NVARCHAR(10) ->
  NVARCHAR(5), DECIMAL(9, 2) -> DECIMAL(5, 2). Widening (INTEGER -> BIGINT,
  VARCHAR(5) -> VARCHAR(10)) and `ADD COLUMN ... NOT NULL DEFAULT 0` are not.
- The database host server jobs (`QUSER/QZDASOINIT`, `QZDASSINIT` for TLS)
  have **`INQMSGRPY(*RQD)`** from job description `QGPL/QDFTSVR`
  (`QSYS2.JOB_INFO.INQUIRY_MESSAGE_REPLY`; `QSYS2.GET_JOB_INFO` has no such
  column).

**Options tried:**
- `CALL QSYS2.QCMDEXC('CHGJOB INQMSGRPY(*SYSRPYL)')` is allowed for a normal
  user profile on its own job, and setting it back works. On PUB400 it does
  **not** help: the only system reply list entry for CPA32B2
  (`QSYS2.REPLY_LIST_INFO`, sequence 3282) replies `I` only for comparison
  data `'ACS Database Schemas'` at offset 1, which DROP COLUMN's message data
  never matches. `*DFT` would apply the default reply `C`. Adding a reply list
  entry (`ADDRPYLE`) is a system-wide change for an administrator.
- QAQQINI: `CRTDUPOBJ` of `QSYS/QAQQINI` is not allowed for our profile
  (CPF2130); `CALL QSYS2.OVERRIDE_QAQQINI(1, '', '')` makes a job-level copy
  in QTEMP without any library (`OVERRIDE_QAQQINI(3, '', '')` removes it).
  None of its 49 options controls inquiry messages (only `MESSAGES_DEBUG`
  mentions messages).
- A mistake in the first `probe_inquiry` run: the original value was read
  with a wrong column name, so the reset did not run and that server job
  disconnected with `*SYSRPYL`. Afterwards no `QUSER` server job had
  `*SYSRPYL`. The probe now refuses to change anything if it cannot read the
  original value.

**Job reuse after disconnect (`probe_job_reuse`, three runs):** each
connection got a fresh `QZDASSINIT` job (prestart reuse count 1 of 200), and
after the disconnect the job was no longer listed in `QSYS2.JOB_INFO` (status
filter `*ALL`): on PUB400 the job ends at disconnect, so a changed `INQMSGRPY`
cannot be inherited by the next client. Whether a reused prestart job keeps
it on other systems could not be observed; the backend restores the original
value explicitly at close either way.

**Backend:** `OPTIONS["inquiry_message_reply"]` (opt-in, connection level)
and the error message for a cancelled ALTER TABLE (`inquiry.py`). DROP COLUMN
with the option stays an expected failure on PUB400 ("no CPA32B2 entry in the
system reply list") until a dedicated IBM i with the entry is available.

### Savepoints (`nox -s probe_savepoints -- --execute`)
2026-10-17, one connection with the backend's settings (CMT=1, autocommit
off), one table in the `default` library (created and dropped by the probe).

- `SAVEPOINT "<sid>" ON ROLLBACK RETAIN CURSORS` is accepted with a quoted,
  Django-style name (`s<thread>_x<n>`) and with a 40-character name. The
  `ON ROLLBACK RETAIN CURSORS` clause is **required**: `SAVEPOINT x` alone fails
  with SQL0104; `ON ROLLBACK RETAIN LOCKS` is not valid (SQL0104). `UNIQUE` is
  accepted.
- `RELEASE SAVEPOINT x` and `RELEASE TO SAVEPOINT x` both work;
  `ROLLBACK TO SAVEPOINT x` undoes the changes after the savepoint and keeps
  the savepoint (a second ROLLBACK TO works). Django's error path, ROLLBACK TO
  followed by RELEASE, works; afterwards the savepoint is gone (SQL0880).
- Nesting: RELEASE of an inner savepoint keeps its changes in the outer one;
  ROLLBACK TO the outer one undoes both. ROLLBACK TO an outer savepoint
  destroys the inner ones (SQL0880).
- A failed statement (SQL0803 duplicate key) inside a savepoint: ROLLBACK TO
  and RELEASE work, and the transaction continues normally.
- Reusing a name without `UNIQUE` replaces the earlier savepoint.
- An open cursor survives ROLLBACK TO SAVEPOINT (RETAIN CURSORS).
- After COMMIT the savepoints are gone (SQL0880). In autocommit mode
  `SAVEPOINT` is accepted but the savepoint is gone at once (SQL0880 on
  RELEASE); Django never creates savepoints in autocommit mode.

Result: `uses_savepoints` and `can_release_savepoints` enabled. Django's
`transactions` module went from 15 passed / 73 skipped to 85 passed /
3 skipped (no failures).

### Extracting date/time parts (`probe -- extract`)
Read-only (`SYSIBM.SYSDUMMY1`), 2026-10-17. Each candidate expression was
evaluated on timestamp literals, `CAST(? AS TIMESTAMP(6))`, `CAST(? AS DATE)`
and `CAST(? AS TIME)` parameters, for 2005-07-28 (Thursday), 2021-01-01
(Friday, ISO 2020-W53), 2024-12-30 (Monday, ISO 2025-W01), 2023-01-01
(Sunday, ISO 2022-W52) and 2026-10-17 (Saturday), and compared with Python's
`isocalendar()` and Django's conventions.

- Correct, returning `int`: `YEAR`, `QUARTER`, `MONTH`, `WEEK_ISO` (ISO week),
  `DAYOFWEEK` (1 = Sunday .. 7 = Saturday, Django's `week_day`),
  `DAYOFWEEK_ISO` (1 = Monday .. 7 = Sunday, `iso_week_day`), `DAY`, `HOUR`,
  `MINUTE`, `SECOND` (whole seconds); ISO year as
  `INTEGER(VARCHAR_FORMAT(x, 'IYYY'))` and as
  `YEAR(x + (4 - DAYOFWEEK_ISO(x)) DAYS)`.
- `EXTRACT(YEAR|QUARTER|MONTH|WEEK|DOW|DAY|HOUR|MINUTE FROM x)` also correct.
  `EXTRACT(SECOND FROM x)` returns `DECIMAL` with the fraction
  (`30.123456`); `EXTRACT(ISODOW FROM x)` is rejected (SQL0104).
- The backend uses the scalar functions throughout.

### Journal setup in the `other` library (`nox -s setup_journal -- --library other --execute`)
Approved by the project owner and run 2026-10-17 against `<USER>B` (the
`other` library). The dry run first confirmed: owned by our user, no journal
objects, and no objects at all (`QSYS2.OBJECT_STATISTICS(..., '*ALL')` empty).
Same commands as for `default` (`CRTJRNRCV ... THRESHOLD(100000)`, `CRTJRN ...
MNGRCV(*SYSTEM) DLTRCV(*YES)`), both accepted without messages. Result:
`JOURNAL_STATE` `*ACTIVE`, `MANAGE_RECEIVER_OPTION` `*SYSTEM`,
`DELETE_RECEIVER_OPTION` `YES`, `RECEIVER_MAXIMUM_SIZE` `*MAXOPT2`, receiver
`THRESHOLD` 100000; the check table `DJJRNCHK` was journaled automatically
(`JOURNALED` = `YES`) and dropped; the library has no tables afterwards. The
`other` alias opens a second connection to PUB400 only when a test uses it.

## Open investigation: string encoding (after 0.1.0a1)

Three findings may share one cause in how strings travel between pyodbc,
the IBM i Access ODBC driver and the server (client CCSID / wide-character
handling):

1. Non-ASCII characters in **statement text** (`é`, `€`, emoji) fail with
   `HY001` "Memory allocation error" (column DEFAULT probe, `probe_defaults`).
2. An escaped quote in a DEFAULT constant, `'O''Brien'`, is stored literally
   as `O''Brien` (NVARCHAR) or garbled (CHAR/VARCHAR), while `UX'...'` is
   stored correctly (`probe_defaults`).
3. **LOB parameters** lose one character from 8185 characters on
   (`probe -- string_limits`).

Plan, one read-only or QTEMP-only probe per step, recording each result here:

1. pyodbc encoding settings: `setencoding()` / `setdecoding()` for `SQL_CHAR`
   and `SQL_WCHAR` (UTF-8 vs UTF-16LE, `ctype`), and what the backend sets now.
2. Driver keywords that affect conversion: CCSID / `UNICODESQL`-style
   options, `TRANSLATE`, `MAXFIELDLEN`, `BLOCKSIZE`/LOB settings
   (IBM i Access ODBC keyword documentation).
   Also the query option `SQL_TRANSLATE_ASCII_TO_JOB` (listed by
   `QSYS2.OVERRIDE_QAQQINI`, which makes a job-level QAQQINI copy in QTEMP
   without touching a library).
3. Re-run the three findings for each combination; one setting may explain
   all three.
4. If a setting fixes them: change the driver defaults (`drivers/pyodbc.py`),
   drop the `UX'...'` workaround if no longer needed and the 8184-unit
   parameter guard, and update docs/user.

Does not block 0.1.0a1.

