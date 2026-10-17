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
