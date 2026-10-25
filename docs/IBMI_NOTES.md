# IBM i notes

IBM i quirks and probe findings. Every claim here is backed by a probe in
`probes/` or by a cited IBM source, with the date it was checked.

**Probe names.** Since 2026-10-23 a probe's name says where it acts:
`qtemp_` (read-only, or only QTEMP and its own job) or `lib_` (changes a
library; runs only through `bin/probe --approved <link>`, CLAUDE.md). The
entries below keep the names and commands of the day; they map as follows
(the `nox -s probe_*` write sessions became `bin/probe --approved <link>
lib_<topic>`):

| Old name | New name |
|---|---|
| `p00_reachability.py` | `qtemp_reachability.py` |
| `p01_connect.py` | `qtemp_connect.py` |
| `p02_system_info.py` | `qtemp_system_info.py` |
| `p03_libraries.py` | `qtemp_libraries.py` |
| `p04_session.py` | `qtemp_session.py` |
| `p05_packages.py` | `qtemp_packages.py` |
| `p06_features.py` | `qtemp_features.py` |
| `p07_string_limits.py` | `qtemp_string_limits.py` |
| `p08_extract.py` | `qtemp_extract.py` |
| `p09_queries.py` | `qtemp_queries.py` |
| `p10_listagg.py` | `qtemp_listagg.py` |
| `p11_trunc.py` | `qtemp_trunc.py` |
| `p12_durations.py` | `qtemp_durations.py` |
| `p13_fetch_errors.py` | `qtemp_fetch_errors.py` |
| `p14_mapping_errors.py` | `qtemp_mapping_errors.py` |
| `p15_long_string_params.py` | `qtemp_long_string_params.py` |
| `p16_in_subquery.py` | `qtemp_in_subquery.py` |
| `p17_tuple_in.py` | `qtemp_tuple_in.py` |
| `p18_tuple_lookups.py` | `qtemp_tuple_lookups.py` |
| `p19_compound_parts.py` | `qtemp_compound_parts.py` |
| `p20_selected_predicates.py` | `qtemp_selected_predicates.py` |
| `p21_numeric_params.py` | `qtemp_numeric_params.py` |
| `p22_constraint_errors.py` | `qtemp_constraint_errors.py` |
| `p23_drop_column.py` | `qtemp_drop_column.py` |
| `p24_alter_table.py` | `qtemp_alter_table.py` |
| `p25_catalog.py` | `qtemp_catalog.py` |
| `setup_journal.py` | `lib_setup_journal.py` |
| `w01_commitment.py` | `lib_commitment.py` |
| `w02_autocommit.py` | `lib_autocommit.py` |
| `w03_operations.py` | `lib_operations.py` |
| `w04_sequence.py` | `lib_sequence.py` |
| `w05_drop.py` | `lib_drop.py` |
| `w06_defaults.py` | `qtemp_defaults.py` |
| `w07_savepoints.py` | `lib_savepoints.py` |
| `w08_inquiry.py` | `qtemp_inquiry.py` |
| `w09_job_reuse.py` | `lib_job_reuse.py` |
| `w10_encoding.py` | `qtemp_encoding.py` |
| `w11_job_ccsid.py` | `qtemp_job_ccsid.py` |
| `w12_locale.py` | `qtemp_locale.py` |
| `w13_constraints.py` | `lib_constraints.py` |
| `w14_column_types.py` | `lib_column_types.py` |

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
  PUB400 user, and `QSYS2.PTF_INFO` with `SQL0443 - NOT AUTHORIZED TO USE
  QSYS/DSPPTF *CMD` (checked again 2026-10-19). Consequence for `capabilities.py`: features that depend on TR or
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
  UTF-16 units with NotSupportedError. (The reason given at the time, that
  pyodbc chooses the binding from the driver's parameter description, is
  wrong; root cause and fix: "String encoding investigation" below.)

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

