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
  into real columns is covered by probe `lib_commitment.py`.

### Commitment control on an unjournaled table, Unicode columns (`probe_write`)
Approved by the project owner and run 2026-10-17 00:01 UTC with
`lib_commitment.py` against `<USER>B` (no `QSQJRN`). Connection `NAM=0`,
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
`lib_autocommit.py` on a journaled table in `<USER>2` (`DJAUTOC (ID INTEGER NOT
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
  DECISIONS.md (NVARCHAR decision). Verified in phase 4: the limit is 32,766
  bytes ("ALTER TABLE, renames, indexes and row length" below); the driver's
  value is not used.
- Repeated 2026-10-17 08:16 UTC after the first Django run (`nox -s pub400`,
  Django `connection.cursor()` with new statement texts and parameter
  markers, `XDYNAMIC=0`): **no `*SQLPKG` objects** owned by the user or in
  the test libraries. This is the confirmation promised above.

### Operations behaviour (`probe_operations`)
Run 2026-10-17 08:31 UTC with `lib_operations.py` on two temporary tables in
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
`lib_sequence.py` on a sequence and two tables in `<USER>2` (journaled), all
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
Requested by the project owner; run 2026-10-17 12:11 UTC with `lib_drop.py`
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
  None of its 49 rows controls inquiry messages (only `MESSAGES_DEBUG`
  mentions messages). **Corrected 2026-10-25:** the copy only lists rows
  that are set; IBM documents the option `SUPPRESS_INQUIRY_MESSAGES`, and it
  works for our profile (next section).
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

### CPA32B2 suppressed per job: QAQQINI `SUPPRESS_INQUIRY_MESSAGES` (`probe -- qaqqini_inquiry`)
2026-10-25, PUB400 (IBM i 7.5), two runs, QTEMP and the probe's own job
only (result: `probes/results/qaqqini_inquiry.json`).

**IBM's documentation:**
- QAQQINI query options table, 7.5 and 7.6 ("Specifies that certain inquiry
  messages will not be issued"):
  - `*DEFAULT` = `*NO`;
  - `*YES`: "System inquiry message CPA32B2 will not be issued when altering
    a table";
  - `*NO`: "No system inquiry messages will be suppressed."

  Sources: https://www.ibm.com/docs/en/ssw_ibm_i_75/rzajq/qryopt.htm and
  https://www.ibm.com/docs/en/ssw_ibm_i_76/rzajq/qryopt.htm.
- IBM support "Add SUPPRESS_INQUIRY_MESSAGES"
  (https://www.ibm.com/support/pages/add-suppressinquirymessages): it "has
  been added to avoid getting the CPA32B2 inquiry message from an Alter
  table statement".
- Availability (Db2 for i DBE Enhancements,
  https://www.ibm.com/support/pages/db2-i-database-engineer-dbe-enhancements):
  - the option: 7.5 and 7.6 base, 7.4 SF99704 level 4;
  - `OVERRIDE_QAQQINI`: 7.5 and 7.6 base, 7.4 SF99704 level 7.
- IBM uses the option itself. IBM i 7.6 TR1, ACS Schemas
  (https://www.ibm.com/support/pages/ibm-i-76-tr1-enhancements): its Table
  Definition dialog uses it "when dropping columns (instead of requiring
  authority to the CHGRPLYE command)".
- `QSYS2.OVERRIDE_QAQQINI`
  (https://www.ibm.com/docs/en/i/7.5?topic=services-override-qaqqini-procedure):
  - operation 1 creates the job's temporary QAQQINI in QTEMP, which
    "inherits all query options that are already in place for the job";
  - operation 2 sets one option;
  - operation 3 discards the copy and reverts "to using the job's version of
    the QAQQINI file".
  - Authority: "For most QAQQINI options, none is required". `*JOBCTL` or
    QIBM_DB_SQLADM is only needed for QUERY_TIME_LIMIT, STORAGE_LIMIT,
    PARALLEL_DEGREE and PARALLEL_MAX_SYSTEM_CPU.

**On PUB400:**
- **Our profile:** no special authorities, group profile `*NONE`.
  `OVERRIDE_QAQQINI(1, '', '')` and
  `(2, 'SUPPRESS_INQUIRY_MESSAGES', '*YES')` both succeed. The row then
  reads back as `*YES` in `QTEMP.QAQQINI`.
- **Before the override:** neither QTEMP nor QUSRSYS has a QAQQINI, so the
  job ran on the defaults. After it, the copy has no row other than this
  option that is not `*DEFAULT`. So the job's other query options stay as
  they were.
- **Outside QTEMP:** the only new object is `QTEMP/QAQQINI *FILE`. The two
  test libraries are unchanged (object lists compared before, during and
  after).
- **Baseline and with the override,** each on a one-row QTEMP table:

  | Change | Without the override | With the override |
  |---|---|---|
  | `DROP COLUMN` | `HY008` (CPD32CE) | done (job log CPC2955) |
  | `SET DATA TYPE` INTEGER -> SMALLINT, the value fits | `HY008` | done |
  | `SET NOT NULL`, no NULLs | `HY008` | done |

- **With the override, data that does not fit:**

  | Change | Result | Rows afterwards |
  |---|---|---|
  | INTEGER -> SMALLINT, a value 100000 | **SQL0406** (`22018`), not changed | unchanged |
  | `SET NOT NULL`, a NULL row | **SQL0407** (`23000`), not changed | unchanged |
  | VARCHAR(10) -> VARCHAR(3), a value `abcdef` | **done**, warning SQL0460 only | `abcdef` is now `abc` |
  | DECIMAL(9, 4) -> DECIMAL(9, 2), a value 1.2345 | **done**, warning SQL0460 only | `1.2345` is now `1.23` |

  So the option is not a reply "only if nothing is lost":
  - numbers that do not fit and NULLs are still refused;
  - strings are truncated and decimals rounded silently.

  This is the same CPA32B2 that a reply list entry with `RPY('I')` answers,
  so the `inquiry_message_reply` path is assumed to behave the same. That
  path was not measured here, because PUB400 has no such entry.
- **After `OVERRIDE_QAQQINI(3, '', '')`:** the three changes are cancelled
  with `HY008` again, and QTEMP has no QAQQINI.
- **Not measured** (QTEMP has no journal): the option inside commitment
  control (`atomic` migrations) on a journaled table, and on a reused
  prestart job.

### OVERRIDE_QAQQINI around transactions, and how narrowing measures (`probe -- qaqqini_lifecycle`)
2026-10-26, PUB400 (IBM i 7.5), QTEMP and the probe's own job only, under
commitment control (isolation `*CS`). The result is in
`probes/results/qaqqini_lifecycle.json`.

- **Repeated and unpaired calls:**
  - operation 3 without a copy succeeds;
  - operation 1 twice succeeds (the copy stays);
  - operation 3 twice succeeds.
- **Not transactional:**
  - operations 1 and 2, then ROLLBACK: the copy and its `*YES` stay, and a
    DROP COLUMN afterwards goes through;
  - operation 3, then ROLLBACK: the copy stays gone, and DROP COLUMN is
    cancelled (HY008) again.

  So the suppression is ended explicitly, after the transaction, and
  operation 3 can run whenever operation 1 may have run.
- **`LENGTH` counts in the column's units:**

  | Value | NVARCHAR | VARCHAR CCSID 1208 | NCLOB |
  |---|---|---|---|
  | `abc` | 3 | 3 | |
  | an emoji (U+1F600) | 2 | 4 | |
  | `é` | 1 | 2 | |
  | `a` + an emoji | | | 3 |

- **CAST to fewer decimals or to an integer truncates:**
  - DECIMAL 1.2355 → (9, 2) gives 1.23, and -1.2355 gives -1.23;
  - DECIMAL 2.7 → INTEGER gives 2, and so does DOUBLE 2.7;
  - DOUBLE 0.29 → DECIMAL(5, 2) gives **0.28**, because the double nearest
    0.29 is just below it.
- **An overflowing CAST gives NULL, not an error:** DECIMAL 999.99 →
  DECIMAL(4, 2) returned NULL. A check like `col <> CAST(col AS ...)` would
  miss it, so the backend checks the range first.

### SQL0910 comes from changed rows only (`lib_pending_change`)
2026-10-26, PUB400 (IBM i 7.5), approved on issue #173. One table,
`DJPRB910 (ID INTEGER NOT NULL PRIMARY KEY, C INTEGER)`, in the journaled
default library, on the cleanup list before each `CREATE` and dropped at the
end (none left). CPA32B2 suppressed as in a migration (QTEMP copy of QAQQINI,
discarded at the end). The result is in `probes/results/lib_pending_change.json`.

Each step ran with autocommit off on a fresh table with three rows without
NULLs, then rolled back. The `UPDATE` and the `ALTER` are the statements of
golden `ddl/alter_field_not_null`:

| Step | Before `ALTER COLUMN "C" SET NOT NULL` | `SET NOT NULL` |
|---|---|---|
| 1 (control) | a committed fourth row with C NULL; `UPDATE ... WHERE "C" IS NULL` changes 1 row | **SQL0910** (HY000) |
| 2 | `UPDATE ... WHERE "C" IS NULL` changes 0 rows | ok |
| 3 | `SELECT 1 ... WHERE "C" IS NULL FETCH FIRST 1 ROW ONLY` | ok |
| 4 | `LOCK TABLE ... IN EXCLUSIVE MODE`, then the `SELECT` of step 3 | ok |

- Only a row that was really changed is a pending change. An `UPDATE` that
  matches no rows, a read, and an exclusive lock leave none.
- So Django's null → not-null with a default already works in an atomic
  migration when the column holds no NULLs: SQL0910 only hits tables that
  really contain NULLs. Skipping the `UPDATE` after a NULL check would change
  nothing.
- Every rollback undid the `SET NOT NULL` (C nullable again).

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
  QTEMP; probe `lib_constraints` (w13) did it in the journaled library: they arrive with `HY000`
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
  with `IS_UNIQUE` `D` (duplicates allowed). The backend keeps creating its
  own index (decision 5), so a foreign key column does end up with an index:
  `indexes_foreign_keys` is True (amended 2026-10-25; Django reads it only in
  its tests).
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
- **With `supports_foreign_keys` on, every type-change path keeps the foreign
  keys enforced** (`SYSCST` `ENABLED` `YES`, a row without a parent refused
  with SQL0530), as migrations (`MigrationExecutor`): a primary key
  `AutoField` -> `BigAutoField` with an incoming foreign key; the same with a
  child whose primary key is a OneToOneField to the parent and a grandchild
  that refers to the child (Django changes the grandchild's column too and
  adds its foreign key again); a `to_field` target (a unique `CharField`) made
  wider; a foreign key moved to a parent with a different key type.
  Introspection (`get_constraints()`, `get_relations()`) reads only enforced
  foreign keys: one in the state of fact b is marked `"enforced": False`
  without `foreign_key`.

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
(`P24_A00001`). Probe `lob_index` (2026-10-26, QTEMP,
`probes/results/lob_index.json`): `BLOB`, `CLOB` and `DBCLOB` columns fail
the same way (SQL0350, HY000), and an `NVARCHAR` column of the same table is
indexed. The schema editor skips `db_index` on every LOB type.

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
`probes/qtemp_check_constraint_unjournaled.py` (named `qtemp_check_journal.py` until 2026-10-28; its published result keeps the old name, `probes/results/check_journal.json`). QTEMP tables cannot be journaled, so they
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
  probe `lib_commitment` ("Commitment control on an unjournaled table").
- Adding a CHECK that a row already violates fails with `SQL0544 - CHECK
  constraint ... cannot be added` (SQLSTATE `HY000`; the driver layer maps
  SQLCODE -544 to IntegrityError, as PostgreSQL reports such a check), and the
  table is unchanged (pub400 test `test_positive_field_to_integer_and_back`,
  journaled library).

### CHECK with LIKE against a column pattern: SQL0546 (Django `migrations`)
2026-10-26, PUB400 (IBM i 7.5), Django `migrations` on 6.1, 6.0 and 5.2, the
test libraries. `test_add_constraint_percent_escaping` and
`test_create_model_constraint_percent_escaping` add a CHECK constraint per
subtest, by `ALTER TABLE ... ADD CONSTRAINT` and in `CREATE TABLE`:

- `~Q(surname__startswith=F("name"))`, written as
  `CHECK (NOT ("SURNAME" LIKE REPLACE(REPLACE(REPLACE(("NAME"), '\', '\\'),
  '%', '\%'), '_', '\_') || '%' ESCAPE '\'))`, fails in both statements
  with `SQL0546 - CHECK condition of constraint CONSTRAINT not valid`
  (SQLSTATE `HY000`), on all three versions. Which rule of the CHECK
  condition it breaks (the column in the pattern, or REPLACE) was not
  probed: a constraint needs a journaled table, so that probe would be a
  `lib_` probe.
- Constant patterns pass (6.1 run, before the SQL0601 below):
  `LIKE 'Albert%' ESCAPE '\'`, `LIKE '%\%' ESCAPE '\'` and `= '%'`.

#### Unresolved: the constraint name "CONSTRAINT" refused with SQL0601
Since the 6.1 `migrations` run, every `ADD CONSTRAINT "CONSTRAINT"` and every
`CREATE TABLE` with a constraint of that name in the `default` test library
fails with `SQL0601 - CONSTRAINT in <library> type *N already exists`, also
when the test runs alone, on 6.1, 6.0 and 5.2. The same tests passed these
subtests earlier in that 6.1 run. Unexplained:

- A read-only probe (`probe -- leftovers`, 2026-10-27) found no object of that
  name: both libraries hold no tables, no constraints in `QSYS2.SYSCST`, and
  no rows for the name in `SYSCST`, `SYSCHKCST`, `SYSKEYCST`, `SYSCSTCOL` or
  `SYSCSTDEP` in any schema; `OBJECT_STATISTICS` shows only the journal and
  its receiver.
- **A guess, not verified:** an orphaned entry for the constraint in the
  system's database cross-reference files, which only a system administrator
  can repair (`RCLDBXREF`). No further action on PUB400.
- Effect: only the subtests named "constraint" of the two tests above; both
  are expected failures for SQL0546 anyway.

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
  come from the own tables of probe `lib_constraints` (w13) instead (see "Foreign keys, unique and
  check constraints"). The libraries' `SYSCOLUMNS` rows (126 columns) show
  `HAS_DEFAULT` `N`, `IS_IDENTITY` `NO`, `IS_NULLABLE` `Y` / `N`, and
  `DATA_TYPE` values `CHAR`, `INTEGER`, `SMALLINT`, `VARCHAR` and `VARG`
  (graphic varying, i.e. NVARCHAR).

### Column types in the catalog (`nox -s probe_column_types -- --execute`)
2026-10-23, PUB400 (IBM i 7.5), probe `lib_column_types` (w14) (approved 2026-10-23, step B
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

### inspectdb on tables created with plain SQL (`tests/pub400/test_inspectdb.py`)
2026-10-27, PUB400 (IBM i 7.5), Django 6.1: two tables created with plain
SQL in the marked test library (own IBM i test, on the cleanup list before
each `CREATE TABLE`, dropped at the end).

- `QSYS2.SYSCOLUMNS.DATA_TYPE` is **`NUMERIC`** for `NUMERIC(p, s)` and
  **`CLOB`** for `CLOB(n)`; neither type is written by the backend, so
  `data_types_reverse` had no entry and `inspectdb` wrote
  `TextField  # This field type is a guess.` for both. Mapped since step D:
  `NUMERIC` to `DecimalField` (precision and scale as for `DECIMAL`),
  `CLOB` to `TextField`.
- A `CHAR(30)` value `'Acme'` is fetched with its blanks (30 characters);
  `WHERE NAME = 'Acme'` matches it (Known Limitations, "inspectdb and
  existing IBM i tables").
- Primary key (`NUMERIC(7, 0)`, no identity), identity column, single-column
  `UNIQUE` and the foreign key come out as Django expects; a model generated
  with `managed = False` reads and writes the rows, also across the foreign
  key (`select_related`).

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
- **Not verified on PUB400: a library journaled with `STRJRNLIB`** (both test
  libraries use `QSQJRN`). The check W001 and, since #156, the test runner
  (`creation.py`) accept such a library when new objects inherit journaling
  and its journal is `*ACTIVE` in `QSYS2.JOURNAL_INFO`; that rests on IBM's
  documentation. Verifying it needs a `lib_` probe with the maintainer's
  approval.
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

### The flags once marked "later" (`probe -- later_flags`)
2026-10-28, PUB400 (IBM i 7.5), `probes/qtemp_later_flags.py` (#191, topic 3):
QTEMP only, one connection with the backend's attributes but without
commitment control (`CMT=0`; the first run with `CMT=1` got SQL7008 on every
row, QTEMP tables have no journal). Result: `probes/results/later_flags.json`.

| What | Statement | Outcome |
|---|---|---|
| `REAL` | `R REAL`, insert 1.5 | ok; described as float, precision 7; reads back `1.5` |
| `DECIMAL` without precision | `D DECIMAL` | `DECIMAL(5, 0)`: 12345 ok; 123456 `22003` (30160, out of range); 1.5 `22001` (30126, truncation) |
| `DECFLOAT(34)` | `Decimal` parameters | 34 significant digits round-trip exactly (`12345678901234567890.123456789`, `0.1`, `-1E-30`, `123456789012345678901234567890.1234`); `1E+300` refused at bind, `01004` (30002, "Data truncated"); values come back as `str` |
| `DECFLOAT(16)` | the same | rounded to 16 digits (`1.234567890123457E+19`), `1E+300` refused the same way |
| No length | `NVARCHAR`, `VARCHAR`, `VARGRAPHIC` | SQL0104 (`NVARCHAR`: "Token ) was not valid"), SQL0604 ("Attributes not valid") |
| `COLLATE` on a column | `UNICODE`, `"UCA500R1_LEN_S1"`, `UCA500R1_LEN_S1`, `SYSTEM` | SQL0104 "Token COLLATE was not valid"; after `CCSID 1200`: SQL0683 "Clause not valid for specified type" |
| Generated column over other columns | `GENERATED ALWAYS AS (A * 2)`, also `STORED`, `VIRTUAL`, `AS (A * 2)`, `AS (CAST(A AS BIGINT) + 1)` | SQL0104; the valid tokens are special registers (`USER`, `ACCTNG`, `APPLNAME`, `PROGRAMID`, `WRKSTNNAME`, ...) |
| Generated column, other forms | `AS (USER)`, `AS (DATA CHANGE OPERATION)`, row change timestamp, identity | ok, values `'<user>'`, `'U'` after an update, the timestamp, 1; `AS (CURRENT TIMESTAMP)`: SQL0104 |
| Materialized view | `CREATE MATERIALIZED VIEW` (Django's test) | SQL0104 "Token MATERIALIZED was not valid" |
| MQT over a QTEMP table | `CREATE TABLE ... AS (SELECT ... FROM QTEMP.x) DATA INITIALLY DEFERRED REFRESH DEFERRED MAINTAINED BY USER` | SQ20058 reason code 2 |
| MQT over `SYSIBM.SYSDUMMY1` | the same clauses | ok; `REFRESH TABLE` ok, one row; `SQLTables` lists no QTEMP object |
| Long names | table name of 129 / 128 characters | SQL0107 / ok |

**Consequences** (`docs/features.toml`):
- off: `supports_unlimited_charfield`, the three collation flags,
  `supports_stored_generated_columns`, `supports_virtual_generated_columns`,
  `supports_alter_generated_column_data_type`, and
  `can_introspect_materialized_views`, whose only effect is Django's
  `CREATE MATERIALIZED VIEW` test.
- `has_real_datatype`: phase 6 (introspection maps `REAL`).
- `truncates_names` (phase 5): the limit is 128, and `quote_name()` already
  shortens longer names.
- `supports_no_precision_decimalfield`: **needs a probe**: how the driver
  binds a `Decimal` with a large exponent (the `01004`), and whether
  `DECFLOAT(34)`'s 34 digits fit Django's unconstrained `DecimalField`.
  `DECFLOAT` values also arrive as `str`, so the backend would need a converter.

### Returning, bulk inserts, indexes, unique NULLs, cursors (phase 5, step 0)
2026-10-29, PUB400 (IBM i 7.5), five probes of phase 5 step 0
([phase-5.md](phases/phase-5.md), section 4): QTEMP only, one connection each
with the backend's attributes but without commitment control (`CMT=0`, QTEMP
tables have no journal). Results: `probes/results/returning.json`,
`bulk.json`, `indexes.json`, `unique_nulls.json`, `cursors.json`. QTEMP
objects are not in the catalog and QTEMP refuses constraints (SQL7008), so
how the catalog shows the new indexes and how a unique *constraint* treats
NULLs need a `lib_` probe (requested separately).

**Returning** (`probes/qtemp_returning.py`):

| Statement | Outcome |
|---|---|
| `SELECT ID, D FROM FINAL TABLE (INSERT INTO t (NAME) VALUES (?))` | ok: the generated identity and the column default; an explicit key is returned as sent; quoted names work |
| `IDENTITY_VAL_LOCAL()` after it | the key of that insert |
| `FINAL TABLE` with 5 rows, without and with `ORDER BY INPUT SEQUENCE` | ok, rows in input order both times |
| 3 rows, an explicit key 500 between two generated ones, `ORDER BY INPUT SEQUENCE` | `11, 500, 12`: input order, not key order |
| 200 rows, names in reverse order, `ORDER BY INPUT SEQUENCE` | all 200 in input order |
| `DEFAULT` in `VALUES`, one row and several rows mixed with values, also inside `FINAL TABLE` | ok; the default is written and returned |
| `VALUES (DEFAULT, DEFAULT, DEFAULT)`, `INSERT ... DEFAULT VALUES` | ok |
| explicit 0 in a `GENERATED BY DEFAULT AS IDENTITY` column | ok; the next generated key is 1 |
| `FINAL TABLE (UPDATE ...)` | SQL0199 "Keyword UPDATE not expected. Valid tokens: INSERT" |
| `OLD TABLE (UPDATE ...)`, `OLD TABLE (DELETE ...)` | SQL0104, SQL0199 |
| `cursor.rowcount` | 1 / 3 for a plain single / multi-row insert; -1 for `SELECT ... FROM FINAL TABLE` |

**Multi-row `INSERT` limits** (`probes/qtemp_bulk.py`; doubling from 256 rows,
then bisecting):

| Form | Largest that worked | Smallest refused | Refusal |
|---|---|---|---|
| parameter markers, 2 columns | 16,256 rows (32,512 markers) | 16,384 rows (32,768 markers) | SQL0901 "SQL system error" at prepare |
| parameter markers, 10 columns | 3,264 rows (32,640 markers) | 3,296 rows (32,960 markers) | SQL0901 at prepare |
| 1000-character literals | 2,080 rows (2,092,508 characters) | 2,112 rows (2,124,700 characters) | driver: `HY090` "Invalid statement length" (30197) |
| the constant 1 | 32,512 rows | 32,768 rows (163,868 characters) | SQL0101 "SQL statement too long or complex" |

- The marker limit lies between 32,640 and 32,768, so it is 32,767 at most;
  past it Db2 for i answers with a *system error* (SQL0901), not a clean
  limit error. `bulk_batch_size()` stays well below it.
- The statement length limit lies between 2,092,508 and 2,124,700
  characters, which fits Db2 for i's documented 2,097,152 (2 MB, not
  verified to the byte).

**LOB columns have a much lower limit** (`probes/qtemp_bulk_types.py`; found by
Django's `test_in_bulk_lots_of_ids`, 1998 rows with one `NCLOB`):

| Columns | Largest that worked | Smallest refused | Refusal |
|---|---|---|---|
| `NCLOB`, also `NCLOB(1M)`, `NCLOB(100M)`, `CLOB(1M)`, `BLOB(1M)` | 1,024 rows | 1,056 rows | `HY000` PWS0001 (19188) at prepare |
| two `NCLOB(1M)` | 512 rows (1,024 LOB markers) | 528 rows | PWS0001 |
| `NVARCHAR(100)`, `NVARCHAR(50)`, `NCLOB`, with and without `FINAL TABLE` | 1,024 rows | 1,056 rows | PWS0001 |
| `NVARCHAR(100)`, `NVARCHAR(50)`, `FINAL TABLE` | 16,128 rows (32,256 markers) | 16,384 rows (32,768 markers) | SQL0901 |
| `NCLOB(1K)`, `NVARCHAR(255)`, `NVARCHAR(16000)` | 16,384 rows | none up to 16,384 | |

- The limit counts the LOB markers of the statement, between 1,024 and 1,056
  (the probe's bisection stopped there). It does not depend on the declared
  length from 1M up, on the values (`NULL` or not) or on `FINAL TABLE`;
  `NCLOB(1K)` is not affected (where between 1K and 1M it starts was not
  measured). The connection stays usable after the refusal.
- `bulk_batch_size()` allows 512 LOB markers per statement, for every LOB
  column whatever its declared length.
- **Three or more LOB columns and `MERGE`** (2026-10-31, own IBM i tests in
  `tests/ibmi/test_inserts.py`, run once with the division by the LOB columns
  taken out): 360 rows with 3 `NCLOB` columns (1,080 markers), 220 rows with 5
  (1,100 markers) and a `MERGE` of 220 rows with 5 (1,100 `CAST(? AS NCLOB)`
  markers) each got PWS0001 at prepare; split by `bulk_batch_size()` they work.
  So a `MERGE` has a limit as well, at or below 1,100. The probe measured where the
  limit lies for `INSERT` with 1 and 2 LOB columns only; for 3 or more, and for
  `MERGE`, it is known only to lie below these sizes (open track in
  `docs/status.toml`).

**Indexes** (`probes/qtemp_indexes.py`): accepted, on a QTEMP table:
`CREATE INDEX ... WHERE` with comparisons, `IS NOT NULL`, `IN`/`OR`, functions
(`UPPER(B) = 'X'`, `LENGTH(B) > 3`) and quoted names; indexes on expressions
(`UPPER(B)`, `A + C`, `LOWER(B) DESC`, `(A, UPPER(B))`, Django's
`((UPPER(B)))`, `CAST(A AS VARCHAR(10))`), also with a `WHERE`.
`CREATE UNIQUE INDEX ... WHERE C > 0` enforces uniqueness only for rows
that match (two `A=1` rows with `C = 0` ok, the second `A=1` with `C > 0`
SQL0803); a unique index on `UPPER(B)` refuses `'abc'` after `'ABC'`
(SQL0803). `INCLUDE (B)`, plain and unique: SQL0104.

**Unique indexes and NULLs** (`probes/qtemp_unique_nulls.py`):

| Index | Two NULLs | `(1, NULL)` twice | `(NULL, NULL)` twice |
|---|---|---|---|
| `CREATE UNIQUE INDEX` | SQL0803: NULLs are equal | SQL0803 | SQL0803 |
| `CREATE UNIQUE WHERE NOT NULL INDEX` | ok | ok | ok |
| `CREATE UNIQUE INDEX ... WHERE A IS NOT NULL` | ok | (not tried) | (not tried) |

Duplicates of non-NULL keys are refused in every form (SQL0803).
`NULLS DISTINCT` / `NULLS NOT DISTINCT`: SQL0199 on an index and on a
constraint. A `UNIQUE` constraint in QTEMP: SQL7008, as expected.

**Cursors and self-referencing statements** (`probes/qtemp_cursors.py`): one
cursor fetched 300 rows in chunks of 100 while a second cursor on the same
connection ran a `SELECT` of another table, an `INSERT` into it, an `UPDATE`
of the same table, or a `SELECT` of the same table between the chunks: every
statement ok, all 300 rows in order each time. `DELETE ... WHERE ID IN
(SELECT ... FROM <same table>)` (also with `FETCH FIRST`), `UPDATE ... SET X
= (SELECT MAX(X) FROM <same table>)`, `UPDATE ... WHERE ID IN (SELECT ...
FROM <same table>)` and a correlated `UPDATE` over the same table: all ok.
Without commitment control; the cursor behaviour under `CMT=1` with a
journaled table is what step E checks with Django's tests.

**Consequences** (`docs/features.toml`, phase 5 steps):
- off, with the reason: `supports_covering_indexes` (no `INCLUDE`),
  `can_return_rows_from_update` (`FINAL TABLE` takes only `INSERT`),
  `supports_nulls_distinct_unique_constraints` (no `NULLS [NOT] DISTINCT`),
  `supports_deferrable_unique_constraints` (nothing is deferrable),
  `allows_multiple_constraints_on_same_fields` (SQL0541, probe
  `lib_constraints`).
- Step A can turn on `can_return_columns_from_insert`, `has_bulk_insert`,
  `can_return_rows_from_bulk_insert` (`ORDER BY INPUT SEQUENCE`), both
  `supports_default_keyword_in_*` and `allows_auto_pk_0`.
- Step C: `supports_partial_indexes`, `supports_functions_in_partial_indexes`,
  `supports_expression_indexes`.
- Step D: a plain unique index treats NULLs as equal; Django's nullable unique
  fields need several NULLs, so the backend would use `UNIQUE WHERE NOT NULL`
  indexes or what the `lib_` probe shows for constraints.
- Step E: `can_use_chunked_reads`, `delete_can_self_reference_subquery`,
  `update_can_self_select`.

### Unique constraints, NULLs and the index catalog (phase 5, step D)
2026-10-30, PUB400 (IBM i 7.5).

**`lib_unique_catalog`** (issue #213, approved in
[comment 6518630670](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/213#issuecomment-6518630670)):
one table, `DJDB2I_P5UNQ`, in the journaled default library. It was on the
cleanup list before its `CREATE TABLE` and was dropped at the end (nothing
left). Each constraint or index was created, then the catalog rows of this
table were read. For a unique case, the inserts ran in their own transaction,
ended with `ROLLBACK` before the `DROP`. The connection had the backend's
attributes (`CMT=1`, `TRUEAUTOCOMMIT=1`). Result: `probes/results/lib_unique_catalog.json`.

| Case | Second NULL in `A` | `(1, NULL)` twice | `(NULL, NULL)` twice | Real duplicate |
|---|---|---|---|---|
| `UNIQUE` constraint `(A)` | ok | SQL0803 (`A` = 1 twice) | ok | SQL0803 |
| `UNIQUE` constraint `(A, B)` | ok | ok | ok | SQL0803 |
| unique index `(A) WHERE B > 0` | ok (outside the condition) | ok | ok | SQL0803 inside the condition, ok outside it (also `B` NULL) |
| `UNIQUE WHERE NOT NULL` index `(A)` | ok | SQL0803 | ok | SQL0803 |

- **NULLs in a unique constraint are distinct.** This is unlike a plain
  unique index (step 0: NULLs are equal). Several NULLs are allowed, and so
  are partially NULL keys.
- **Unique constraints have no row in `SYSINDEXES`** (only `SYSCST` /
  `SYSKEYCST`), so `get_constraints()` does not list them twice.
- **`SYSINDEXES.IS_UNIQUE`:** `D` for a plain index, `U` for a unique index,
  `V` for `UNIQUE WHERE NOT NULL`.
- **Partial indexes:** `INDEX_HAS_SEARCH_CONDITION` is `Y`, and
  `SEARCH_CONDITION` holds the condition as text (`B > 0`).
- **Expression keys:** in `SYSKEYS`, `COLUMN_IS_EXPRESSION` is `Y`,
  `COLUMN_NAME` is a generated name (`IXCOL00001`), and `KEY_EXPRESSION`
  holds the expression (`UPPER ( C )`). For a column key they are `N`, the
  column name and the column name. A mixed index `(A, UPPER(C)) WHERE B > 0`
  shows one row of each.

**`qtemp_unique_nulls`, extended for step D** (QTEMP only, `CMT=0`):
`UNIQUE WHERE NOT NULL` combined with a condition and with expression keys.
Result: `probes/results/unique_nulls.json`.

| Index | `(1, NULL)` twice | NULL expression twice | Duplicate | Outside the condition |
|---|---|---|---|---|
| `UNIQUE WHERE NOT NULL (A, B) WHERE C = 'x'` | ok | ok | SQL0803 | ok |
| `UNIQUE WHERE NOT NULL (UPPER(C))` | n/a | ok | SQL0803 (also `'x'` / `'X'`) | n/a |
| `UNIQUE WHERE NOT NULL ((UPPER(C)), A) WHERE B > 0` | ok | ok | SQL0803 (also `'x'` / `'X'`) | ok |
| `UNIQUE INDEX (UPPER(C))` (baseline) | n/a | SQL0803 | SQL0803 | n/a |

**Consequences (step D):**
- `supports_nullable_unique_constraints` and
  `supports_partially_nullable_unique_constraints` go on: `unique=True` and
  `UniqueConstraint(fields=...)` are `UNIQUE` constraints, whose NULLs are
  distinct.
- A `UniqueConstraint` with a condition or expressions is a unique index
  (step C). The backend writes it as `CREATE UNIQUE WHERE NOT NULL INDEX`,
  so its NULLs are distinct as well, as Django assumes by default
  (`nulls_distinct` stays off: no `NULLS [NOT] DISTINCT`).

### A repeated FINAL TABLE insert after a column grows

2026-10-31, PUB400 (IBM i 7.5), `probes/qtemp_final_table_after_alter.py`: QTEMP only,
`CMT=0`, one connection. Result: `probes/results/final_table_after_alter.json`. Found by
`migrations...test_*_foreignfield_growth`, which inserts, widens a column and sends the same
insert with a value that needs the new size.

**The first prepare of a `SELECT ... FROM FINAL TABLE (INSERT ...)` text on a connection fixes
the parameter types of that text.** It is not pyodbc's reuse of a prepared statement, which is
per cursor: every attempt here had a new cursor. Whether the driver or the job holds it was not
separated; a new connection does not have it.

| The same statement text before and after `ALTER COLUMN ... SET DATA TYPE` | After it |
|---|---|
| `SELECT ... FINAL TABLE`, `INTEGER` to `BIGINT`, a value over the old range | **HY019 "Numeric value out of range"** (30018) |
| the same, `NVARCHAR(10)` or `VARCHAR(10)` to length 100, a longer string | **22001, CWB0111** "Input data is too big" (30207) |
| the same, `DECIMAL(5, 2)` to `(12, 2)`, a larger value | **22003** (30160) |
| the same, `DECIMAL(5, 2)` to `(9, 4)`, more decimals | **22001** (30126) |
| the same text, a value that fits the old type | ok |
| plain `INSERT`, `UPDATE ... SET`, `SELECT ... WHERE col = ?` | ok, also the new sizes |
| `SELECT ... FINAL TABLE` first sent after the `ALTER` | ok, and that text then keeps the wide types, also on a table with the old ones |
| a trailing space, or a line comment (`-- 1` and a line end) after the `ALTER` | ok: a new text |
| a typed marker, `VALUES (CAST(? AS BIGINT))`, both times | ok |

- **Never silent:** the longer value is refused with an error; nothing was cut off in these cases.
- **Nothing on the connection clears it:** the control and each of a commit, a rollback, a plain
  insert of the big value, a query without parameters and a new cursor all still fail with HY019.
  So does `DROP` and `CREATE` of the table with the wide column.
- **Fix:** once a connection has run `ALTER`, `CREATE`, `DROP` or `RENAME`, the driver layer adds a
  comment with the number of such statements to a `FINAL TABLE` statement
  (`drivers/pyodbc.py`). A typed marker in every insert would also work, also for another
  job's change, but changes every insert's SQL.
- **Not verified on IBM i:** a column changed by another connection while this one stays open. It
  needs two connections. The driver cannot see that change, so the same error is expected until
  this connection closes (Known Limitations).

### MERGE for conflicts in bulk_create() (phase 5, step B)
2026-10-30, PUB400 (IBM i 7.5), `probes/qtemp_merge.py`: QTEMP only,
`CMT=0`. Result: `probes/results/merge.json`. The table had a generated
identity, a unique `K` and a nullable `UNIQUE WHERE NOT NULL` `U`, with the
rows `K` = 1 and 2. QTEMP refuses `PRIMARY KEY` (SQL7008, as every
constraint), so the key was a unique index. Each case ran on fresh rows:

| Statement | Result |
|---|---|
| `MERGE ... USING (VALUES (?, ?, ?), ...)` (untyped markers) | SQL0584: no parameter marker in `VALUES` |
| the same with `CAST(? AS <type>)` per marker | ok |
| ignore form (`WHEN NOT MATCHED THEN INSERT`), one row exists | ok, row count 1 (only the new row) |
| update form (`WHEN MATCHED THEN UPDATE ... WHEN NOT MATCHED THEN INSERT`) | ok, row count 2 (one updated, one inserted) |
| a new key twice in one source, ignore or update form | SQL0803 |
| an existing key twice in one source, update form | SQL0788 (duplicate row for the MERGE target) |
| ignore form, `ON` the key `K` only, conflict in `U` | SQL0803 |
| ignore form, `ON (K match OR U match)` | ok: the conflicting row is skipped |
| the same with `U` NULL in two new rows | ok, both inserted (a NULL never matches) |
| `... NOT ATOMIC CONTINUE ON SQLEXCEPTION`, conflict in `U` | SQL0803: no help |
| `SELECT ... FROM FINAL TABLE (MERGE ...)` | SQL0199: `FINAL TABLE` takes only `INSERT` |

**Consequences (step B):**
- `bulk_create(ignore_conflicts=True)` and `update_conflicts=True` are a
  `MERGE` with cast markers (compiler.py).
- **`ON`:**
  - `ignore_conflicts` matches every unconditional unique key whose columns
    are inserted (`OR`);
  - `update_conflicts` matches its `unique_fields`
    (`supports_update_conflicts_with_target`).
- **No keys back:** a `MERGE` returns no rows, so `update_conflicts` leaves
  the keys of the objects unset.
- **Duplicates in one batch:** the same key twice in one batch is refused
  (SQL0803 / SQL0788), where PostgreSQL skips or refuses it.
- **Unique indexes are not matched:** conflicts in a conditional or
  functional unique constraint raise `IntegrityError`.

### MERGE under concurrency (not verified on IBM i)

**Verified since 2026-11-11** by `lib_merge_concurrency`: the results are in
[Two jobs: row locks, LOCK TABLE, MERGE](#two-jobs-row-locks-lock-table-merge-lib_select_for_update-lib_lock_table-lib_merge_concurrency),
which replace the expectations below. Phase 5
answer a asked for this to be investigated and documented; what follows is the
documented part, and the investigation waits for a dedicated IBM i.

**From IBM's documentation**
([MERGE, IBM i 7.5](https://www.ibm.com/docs/en/i/7.5?topic=statements-merge),
read 2026-10-31):

- `MERGE` works out which target rows are affected before it runs its inserts.
  Other jobs can insert or change rows in between, unless a restrictive isolation
  level such as repeatable read is used. IBM's own example is a concurrent insert
  of the same key, which gives a duplicate key error when `MERGE` inserts its row.
- `ATOMIC`: on an error the entire statement is rolled back; honored only with an
  isolation level other than No Commit. The page does not say in words which of
  `ATOMIC` / `NOT ATOMIC` is the default (`ATOMIC` comes first in the syntax
  diagram).
- A successful `MERGE` takes exclusive locks, held until commit or rollback, which
  can keep other jobs from their operations on the table.
- SQLCODE -913 / SQLSTATE 57033 is "deadlock or timeout occurred without automatic
  rollback" ([SQL messages and codes, 7.6](https://www.ibm.com/docs/en/ssw_ibm_i_76/pdf/rzalapdf.pdf);
  no 7.5 page was found). Whether a `MERGE` waiting for another job's uncommitted
  row ends in this error is our expectation, not IBM's statement.

**Verified with one job** (own IBM i tests, `tests/ibmi/test_inserts.py`): a
duplicate key met by the `MERGE`'s own insert, here the same new key twice in one
source, raises SQL0803, mapped to `IntegrityError`, and undoes the whole statement
under `*CS`, in autocommit and in a transaction, also its rows without a conflict.
This is the same error the race should give, reached another way; it says nothing
about the timing or the locks between two jobs.

**Not specific to `MERGE`:** without `supports_ignore_conflicts` Django's `m2m.add()`
does a `SELECT` and then an `INSERT`, with the same race and the same error. With
it, `add()` sends one `MERGE`, and with no `m2m_changed` listener no `SELECT` first
(`_get_add_plan()` in `related_descriptors.py`). The window is not larger. PostgreSQL's
`ON CONFLICT` does not have it, which is why this is a limitation here.

**Open verification, for a dedicated IBM i:** a `lib_` probe (`lib_merge_concurrency`,
with its own approval), one journaled table with a unique key, two connections:

| Case | To see |
|---|---|
| A merges a new key and does not commit; B merges the same key | does B wait, for how long, and with which error (SQL0913?) |
| the same, A commits while B waits | B: SQL0803, or the row skipped? |
| the same, A rolls back while B waits | B inserts its row? |
| both loop over the same new keys, with `ignore_conflicts` and with `m2m.add()` | how often SQL0803 occurs in a real race |
| a multi-row batch, one row in conflict | the whole batch undone, as with one job? |
| the retry of Known Limitations | does it succeed once A has committed, also inside `transaction.atomic()` |
| isolation `*RR` | does it prevent the error, as IBM's text suggests, and what it costs in locks |

Afterwards, Known Limitations and this section state results instead of
expectations, with an own IBM i test if it can be made reliable.

### Phase 6 probes: window functions, JSON, db functions, row locks

2026-10-31, PUB400 (IBM i 7.5). QTEMP only, `CMT=0`, one connection, before the plan was approved
([phase-6.md](phases/phase-6.md)). Results: `probes/results/window.json`, `json_functions.json`,
`db_functions.json`, `select_for_update.json`, `phase6_flags.json`, with every case and value.

**Window functions** (`probes/qtemp_window.py`):

| Form | Result |
|---|---|
| `ROW_NUMBER`, `RANK`, `DENSE_RANK`, `NTILE`, `LAG`, `LEAD`, `FIRST_VALUE`, `LAST_VALUE`, `NTH_VALUE` | ok, right values |
| `PERCENT_RANK`, `CUME_DIST` | ok; fetched as `str` (`'0.25'`) |
| `OVER ()`, `PARTITION BY`, `ORDER BY`, `SUM(SUM(V)) OVER`, a window in `ORDER BY`, in a subquery | ok |
| over `NVARCHAR`, `FIRST_VALUE` over `NCLOB` | ok |
| `NTILE(?)`, `NTILE(CAST(? AS INTEGER))`, `NTH_VALUE(V, ?)` | ok |
| `NTH_VALUE(V, CAST(? AS INTEGER))` | SQL0171 |
| `LAG(V, ?)`, `LAG(V, CAST(? AS INTEGER))` | SQL0104, SQL0199: the offset must be a constant |
| `LAG(V, 1, ?)` / `LAG(V, 1, CAST(? AS DOUBLE))` | SQL0418 / ok |
| `PARTITION BY MOD(I, ?)` | SQL0402 |
| `ROWS BETWEEN ...`, `RANGE BETWEEN UNBOUNDED ...`, `RANGE BETWEEN 5 PRECEDING AND 5 FOLLOWING` on a number | ok |
| `RANGE` on a date: `7 DAYS PRECEDING` / `7 PRECEDING` | SQL0104 / SQL0182 |
| `EXCLUDE CURRENT ROW`, `EXCLUDE TIES`, `GROUPS` | SQL0104 |
| a window directly in `WHERE` | SQL0120 (Django wraps it in a subquery) |

**JSON** (`probes/qtemp_json_functions.py`):

| Form | Result |
|---|---|
| `NCLOB`, `CLOB(1M) CCSID 1208`: round trip with `é` and an emoji, `IS JSON`, `JSON_VALUE`, `JSON_QUERY`, `JSON_EXISTS` | ok, text intact |
| **`BLOB`** holding the same UTF-8 document | **`IS JSON` false, every function NULL or false, no error** |
| a path as a marker, also typed | ok |
| `$."g h"`, `$.d[1]`, `$.d[last]`, `$.d[last-1]` | ok |
| `$.d[-1]` | NULL, no error |
| `JSON_VALUE` of an array, or of a string with `RETURNING INTEGER` | NULL, no error |
| `JSON_VALUE` of JSON null and of a missing key | NULL for both |
| `JSON_EXISTS` of JSON null / of a missing key | true / false |
| `JSON_QUERY` of a scalar | `1`; with `WITH CONDITIONAL WRAPPER` `[1]` |
| `RETURNING BOOLEAN`, `DOUBLE`; in `WHERE`, `ORDER BY`, `GROUP BY`; `JSON_TABLE` | ok |
| `DISTINCT` on the column; the column `= ?` | ok |
| the filters `$.d[*]?(@ == 20)` and `$?(@.a == 1)` in `JSON_EXISTS` | **false, where they should match** |
| a root array: `$[1]` | ok; IBM's `$.SYSIBM_ROOT_ARRAY[1]` gives NULL |
| a root number, string, `true`, `null`: `IS JSON` | true |
| the same: `JSON_VALUE(C, '$')`, `JSON_QUERY(C, '$')` | NULL; **on a root `null` `JSON_QUERY` gives `{}`** |
| not JSON: `IS JSON` / `JSON_VALUE` | false / NULL |
| `JSON_OBJECT` with constants, typed markers, a key marker, NULL, nesting, `FORMAT JSON`, `RETURNING NCLOB`; `JSON_ARRAY` | ok |

**JSON lookups** (`probes/qtemp_json_lookups.py`, 2026-11-04, PUB400, QTEMP only): the forms Django's
`JSONField` lookups need, on an `NCLOB` holding an object (with a string, numbers, JSON null, an array, a
nested object, `true`, keys with `'` and `%`), a second object, a root array, a root string and SQL NULL:

| Form | Result |
|---|---|
| `JSON_QUERY(C, <path>)` of a string, number, `true`, object, array, nested key, root array element | JSON text: `"téxt 😀"` (quotes kept), `1`, `2.5`, `true`, `{"g":[1,2],"f":true}` (compact, key order kept) |
| the same of JSON null, a missing key, a root scalar (`$` of `"scalar"`) | NULL for all three |
| `JSON_QUERY ... OMIT QUOTES` | `téxt 😀`: a string without quotes |
| `JSON_QUERY` result type | a `CLOB` of 2G by default; `RETURNING NVARCHAR(4000)` and `NCLOB(1M)` work |
| a path as a marker, also `$."k'%"` and a non-ASCII value | ok |
| `JSON_VALUE ... RETURNING NVARCHAR(4000)` of a string, number, `true` / an object | the text, `1`, `2.5`, `true` / NULL |
| `JSON_VALUE ... RETURNING DECFLOAT(34)` of a number / of the string `"1"` | the number / 1 |
| `JSON_QUERY(JSON_OBJECT('value' VALUE CAST(? AS NVARCHAR(4000)) FORMAT JSON), '$.value')` | the marker's JSON compacted: `{"g":[1,2],"f":true}`, `"téxt"`; through `NCLOB(1M)`: `[1,2.5, null ]` |
| `JSON_QUERY(...) = ?` (a `CLOB` against a marker), `ORDER BY` and `DISTINCT` on the `CLOB` | ok |
| an object against the normalized right-hand side, same key order / other key order | equal / not equal |
| the number `1` against the normalized `1.0` | equal |
| `JSON_VALUE ... RETURNING DECFLOAT(34) < ?` | ok; `JSON_VALUE ... RETURNING NVARCHAR < 2` matches nothing |
| `LOWER(JSON_VALUE(...)) LIKE ? ESCAPE '\'`, also on `a'b%` | ok |
| `JSON_EXISTS(C, ?)`, `NOT JSON_EXISTS(C, ?)`, `$[1]`, `$."d"[2]."x"` | ok; JSON null exists, SQL NULL is neither |
| `JSON_QUERY ... IN (<normalized>, <normalized>)` | ok |
| keys in a path, as Django's `json.dumps` writes them (`\\`, `\uXXXX` escapes) | **never found**: a path takes no JSON escapes |
| the same keys raw: a backslash, `é` | found, as a literal and as a marker |
| raw: an emoji, U+FFFF | found as a marker only; as a literal in the statement, not found |
| a key with a double quote: `\"`, `""` | not found in any form |
| `JSON_OBJECT((CAST(? AS NVARCHAR(32))) VALUE K RETURNING NCLOB(1M))`, also without the parentheses or with `KEY` | ok |
| `JSON_OBJECT()`, `JSON_OBJECT(RETURNING NCLOB(1M))`, `JSON_ARRAY(RETURNING NCLOB(1M))` | `{}`, `{}`, `[]` |
| `JSON_OBJECT` with a NULL value, with or without `NULL ON NULL` | `{"k":null}`: JSON null by default |
| `JSON_ARRAY(K, CAST(NULL AS INTEGER), ? NULL ON NULL ...)` | `[1,null,"x"]` (without `NULL ON NULL` the NULL is left out: `db_functions` on 6.1) |
| a nested `JSON_OBJECT`, a JSON column, `JSON_OBJECT`s in `JSON_ARRAY`, each with `FORMAT JSON` | JSON, not a string |
| `JSON_OBJECT('d' VALUE CAST(? AS DOUBLE))` of 30000.15 | `3.0000150000000001E4`, which Python reads as 30000.15 |
| `LISTAGG(JSON_QUERY(C, ... OMIT QUOTES), CAST(? AS NVARCHAR(32)))` | **SQL0171**: `JSON_QUERY` returns a `CLOB` |
| the same with `RETURNING NCLOB(1M) OMIT QUOTES`, also in `WITHIN GROUP (ORDER BY ...)` | ok |

**Db functions** (`probes/qtemp_db_functions.py`), on `héllo 😀`, NULL, 7, 2.5 and 2.50:

| Function | Result |
|---|---|
| `LENGTH` / `CHARACTER_LENGTH` | 8 / 7: `LENGTH` counts UTF-16 units |
| `CHR(65)` / `CHR(233)` / `CHR(128512)` | `A` / a substitute character / NULL |
| `ASCII`, `LOWER`, `UPPER`, `LPAD`, `RPAD` (also cutting), `LTRIM`, `RTRIM`, `TRIM`, `REPLACE`, `INSTR`, `LOCATE`, `POSITION`, `SUBSTRING`, `SUBSTR`, `COALESCE`, `NULLIF`, `GREATEST`, `LEAST`, `MAX(a, b)`, `MIN(a, b)` | ok; `GREATEST` of a NULL gives NULL |
| `CONCAT(S, N)` with N NULL / `CONCAT` of three | NULL / SQL0170 |
| `LEFT(S, ?)`, `RIGHT(S, ?)`, `REPEAT(S, ?)`, `SUBSTRING(S, ?, ?)`, `ROUND(D, ?)` | SQL0171 or SQL0418: a plain marker is refused |
| `ROUND(D, CAST(? AS INTEGER))` | ok; other functions with a typed marker were not tried |
| `REVERSE`, `UNICODE`, `MD5`, `HASH_SHA224`, `HASH_SHA384` | SQL0204: no such function |
| `HASH_MD5`, `HASH_SHA1`, `HASH_SHA256`, `HASH_SHA512`, `HASH(x, 0)`, `HASH(x, 3)` | ok; on UTF-8 only through `CAST(S AS VARCHAR(100) CCSID 1208)`, `HASH_MD5(S)` hashes other bytes |
| all math functions Django writes, `RAND()`, `RANDOM()` | ok; `LOG(2, 8)` SQL0170 (it takes one argument) |
| `ROUND` of 2.5, 3.5, 0.5, -2.5 | 3, 4, 1, -3: away from zero; also with no second argument |
| `CAST(2.55 AS DECIMAL(9, 1))`, `CAST(D AS DECIMAL(9, 0))`, `CAST(3.7 AS INTEGER)` | 2.5, 2, 3: cut off, not rounded |

**Db function arguments** (`probes/qtemp_db_function_args.py`, 2026-11-02, PUB400, QTEMP only), on
`héllo 😀`, NULL, 2 and an `NCLOB` of 3,000 `é` and an emoji:

| Form | Result |
|---|---|
| `LEFT`, `RIGHT`, `REPEAT`, `SUBSTRING`, `SUBSTR`, `LPAD` with typed markers (`CAST(? AS INTEGER)`) or a column as the number | ok, also on the `NCLOB` |
| `CONCAT(COALESCE(S, ''), COALESCE(N, ''))`, also with typed markers and an `NCLOB` | ok: NULL as empty text |
| `LN(8) / LN(2)`, also with typed markers | 3.0 |
| `ASCII` of `é` / of an emoji | 26 / 26: a substitute character |
| `LOWER(HEX(HASH_MD5(CAST(<x> AS CLOB(2G) CCSID 1208))))`, also `HASH_SHA256`, on the `NCLOB` | Python's `hashlib` result; the `VARCHAR(32000)` cast too, `HASH_MD5(<NCLOB>)` hashes other bytes |
| the same on NULL | NULL |
| `CAST(ROUND(D, 2) AS DECIMAL(8, 2))` with D = -1.934 (DOUBLE) | -1.92: `ROUND` stays binary, the cast cuts off |
| `CAST(ROUND(CAST(D AS DECFLOAT(34)), 2) AS DECIMAL(8, 2))`; also 3.467 to 1 place, 2.5 and -2.5 to 0, 1E20 | -1.93; 3.5; 3 and -3; exact |
| the same through `DECIMAL(63, 30)`; `ROUND` of a `DECIMAL(9, 3)` 2.555 to 2 places | -1.93, 3, exact; 2.56 |
| `CURRENT DECFLOAT ROUNDING MODE` | `ROUND_HALF_EVEN`, yet `ROUND` takes halves away from zero |

**A DOUBLE as text** (`probes/qtemp_float_text.py`, 2026-11-04, PUB400, QTEMP only), on 3, 4.5,
0.1, 1/3, 300, 10, 1E15, 1E16, 1E20, 0.1 + 0.2, -2.5, 1.23E-7, 1E-5, 0, -0, 2.5E-300 and the largest DOUBLE:

| Form | Result |
|---|---|
| `CAST(D AS NVARCHAR(100))`, `VARCHAR(D)`, `CHAR(D)` | exponent notation: `3E0`, `4.5E0`, `1.0000000000000001E-1`, `3E2` |
| `CAST(CAST(D AS DECFLOAT(16)) AS NVARCHAR(100))`, also with `NORMALIZE_DECFLOAT` or `VARCHAR_FORMAT` | `3`, `4.5`, `0.1`, `0.3333333333333333`, `0.3` (for 0.1 + 0.2), but `3E+2`, `1E+1`, `1E+15` |
| the same through `DECFLOAT(34)`, `VARCHAR_FORMAT(D)` | the binary value in full: `0.1000000000000000055511151231257827` |
| `CAST(CAST(D AS DECFLOAT(16)) + 0 AS NVARCHAR(100))`, also `+ CAST(0 AS DECFLOAT(16))` | `3`, `4.5`, `0.1`, `300`, `10`, `1000000000000000`, `0.3`, `-2.5`, `1.23E-7`, `0.00001`, `0` (also for -0); from 1E16 `1.000000000000000E+16`, `1.797693134862316E+308` |
| `CASE` with `QUANTIZE(..., DECFLOAT(0))` for whole numbers below 1E15 | the same, but `1E+15` and `-0`; the column three times |

`DECFLOAT(16)` keeps 16 significant digits, so a value that needs 17 (0.1 + 0.2) loses its last digit.

**Row locks** (`probes/qtemp_select_for_update.py`): **syntax only**: `CMT=0` on an unjournaled table, one
job, so it shows nothing about what is locked.

| Form | Result |
|---|---|
| `FOR UPDATE` alone, with `WHERE`, `ORDER BY`, `FETCH FIRST`, `OFFSET`, a subquery in `WHERE` or `FROM` | accepted |
| `FOR UPDATE OF V` / `OF T.V` | accepted / SQL0104 |
| `FOR UPDATE` with a join, also with `OF`, `DISTINCT`, `GROUP BY`, `UNION` | SQL0511 |
| `WITH RS USE AND KEEP EXCLUSIVE LOCKS`, `WITH RR ...`, also with a join and `FETCH FIRST` | accepted |
| `FOR UPDATE SKIP LOCKED DATA`, `SKIP LOCKED DATA`, `WITH CS SKIP LOCKED DATA`, `WAIT FOR OUTCOME` | accepted |
| `SKIP LOCKED`, `NOWAIT`, `WAIT 0` | SQL0104 |

**Smaller flags** (`probes/qtemp_phase6_flags.py`):

| Form | Result |
|---|---|
| `GROUP BY` an `NCLOB` or a `BLOB`, `DISTINCT` and `ORDER BY` an `NCLOB` | ok |
| `ORDER BY` in an `IN`, `FROM` or `EXISTS` subquery | ok |
| `LISTAGG(DISTINCT S, ',')`, also `WITHIN GROUP (ORDER BY S)` or `(ORDER BY I)` | ok |
| `REAL` | a float; 0.1 reads `0.10000000149011612` |
| `DECFLOAT(34)`: `Decimal('1E+300')` | 01004 (30002) at bind, also with a typed marker |
| the same as a string, a float | ok |
| `Decimal` with 34 digits, `Decimal('1E-300')` | ok, exact |
| a string with 35 digits | ok, rounded without an error (`1.234...234E+34`) |

### JSON functions with an error clause (`probes/qtemp_json_errors.py`)

2026-11-02, PUB400 (IBM i 7.5). QTEMP only, `CMT=0`, one connection, the maintainer's answer 2 on #218.
Result: `probes/results/json_errors.json`. Every error below came at **fetch** (`SQLFetch`), not at prepare,
and the connection answered after each of the 38. All have SQLSTATE `HY000` except SQL0406.

| Situation | Default | `ERROR ON ERROR` | `ERROR ON EMPTY` |
|---|---|---|---|
| not JSON | NULL | **SQ16402 "JSON data is not valid"** | NULL |
| a root number or string, `$` (`IS JSON` is true) | NULL | **SQ16402** | NULL |
| a missing key | NULL | NULL | **SQ16405 "Result contains no SQL/JSON item"** |
| `JSON_VALUE` of an object | NULL | NULL | SQ16405 |
| `JSON_VALUE` of an array | NULL | **SQ16404 "more than one SQL/JSON item"** | NULL |
| a negative position, `$.d[-1]` | NULL | **SQ16403 "subscript is not valid"** | NULL |
| **a malformed path, `$.a[`** | NULL | **NULL: no error**, also as a marker | SQ16405 |
| `RETURNING INTEGER` of a string | NULL | **SQL0406, `22018`** | not tried |
| JSON null | NULL | NULL | NULL |
| a SQL NULL: `JSON_VALUE` | NULL | NULL | NULL |
| a SQL NULL: `JSON_QUERY` | NULL | **SQ16402** | NULL |
| a root `null`: `JSON_QUERY(C, '$')` | `{}` | `{}` | `{}` |

- **`JSON_EXISTS`:** `ERROR ON ERROR` raises SQ16402 on not JSON and SQ16403 on a negative position. `TRUE ON
  ERROR` gives true there, `FALSE` and `UNKNOWN ON ERROR` false. A SQL NULL gives false under all of them. A
  malformed path gives false under all of them, also `ERROR ON ERROR`.
- **`strict` paths:** a missing key or a key of an array gives **SQ16410 "member not found"** with `ERROR ON
  ERROR`; `lax` gives NULL. A root number gives SQ16402 under both.
- **Path filters:** `$.d[*]?(@ == 20)` and `$?(@.a == 1)` stay false with `ERROR ON ERROR`, and `strict` gives
  SQ16410. So they match nothing and do not raise: not usable for `contains`.
- **Several rows:** one row of not JSON raises for the whole query, in the select list and in `WHERE`.
  `JSON_TABLE ... ERROR ON ERROR` gives SQ16402 too.
- **Not settled by this:** the mapping. SQ164xx arrive as `HY000`, so today they would be a plain
  `DatabaseError`; the `JSONField` PR needs entries by SQLCODE, as for SQL0532.

### Delete rules of a foreign key (`probes/lib_on_delete.py`)

2026-11-02, PUB400 (IBM i 7.5), in the journaled default library, approved on
[#220](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/220#issuecomment-6554356422). Tables
`DJDB2I_P6DELP` and `DJDB2I_P6DELC`, on the cleanup list, dropped child first with `RESTRICT`; nothing left.
Result: `probes/results/lib_on_delete.json`. Two parents (1, 2), a child of each (10 of 1, 20 of 2), `P_ID`
`DEFAULT 1`, each case in its own transaction ended with `ROLLBACK` (CMT=1).

| `ON DELETE` | Parent deleted | Result | Children after | `SYSREFCST.DELETE_RULE` |
|---|---|---|---|---|
| `NO ACTION` | 2 | SQL0532 (`HY000`), nothing deleted | as before | `NO ACTION` |
| `RESTRICT` | 2 | SQL0532, nothing deleted | as before | `RESTRICT` |
| `CASCADE` | 2 | ok | child 20 gone | `CASCADE` |
| `SET NULL` | 2 | ok | child 20: NULL | `SET NULL` |
| `SET DEFAULT` | 2 | ok | child 20: 1 | `SET DEFAULT` |
| `SET DEFAULT` | **1, the default's parent** | **SQL0532, nothing deleted** | as before | `SET DEFAULT` |

- `UPDATE_RULE` is `NO ACTION` in every case.
- All of it works inside a transaction, read back before the `ROLLBACK`.
- Foreign keys between tables in **different journals**: see the next section (`lib_fk_across_journals`).
- **Not tested:** DDL after these deletes in one transaction (SQL0910 would be expected, as for other pending
  row changes; each case rolled back first).

### Foreign keys across two journals (`probes/lib_fk_across_journals.py`)

2026-11-12, PUB400 (IBM i 7.5), approved on
[#249](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/249#issuecomment-6828621622).
Parent table `DJDB2I_XJP` in the default library, child table `DJDB2I_XJC` in the
`other` library, each journaled to its own library's `QSQJRN` (read from
`QSYS2.JOURNALED_OBJECTS`). Both on the cleanup list, dropped at the end (child first,
`RESTRICT`); `bin/ibmi-cleanup` afterwards: nothing left. Result:
`probes/results/lib_fk_across_journals.json`. Two parents (1, 2), a child of each, delete
parent 2, read both tables, `ROLLBACK` (CMT=1).

| `ON DELETE` | `ADD CONSTRAINT` | Delete parent 2 | `SYSREFCST.DELETE_RULE` |
|---|---|---|---|
| `NO ACTION` | ok | SQL0532, nothing deleted | `NO ACTION` |
| `RESTRICT` | ok | SQL0532, nothing deleted | `RESTRICT` |
| `CASCADE` | ok | **SQL7008** "DJDB2I_XJP ... not valid for operation", nothing deleted | `CASCADE` |
| `SET NULL` | ok | **SQL7008**, nothing deleted | `SET NULL` |

- **A foreign key whose delete rule changes the child (`CASCADE`, `SET NULL`) needs both
  tables in the same journal.** Db2 for i accepts the constraint, but every delete of a
  parent row then fails with SQL7008 (`HY000`), also a delete that matches no child. The
  same rules in one journal work (`lib_on_delete`, above). `SET DEFAULT` was not run
  (by the same reasoning it changes the child too).
- `NO ACTION` and `RESTRICT` work across journals: they only check, as in one journal.
- The `CASCADE` round that was meant to `COMMIT` hit the same SQL7008, so its
  clean-up delete of the parents failed too and rows 1 and 2 stayed committed; the
  `SET NULL` round's parent inserts then got SQL0803 (duplicate key). Its result is the
  same: the delete of parent 2 fails with SQL7008. Both tables were dropped at the end.
- So Django's `DB_CASCADE` / `DB_SET_NULL` (6.1+) between models whose tables are in
  libraries with different journals fail on every delete of the parent; Django's own
  `CASCADE` (in Python, the database rule `NO ACTION`) is not affected.

### Constraints and indexes on a table in another library (`probes/lib_other_library.py`, #124)

2026-11-12, PUB400 (IBM i 7.5), approved on
[#124](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/124#issuecomment-6839279187).
The connection's current schema is the default library (`DBQ = NAME`); tables
`DJDB2I_OLP` and `DJDB2I_OLC` in the `other` library, on the cleanup list, dropped at the
end (child first, `RESTRICT`), each index dropped explicitly first; a last catalog check
found no `DJDB2I_OL*` object in either library. No data rows. Result:
`probes/results/lib_other_library.json`.

| Statement on `<other>.DJDB2I_OLC` | Unqualified name | Qualified `<other>.` |
|---|---|---|
| `ADD CONSTRAINT ... FOREIGN KEY` (to a table in `other`) | **SQL5051** "Qualifier <default> not same as name <other>" | ok, in `other` |
| `ADD CONSTRAINT ... UNIQUE` | **SQL5051** | ok, in `other` |
| `ADD CONSTRAINT ... CHECK` | **SQL5051** | ok, in `other` |
| `CREATE INDEX` | ok, but the index lands in **the default library** (`SYSINDEXES.INDEX_SCHEMA`) | ok, in `other` |

- `CREATE INDEX <default>.X ON <other>.T` is accepted too: an index may live in another
  library than its table. `DROP INDEX` needs the index's own library.
- So for a model whose `db_table` is in another library, the schema editor must qualify
  every constraint name and every index name with the table's library. Unqualified, a
  constraint fails and an index ends up in the `NAME` library, where Django's
  introspection of the table's library (and `bin/ibmi-cleanup`) would not find it.
- `DROP CONSTRAINT <other>.<name>` works with the qualified name.

### CHECK ... IS JSON on an NCLOB (`probes/lib_json_check.py`)

2026-11-02, PUB400 (IBM i 7.5), in the journaled default library, approved on
[#221](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/221#issuecomment-6554376430). Table
`DJDB2I_P6JSON` on the cleanup list, dropped with `RESTRICT`; nothing left. The second table's `CREATE TABLE` was
refused, so it never existed. Result: `probes/results/lib_json_check.json`.

| Statement | Result |
|---|---|
| `ALTER TABLE ... ADD CONSTRAINT ... CHECK (C IS JSON)` | **SQL0546 "CHECK condition of constraint *N not valid"** |
| `CREATE TABLE ... (C NCLOB CHECK (C IS JSON))` | **SQL0546** |
| `CHECK (C IS JSON VALUE)`, `SCALAR`, `ARRAY`, `OBJECT` | **SQL0546 each** |

- **So a `JSONField` column cannot have a `CHECK ... IS JSON` on an `NCLOB`.** Nothing in the database stops text
  that is not JSON, and `can_introspect_json_field` has no check to recognize.
- SQL0546 is the same message for every form, and no form got a syntax error, so this does not show which forms
  exist as predicates. `IS JSON` works as a predicate in a `SELECT` (probe `qtemp_json_functions`).
- **Not tried:** a `CHECK` on a type other than `NCLOB`, or with another condition: outside this approval.
- **Without any check** (the control), every value is stored, and **JSON null and SQL NULL stay distinct:**
  the text `null` reads back as the string `null`, a SQL NULL as NULL (`C IS NULL`).
- **A slip in the first run's result:** `probes/results/lib_json_check.json` says "scalars IS JSON refused: none: no
  variants tried", although the variants did run, because the check itself was refused. The script is corrected;
  the cases above are right. Not run again for a label.

### Connections at the same time (`probes/qtemp_connections.py`, #234)

PUB400 (IBM i 7.5), 2026-11-11, read-only (nothing created or changed), once,
with the maintainer's "ok" on #234; result in
[probes/results/qtemp_connections.json](../probes/results/qtemp_connections.json).

- **Four connections at the same time work.** Each was opened while the earlier
  ones stayed open (about 1.4 to 1.6 s each, TLS), each is its own job
  (`QZDASSINIT`, the TLS database server job), none was refused.
- **They stay usable together:** all four answered a `SELECT 1` after each new
  connection and every 10 seconds during 30 seconds held open.
- **The limit itself is unknown:** the probe stops at four by design (no fifth
  connection was tried), and PUB400 states only "a hard restriction on number of
  connections from a single IP".
- So the earlier statement "PUB400 allows one connection per run" (here and in
  DECISIONS) was this project's rule, not PUB400's limit. The new rule: at most three
  at the same time, the extra ones only for lock and concurrency tests (CLAUDE.md,
  DECISIONS 2026-11-11).

### Two jobs: row locks, LOCK TABLE, MERGE (`lib_select_for_update`, `lib_lock_table`, `lib_merge_concurrency`)

PUB400 (IBM i 7.5), 2026-11-11, two connections at the same time (#236), each probe
once with the maintainer's approval (#237, #162, #238). Own tables in the journaled
default library, `CHGPF WAITRCD(2)`, dropped at the end (none left). Both jobs use the
backend's attributes (`*CS`, autocommit off). Results:
[lib_select_for_update.json](../probes/results/lib_select_for_update.json),
[lib_lock_table.json](../probes/results/lib_lock_table.json),
[lib_merge_concurrency.json](../probes/results/lib_merge_concurrency.json).

- **A CL command takes the system name.** `CHGPF FILE(<lib>/DJDB2I_SFUPARENT)` fails
  with CPD0074 (more than 10 characters, shown as SQL0443 / CPF0006); the name from
  `QSYS2.SYSTABLES.SYSTEM_TABLE_NAME` works.
- **Wait times:** a blocked row waits the file's `WAITRCD` (2 s here, SQL0913 after
  about 2.3 s); a blocked table (object) lock waits the job's default wait, about
  30 s on PUB400, whatever `WAITRCD` says.

**Row locks** (`lib_select_for_update`). Job A locks row 1, fetches all rows and
closes the cursor, as Django does; then job B:

| A's statement | B reads row 1 (`*CS`) | B updates row 1 | B `SKIP LOCKED DATA` returns | row 2, `WITH UR` / `NC` |
|---|---|---|---|---|
| `FOR UPDATE` | ok | ok | 1, 2, 3 | free |
| `FOR UPDATE OF V` | ok | ok | 1, 2, 3 | free |
| `FOR UPDATE WITH RS` | SQL0913 | SQL0913 | 2, 3 | free |
| `FOR UPDATE OF V WITH RS` | SQL0913 | SQL0913 | 2, 3 | free |
| `WITH RS USE AND KEEP EXCLUSIVE LOCKS` | SQL0913 | SQL0913 | 2, 3 | free |
| a slice (`FETCH FIRST 1 ROWS ONLY`), `USE AND KEEP` | SQL0913 | SQL0913 | 2, 3 | free |
| a join parent–child, `USE AND KEEP` | SQL0913 | SQL0913, also the child row | 2, 3 | free |

- **Under `*CS` a plain `FOR UPDATE` locks nothing once the rows are fetched**: the
  lock moves with the cursor and is gone when it closes. `WITH RS` keeps the locks
  until the transaction ends; that is the form `select_for_update()` needs.
- `SKIP LOCKED DATA` skips exactly the locked rows (`FOR UPDATE ... SKIP LOCKED DATA`,
  also with `OF V`, and `WITH CS SKIP LOCKED DATA`).
- `FOR UPDATE OF <column> WITH RS` locks like the form without `OF`.
- A join locks the rows of every table in it; `FOR UPDATE` is refused with a join
  (SQL0511, `qtemp_select_for_update`), so `of=` cannot limit a join's locks to one table.
- `SET CURRENT LOCK TIMEOUT` (`= 0`, `NOT WAIT`, `NULL`) is SQL0104: there is no
  per-statement "no wait" (and `NOWAIT`, `WAIT 0` were SQL0104 before).
- B waiting for row 1 continues as soon as A commits or rolls back (B done after
  about 0.5 s, when A ended).

**LOCK TABLE** (`lib_lock_table`, #162). While A holds `LOCK TABLE ... IN EXCLUSIVE
MODE`, every statement of B fails with SQL0913 after about 30 s: `SELECT` (also
`WITH UR` and `WITH NC`), `INSERT`, `UPDATE`, `DELETE`, `ALTER TABLE ... ADD COLUMN`,
`LOCK TABLE ... IN SHARE MODE`. **After A's `ROLLBACK`, B's control `SELECT` and
`INSERT` still failed with SQL0913**, so the lock was apparently not released by the
rollback; the `IN SHARE MODE` series that followed is therefore not valid (every
statement SQL0913, as under the exclusive lock). What releases it: see "What releases the lock" below. It matters for `add_field()`, which locks the table
this way (`schema.py`, `sql_lock_table`).

What the documentation says (sources found by the maintainer, 2026-11-11; not yet
checked by a probe, except where a probe result above says so):

- IBM's [LOCK TABLE](https://www.ibm.com/support/knowledgecenter/ssw_ibm_i_73/db2/rbafzh2lockt.htm)
  (7.3, read 2026-11-11): the lock is released when the unit of work ends, **unless
  it ends with `COMMIT HOLD` or `ROLLBACK HOLD`**; also when the activation group
  ends, when the connection is disconnected, and in a few other cases (the first SQL
  program in the stack ends, a type 1 `CONNECT`, release-pending). It can be released
  by hand with the CL command `DLCOBJ`.
- There is **no `UNLOCK TABLE`** statement in SQL on IBM i, also not in 7.6;
  `DLCOBJ` is the way ([midrange-l, 2026-03](https://archive.midrange.com/midrange-l/202603/msg00197.html)).
- IBM i Access ODBC keyword
  [`TRUEAUTOCOMMIT`](https://www.ibm.com/support/knowledgecenter/en/ssw_ibm_i_74/rzaik/connectkeywords.htm),
  default 0: autocommit then runs under `*NONE`, with no unit of work, so a rollback
  cannot release a lock. The backend sets `TRUEAUTOCOMMIT=1`
  (`drivers/pyodbc.py`, `CONNECTION_DEFAULTS`), and so did job A in this probe.
- **Hypothesis, not verified:** the driver preserves cursors over commit and
  rollback by default (`CWB_ATTR_PRESERVE_CURSORS`), possibly as `COMMIT HOLD` /
  `ROLLBACK HOLD`, which would keep the `LOCK TABLE` lock. Row locks were released by
  the driver's rollback in `lib_select_for_update` (B continued at once).

**What releases the lock** (`lib_lock_table --followup`, 2026-11-11, approved on
#162; [lib_lock_table_followup.json](../probes/results/lib_lock_table_followup.json)).
Job A `*CS`, ODBC pooling off as in the backend; each case on a free table, A locks
`IN EXCLUSIVE MODE` (three locks show in `OBJECT_LOCK_INFO`: `*SHRRD`, `*SHRRD`,
`*EXCL`, scope `JOB`), then:

| Case | Job A | Release | B after |
|---|---|---|---|
| 2 | transaction, `TRUEAUTOCOMMIT=1` (the backend) | pyodbc `rollback()` | **SQL0913: still locked** |
| 3 | the same | SQL statement `ROLLBACK` | ok, the locks are gone |
| 4a | the same | pyodbc `commit()` | **SQL0913: still locked** |
| 4b | the same | SQL statement `COMMIT` | ok |
| 5 | the same | `DLCOBJ` of each of A's three locks (`QSYS2.QCMDEXC`) | ok |
| 1 | autocommit, `TRUEAUTOCOMMIT=0` | pyodbc `rollback()` | **SQL0913: still locked** |
| 6 | autocommit, `TRUEAUTOCOMMIT=1` | pyodbc `rollback()` | **SQL0913: still locked** |
| 7 | transaction | the connection closed | ok |

- **The driver's commit and rollback (`SQLEndTran`) keep a `LOCK TABLE` lock; the SQL
  statements `COMMIT` and `ROLLBACK` release it.** This fits IBM's text (the lock
  stays when the unit of work ends with `COMMIT HOLD` / `ROLLBACK HOLD`) and the
  hypothesis that the driver ends units of work with HOLD; the driver's own setting is
  not known. Row locks are released by the driver's commit and rollback
  (`lib_select_for_update`).
- In autocommit (`TRUEAUTOCOMMIT` 0 or 1) the lock also outlives the statement.
- Closing the connection, `DLCOBJ` of every lock, or an SQL `COMMIT` / `ROLLBACK`
  release it.
- So **the backend's `LOCK TABLE` in `add_field()` and `_refuse_changed_values()`
  keeps the table locked for every other job after the migration's commit, until the
  connection closes.** The connection's own job is not blocked (the locks are
  job-scoped), which is why the test runs, with one connection, never showed it.
  Fixed: such a transaction ends with the SQL statement (DECISIONS, 2026-11-11, "A
  transaction that took a LOCK TABLE ends with the SQL COMMIT / ROLLBACK").
- `QSYS2.OBJECT_LOCK_INFO.OBJECT_NAME` holds the SQL name (`DJDB2I_LOCKPROBE`), not
  the system name: the probe's filter on the system name found no rows, so its
  summary column "A's locks left" reads 0 throughout; the library-wide rows it
  printed instead are the evidence above.
- The two earlier follow-up runs stopped after case 2 (the probe's own faults: the
  leftover lock was not released, and ODBC pooling was on, so closing A did not
  disconnect it); the table was dropped each time. With pooling on, the `*RR` part of
  `lib_merge_concurrency` briefly had four physical connections (two closed ones
  still connected in the pool, two new), not two; the helper turns pooling off since.

**DDL and row changes** (`lib_lock_table --ddl`, 2026-11-11, approved on #162;
[lib_lock_table_ddl.json](../probes/results/lib_lock_table_ddl.json)). Job A as the
backend (`*CS`, `TRUEAUTOCOMMIT=1`, a transaction, pooling off):

- The driver reports `SQL_CURSOR_COMMIT_BEHAVIOR` and `SQL_CURSOR_ROLLBACK_BEHAVIOR`
  = 2 (`SQL_CB_PRESERVE`): it keeps cursors over commit and rollback, which fits the
  `COMMIT HOLD` / `ROLLBACK HOLD` explanation above.
- **Only the `LOCK TABLE` lock outlives the driver's commit.** After the driver's
  commit (or rollback) of `CREATE TABLE`, `ALTER TABLE ... ADD COLUMN` and
  `CREATE INDEX`, job B read and wrote the table at once; the same after an SQL
  `COMMIT` (control).
- Row locks: after A's `INSERT` or `UPDATE` and the driver's commit, B updated the
  row at once; while A's `UPDATE` was not yet committed, B waited and got SQL0913
  after 2.2 s, and succeeded right after A's commit.
- The probe's `OBJECT_LOCK_INFO` query named a column that does not exist
  (`MEMBER_NAME`, SQL0206), so this run has no lock rows; job B's results are the
  evidence.

**MERGE with two jobs** (`lib_merge_concurrency`), the backend's `MERGE` with the
conflict on a unique key `K`; A merges `K = 1` and does not commit yet:

| Case | `ignore_conflicts` (`*CS`) | `update_conflicts` (`*CS`) | `ignore_conflicts` (`*RR`) |
|---|---|---|---|
| B merges the same key | **no wait, 0 rows inserted** | SQL0913 after 2.3 s | SQL0913 after 30 s |
| A commits within the wait (0.5 s) | 0 rows; A's row stays | B waits, then updates A's row | B waits, then 0 rows |
| A commits after the wait (3 s) | 0 rows | SQL0913, A's row unchanged | B waits about 3.1 s, then 0 rows |
| A rolls back (0.5 s) | **0 rows: neither row is there** | B waits, then inserts its row | B waits, then inserts its row |
| B's batch of 5, one key A's | 4 rows, A's key skipped | SQL0913 | not run |
| race, 20 keys, both jobs | A: 2 × SQL0803; B: 20 ok | no errors | not run |
| B retries once A committed | ok (transaction and autocommit) | ok | not run |

- **Under `*CS`, `ignore_conflicts` treats another job's uncommitted row as a
  conflict without waiting for it.** If that job rolls back, the row is missing from
  both. Under `*RR` B waits and inserts its row after the rollback.
- `update_conflicts` waits for the other job's row (2 s here) and then updates it or
  inserts; it gives up with SQL0913 if the other job takes longer.
- A real race still gives SQL0803 with `ignore_conflicts` (2 of 20 keys here), as
  IBM's documentation says: the retry of Known Limitations is needed.

### System names (`probes/qtemp_system_names.py`, phase 7 section 6)

PUB400 (IBM i 7.5), 2026-11-12, one connection, QTEMP only (tables and indexes gone
with the job), without commitment control. Result:
[system_names.json](../probes/results/system_names.json).

| Statement | Result |
|---|---|
| `CREATE TABLE <long> FOR SYSTEM NAME <sys> (...)` | ok; `INSERT` by the SQL names, `SELECT` by the system names (table and column) both work |
| `CREATE TABLE <short> FOR SYSTEM NAME <other>` (SQL name of at most 10 characters) | **SQL7029** "System name ... cannot be specified", also when both names are equal |
| a system name that is already taken | SQL0601 (exists), also between a table and an index: both are `*FILE` objects |
| a system name of 11 characters | SQL0107 (tables and columns) |
| lowercase undelimited | ok, stored uppercase (`PSNLOWER`) |
| delimited lowercase `"psnlower"` | ok, stored **with the quotes** (`"psnlower"`): to avoid |
| starting with a digit / with `#@$` / with `_` | SQL0103 / SQL0113 / ok |
| `<long> FOR COLUMN <sys> <type>` in `CREATE TABLE` | ok |
| a **short** column name with another `FOR COLUMN` | ok (unlike tables) |
| two columns with the same system name | SQL0612 (duplicate column name), also in `ADD COLUMN` |
| `ALTER TABLE ... ADD COLUMN <long> FOR COLUMN <sys> <type>` | ok; the column reads by both names |
| `ALTER TABLE ... RENAME COLUMN` | SQL0199 (no column rename on 7.5, as known) |
| `CREATE INDEX <long> FOR SYSTEM NAME <sys> ON ...` | ok; without it the system name is generated (`PROBE00001`) |
| `RENAME INDEX <long> TO <long> FOR SYSTEM NAME <sys>`, then `DROP INDEX <sys>` | ok, ok |
| `RENAME TABLE <long> TO <long> FOR SYSTEM NAME <sys>` | ok; reads by the new system name |
| `RENAME TABLE <long> TO <long>` without a system name | ok, **the old system name stays** |
| `RENAME TABLE <long> TO <short>` | ok, the short name becomes the system name |

- **For the backend (phase 7, options A and C):** write `FOR SYSTEM NAME` only for a
  table or index whose SQL name is longer than 10 characters (option C needs no
  clause: a short name *is* the system name); `FOR COLUMN` works for any column.
  A system name must be a valid undelimited name (letters, digits, `_`, not starting
  with a digit); check duplicates across tables *and* indexes of the library.
  A rename without `FOR SYSTEM NAME` keeps the old system name, so a rename must
  pass it again.
- **The catalog views show nothing for QTEMP** (`QSYS2.SYSTABLES`, `SYSCOLUMNS`,
  `SYSINDEXES` returned no rows); `QSYS2.OBJECT_STATISTICS('QTEMP', '*FILE')` does
  (`OBJNAME`, `OBJLONGNAME`). Introspection of system names needs a journaled
  library: an own IBM i test in the backend branch.

### The LOB limit for 3 and 5 columns (`probes/qtemp_bulk_lobs.py`, phase 7 section 3)

PUB400 (IBM i 7.5), 2026-11-12, one connection, QTEMP only, without commitment
control. `NCLOB(1M)` columns next to an `INTEGER` key; each case doubles the rows from
64, then bisects (6 steps). Result: [bulk_lobs.json](../probes/results/bulk_lobs.json).

| LOB columns | Statement | Largest that worked | Smallest refused (PWS0001) |
|---|---|---|---|
| 1 | `INSERT` | 1,024 rows = 1,024 LOB markers | 1,040 |
| 2 | `INSERT` | 512 rows = 1,024 | 520 rows = 1,040 |
| 3 | `INSERT`, also `FINAL TABLE`, also non-NULL values | 340 rows = 1,020 | 344 rows = 1,032 |
| 5 | `INSERT`, also `FINAL TABLE` | 204 rows = 1,020 | 206 rows = 1,030 |

- **The limit is about 1,024 LOB markers per statement, whatever the number of LOB
  columns**, the same inside `FINAL TABLE` and with values. The backend allows 512
  (`BULK_MAX_LOB_PARAMS`), half of it; up to about 1,000 would work (a decision for the
  backend branch: the margin is the point of 512).
- **`MERGE` on a QTEMP table is refused** (SQL7008, the table has no journal), so the
  `MERGE` of `ignore_conflicts` / `update_conflicts` cannot be measured here; it needs
  a journaled library (an own IBM i test in the backend branch).

### Flags off "not verified", and `CHR` / `ASCII` (`probes/qtemp_phase7_flags.py`)

PUB400 (IBM i 7.5), 2026-11-12, one connection, QTEMP only, without commitment
control. Result: [phase7_flags.json](../probes/results/phase7_flags.json).

| Flag | Probe | Result | Verdict |
|---|---|---|---|
| `allows_group_by_selected_pks` | `GROUP BY ID` with `NAME` selected, a unique index on `ID` (a `PRIMARY KEY` needs a journal) | SQL0122 | stays off |
| `greatest_least_ignores_nulls` | `GREATEST(1, NULL, 3)`, `LEAST`, scalar `MAX` | NULL | stays off |
| `has_case_insensitive_like` | `'ABC' LIKE 'abc'`; `NAME LIKE 'alpha%'` | 0; 1 of `Alpha` / `alpha` | stays off |
| `has_native_json_field` | a `JSON` column | SQL0204 (no such type) | stays off |
| `has_native_uuid_field` | a `UUID` column | SQL0204 (no such type) | stays off |
| `supports_explaining_query_execution` | `EXPLAIN PLAN FOR ...`, `EXPLAIN SELECT ...` | SQL0104 | stays off |
| `supports_logical_xor` | `XOR` in a predicate; `TRUE XOR FALSE` | SQL0104; SQL0199 | stays off |
| `supports_tablespaces` | `CREATE TABLE ... IN USERSPACE1` | **accepted** (no such tablespace on IBM i) | stays off: Django's tablespace options would be accepted and mean nothing |
| `supports_uuid4_function` | `GENERATE_UUID()` | **a UUID with version nibble 4**; `GENERATE_UUID_BINARY()` 16 bytes | **candidate** for the backend branch |
| `supports_uuid7_function` | (no time-ordered UUID function) | `GENERATE_UNIQUE()` is 13 bytes, not a UUID | stays off |

`CHR` / `ASCII` (Django's `Chr` / `Ord`):

- `CHR(65)` is `A`; `CHR(233)` gives the substitute character (`X'3F'`); `CHR(8364)`
  NULL. `ASCII(?)` with a parameter: SQL0204 (no function for an untyped marker).
- **UTF-16 works for both directions:**
  - `Chr`: `INTERPRET(HEXTORAW(RIGHT(HEX(CAST(? AS INTEGER)), 4)) AS GRAPHIC(1) CCSID 1200)`
    gives `é` for 233 and `€` for 8364; above `U+FFFF` (128512) it gives the wrong
    character (`U+F600`): a surrogate pair would be needed.
  - `Ord`: `INTERPRET(BX'0000' CONCAT CAST(CAST(? AS GRAPHIC(1) CCSID 1200) AS
    BINARY(2)) AS INTEGER)` gives 233 for `é`; `HEX(... GRAPHIC ... CCSID 1200)`
    gives `20AC` for `€`.
  - `UX'00E9'` literals work too.
- For the backend branch: `Chr` and `Ord` through these forms for the Basic
  Multilingual Plane, and a `NotSupportedError` or a Known Limitation above it.

### `Chr` and `Ord` above U+FFFF (`probes/qtemp_supplementary_chars.py`, #252)

PUB400 (IBM i 7.5), 2026-11-13, one connection, QTEMP only (one table, gone with the
job), without commitment control. Result:
[supplementary_chars.json](../probes/results/supplementary_chars.json). Every value
compared with Python's `chr()` / `ord()`: code points 65, 233, 8364, U+FFFD, U+10000,
U+1F600, U+10FFFF; strings `A`, `é`, `€`, an emoji, emoji + `x`, `x` + emoji,
U+10FFFF, `''` and NULL; as parameters, as `NVARCHAR` and as `NCLOB` column values.

- **`Chr` works for every code point** with a surrogate pair above U+FFFF:
  `CASE WHEN cp < 65536 THEN CAST(INTERPRET(HEXTORAW(RIGHT(HEX(cp), 4)) AS GRAPHIC(1)
  CCSID 1200) AS VARGRAPHIC(2) CCSID 1200) ELSE CAST(INTERPRET(HEXTORAW(RIGHT(HEX(55296
  + (cp - 65536) / 1024), 4) CONCAT RIGHT(HEX(56320 + MOD(cp - 65536, 1024)), 4)) AS
  GRAPHIC(2) CCSID 1200) AS VARGRAPHIC(2) CCSID 1200) END`: all match, parameters and
  columns, and equal the stored `NVARCHAR`. The `GRAPHIC(1)` form alone gives the wrong
  character above U+FFFF (U+1F600 becomes U+F600).
- One `INTERPRET(... AS VARGRAPHIC(2) CCSID 1200)` of 2 or 4 bytes: SQL0420 ("Value
  for cast argument not valid"), for every code point; hence the `CASE`.
- **`Ord` works for every string** through the first two code units:
  `HEX(CAST(s AS VARGRAPHIC(2) CCSID 1200))`, each half `INTERPRET(HEXTORAW('0000'
  CONCAT ...) AS INTEGER)`, a high surrogate (55296-56319) combined with the next unit;
  `''` gives 0, NULL gives NULL.
- **On an `NCLOB`, `SUBSTR(t, 1, 2)` and `LEFT(t, 2)` pad with blanks** (`'A'` becomes
  `'A '`, an emoji `'<pair> '`), and `SUBSTR(t, 1, 1)` of an emoji, or a `CAST` of
  `SUBSTR(t, 1, 2)` of `x` + emoji, is NULL (it splits the pair); `SUBSTRING(...,
  CODEUNITS16)` is SQL0104. The `CAST` of the whole value to `VARGRAPHIC(2)` keeps
  exactly the first two code units, without an error for a longer value.

### `FOR UPDATE ... WITH RS` in QTEMP (`probes/qtemp_select_for_update.py`, phase 7)

PUB400 (IBM i 7.5), 2026-11-12, QTEMP only. The forms the backend would write for
`select_for_update()`:

- **Every `FOR UPDATE ... WITH RS` form is SQL7008 in QTEMP** (the table has no
  journal): `FOR UPDATE WITH RS`, with `SKIP LOCKED DATA`, with `OF V`, after `ORDER
  BY ... OFFSET ... FETCH FIRST`, with a subquery in `WHERE`. SQL7008 comes at
  execution, after the parser (a syntax error is SQL0104), but QTEMP cannot show more.
  `FOR UPDATE WITH RS` and `FOR UPDATE OF V WITH RS` are verified in a journaled
  library (`lib_select_for_update`, above); the combinations with `SKIP LOCKED DATA`
  and `OFFSET` get own IBM i tests in the journaled test library (backend branch).
- `WITH RS USE AND KEEP EXCLUSIVE LOCKS`, also `... SKIP LOCKED DATA` and with a join,
  is accepted in QTEMP.

### The record wait of a table created with SQL (`probes/qtemp_record_wait.py`)

PUB400 (IBM i 7.5), 2026-11-12, QTEMP only: a table from `CREATE TABLE`, read with
`DSPFD ... TYPE(*ATR) OUTPUT(*OUTFILE)` into QTEMP. Result:
[record_wait.json](../probes/results/record_wait.json).

- **Maximum record wait (`PHWATR`, `WAITRCD`): 60 seconds; maximum file wait
  (`PHWAIT`, `WAITFILE`): 30 seconds.** After `CHGPF WAITRCD(5)` the record wait is 5.
- So a statement that meets another job's row lock (`select_for_update()`, also a
  plain read under `*CS`) waits up to 60 s on a table Django created, then fails with
  SQL0913. Django's `select_for_update.tests.test_block` reads the locked row without
  `FOR UPDATE` and expects no wait (PostgreSQL); here it waits and fails.
- The system names that `QSYS2.SYSTABLES` returns (`SYSTEM_TABLE_SCHEMA`,
  `SYSTEM_TABLE_NAME`) are padded with blanks; a CL command needs them stripped
  (`CHGPF FILE(<lib> /<name>)` is CPD0104 "Expression not allowed").

### A Decimal value with more digits than its DecimalField (`probes/qtemp_decimal_values.py`, #95)

PUB400 (IBM i 7.5), 2026-11-12, read-only (`SYSIBM.SYSDUMMY1`). Result:
[decimal_values.json](../probes/results/decimal_values.json).

| Marker | Value | Result |
|---|---|---|
| `CAST(? AS DECIMAL(5, 2))` | `123.45` | ok |
| the same | `123456.78` (more integer digits) | the driver refuses it: 22003 "Numeric value out of range" |
| the same | `1.2345` (more decimals) | the driver refuses it: 22001 "right truncation" |
| `CAST(? AS DECIMAL(9, 3))`, the value's own | `123456.789` | ok, exact |
| `CAST(CAST(? AS DECIMAL(9, 3)) AS DECIMAL(5, 2))` | `123456.789` | **NULL**, no error |
| `?` / `? + 0` | `123456.789` | SQL0418 / 22001 |
| `CAST(? AS DECIMAL(63, 3))` | 63 digits | ok |

- So a `Value(Decimal)` wider than its `DecimalField` is written with the value's own
  `DECIMAL(p, s)` (expressions.py), as #78 does for strings: exact, as on Django's
  other backends. Narrowing it in SQL would give NULL silently.

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