### Operators for combine_expression (`probe -- queries`, area arith)
2026-10-19. Db2 for i has no `%`, `^`, `&`, `|`, `#`, `<<`, `>>` operators
(SQL0104); `MOD`, `POWER`, `BITAND`, `BITOR`, `BITXOR` work and give NULL for a
NULL argument (`MOD(-7, 3)` = -1, the sign of the dividend). **`POWER` always
returns DOUBLE** (`POWER(2, 3)` = 8.0), so `FLOOR(<BIGINT> / POWER(2, n))`
loses precision (2^63-1 >> 62 gave 2); powers of two themselves are exact,
so `BIGINT(POWER(2, n))` is. Integer division truncates toward zero (-5 / 2 =
-2), while Python's `>>` rounds down (-5 >> 1 = -3).
`BIGINT(FLOOR(CAST(x AS DECFLOAT(34)) / CAST(POWER(2, n) AS DECFLOAT(34))))`
gives Python's result for every case probed, including -1 >> 62 = -1 and the
BIGINT extremes, NULL and a typed marker for n; a `VALUES` subquery with
`MOD` correction works too but fails for n = 63. Left shift: `x *
BIGINT(POWER(2, n))` is exact. An untyped NULL argument of BITXOR fails
(SQL0171, Django's `F("x").bitxor(None)`).

### Durations (`probe -- durations`)
2026-10-19, read-only (SYSDUMMY1), results compared with Python's own
arithmetic. System: PUB400, IBM i 7.5; TR level and Db2 PTF Group level not
readable there (`QSYS2.GROUP_PTF_INFO` and `QSYS2.PTF_INFO`: SQL0443, see
"OS release, TR level ..."), so the two NULL limits below may differ on other
levels. A DurationField is stored as BIGINT microseconds.

- **`<timestamp> + n MICROSECONDS` stops at 15 digits:** n = 999,999,999,999,999
  (about 31.7 years) works, n = 10^15 and larger give **NULL**, silently (not
  an error). 10000 days (8.64 * 10^14) still works.
- **Split into days and the rest:** `<ts> + INTEGER(n / 86400000000) DAYS +
  MOD(n, 86400000000) MICROSECONDS` (truncated division, the remainder has the
  sign of n) is exact for every case probed: negative n, 10^15 and 10^16
  microseconds, year 1 + 1 day, year 9999 - 1 day and the whole span from
  0001-01-01 to 9999-12-31. Python's `timedelta.max` (999,999,999 days) does
  not fit a BIGINT; the largest DurationField value is 2^63 - 1 microseconds
  (106,751,991 days 4:00:54.775807). A result outside the timestamp range
  (n = 2^63 - 1) is **NULL**, not an error.
- **DATE and TIME:** a labeled duration on a DATE or TIME with MICROSECONDS is
  rejected (SQL0187). `TIMESTAMP(<date>)` drops the microseconds of the result
  (precision 0); `CAST(<date> AS TIMESTAMP(6))` and `TIMESTAMP(<date>,
  TIME('00:00:00'))` keep them. `TIME(TIMESTAMP(DATE('2000-01-01'), <time>) +
  ...)` adds to a time and wraps at 24 hours. This matches PostgreSQL
  (`time '23:30' + interval '25 hours'` is 00:30).
- **Duration times or divided by a number:** `BIGINT(<bigint> * <DOUBLE /
  DECIMAL / INTEGER>)` gives the truncated microseconds.
- **Exact subtraction in microseconds:** `BIGINT(DAYS(a) - DAYS(b)) *
  86400000000 + BIGINT(MIDNIGHT_SECONDS(a) - MIDNIGHT_SECONDS(b)) * 1000000 +
  (MICROSECOND(a) - MICROSECOND(b))` matches Python for spans of months and
  years (leap days), negative results, year 1 to 9999 and microseconds; for
  dates `BIGINT(DAYS(a) - DAYS(b)) * 86400000000`, for times
  `BIGINT(MIDNIGHT_SECONDS(a) - MIDNIGHT_SECONDS(b)) * 1000000`.
  **`TIMESTAMPDIFF(1, CHAR(a - b))`** is NULL or wrong for anything beyond a
  few days (only the same-day case was right); the backend never uses it.

### Statements that leave the connection unusable (`nox -s probe -- fetch_errors`)
2026-10-19, read-only, PUB400 (IBM i 7.5; TR and Db2 PTF Group levels not
readable), IBM i Access ODBC Driver **07.01.029** (`SQL_DRIVER_VER`), pyodbc
5.3.0, the backend's connection attributes (pooling off, `CMT=1`). Each
scenario on a fresh connection, opened one at a time.

**Correction:** an earlier assumption (PR #58) was that a statement failing
*during fetch* leaves the connection unusable. It does not:

| Failing statement | Fails at | Next statements after closing the failed cursor |
|---|---|---|
| `SELECT MAX(PTF_GROUP_LEVEL) FROM QSYS2.GROUP_PTF_INFO` (no parameter) | fetch, SQL0443 | ok |
| `... FROM NOSUCHLIB.NOSUCHTABLE WHERE X = ?` | prepare, SQL0204 | ok |
| `... WHERE 1 = CAST(? AS INTEGER) / 0` | execute, SQL0802 | ok |
| `... FROM QSYS2.GROUP_PTF_INFO WHERE PTF_GROUP_DESCRIPTION LIKE ?` | **execute, SQL0443** | **SQL0519** "Prepared statement STMT0002 in use", every statement, plain or prepared |

**The real trigger:** a **parameterized** statement on a **service** (a QSYS2
table function or view that calls system APIs or commands, here the PTF
group service a normal user is not authorized to) that fails with SQL0443 at
execute. While the failed cursor is open, other statements still work; as
soon as it is **closed**, the driver reuses its statement name (STMT0002)
while the server still has it in use, and every later statement fails with
SQL0519, in autocommit and inside a transaction, also after a rollback.
Rollback, `cancel()` or reusing the failed cursor before closing it do not
help; only a new connection clears it. The backend marks the connection
unusable at the trigger and on any SQL0519 (DECISIONS.md, 2026-10-19).

**Errors in the select list give NULL:** `SELECT CAST('abc' AS INTEGER)` and a
division by zero in the select list return NULL without an error (see the
separate note on data mapping errors); in WHERE the same errors raise SQL0802.

### Data mapping errors in the select list (`nox -s probe -- mapping_errors`)
2026-10-19, read-only, PUB400 (IBM i 7.5), IBM i Access ODBC Driver 07.01.029,
pyodbc 5.3.0, the backend's connection attributes.

A value that cannot be converted, or a division by zero, **in the select
list** gives **NULL without an error**: `SELECT CAST('abc' AS INTEGER)`, the
same with a parameter (`CAST(CAST(? AS VARCHAR(3)) AS INTEGER)`), and `SELECT
1 / 0` (via a subquery) all return NULL. With several rows, only the bad row
is NULL (`'1', 'x', '3'` cast to INTEGER gives 1, NULL, 3). The driver reports
**no warning**: pyodbc's `cursor.messages` is empty after execute and after
fetch (so there is no SQL_SUCCESS_WITH_INFO the backend could turn into an
error). In WHERE, the same errors raise SQL0802 ("Data conversion or data
mapping error").

### UPPER() on NVARCHAR (pub400 test, 2026-10-19)
`tests/pub400/test_lookups.py::test_iexact_with_non_ascii_letters`: Db2 for i's
`UPPER()` on NVARCHAR uppercases `é` to `É` and `ü` to `Ü`, but keeps `ß` as `ß`
(Python's `"straße".upper()` is `"STRASSE"`): `iexact="STRASSE"` does not match
`straße`, `iexact="STRAßE"` does. Case-insensitive lookups compare
`UPPER(column)` with `UPPER(value)`, both on the server, so they agree with each
other.

### String parameters longer than the column (`nox -s probe -- long_string_params`)
2026-10-19, PUB400 (IBM i 7.5), driver 07.01.029, the backend's connection
attributes; a QTEMP table with `NAME NVARCHAR(10)`, `SMALL SMALLINT`,
`AMOUNT DECIMAL(5, 2)` and a row holding the truncated value `nonexisten`.

- An **untyped** marker compared with a string column (`=`, `IN`, `NOT IN`,
  `<>`, `>`) is sized by the column: a longer value (`nonexistent`, 11
  characters) fails on the client with **CWB0111** "Input data is too big to
  fit into field" (30207). Nothing is truncated: the row `nonexisten` is never
  matched. The length counts **UTF-16 units**: `nonexiste` + an emoji (10 by
  `len()`, 11 units) fails too. pyodbc's `setinputsizes` does not change it.
- Expressions are sized by their result: `LOWER(NAME) = ?` and `SUBSTR(NAME,
  1, 3) = ?` fail the same way (SUBSTR at 3 characters, whatever the field
  says); `NAME || 'x' = ?` and `CAST(NAME AS NVARCHAR(16370)) = ?` do not.
- `LIKE ?` and `UPPER(NAME) = UPPER(?)` are not affected.
- A typed marker `CAST(? AS NVARCHAR(32))` works in every comparison, with the
  correct result.
- Numbers: `SMALLINT = ?` / `> ?` with 100000 fail with "Numeric value out of
  range" (30018); `DECIMAL(5, 2) = ?` with 123456.789 fails (30160, out of
  range) and with 1.005 (30126, right truncation). Errors, never a silent
  match. Django settles out-of-range integers for `exact`/`gt`/... in Python
  (`integer_field_ranges`, which match Db2's SMALLINT/INTEGER/BIGINT).
- A typed marker shorter than the value fails the same way:
  `NAME = CAST(? AS NVARCHAR(10))`, `(NAME, SMALL) = (CAST(? AS NVARCHAR(10)),
  ?)` and `SELECT CAST(? AS NVARCHAR(10))` with `nonexistent` give CWB0111
  (2026-10-19); never a truncated match.

### Constraint violations: SQLSTATE and SQLCODE (`nox -s probe -- constraint_errors`)
2026-10-20, PUB400 (IBM i 7.5), the backend's connection attributes, QTEMP.

| Violation | SQLSTATE | SQLCODE | Backend class |
|---|---|---|---|
| duplicate key (unique index) | `23000` | -803 | IntegrityError |
| NOT NULL | `23000` | -407 | IntegrityError |
| CHECK (Django's `model_fields.test_integerfield`, issue #96) | **`HY000`** | -545 | IntegrityError (by SQLCODE) |

- **QTEMP tables take no constraints:** `PRIMARY KEY`, `UNIQUE`, `CHECK` and
  `REFERENCES` all fail with SQL7008 ("not valid for operation"; constraints
  need a journal). A `UNIQUE INDEX` and `NOT NULL` work, so duplicate keys and
  NOT NULL can be probed there, CHECK and foreign keys cannot.
- The driver reports SQL0545 with SQLSTATE `HY000` instead of `23513`, so the
  SQLSTATE class mapping (`23` -> IntegrityError) misses it; the driver layer
  maps SQLCODE -545 to IntegrityError (#96).
- Foreign key violations (SQL0530 / SQL0531 / SQL0532) cannot be probed in
  QTEMP; probe w13 did it in the journaled library: they arrive with `HY000`
  too (see "Foreign keys, unique and check constraints").

### Foreign keys, unique and check constraints (`nox -s probe_constraints -- --execute`)
2026-10-22, PUB400 (IBM i 7.5), the journaled `default` library, write probe
w13 (approved: phase 4 decision 3): its own `DJW13` tables only, one
connection, through the PUB400 lock, all dropped at the end (checked: no
`DJW13` object left). Catalog queries were limited to its own tables.

- **Constraint names land in `CURRENT SCHEMA`.** A first run connected
  without `DBQ` and every `ADD CONSTRAINT` failed with SQL5051 ("Qualifier ...
  not same as name"): an unqualified constraint name goes to the default
  schema, which must be the table's library. The backend sets `DBQ` to the
  library (`drivers/pyodbc.py`); the probe now does too and checks
  `CURRENT SCHEMA` before it creates anything. Only the rollback check of
  that first run is used below.
- **Foreign key violations**, with `ALTER TABLE ... ADD CONSTRAINT ...
  FOREIGN KEY ... REFERENCES` as Django writes it:

  | Violation | SQLSTATE | SQLCODE |
  |---|---|---|
  | insert or update a child with a missing parent | **`HY000`** | -530 |
  | delete a referenced parent | **`HY000`** | -532 |
  | update a referenced parent key | **`HY000`** | -531 |
  | update another column of a referenced parent | (works) | |

  As SQL0545 (CHECK), they arrive with `HY000`, not `23503`, so the
  SQLSTATE class mapping misses them; the driver layer maps SQLCODE
  -530 / -531 / -532 to IntegrityError (#96; own IBM i test
  `tests/pub400/test_foreign_keys.py`). `SYSREFCST` records
  `UPDATE_RULE` and `DELETE_RULE` `NO ACTION` and the parent's primary key as
  `UNIQUE_CONSTRAINT_NAME`.
- **No visible index for a foreign key:** `SYSINDEXES` lists nothing for the
  child table after the foreign key (nor for the primary keys); the access
  paths constraints use are not SQL indexes. Django's own index on the column
  (`CREATE INDEX ... (P_ID)`) works next to the foreign key and is listed
  with `IS_UNIQUE` `D` (duplicates allowed). So `indexes_foreign_keys` is
  False, and the backend keeps creating its own index (decision 5).
- **Two constraints on the same columns:** a unique index next to a unique
  constraint works, and so does a second foreign key on the same column; a
  **second unique constraint on the same column fails with SQL0541**
  ("Duplicate UNIQUE constraint exists", the baseline's one SQL0541).
- **CHECK:** `ADD CONSTRAINT ... CHECK (A >= 0)` works; a violation is
  SQL0545 / `HY000` (as in Django's test, #96); `SYSCHKCST.CHECK_CLAUSE`
  holds the text as written (`A >= 0`); both `DROP CONSTRAINT` and `DROP CHECK`
  remove it.
- **DDL under commitment control is rolled back:** with autocommit off,
  `CREATE TABLE` and `ALTER TABLE ... ADD COLUMN`, then `ROLLBACK`: the table
  and the column are gone (both runs). `can_rollback_ddl` can be True, with
  its own test when it is switched on.

### Foreign keys through the schema editor (own IBM i tests, facts a-d)
2026-10-25, PUB400 (IBM i 7.5), the test library, own IBM i tests in
`tests/pub400/test_foreign_keys.py` (a parent and a child model of their own,
created with foreign keys enabled, as a migration with `supports_foreign_keys`
on creates them; dropped after each test). Input for switching the flag on.

- **a. A primary key type change with an incoming foreign key works as a
  migration.** `MigrationExecutor`: CreateModel parent and child, then
  AlterField of the parent's `AutoField` to `BigAutoField`. Django drops the
  incoming foreign key, changes the parent key and the child's column (both
  `BIGINT` afterwards) and adds the foreign key again (`..._fk`); a row without
  a parent is refused (SQL0530). Django keeps the types equal through the
  migration state, so `related_fields_match_type` is not needed for this.
  (Done with the schema editor directly on the old model classes instead, the
  child's column keeps its old type, Django's re-added foreign key fails with
  SQL0538: the migration state is what makes it work.)
- **b. A type change of a column in a foreign key silently disables it.**
  `ALTER COLUMN ... SET DATA TYPE` (INTEGER to BIGINT) on the child's column,
  or on the parent key, while the foreign key exists, is accepted. Afterwards
  the foreign key is still in `QSYS2.SYSCST`, but with `ENABLED` and
  `CHECK_PENDING` empty (before: `YES` / `NO`), and **a row without a parent
  is accepted**: it is no longer enforced, without any message. After the
  change of the child's column introspection no longer lists it; after the
  change of the parent key it still does. Django drops a foreign key before a
  type change of its column (and the incoming ones before a change of a
  referenced key) and adds it again, so migrations are not affected; the
  backend must never change such a column without that.
- **c. RENAME TABLE keeps foreign keys.** After `alter_db_table` of the parent
  and of the child, the foreign key refers to the parent's new name and is
  still enforced (SQL0530).
- **d. AlterField of a ForeignKey to a plain IntegerField** finds the foreign
  key by introspection and drops it; the values stay, and a value without a
  parent is accepted afterwards.

### DROP COLUMN with and without CASCADE (`nox -s probe -- drop_column`)
2026-10-20, PUB400 (IBM i 7.5), the backend's connection attributes, QTEMP,
the job's inquiry message reply set to `*DFT` for the run (set back to
`*RQD` afterwards). Phase 3 step B, decision 4: Django 5.2 writes
`ALTER TABLE t DROP COLUMN c CASCADE`, 6.0+ writes it without a keyword.

A table with one row; column B with a dependent index or a dependent view
(created fresh for each case), column C without dependents as control:

| Dependent | No keyword | RESTRICT | CASCADE |
|---|---|---|---|
| none (C) | HY008, cancelled | HY008, cancelled | HY008, cancelled |
| index on B | HY008, cancelled; index kept | HY008, cancelled; index kept | HY008, cancelled; index kept |
| view on B | HY008, cancelled; view kept | HY008, cancelled; view kept | HY008, cancelled; view kept |

- Every case ends the same way: SQLSTATE `HY008` "Operation cancelled"
  (30071), job log SQL0952 / CPF7304 / CPD32CE (inquiry message CPA32B2
  answered with its default reply C), the column, the index and the view
  all still there.
- **All three forms are valid syntax** (no SQL0104), and **none is refused
  over the dependency before the inquiry message**: even `RESTRICT` with a
  dependent view gets the same cancel, not a dependency error (e.g.
  SQL0478). Db2 for i asks CPA32B2 before it handles dependent objects.
- **Db2 for i's default (CASCADE or RESTRICT) cannot be determined on
  PUB400**: that needs a DROP COLUMN that is not cancelled, i.e. a system
  reply list entry `MSGID(CPA32B2) RPY('I')` and
  `OPTIONS["inquiry_message_reply"] = "*SYSRPYL"` (see "ALTER TABLE that
  may lose data"), which PUB400 does not have and which is outside QTEMP.
  Not assumed here; to be probed on a system with that entry (a dedicated
  IBM i).
- Constraint dependencies (a CHECK or foreign key on the column) cannot be
  probed in QTEMP (SQL7008, probe 22).

### ALTER TABLE, renames, indexes and row length (`probe -- alter_table`)
2026-10-22, PUB400 (IBM i 7.5), the backend's connection attributes, QTEMP
only, the job's inquiry message reply left at `*RQD` (the probe refuses to
run otherwise and changes no job attribute). Every statement ran on a fresh
one-row table; phase 4 step A, probe 24.

**Column type changes** (`ALTER COLUMN c SET DATA TYPE t`):

| Change | Result |
|---|---|
| INTEGER -> BIGINT, INTEGER -> DECIMAL(15, 2) | ok |
| DECIMAL(9, 2) -> DECIMAL(12, 2), -> DECIMAL(11, 4) | ok |
| NVARCHAR(20) -> NVARCHAR(40), -> NCLOB(1M) | ok |
| BIGINT -> INTEGER, DECIMAL(9, 2) -> INTEGER, DECIMAL(9, 2) -> DECIMAL(7, 2) | CPA32B2, cancelled (HY008) |
| NVARCHAR(20) -> NVARCHAR(10), NCLOB(1M) -> NVARCHAR(100) | CPA32B2, cancelled (HY008) |
| BOOLEAN -> SMALLINT, INTEGER -> BOOLEAN | SQL0190 "attributes not compatible" |

- **`ALTER COLUMN c TYPE t` is not Db2 for i syntax** (SQL0199 "Keyword TYPE
  not expected. Valid tokens: SET DROP RESTART"): only `SET DATA TYPE`.
  Django's base template writes `TYPE`, which is the 18 SQL0199 errors of the
  `schema` baseline run.
- Widening keeps the value; every narrowing change sends CPA32B2, also when
  the value fits (as in "ALTER TABLE cancelled by CPA32B2").

**NULL and defaults:** `SET NOT NULL` sends CPA32B2 and is cancelled **also
without NULLs in the data**; `DROP NOT NULL`, `SET DEFAULT` and `DROP DEFAULT`
work. So making a column NOT NULL needs the CPA32B2 reply list entry, like
DROP COLUMN.

**Renames:**
- `ALTER TABLE t RENAME COLUMN a TO b`: SQL0199 "Keyword RENAME not
  expected" (the 11 SQL0199 RENAME errors of the baseline). No column rename
  form was found in this probe; to be looked up before step C.
- `ALTER TABLE t RENAME TO n`: SQL0199. `RENAME TABLE t TO n` works. A long
  new name gets a generated system name (`P24_R00001` for
  `P24_RENAMED_WITH_A_LONG_NAME`); `... FOR SYSTEM NAME s` sets it.
- `ALTER INDEX i RENAME TO j`: SQL0199. `RENAME INDEX i TO j` works.

**Identity:** `ALTER COLUMN c SET GENERATED ... AS IDENTITY` on a plain column
fails (SQL0190), for BY DEFAULT and ALWAYS. `ADD COLUMN ... GENERATED BY
DEFAULT AS IDENTITY` works (the column is NOT NULL and numbered). `DROP
IDENTITY` works; the column then stays NOT NULL without a value (an insert
without it fails with SQL0407).

**Several clauses in one ALTER TABLE:** `ALTER COLUMN ... ALTER COLUMN ...`,
`ADD COLUMN ... ALTER COLUMN ...` and `ADD COLUMN ... ADD COLUMN ...` work
when the clauses follow each other **without commas**; with commas SQL0104
(`supports_combined_alters` needs the space-separated form).

**Column order (#23):** `SELECT *` returns the columns in `CREATE TABLE`
order, and `ADD COLUMN` appends at the end.

**Indexes:** `CREATE INDEX ... (a DESC, b ASC)` works. An index on an `NCLOB`
column fails with SQL0350 "Column ... not valid" (the baseline's one SQL0350,
a `TextField` index). A long index name gets a generated system name
(`P24_A00001`).

**Comments:** `COMMENT ON` takes a plain string literal only: `UX'...'` and
`N'...'` are rejected (SQL0104), and the `N'...'` error shows the text already
as substitution characters (`\x1a`): the statement text is converted to the
job CCSID before it is parsed, so text outside it is lost. Reading a comment
back is not possible in QTEMP (probe 25). **`supports_comments` stays off**
(phase 4 decision 7: only if any Unicode text works).

**Row length:** the largest NOT NULL `CHAR(n)` is 32,766 (nullable 32,765;
SQL0604 beyond); two or three NOT NULL `CHAR` columns also total at most
**32,766 bytes** (SQL0101 "statement too long or complex" beyond). That
confirms 32,766 (DECISIONS), not the 32,740 `SQL_MAX_ROW_SIZE` reports.

### ALTER COLUMN on indexed, unique and identity columns (`probe -- alter_column`)
2026-10-24, PUB400 (IBM i 7.5), the backend's connection attributes, QTEMP
only, inquiry message reply `*RQD` (as probe 24). Phase 4 step C item 7,
`probes/qtemp_alter_column.py`. Each case on a fresh two-row table:

| Change | Result |
|---|---|
| INTEGER -> BIGINT on a column with an index | ok; values kept, the index is still there |
| NVARCHAR(10) -> NVARCHAR(20) on a column with a unique index | ok; values kept, a duplicate still fails (SQL0803), a longer value fits |
| DECIMAL(5, 2) -> DECIMAL(7, 3) (precision and scale) | ok; `123.45` -> `123.450`, `-0.01` -> `-0.010` |
| `SET DEFAULT UX'...'` (`O'Brien 100% Ж`) | ok; an insert without the column gets exactly that text |
| identity INTEGER -> BIGINT, `SET DATA TYPE BIGINT` | ok; still an identity, still NOT NULL, the next row gets 3 |
| identity INTEGER -> BIGINT, `SET DATA TYPE BIGINT GENERATED BY DEFAULT AS IDENTITY` | ok, the same |

- A **unique constraint cannot be created in QTEMP** under commitment control:
  `SQL7008 - <table> in QTEMP not valid for operation` (QTEMP is not
  journaled). A named constraint without a qualifier goes to the current
  schema instead (`SQL5051 - Qualifier <library> not same as name QTEMP`).
  The probe uses a unique index in its place.
- The pub400 test `test_alter_field_and_back` (Django's own `alter_field()`,
  rows in a real library) confirms the widening forms, `DROP NOT NULL` and
  `SET DEFAULT`, and that the way back is cancelled by CPA32B2. For
  `null=True` -> `null=False` with a default, Django's `UPDATE ... WHERE ...
  IS NULL` before `SET NOT NULL` is not undone when `SET NOT NULL` is
  cancelled: the schema editor runs no transaction while `can_rollback_ddl` is
  off (Known limitations; phase 4 item 11a).

### Column renames and identity changes (`probe -- renames`)
2026-10-24, PUB400 (IBM i 7.5), the backend's connection attributes, QTEMP
only, inquiry message reply `*RQD`. Phase 4 step C item 8,
`probes/qtemp_renames.py`; each case on a fresh two-row table (a unique index
on `ID` in place of a primary key, which QTEMP does not take under commitment
control).

**No statement renames a column.** Every form tried fails:

| Form | Result |
|---|---|
| `ALTER TABLE t RENAME COLUMN a TO b` | SQL0199 (-199) "Keyword RENAME not expected. Valid tokens: ADD LOG NOT SET DATA DROP ALTER CHECK APPEND ATTACH DETACH" |
| `RENAME COLUMN t.a TO b` | SQL0104 (-104) "Token QTEMP was not valid. Valid tokens: TO" |
| `ALTER TABLE t ALTER COLUMN a RENAME TO b` | SQL0199 (-199) "Valid tokens: SET DROP RESTART" |
| `RENAME t.a TO b` | SQL0950 (-950) (reads `t` as a relational database) |

IBM's documentation agrees (checked 2026-10-24): the Db2 for i SQL reference
for 7.6 lists no rename clause in `ALTER TABLE` (`ALTER COLUMN` takes only
`SET DATA TYPE`, `SET` default / generated / `NOT NULL` / hidden / fieldproc,
the `DROP` forms and the identity alterations), and the `RENAME` statement
renames tables and indexes. The 7.5 page could not be loaded (HTTP 503);
a form missing in 7.6 is not in 7.5. IBM idea IBMI-I-1002 ("DB2 Alter Table
Rename column", open since 2016) has a Db2 for i team comment of
2026-09-16: "Unfortunately, we haven't been able to deliver this enhancement
yet"; IBMI-I-5030, a duplicate, is "Future consideration". So no TR or PTF
level has it, and there is no capability for it: the schema editor raises
`NotSupportedError` (Known limitations, "Renaming a column").

**Identity changes**, as Django writes them:

| Change | Result |
|---|---|
| AutoField -> IntegerField: `SET DATA TYPE INTEGER` on the identity column | accepted, but **the identity stays** (an insert without `ID` still gets 3) |
| AutoField -> IntegerField: `DROP IDENTITY` | ok: explicit keys work, an insert without `ID` fails (SQL0407) |
| IntegerField -> AutoField on a column with rows: `SET DATA TYPE INTEGER GENERATED BY DEFAULT AS IDENTITY` | accepted, but numbering starts at 1: the next insert collides (SQL0803) |
| ... then `RESTART WITH 3` | ok, the next row gets 3 |
| ... then a dynamic compound statement (`BEGIN DECLARE ...; SET n = (SELECT COALESCE(MAX(ID), 0) + 1 ...); EXECUTE IMMEDIATE 'ALTER TABLE ... RESTART WITH ' CONCAT VARCHAR(n); END`) | ok, the next row gets 3 |
| SmallAutoField -> AutoField | ok, numbering continues |
| BigAutoField -> AutoField (narrowing) | CPA32B2, cancelled (HY008) |

The schema editor therefore drops the identity with `DROP IDENTITY` and, for a
new identity, restarts it with the compound statement (it needs no query
before, so it also works for collected SQL, `sqlmigrate`).

### Column type changes in place (`probe -- type_changes`)
2026-10-24, PUB400 (IBM i 7.5), the backend's connection attributes, QTEMP
only, inquiry message reply `*RQD`. Phase 4 step C item 9,
`probes/qtemp_type_changes.py`: every ordered pair of the 14 base types the
backend writes (182 pairs), each `ALTER COLUMN ... SET DATA TYPE` on an empty
one-column table, so only the type rules show.

| From \ to | in place | CPA32B2 (needs the reply list entry) | SQL0190 (never in place) |
|---|---|---|---|
| SMALLINT | INTEGER, BIGINT, DECIMAL | DOUBLE | all others |
| INTEGER | BIGINT | SMALLINT, DECIMAL, DOUBLE | all others |
| BIGINT, DECIMAL, DOUBLE | - | the other numeric types | all others |
| CHAR | VARCHAR, NVARCHAR, NCLOB | - | all others |
| VARCHAR | NVARCHAR, NCLOB | CHAR | all others |
| NVARCHAR | NCLOB | CHAR, VARCHAR | all others |
| NCLOB | - | CHAR, VARCHAR, NVARCHAR | all others |
| BLOB | - | CHAR, VARCHAR | all others (also NVARCHAR, NCLOB) |
| BOOLEAN, DATE, TIME, TIMESTAMP | - | - | every other type (also DATE -> TIMESTAMP) |

So a type changes in place, or with the reply list entry, only within the
numeric types and within the character types (and BLOB to CHAR / VARCHAR).
The schema editor raises `NotSupportedError` for every other change before it
sends any statement (`alter_field()`; Django drops the column's foreign keys,
unique constraints and indexes before the type change, and without
`can_rollback_ddl` a later error would leave them dropped).

### CHECK constraints on a table that is not journaled (`probe -- check_journal`)
2026-10-24, PUB400 (IBM i 7.5), the backend's connection attributes (`CMT=1`,
`TRUEAUTOCOMMIT=1`), QTEMP only. Phase 4 step C item 11,
`probes/qtemp_check_journal.py`. QTEMP tables cannot be journaled, so they
stand in for a table in a library without a journal. Each CHECK form the
schema editor writes, in autocommit mode and in a transaction (rolled back):

| Statement | autocommit | transaction |
|---|---|---|
| `CREATE TABLE` without a constraint (control) | ok | ok |
| column check in `CREATE TABLE` (`A INTEGER CHECK (A >= 0)`) | SQL7008 | SQL7008 |
| named check in `CREATE TABLE` (`CONSTRAINT QTEMP.C CHECK (...)`) | SQL7008 | SQL7008 |
| `ALTER TABLE ... ADD CONSTRAINT QTEMP.C CHECK (...)` | SQL7008 | SQL7008 |

- Every CHECK fails with `SQL7008 - PCKJ in QTEMP not valid for operation`,
  SQLSTATE `HY000`, as `PRIMARY KEY`, `UNIQUE` and `REFERENCES` do (probe 22):
  a constraint needs a journaled table under commitment control, and the
  backend always runs under it (`TRUEAUTOCOMMIT=1`, also in autocommit mode).
- So check constraints add no new requirement: a Django table has a primary
  key, so its `CREATE TABLE` already needs the journal. What they add is
  `ADD CONSTRAINT` on an existing table (AddConstraint, AlterField to a
  positive integer field): a table that is not journaled (created before the
  library's `QSQJRN`, or outside SQL) fails there.
- A table in a user library without a journal was not probed with constraints
  (that needs approval); it gave the same SQL7008 for a transaction in
  probe `w01_commitment` ("Commitment control on an unjournaled table").
- Adding a CHECK that a row already violates fails with `SQL0544 - CHECK
  constraint ... cannot be added` (SQLSTATE `HY000`; the driver layer maps
  SQLCODE -544 to IntegrityError, as PostgreSQL reports such a check), and the
  table is unchanged (pub400 test `test_positive_field_to_integer_and_back`,
  journaled library).

### DDL under commitment control: what ROLLBACK undoes (`lib_rollback_ddl`)
2026-10-24, PUB400 (IBM i 7.5), write probe in the journaled default library,
approved by the maintainer on issue #149 (started via `bin/probe --approved`).
Phase 4 step C item 11a, `probes/lib_rollback_ddl.py`, result in
`probes/results/lib_rollback_ddl.json`. One connection, `CMT=1`; each case on
a fresh two-row table: autocommit off, a marker row into a helper table, the
DDL as the schema editor writes it, `ROLLBACK`.

- **Every form is undone and none commits implicitly** (the marker row was
  gone after every `ROLLBACK`): `CREATE TABLE`, `DROP TABLE`, `ADD COLUMN`;
  `ALTER COLUMN` `SET DATA TYPE` (widening), `DROP NOT NULL`, `SET DEFAULT`,
  `DROP DEFAULT`, `DROP IDENTITY`, `SET DATA TYPE ... AS IDENTITY` with the
  compound `RESTART` statement; `CREATE [UNIQUE] INDEX`, `DROP INDEX`,
  `RENAME INDEX`, `RENAME TABLE`; `ADD CONSTRAINT` (unique, check, foreign
  key), `DROP CONSTRAINT`; `LABEL ON COLUMN`, `COMMENT ON TABLE`.
- **A migration cancelled by CPA32B2 halfway** (`CREATE TABLE`, `ADD
  COLUMN`, `CREATE INDEX`, then a narrowing `SET DATA TYPE`): after
  `ROLLBACK` the table and the index are gone; the transaction and the
  connection stay usable after the cancel (HY008).
- **`UPDATE ... WHERE ... IS NULL`, then a cancelled `SET NOT NULL`**: after
  `ROLLBACK` the NULLs are back and the column is still nullable.
- `DROP COLUMN` is cancelled by CPA32B2 (nothing to undo).

So `can_rollback_ddl` can be True: with it the schema editor runs a migration
in one transaction, and a statement cancelled by CPA32B2 leaves nothing of
the migration behind (item 11a).

### No statement starts a transaction (`probe -- transaction_start`)
2026-10-24, PUB400 (IBM i 7.5), QTEMP probe that writes nothing: the
backend's connection attributes (commitment control, `TRUEAUTOCOMMIT=1`),
autocommit off, each candidate followed by `ROLLBACK`. Result in
`probes/results/transaction_start.json`.

| Statement | Result |
|---|---|
| `BEGIN` | SQL0104 (42000), token `<END-OF-STATEMENT>` not valid |
| `BEGIN WORK`, `BEGIN TRANSACTION` | SQL0104 (42000) |
| `START TRANSACTION` | SQL0199 (42000), keyword `START` not expected |
| `BEGIN ATOMIC END` | ok: an (empty) compound statement, not a transaction start |

Under commitment control the transaction starts with the first statement
(`lib_rollback_ddl` rolled DDL back without any start statement), so
`start_transaction_sql()` returns `""`: that is what `sqlmigrate` prints
before an atomic migration once `can_rollback_ddl` is on.

### ADD COLUMN ... NOT NULL without a default (`probe -- add_column_default`)
2026-10-25, PUB400 (IBM i 7.5), QTEMP only, the backend's connection
attributes. Result in `probes/results/add_column_default.json`. For each base
type the backend writes (SMALLINT, INTEGER, BIGINT, DECIMAL, DOUBLE, BOOLEAN,
CHAR, VARCHAR, NVARCHAR, NCLOB, BLOB, DATE, TIME, TIMESTAMP):

- `ADD COLUMN c <type> NOT NULL` fails with **SQL0109** (42000), "NOT NULL
  clause not allowed", also on an empty table: Db2 for i needs a DEFAULT with
  NOT NULL (IBM's SQL reference: unless the column is an identity column).
  This is what Django's AddField of a NOT NULL field without any default
  writes (Django's `test_indexes`, `test_remove_constraints_capital_letters`,
  `test_unique_together_with_fk_with_existing_index`).
- A bare DEFAULT (the type's system default) is accepted in every spelling:
  `DEFAULT NOT NULL`, `NOT NULL DEFAULT`, `NOT NULL WITH DEFAULT`, `WITH DEFAULT
  NOT NULL`, for every type including NCLOB and BLOB. `ALTER COLUMN c DROP
  DEFAULT` works afterwards; an INSERT without the column then fails with
  SQL0407 (23000): the column is NOT NULL without a default.
- What value existing rows get was not recorded: an INSERT into the QTEMP
  table is not possible under commitment control (QTEMP is not journaled).
  The backend refuses a table with rows anyway (schema.py `add_field()`).
- `LOCK TABLE ... IN EXCLUSIVE MODE` and `IN SHARE MODE` are accepted, in a
  transaction and in autocommit. What the lock allows other jobs needs a table
  outside QTEMP (`lib_lock_table`, #162, not run yet).

### Catalog views for introspection (`probe -- catalog`)
2026-10-22, PUB400 (IBM i 7.5), read-only outside QTEMP; phase 4 step A,
probe 25. The views' columns, from their own `QSYS2.SYSCOLUMNS` rows:

| View | Columns introspection needs |
|---|---|
| `SYSCST` | `CONSTRAINT_SCHEMA`, `CONSTRAINT_NAME`, `CONSTRAINT_TYPE`, `TABLE_SCHEMA`, `TABLE_NAME`, `IS_DEFERRABLE`, `INITIALLY_DEFERRED`, `CONSTRAINT_KEYS`, `ENABLED`, `CHECK_PENDING` |
| `SYSKEYCST` | `CONSTRAINT_SCHEMA`, `CONSTRAINT_NAME`, `TABLE_SCHEMA`, `TABLE_NAME`, `COLUMN_NAME`, `ORDINAL_POSITION`, `COLUMN_POSITION` |
| `SYSREFCST` | `CONSTRAINT_NAME`, `UNIQUE_CONSTRAINT_SCHEMA`, `UNIQUE_CONSTRAINT_NAME`, `MATCH_OPTION`, `UPDATE_RULE`, `DELETE_RULE`, `COLUMN_COUNT` |
| `SYSCHKCST` | `CONSTRAINT_SCHEMA`, `CONSTRAINT_NAME`, `CHECK_CLAUSE` |
| `SYSINDEXES` | `INDEX_SCHEMA`, `INDEX_NAME`, `TABLE_SCHEMA`, `TABLE_NAME`, `IS_UNIQUE`, `COLUMN_COUNT`, `SYSTEM_INDEX_NAME`, `INDEX_HAS_SEARCH_CONDITION`, `SEARCH_CONDITION`, `INDEX_HAS_INCLUDE_EXPRESSION` |
| `SYSKEYS` | `INDEX_SCHEMA`, `INDEX_NAME`, `COLUMN_NAME`, `ORDINAL_POSITION`, `COLUMN_POSITION`, `ORDERING`, `COLUMN_IS_EXPRESSION`, `KEY_EXPRESSION` |
| `SYSCOLUMNS` | `ORDINAL_POSITION`, `DATA_TYPE`, `LENGTH`, `NUMERIC_SCALE`, `NUMERIC_PRECISION`, `IS_NULLABLE`, `HAS_DEFAULT`, `COLUMN_DEFAULT`, `IS_IDENTITY`, `IDENTITY_GENERATION`, `CCSID`, `LONG_COMMENT` |
| `SYSCSTCOL` | `CONSTRAINT_SCHEMA`, `CONSTRAINT_NAME`, `TABLE_SCHEMA`, `TABLE_NAME`, `COLUMN_NAME` (the columns a constraint references, used for checks; no position column; probe 25 rerun 2026-10-23) |

- **QTEMP objects do not appear** in `SYSTABLES`, `SYSCOLUMNS`, `SYSINDEXES` or
  `SYSKEYS` (a QTEMP table with a unique and a descending index: no rows).
  Introspection tests therefore need tables in a real library.
- The two test libraries held no constraints or indexes when the probe ran,
  so the coded values (`CONSTRAINT_TYPE`, the rules, `IS_UNIQUE`, `ORDERING`)
  come from probe w13's own tables instead (see "Foreign keys, unique and
  check constraints"). The libraries' `SYSCOLUMNS` rows (126 columns) show
  `HAS_DEFAULT` `N`, `IS_IDENTITY` `NO`, `IS_NULLABLE` `Y` / `N`, and
  `DATA_TYPE` values `CHAR`, `INTEGER`, `SMALLINT`, `VARCHAR` and `VARG`
  (graphic varying, i.e. NVARCHAR).

### Column types in the catalog (`nox -s probe_column_types -- --execute`)
2026-10-23, PUB400 (IBM i 7.5), write probe w14 (approved 2026-10-23, step B
item 6): four own `DJW14` tables in the journaled `default` library, each on
the table list before its `CREATE TABLE`, all dropped at the end (none left).
`QSYS2.SYSCOLUMNS` for every type of `DatabaseWrapper.data_types`:

| Backend type (Django field) | `DATA_TYPE` | `LENGTH` | Other |
|---|---|---|---|
| `INTEGER` / identity (`AutoField`) | `INTEGER` | 4 | precision 9 |
| `BIGINT` / identity (`BigAutoField`, `DurationField`) | `BIGINT` | 8 | precision 18 |
| `SMALLINT` / identity (`SmallAutoField`) | `SMALLINT` | 2 | precision 4 |
| `BOOLEAN` | `BOOLEAN` | 1 | |
| `NVARCHAR(n)` (`CharField`, `SlugField`, ...) | `VARG` | n | CCSID 1200, octet length 2n |
| `NCLOB` (`TextField`) | `DBCLOB` | 1048576 | CCSID 1200 |
| `VARCHAR(n)` (`IPAddressField`, ...) | `VARCHAR` | n | job CCSID (273 on PUB400) |
| `CHAR(32)` (`UUIDField`) | `CHAR` | 32 | job CCSID |
| `BLOB` (`BinaryField`) | `BLOB` | 1048576 | CCSID 65535 |
| `DECIMAL(p, s)` | `DECIMAL` | p | precision p, scale s |
| `DOUBLE` (`FloatField`) | `FLOAT` | 8 | precision 52, radix 2 |
| `DATE` | `DATE` | 4 | |
| `TIME` | `TIME` | 3 | |
| `TIMESTAMP(6)` | `TIMESTMP` | 10 | the fraction digits are not in `NUMERIC_SCALE` (the driver reports scale 6) |

- **Identity:** `IS_IDENTITY` `YES`, `IDENTITY_GENERATION` `BY DEFAULT`,
  `HAS_DEFAULT` **`J`**, `COLUMN_DEFAULT` NULL.
- **Defaults:** `HAS_DEFAULT` `Y` and `COLUMN_DEFAULT` the clause as text:
  `42`, `-1`, `1.50`, `2.5`, `'abc'`, `'it''s'`, `''` (quoted as in SQL),
  `TRUE`, `CURRENT_DATE`, `CURRENT_TIMESTAMP` (with an underscore, although
  the DDL said `CURRENT DATE` / `CURRENT TIMESTAMP`), and `NULL` for an
  explicit `DEFAULT NULL`. **A nullable column without a `DEFAULT` clause
  also has `HAS_DEFAULT` `Y`**, with `COLUMN_DEFAULT` NULL (the implicit null
  default); a `NOT NULL` column without one has `N`.
- **Column check** in Django's form `CHECK (k_pos >= 0)`: a system name
  `Q_<library>_<table>_<column>_00001`, `SYSCHKCST.CHECK_CLAUSE`
  `K_POS >= 0` (the identifier uppercased), one `SYSCSTCOL` row (`K_POS`).
- **`cursor.description`** (pyodbc): `display_size` is always `None`;
  `internal_size` and `precision` are the same number: the length for
  strings and LOBs (characters), the digits for numbers (`INTEGER` 10,
  `BIGINT` 20, `SMALLINT` 5, `DOUBLE` 15), 10 / 8 / 26 for `DATE` / `TIME` /
  `TIMESTAMP(6)`; scale 6 for `TIMESTAMP(6)`, s for `DECIMAL`.

### Numeric values that do not fit the column (`nox -s probe -- numeric_params`)
2026-10-20, PUB400 (IBM i 7.5), the backend's connection attributes; a QTEMP
table with `SMALL SMALLINT` and `AMOUNT DECIMAL(5, 2)` whose rows hold the
truncated (1.00) and the rounded (1.01) value of 1.005, the SMALLINT limits
and NULLs.

- Untyped markers (control): `SMALL IN (?, ?)` with 100000 gives 30018
  ("Numeric value out of range"); `AMOUNT = ?` with 1.005 gives 30126 (right
  truncation).
- **A marker typed by the value, `CAST(? AS DECIMAL(p, s))`, compares
  exactly**: for 1.005, `=` matches neither 1.00 nor 1.01; `<>`, `<`, `>`,
  `IN` (mixed with untyped markers), `NOT IN` and `BETWEEN` give exactly the
  rows of exact arithmetic (19 checks), also for 123456.789, `1E+5` as
  `DECIMAL(6, 0)`, `-0.0`, a trailing zero (1.50), integers out of the
  SMALLINT range as `DECIMAL(6, 0)`, and 10**20 as `DECIMAL(21, 0)`.
- **DECIMAL holds at most 63 digits**: `CAST(? AS DECIMAL(63, 0))` and
  `DECIMAL(63, 62)` work, `DECIMAL(64, 0)` fails with SQL0604 ("Attributes
  not valid").
- **pyodbc binds a Python int as a 64-bit integer**: a larger int fails before
  the driver (`OverflowError: int too big to convert`); the same value as a
  `Decimal` binds exactly.

### IN (subquery) inside CASE WHEN (`probe -- in_subquery`, `probe -- queries`)
2026-10-19, read-only, PUB400 (IBM i 7.5). **`x IN (subquery)` and `x = ANY
(subquery)` are rejected inside CASE WHEN** with SQL0115 ("Comparison operator
IN / = not valid"), also when the CASE is in a WHERE clause (Django's XOR
emulation: `CAST(? AS INTEGER) = (CASE WHEN x IN (...) THEN 1 ELSE 0 END +
...)`) and in the select list; `EXISTS` has the same restriction. A first-row
subquery works there: `CASE WHEN (SELECT 1 FROM (<subquery>) AS S (V) WHERE
S.V = x FETCH FIRST 1 ROWS ONLY) IS NOT NULL`, also correlated through
`LATERAL`. Three-valued form checked against plain `IN` / `NOT IN` in WHERE
for x = 1, 2, 3, NULL and subqueries {1, NULL}, {2}, {NULL} and empty, positive
and negated, in WHERE and inside CASE WHEN: all 16 combinations identical,
including `NULL NOT IN (empty)` (TRUE) and `1 NOT IN (2, NULL)` (UNKNOWN):

    (CASE WHEN <match> IS NOT NULL THEN TRUE WHEN <any row> IS NULL THEN FALSE
          WHEN x IS NULL THEN NULL WHEN <NULL row> IS NOT NULL THEN NULL
          ELSE FALSE END) = TRUE

The backend now uses the equivalent general form for any number of columns
(see "Tuple IN (subquery)" below).

Sliced subqueries (`allow_sliced_subqueries_with_in`, 2026-10-19): `x IN
(SELECT ... ORDER BY ... FETCH FIRST n ROWS ONLY)`, also with `OFFSET`, works
in WHERE; inside CASE WHEN it gives SQL0115 like any IN (subquery). The
rewrite over `LATERAL (<sliced subquery>)` gives exactly the rows of plain IN
/ NOT IN for both forms, positive, negated and inside CASE WHEN (probe
`in_subquery`).

### Tuple IN (subquery) (`probe -- tuple_in`)
2026-10-19, read-only (VALUES only), PUB400 (IBM i 7.5). Row-value
`(a, b) IN (subquery)` and `NOT IN` work in WHERE. For IN (subquery) outside
a search condition one general form, with one column per tuple element, gives
exactly the rows of plain IN / NOT IN: for pairs ((1, 1), (1, NULL),
(NULL, NULL), (2, 2), (3, 9)) against subqueries with a match and a partly
NULL row, no NULL, only (NULL, NULL), (1, NULL) and empty, and for one column
against probe 16's subqueries, positive, negated and inside CASE WHEN (all 9
identical):

    (CASE WHEN <a row with V1 = x1 AND ... AND Vn = xn> IS NOT NULL THEN TRUE
          WHEN <a row with (Vi = xi OR Vi IS NULL OR xi IS NULL) for every i>
               IS NOT NULL THEN NULL
          ELSE FALSE END) = TRUE

### Row-value predicates for tuple lookups (`probe -- tuple_lookups`)
2026-10-19, read-only (VALUES only), PUB400 (IBM i 7.5). The forms Django
writes with `supports_tuple_lookups`, on rows with NULLs in either column,
compared with Django's expanded form, in WHERE and negated:

- `(a, b) = (?, ?)` and `<>`: accepted with untyped and typed markers;
  identical rows, also negated (UNKNOWN for a NULL in either column), and in
  CASE WHEN.
- `(a, b) IN ((?, ?), (?, ?))`: rejected (SQL0104), typed or not.
- `(a, b) > / >= / < / <= (?, ?)`: rejected (SQL0115), typed or not.
- `(a, b) IN (subquery)`: accepted in WHERE; positive rows identical to
  Django's EXISTS fallback, negated rows three-valued (`NOT IN` leaves out
  rows that are UNKNOWN, `NOT EXISTS` returns them). Inside CASE WHEN: SQL0115
  (the IN rewrite handles it).
- Against a subquery: `(a, b) = (subquery)` works, `(a, b) > (subquery)` is
  rejected (SQL0115).

### Ordered and sliced parts of compound queries (`probe -- compound_parts`)
2026-10-19, read-only (VALUES only), PUB400 (IBM i 7.5). Besides probe 9's
parenthesised top-level parts with `ORDER BY` + `FETCH FIRST` / `OFFSET`, all
13 shapes Django writes with `supports_slicing_ordering_in_compound` and
`supports_parentheses_in_compound` work with the expected rows: a part's
`ORDER BY` with the NULL ordering emulation (`X IS NULL, X`), by a column
that is not selected, or without `FETCH FIRST`; typed markers with `OFFSET`;
`FETCH FIRST` after parenthesised parts; a nested compound query as a
parenthesised part, also with parenthesised parts inside; and inside
subqueries: `IN ((part) UNION (part))` with sliced and with correlated
parts, a scalar subquery, `EXISTS`, and the backend's `SELECT * FROM LATERAL
((part) UNION (part))` wrapper, correlated and with an expression in its
ORDER BY. `ORDER BY X DESC` inside a part puts NULLs first (NULLs sort as
the largest value).

### Predicates as three-valued values (`probe -- selected_predicates`)
2026-10-19, read-only (VALUES only), PUB400 (IBM i 7.5). Issue #75's
candidate `CASE WHEN p THEN TRUE WHEN NOT (p) THEN FALSE END` (NULL
otherwise), in the select list, and `WHERE p` / `WHERE NOT (p)`, compared with
the three-valued truth computed in Python, on rows with NULLs:

- **Exact for every real predicate** (11 kinds): `X < ?` (untyped) and
  `X < CAST(? AS INTEGER)`, `V = TRUE`, `V = FALSE`, AND / OR with NULLs, LIKE,
  `REGEXP_LIKE`, row-value `(X, S) = (?, ?)`, the NegatedValue CASE compared
  with TRUE, and predicates with subqueries evaluated twice by the form (the
  IN rewrite over a subquery with a NULL, a correlated sliced scalar
  subquery).
- **Wrong for a bare BOOLEAN value used as a predicate** (3 kinds): `V`,
  `NOT V` and the NegatedValue CASE as a condition. The selected value gives
  FALSE/TRUE for NULL, and `WHERE NOT V` / `WHERE NOT (V)` return the NULL rows
  (Db2 for i's NOT of a BOOLEAN value is two-valued, see "NOT of a NULL
  BOOLEAN value is TRUE" above). Their comparison forms (`V = TRUE`, `V =
  FALSE`, `(CASE ...) = TRUE`) are exact in every position.

### Truncating dates and times (`probe -- trunc`)
2026-10-18, read-only (SYSDUMMY1), timestamps around week and year edges
compared with Django's truncation in Python.

- `TRUNC_TIMESTAMP(<timestamp>, '<format>')` matches Django for `'YEAR'` /
  `'YYYY'`, `'Q'`, `'MONTH'` / `'MM'`, `'DD'` / `'DDD'` / `'J'`, `'HH'` /
  `'HH24'`, `'MI'` and `'SS'` (microseconds dropped). **Week: only `'IW'`**
  starts on Monday (the ISO week, Django's convention: Sunday 2023-01-01 ->
  2022-12-26); `'WW'` and `'W'` count from the first day of the year / month
  and `'DAY'` / `'D'` start on Sunday.
- A DATE argument works and returns a TIMESTAMP; `DATE(TRUNC_TIMESTAMP(...))`
  gives the DATE. A TIME argument is rejected (SQL0171);
  `TIME(TRUNC_TIMESTAMP(TIMESTAMP(DATE('0001-01-01'), TIME(<x>)), ...))`
  works for a TIME and for a TIMESTAMP `<x>` (Django sends timestamps with a
  TimeField output to time_trunc_sql).
- An untyped marker as the argument is rejected (SQL0171); a NULL gives NULL.
  `DATE(<timestamp>)` and `TIME(<timestamp>)` give the date / time (TIME
  without fractions).

### SQL features for phase 2 (`probe -- queries`)
2026-10-18, read-only (`SYSIBM.SYSDUMMY1`, `VALUES`, derived tables, two
catalog views), one connection.

**Compound queries.** `UNION`, `UNION ALL`, `INTERSECT`, `EXCEPT` work, also
with typed markers in the parts. `INTERSECT ALL` and `EXCEPT ALL` are
rejected (SQL0104, "valid tokens: DISTINCT"). Parenthesised parts are
accepted, also with `ORDER BY` + `FETCH FIRST` or `OFFSET` inside a part;
`ORDER BY` by column name or position and `FETCH FIRST` after the compound
work; a `UNION` inside `IN (...)` works.
An **expression** in the ORDER BY of a compound query is rejected, also
when it uses only result columns (`... UNION ... ORDER BY X IS NOT NULL, X`:
SQL0214). Wrapped as `SELECT * FROM (<compound>) ORDER BY X IS NOT NULL, X`
it works, also with markers and `FETCH FIRST`, and a correlation name is not
needed. Inside a correlated scalar subquery the wrapped form cannot see the
outer table (SQL5001 "Column qualifier or table *N undefined"; via ODBC with
Django's quoting SQL0204 "<table> in QSYS type *LIB not found"); with
`SELECT * FROM LATERAL (<compound>)` (or `TABLE (...)`) it can, and LATERAL
also works uncorrelated. (Added 2026-10-18 for `supports_select_union`.)

**Subqueries.** `IN (subquery ... FETCH FIRST n ROWS ONLY)` and with
`OFFSET` work; a scalar subquery in `GROUP BY` works; a correlated scalar
subquery in the select list works. `GROUP BY 1` (select index) is rejected
(SQL0122). **`EXISTS` is accepted only as a search condition** (`WHERE`):
in the select list it is rejected (SQL0104), also inside `CASE WHEN EXISTS
(...) THEN ...` and inside a derived table's select list; `CASE WHEN 1 IN
(subquery)` in the select list is rejected too (SQL0115). `CASE WHEN
(SELECT COUNT(*) ...) > 0` works. **Rewrite for `Exists()` in the select
list** that stops at the first row: `(SELECT 1 FROM ... WHERE ... FETCH
FIRST 1 ROW ONLY) IS NOT NULL` works as a select-list predicate (BOOLEAN),
also correlated, with a parameter marker inside, and in `WHERE` / `ORDER
BY`; `CASE WHEN <that> THEN TRUE ELSE FALSE END` works too. `(SELECT
COUNT(*) ...) > 0` gives the same results but counts every matching row.
**`EXISTS` is accepted only directly as a search condition**: `CASE WHEN
EXISTS (...)` fails also inside a WHERE clause (SQL0104), and `ORDER BY
EXISTS (...)` fails (SQL0115); the first-row form works in GROUP BY, ORDER
BY and under `NOT`. **A parameter marker in the select list of an `EXISTS`
subquery fails in the host server**: `WHERE EXISTS (SELECT CAST(? AS
INTEGER) AS A ...)` gives "Error in host server data stream" (30187, at
prepare), typed or untyped, with or without `FETCH FIRST`, correlated or
not (on the backend's connection; nested inside a first-row subquery:
"Internal driver error" 30101). Markers in the subquery's WHERE work, and a
marker in the select list of an `IN (SELECT ...)` subquery works. Django's
`Exists` selects `Value(1)`, so `compiler.py` selects a literal `1`.

**Boolean expressions** (7.5 BOOLEAN): predicates in the select list
(`1 = 1`, `X > 1`) return `True`/`False`; a boolean column alone and
`NOT column` work in `WHERE`; `CAST(? AS BOOLEAN)` works.
**A predicate is not accepted as an operand** (found by Django's `lookup`
tests): `WHERE (X < 3) = (X < 2)`, `WHERE X < 3 = X < 2`, `WHERE B = (X <
3)` (B a BOOLEAN column), `WHERE (X < 2) = TRUE` and `CASE WHEN ... THEN 1
ELSE 0 END = (X < 2)` all fail with SQL0104. `CASE WHEN <predicate> THEN
TRUE ELSE FALSE END` is a BOOLEAN value and works on either side
(`CASE ... = CASE ...`, `B = CASE ...`). In the select list a predicate
works alone and in parentheses (`SELECT (X < 2)`), **but not with an untyped
parameter marker**: `SELECT X < ?` fails with SQL0418, while `SELECT X <
CAST(? AS INTEGER)` and `SELECT CASE WHEN X < ? THEN TRUE ELSE FALSE END`
(untyped) work. **GROUP BY an expression with a parameter marker** fails
even when the same text is selected: `SELECT CASE WHEN X < CAST(? AS
INTEGER) ... GROUP BY CASE WHEN X < CAST(? AS INTEGER) ...` gives "Internal
driver error" (30101); without a marker it works (markers never match, as
for ORDER BY under DISTINCT; `GROUP BY 1` is not allowed either).

**GROUP BY: candidate fixes (2026-10-18).** A grouped expression is only
matched when it is selected as a whole, also without markers: `SELECT X + X
+ 1 ... GROUP BY X + X` and `SELECT LEAST(MIN(X), X + X) ... GROUP BY X + X`
fail with SQL0122 (a grouped *column* nested with an aggregate works).
`GROUP BY` a select alias fails (SQL0206); an untyped marker in `MOD(X, ?)`
fails with SQL0402; `COUNT(*)` over a grouped subquery with markers fails
with 30125 ("Character data right truncation"). Inline literals instead of
markers work when the expression is selected whole (integer, DECIMAL,
DOUBLE, BOOLEAN), but not nested (SQL0122), and a literal in GROUP BY with a
marker in the select list fails (SQL0122). A derived table that computes the
value and groups by its column works in every shape, and so does a
**LATERAL derived table** per row: `FROM ... CROSS JOIN LATERAL (SELECT
<expr> AS G1 FROM SYSIBM.SYSDUMMY1) AS G ... GROUP BY G.G1` with markers,
after a LEFT JOIN with aggregates of the joined table, nested
(`LEAST(MIN(T.X), G.G1)`), with markers in HAVING and the select list,
under `COUNT(*)`, with a correlated scalar subquery or a first-row EXISTS
value as the expression, and with `G.G1` in WHERE. The backend uses the
LATERAL form (compiler.py).

**NOT of a BOOLEAN value (2026-10-19).** `SELECT NOT CAST(? AS BOOLEAN)` works
in the select list, but as a comparison operand (`B = (NOT CAST(? AS
BOOLEAN))`) it fails with SQL0199, like every predicate operand. `CASE <value>
WHEN TRUE THEN FALSE WHEN FALSE THEN TRUE END` works there, also with a
marker, and gives NULL for NULL.

**NOT of a NULL BOOLEAN value is TRUE (probe finding, 2026-10-19).** Db2 for
i evaluates a BOOLEAN *value* used as a predicate two-valued, NULL as false.
Probe `queries` (`nox -s probe -- queries`, area boolean), with
`VB = (VALUES (1, CAST(TRUE AS BOOLEAN)), (2, CAST(FALSE AS BOOLEAN)),
(3, CAST(NULL AS BOOLEAN))) B (K, V)`:

| SQL | Result on PUB400 | SQL standard (three-valued) |
|---|---|---|
| `SELECT NOT V FROM (VALUES CAST(TRUE AS BOOLEAN), CAST(FALSE AS BOOLEAN), CAST(NULL AS BOOLEAN)) B (V)` | FALSE, TRUE, **TRUE** | FALSE, TRUE, NULL |
| `SELECT 1 FROM (VALUES CAST(NULL AS BOOLEAN)) B (V) WHERE NOT V` | **1 row** | no row |
| `SELECT K FROM VB WHERE NOT (V) ORDER BY K` | 2, **3** | 2 |
| `SELECT K FROM VB WHERE V` | 1 | 1 |
| `SELECT K FROM VB WHERE V = FALSE` | 2 | 2 |
| `SELECT K FROM VB WHERE NOT (V = TRUE) ORDER BY K` | 2 | 2 |
| `SELECT CASE V WHEN TRUE THEN FALSE WHEN FALSE THEN TRUE END FROM VB ORDER BY K` | FALSE, TRUE, NULL | FALSE, TRUE, NULL |
| `SELECT K FROM VB WHERE CASE V WHEN TRUE THEN FALSE WHEN FALSE THEN TRUE END` | 2 | 2 |
| `SELECT (NOT V) IS NULL FROM (VALUES CAST(NULL AS BOOLEAN)) B (V)` | SQL0199 | |

Comparisons (`V = FALSE`, `NOT (V = TRUE)`) are three-valued as expected;
only NOT applied directly to a BOOLEAN value is affected. System: PUB400,
IBM i 7.5 (`SYSIBMADM.ENV_SYS_INFO`); the **TR level and Db2 PTF Group level
cannot be read** there by a normal user (`QSYS2.GROUP_PTF_INFO`: SQL0443 "not
authorized to command WRKPTFGRP"; `QSYS2.PTF_INFO`: SQL0443 "not authorized to
use QSYS/DSPPTF"; probe `sysinfo`). This may be an IBM defect fixed by a
later PTF: rerun `nox -s probe -- queries` (area boolean) on a system with
known levels before relying on it; the backend's CASE form is correct either
way (DECISIONS.md, 2026-10-19).

**Untyped markers and NULL.** `WHERE ? > ?` with two untyped markers
(parameters 2 and 1) is accepted but **returns no row** (wrong, silently);
`WHERE CAST(? AS INTEGER) > ?` is correct. The backend therefore never
emits a comparison with untyped markers on both sides (rule in
docs/DECISIONS.md; guarded by `tests/offline/test_typed_markers.py` and a
pub400 test). A bare `NULL` as an expression
is rejected: `WHERE NULL IS NULL` fails with SQL0206 ("column or global
variable NULL not found").

**NULL ordering.** NULLs sort as the largest value (last ascending, first
descending). `NULLS FIRST` / `NULLS LAST` are rejected (SQL0199).
Django's emulation `ORDER BY X IS NOT NULL, X` works, **except with
`SELECT DISTINCT`**: then every `ORDER BY` expression must also be in the
select list; a predicate or a `CASE` that is not selected fails with
SQL0214 ("ORDER BY expression is not valid"). Selecting the predicate as
well (`SELECT DISTINCT X, X IS NOT NULL ... ORDER BY X IS NOT NULL, X`)
works, **but not when the expression contains parameter markers**: then the
ORDER BY expression never matches the selected one, even with identical
text (SQL0214 on the backend's connection; "Internal driver error" (30101)
on the probe's connection), typed or untyped markers alike. Ordering by
select-list positions (`ORDER BY 2 ASC, 1 ASC`) works with markers, `DESC`
and `FETCH FIRST`; BOOLEAN sorts FALSE before TRUE (used by `compiler.py`).

**Regular expressions.** `REGEXP_LIKE(value, pattern)` works with a constant
or a typed marker as pattern, with flag `'i'`, and with backreferences
(`'^(ab)\1$'`). It is a predicate (IBM i 7.5 SQL reference: ICU regular
expressions; flags `c`, `i`, `m`, `n`/`s`, `x`; pattern at most 32K; any
NULL argument gives unknown). An untyped marker works as pattern, but takes
the job CCSID (273): an emoji in it fails with 22018 (`CWBNL0107`); a typed
marker `CAST(? AS NVARCHAR(16370))` works (used by `regex_lookup()`). An
INTEGER source is converted implicitly (`REGEXP_LIKE(X, '^2$')` matches 2);
NULL never matches, also not `'^$'`; the `i` flag folds non-ASCII letters
(`ÜBER` matches `^über$`).

A predicate also works in GROUP BY (`GROUP BY X < 2`), and `NOT (X < 2)`
and `CASE WHEN X < 2 THEN TRUE ELSE FALSE END` work in the select list.

**LIKE on a TIMESTAMP column** is rejected (SQL0414, "Operand not valid in
LIKE predicate"; Django's `lookup` test `test_lookup_date_as_str`):
`supports_date_lookup_using_string` stays off (as on MySQL).

**Arithmetic.** Integer division truncates toward zero (`7 / 2` = 3,
`-7 / 2` = -3, also for typed markers); `MOD(-7, 3)` = -1; `POWER` returns
DOUBLE (`POWER(2, 10)` = 1024.0); `BITAND`, `BITOR`, `BITXOR`, `BITNOT`
work; DECIMAL + DOUBLE gives DOUBLE.

**Strings.** `CONCAT` and `||` with NULL give NULL. `LIKE CAST(? AS
NVARCHAR(n)) ESCAPE '\'` works with escaped `%` / `_`. `UPPER` of a marker
`'straße'` gives `'STRAßE'` (no expansion of `ß`).

**LOB values.** `NCLOB` values (derived tables), a stored `DBCLOB` column
(`QSYS2.SYSPACKAGESTMTSTAT.STATEMENT_TEXT`, empty result, the statements
compile) and a stored `BLOB` column (`QSYS2.SYSVARIABLEDEP.PARM_SIGNATURE`)
are **accepted in `ORDER BY`, `GROUP BY` and `DISTINCT`**, and in `UNION`
(which implies DISTINCT). `NCLOB = NCLOB`, `NCLOB = ?` (untyped and typed
marker), `NCLOB LIKE ?`, `UPPER(NCLOB)` and `NCLOB IN (subquery)` work. (The
expected restriction on LOBs in these clauses does not apply on 7.5.)

**Aggregates.** `STDDEV`/`STDDEV_SAMP`, `VARIANCE`/`VAR_SAMP` (DOUBLE),
`COUNT(DISTINCT)`, `ANY_VALUE`, `LISTAGG(...) WITHIN GROUP (ORDER BY ...)`
work; `AVG` of INTEGER returns INTEGER (`AVG(3, 1, 2)` = 2). `BIT_AND` does
not exist (SQL0204). `FILTER (WHERE ...)` is rejected (SQL0104). An
aggregate over no rows gives NULL (`COUNT` 0); `COALESCE(SUM(...), CAST(?
AS INTEGER))` works. `COUNT(NULL)` (untyped) fails with SQL0171;
`COUNT(CAST(NULL AS INTEGER))` gives 0.

**Temporal.** `TIMESTAMP - TIMESTAMP` gives a DECIMAL duration
(`1013000.000001` = 1 day 1 h 30 min 0.000001 s as `yyyymmddhhmmss.ffffff`);
`TIMESTAMPDIFF(1, CHAR(<duration>))` gives microseconds; `TIMESTAMP + n
MICROSECONDS` works; a DATE compared with a string constant works.

**Parameter markers.** 8192 typed markers in one statement are accepted;
10000 fail with SQL0101 ("statement too long or complex", at prepare).

### LISTAGG, for StringAgg (`probe -- listagg`)

Run 2026-10-18 on PUB400 (IBM i 7.5), read-only (VALUES and a recursive
common table expression).

- **Result type follows the argument:** VARCHAR(4000) for a VARCHAR, 2000
  characters for an NVARCHAR, a LOB of 1M (1048576) characters for an NCLOB
  or CLOB argument (also NCLOB(1K)).
- **Too long a result is an error, not truncation:** SQL0802 ("Data conversion
  or data mapping error"), at fetch or execution: from 4003 characters for
  VARCHAR/NVARCHAR arguments, and from about 1048576 characters with an NCLOB
  argument (1000999 characters work, 1049047 fail). `ON OVERFLOW TRUNCATE`
  is accepted and truncates instead, ending in `...(<omitted count>)`;
  `ON OVERFLOW ERROR` is accepted too.
- **Separator:** an untyped string constant (`','`) fails with SQL0171
  ("Argument 02 of function LISTAGG not valid") once the NCLOB argument is
  8K or longer; a typed marker `CAST(? AS NVARCHAR(32))` works with every
  NCLOB length up to NCLOB(1M).
- **WITHIN GROUP ordering:** an expression with a typed marker, an NVARCHAR
  sort key with an NCLOB argument, DISTINCT, and the full StringAgg form
  (filter CASE, typed separator, NULL-safe CASE) work. A predicate is not
  valid there: Django's NULL ordering emulation `<expr> IS NULL, <expr>`
  fails with SQL0199 ("Keyword IS not expected"); a sort key `CASE WHEN
  <expr> IS NULL THEN 0 ELSE 1 END` works. (Added 2026-10-18.)
- `DISTINCT`, `WITHIN GROUP (ORDER BY ... DESC)`, a `CASE` argument (Django's
  filter emulation) and non-ASCII values (as parameters) work; NULL values are
  skipped; an NCLOB argument works with DISTINCT and WITHIN GROUP.
- **NULL over no values is fetched as an empty string.** `LISTAGG` over no
  rows is NULL in Db2 (`IS NULL` is true, `COALESCE` takes the default,
  `LENGTH` is NULL), but the IBM i Access ODBC driver returns `''` when it is
  fetched as the only column (also with a second non-NULL column, but not
  with a second NULL column). With only NULL values the result is fetched as
  NULL. `CASE WHEN COUNT(<arg>) = 0 THEN NULL ELSE LISTAGG(...) END` and
  `NULLIF(LISTAGG(...), '')` are fetched as NULL; one empty string value
  gives a non-NULL `''`, so the CASE form keeps it while NULLIF would not.

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

### Reading a library's journaling state (`probe -- library_journal`)

2026-10-24, PUB400 (IBM i 7.5), read-only: only catalog services, nothing
created, also not in QTEMP. Run on the `default` and `other` libraries, a
library that does not exist (`DJDB2INONE`) and `QTEMP`. Raw result:
`probes/results/library_journal.json`. For the system check
`django_db2_for_i.W001` (validation.py, `bin/doctor`).

| Library | `LIBRARY_INFO`: `JOURNALED` / `INHERIT_JOURNALING` | `QSQJRN` (`OBJECT_STATISTICS`) | `QDFTJRN` |
|---|---|---|---|
| `default`, `other` | `NO` / `NO`, journal columns null | yes | no |
| does not exist | no row | no row | no row |
| `QTEMP` | `NO` / `NO` | no row | no row |

- **The library's own journaling state** (STRJRNLIB) is in
  `QSYS2.LIBRARY_INFO(LIBRARY_NAME => ..., DETAILED_INFO => 'NO')`: `JOURNALED`,
  `JOURNAL_LIBRARY`, `JOURNAL_NAME` and `INHERIT_JOURNALING` (IBM docs: whether
  new journal-eligible objects inherit journaling from the library, by its
  inherit rules). `DETAILED_INFO => 'NO'` skips the library size. It needs
  `*READ` authority to the library.
- **A library that does not exist** gives no row and no error, both with and
  without `IGNORE_ERRORS => 'YES'`; `OBJECT_STATISTICS` on it gives no row either.
  Parameter markers worked in every query here; the check still uses the
  validated name as a literal (a failing service with parameters poisons the
  connection, `drivers/pyodbc.py`).
- **Every query takes about 0.1 s**, also the combined query the check runs
  (`LIBRARY_INFO` with a scalar subquery on `OBJECT_STATISTICS` for `QSQJRN`).
- **Files already in the libraries:** only the six SQL catalog views
  (`SYSCHKCST`, `SYSCST`, `SYSCSTCOL`, `SYSCSTDEP`, `SYSKEYCST`, `SYSREFCST`;
  `LF`, `VIEW`), which `OBJECT_STATISTICS` shows as journaled to
  `QRECOVERY/QDBJRNFILE`. `QSYS2.JOURNALED_OBJECTS` lists only the receiver for
  `QSQJRN`, which matches: no test tables were left.
- **Not probed:** a library journaled with `STRJRNLIB` (that changes a library
  and would need a `lib_` probe). That new tables then journal to the
  library's journal by its inherit rules is from IBM's STRJRNLIB documentation
  (default `INHRULES`: all object types, all operations, `*INCLUDE`).

## String encoding investigation (`nox -s probe_encoding`)

2026-10-17, PUB400 (IBM i 7.5, job CCSID 273), `probe_encoding`: one
connection per variant, strictly sequential, only `SESSION.x` / `QTEMP`
tables (and a job-level QAQQINI copy in QTEMP for one variant). Every
variant uses the backend's connection keywords and changes one variable;
each runs the same checks for the three findings:

- **A**: non-ASCII characters in statement text fail with `HY001`
  "Memory allocation error" (found by `probe_defaults`).
- **B**: `DEFAULT 'O''Brien'` is stored as `O''Brien` (NVARCHAR) or garbled
  (CHAR/VARCHAR) (found by `probe_defaults`).
- **C**: string parameters bound as LOB lose one character from 8185
  characters on (found by `probe -- string_limits`).

### Step 1: the current situation

- Client: pyodbc **5.3.0**, IBM i Access ODBC Driver `libcwbodbc.so`
  **07.01.029** (package `ibm-iaccess` 1.1.0.29), ODBC 3.51, unixODBC from
  Debian. Server `SQL_DBMS_VER` 07.05.0015.
- Server job: `CCSID` = 273, `DEFAULT_CCSID` = 273 (`QSYS2.ACTIVE_JOB_INFO`).
- Process locale in the container: `LANG`/`LC_ALL` unset (POSIX), but
  Python coerces the C locale (PEP 538): `LC_CTYPE=C.UTF-8`, codeset UTF-8.
- The backend calls neither `setencoding()` nor `setdecoding()`, and sets no
  `CCSID` or `UNICODESQL` keyword. pyodbc's defaults (source,
  `connection.cpp`): `str` is encoded as UTF-16LE with `SQL_C_WCHAR`, and
  `SQL_CHAR`, `SQL_WCHAR` and metadata are read as `SQL_C_WCHAR` (UTF-16LE).
- **Statement text**: pyodbc calls `SQLExecDirectW` (no parameters) or
  `SQLPrepareW` (with parameters) when the `str` encoding's ctype is
  `SQL_C_WCHAR`, and `SQLExecDirect` / `SQLPrepare` (bytes) when it is
  `SQL_C_CHAR` (`cursor.cpp`, `params.cpp`). Default: the `W` functions.
- **String parameters**: pyodbc binds a `str` as `SQL_WVARCHAR` with the
  whole value if its encoded size in **bytes** is at most the
  `COLUMN_SIZE` that `SQLGetTypeInfo(SQL_WVARCHAR)` reports. Otherwise it
  binds `SQL_WLONGVARCHAR` as data-at-execution and sends the value with
  `SQLPutData` in chunks of that same size (`params.cpp`). pyodbc does not
  ask the driver for the parameter's target type (no `SQLDescribeParam`), so
  the earlier note in "Long strings" that the binding follows the target is
  wrong. The driver reports `COLUMN_SIZE` **16369** for `SQL_WVARCHAR`
  (`VARGRAPHIC() CCSID 13488`), 32739 for `SQL_VARCHAR` and `SQL_VARBINARY`.
  `Connection.maxwrite` (0 by default) replaces these limits when it is set.

### Step 2: variants and results

**Correction (2026-10-17, during fix A):** the first runs below used pyodbc's
default `pyodbc.pooling = True`. The backend connects with pooling **off**
(`drivers/pyodbc.py`), and with pooling off finding A looks different: see
"Step 2 repeated with pooling off" after this table. B and C are the same
either way. Kept for the record:

| Variant (pooling on) | A (statement text) | B (DEFAULT `'O''Brien'`) | C (LOB > 8184 chars) |
|---|---|---|---|
| base (pyodbc defaults) | HY001 for every non-ASCII character, also in a comment or an alias; an emoji literal returns `'=\x00'` | wrong | loses characters |
| `UNICODESQL=1` | same as base | wrong | loses |
| `CCSID=1208` | same as base | wrong | loses |
| `UNICODESQL=1;CCSID=1208` | same as base | wrong | loses |
| `CCSID=1200` | every statement fails, also ASCII ones: SQL0104 with a garbled message | - | - |
| `LC_ALL=C.UTF-8` | same as base | wrong | loses |
| QAQQINI `SQL_TRANSLATE_ASCII_TO_JOB` = `*YES` (job copy, value read back) | same as base | wrong | loses |
| `setencoding("utf-8", SQL_CHAR)` | no error; characters in CCSID 273 correct (`é`), others silently SUB (`€`, emoji) | wrong | ok for ASCII text; multi-byte text fails with 22018 at chunk boundaries |
| utf-8 / `SQL_CHAR` + `CCSID=1208` | same as the previous row | wrong | as the previous row |
| utf-8 / `SQL_CHAR` + `UNICODESQL=1` | **correct** (`é`, `€`, emoji in literals, comments, aliases) | wrong | as the previous row |
| utf-8 / `SQL_CHAR` + `UNICODESQL=1`, `LC_ALL=C` (no PEP 538 coercion) | **silent mojibake** in statement text *and* parameters (`é€` -> `Ã©â‚¬`) | wrong | lengths wrong (bytes counted as characters) |
| utf-8 / `SQL_CHAR` + `UNICODESQL=1` + `CCSID=1208`, `LC_ALL=C` | **correct** | wrong | as with UTF-8 above |
| `maxwrite` = 1 GiB (W path or UTF-8 path) | - | - | **correct** for every target and length |

C binding modes tried on the base variant (characters seen by the server
for 8184 / 8185 / 8186 / 16370 / 24555 / 32768 characters sent):

| Binding | `NCLOB(1M)`, `DBCLOB(1M)`, `CLOB(1M) CCSID 1208` | `NVARCHAR(16370)` |
|---|---|---|
| default | 8184 / 8184 / 8185 / 16369 / 24553 / 32766 | intact |
| `maxwrite` = 1 GiB | intact | intact |
| `setinputsizes` `SQL_WVARCHAR(n)` | as default | intact |
| `setinputsizes` `SQL_WLONGVARCHAR(n)` | as default | intact |
| `setinputsizes` `SQL_WLONGVARCHAR(0)` (data-at-execution) | as default | intact |

Multi-byte texts (`é`, `€`, emoji repeated 8185 to 20000 times) through
`NCLOB(1M)`: default binding on the W path loses one character per broken
chunk, and emoji texts come back as invalid UTF-16 (a lone surrogate was
stored); default binding on the UTF-8 path fails with `22018` for `é` and
emoji (`€` is 3 bytes, and 32739 = 3 x 10913, so it never splits). With
`maxwrite` every text round-trips on both paths. Writing into a QTEMP table
(`NCLOB(1M)`, `BLOB(1M)`, 8184 to 70,000 characters/bytes) and reading back
gives the same picture; BLOB values are always intact. The read path is
intact: a 40,000-character NCLOB built on the server reads back complete.

### Step 2 repeated with pooling off (the backend's setting)

`probe_encoding` now sets `pyodbc.pooling = False` like the backend; all
variants rerun, plus `UNICODESQL=1` under `LC_ALL=C` and the planned fix
(`fix_a`: `setencoding("utf-8", SQL_CHAR)` only, pyodbc's default decoding,
`UNICODESQL=1`, `CCSID=1208`, `maxwrite`). Statement text checks: `'é'`,
`N'é€'`, `N'😀'` literals, comments, aliases; read and metadata checks:
values written with `UX'...'` and with parameters into `VARCHAR(20)` (job
CCSID 273), `CHAR(10)`, `NVARCHAR(20)`, `NCLOB(1K)` and read back, result
column name `"ÄÖÜ"`, error message for `QTEMP."ÄÖÜX"`.

| Variant (pooling off) | A: `N'é€'` / `N'😀'` | Column name / error message |
|---|---|---|
| base (the backend before this fix) | **silently** `'é\x1a'` / `'=\x00'`: converted to job CCSID 273 (`é` survives, `€` becomes SUB, emoji garbage); no HY001 | correct |
| `CCSID=1208`, `LC_ALL=C.UTF-8`, QAQQINI | same as base | correct |
| `CCSID=1200` | the process crashes (segmentation fault) | - |
| `UNICODESQL=1` (W path) | `'é€'` correct / emoji **silently** `'=\x00'` (IBM documents UNICODESQL as UCS-2) | correct |
| `UNICODESQL=1` + `CCSID=1208` (W path) | as `UNICODESQL=1` | correct |
| `UNICODESQL=1`, `LC_ALL=C` (W path) | `'é¬'` / HY001 | error message garbled |
| utf-8 / `SQL_CHAR` | `'é\x1a'` / `'\x1a'` (job CCSID 273) | correct |
| utf-8 / `SQL_CHAR` + `UNICODESQL=1` | **correct** / **correct** | correct |
| utf-8 / `SQL_CHAR` + `UNICODESQL=1`, `LC_ALL=C` | mojibake in statement text and parameters | statements fail |
| utf-8 / `SQL_CHAR` + `UNICODESQL=1` + `CCSID=1208`, `LC_ALL=C` | **correct** / **correct** | garbled |
| **`fix_a`** | **correct** / **correct** | correct |

In every variant: parameters `'éÄß'` round-trip through all four column
types; a parameter with a character CCSID 273 cannot hold (`€`, emoji)
into `VARCHAR`/`CHAR` fails with `22018` (`CWBNL0107`) instead of being
replaced, while a `UX'...'` constant is stored with SUB; reading
`NVARCHAR`/`NCLOB` values with emoji is correct; `"EURO€"` as an identifier
is rejected by the server (SQL0104; identifiers must fit the job CCSID).
`COMMENT ON ... IS '<text>'` (pub400 tier, fix A): text in the job CCSID is
stored correctly, quotes included (`Grüße, O''Brien` reads back as
`Grüße, O'Brien`); with `€` or an emoji the server treats the constant as a
graphic constant (its message shows it as `UX'...'`) and rejects it with
SQL0104, valid token `<CHARSTRING>`; `UX'...'` itself is rejected the same
way. C
is unchanged (`maxwrite` needed on both paths). With pooling **on**, result
column names and error messages with non-ASCII characters come back garbled
on the UTF-8 path even in a UTF-8 locale; the backend never enables pooling.

B in more forms, all with the same wrong result in every variant: `CREATE
TABLE QTEMP.x` (not only declared temporary tables), and `ALTER TABLE ...
ADD COLUMN ... DEFAULT 'O''Brien'`. The same constant in `SELECT` and in
`INSERT ... VALUES` is correct (`O'Brien`, length 7).

### Conclusions

- **C, root cause found (pyodbc).** pyodbc compares the parameter's size in
  bytes with `SQLGetTypeInfo`'s `COLUMN_SIZE`, which is in characters, and
  uses that number as the `SQLPutData` chunk size. The driver reports 16369
  for `SQL_WVARCHAR`, so strings of 8185 characters or more (over 16369 bytes) are sent
  in 16369-byte chunks: odd, so every second chunk boundary splits a UTF-16
  unit. For LOB targets the driver drops the split unit (or stores half a
  surrogate pair); `NVARCHAR` targets reassemble it. The loss counts match
  exactly: one per odd boundary (8185 and 16370 characters: 1; 24555 and
  32768: 2; 70,000: 4). On the UTF-8 path the chunks are 32739 bytes and
  split multi-byte characters (22018). **Fix**: set `Connection.maxwrite`
  high enough that pyodbc never uses data-at-execution; every value is then
  bound in one buffer.
- **A, the driver's wide-character statement path.** With the backend's
  settings (pooling off), `SQLExecDirectW` / `SQLPrepareW` silently convert
  statement text to the job CCSID (273): characters outside it become SUB
  or garbage, without an error. (HY001 occurs only with pyodbc pooling on,
  as in the first probe runs.) `UNICODESQL=1` on the W path fixes BMP
  characters but still garbles characters outside the BMP (emoji), as IBM
  documents it as UCS-2. The narrow path works:
  pyodbc `setencoding("utf-8", SQL_CHAR)` sends UTF-8 bytes through
  `SQLExecDirect`/`SQLPrepare`; `UNICODESQL=1` makes the driver send the
  statement to the server as Unicode (without it the statement is converted
  to the job CCSID 273 and characters outside it silently become SUB); and
  `CCSID=1208` fixes the driver's client codepage to UTF-8 (without it the
  driver takes the codepage from the process locale, and a non-UTF-8 locale
  silently corrupts statement text and string parameters). **Fix**: all
  three together. Note that `setencoding` also changes how `str`
  parameters are sent (UTF-8 `SQL_C_CHAR`), which the probe verified.
  Result column names and error messages are decoded correctly in a UTF-8
  process locale (Python's default, PEP 538); in a non-UTF-8 locale
  (`LC_ALL=C`) they are garbled, also on the W path.
- **B, no fix found on the client.** Identical for EBCDIC statement text
  (W path), UTF-8 and Unicode statement text, declared temporary and regular
  tables, `CREATE TABLE` and `ADD COLUMN`, and for job CCSID 273 and 37
  (`probe_job_ccsid`, below). It is server-side handling of an escaped quote
  in a column DEFAULT. The `UX'...'` constants stay.

### Next steps

1. Driver fix for C: `maxwrite`, the 8184-unit guard replaced by a 1M-unit
   limit (done, PR #18).
2. Driver fix for A: `setencoding("utf-8", SQL_CHAR)` + `UNICODESQL=1` +
   `CCSID=1208` as driver defaults; `setdecoding` stays at pyodbc's
   defaults (the checks above need nothing else).
3. B: keep `UX'...'` (decided by the project owner).

### Non-UTF-8 process locale (`nox -s probe_locale`)
2026-10-17, one connection per locale opened by the backend itself (Django
settings `settings_pub400`, the real driver defaults), QTEMP only.

| Check | Default locale (C.UTF-8) | `LC_ALL=C` (ASCII) |
|---|---|---|
| Data values: `N'é€😀'`, `'éÄß'` literals; parameters and literals into `VARCHAR(10)` (CCSID 273), `NVARCHAR`, `NCLOB`, read back | correct | **correct** |
| Result column name `"ÄÖÜ"` | correct | `'Ã\x84Ã'` |
| Error message for `QTEMP."ÄÖÜX"` | correct | garbage (what looks like uninitialized memory) |
| ... with `setdecoding(SQL_WMETADATA, encoding="utf-8")` | `UnicodeDecodeError`; pyodbc fails to build the error (`SystemError`) | same |
| ... with `setdecoding(SQL_WMETADATA, encoding="latin-1")` | garbled (`'Ä\x00Ö'`) | garbled |

Not fixable on the client: the driver returns the text already broken. The
pyodbc driver logs a warning at the first connection when the process
locale's codeset is not UTF-8.

### Job CCSID and finding B (`nox -s probe_job_ccsid`)
2026-10-17, approved by the project owner: one connection, QTEMP tables and
the probe's own job only. The probe read the job CCSID first (273, default
273; it refuses to change anything if that is not readable), ran the B
checks, ran `CHGJOB CCSID(37)` (read back: 37, 37), ran the B checks again,
and set the CCSID back (read back: 273, 273).

| Column | Job CCSID 273 | Job CCSID 37 |
|---|---|---|
| `NVARCHAR(20) DEFAULT 'O''Brien'` | `O''Brien` | `O''Brien` |
| `VARCHAR(20) DEFAULT 'O''Brien'` | `O'Brie ` | `O'Brie n` |
| `CHAR(10) DEFAULT 'O''Brien'` | `O'Brie n  ` | `O'Brie n  ` |
| `INSERT ... VALUES ('O''Brien')` (all three) | correct | correct |

Same for a regular `QTEMP` table and `ADD COLUMN`. The job CCSID changes
only how the VARCHAR value is garbled, not whether: B does not depend on
the job CCSID either. (The driver keeps converting statement text to the
CCSID it saw at connect, 273; the statements are ASCII only, and those
characters have the same code points in 273 and 37.)
