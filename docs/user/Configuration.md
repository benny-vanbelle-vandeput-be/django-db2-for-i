# Configuration

```python
DATABASES = {
    "default": {
        "ENGINE": "django_db2_for_i",
        "NAME": "MYLIB",  # default schema (library)
        "HOST": "ibmi.example.com",  # the IBM i system
        "USER": "MYUSER",
        "PASSWORD": "...",  # e.g. from an environment variable
        "OPTIONS": {},
    }
}
```

| Setting | Meaning |
|---|---|
| `NAME` | **Required.** The default schema (library) for unqualified table names. Uppercased. |
| `HOST` | **Required.** Host name of the IBM i system. |
| `USER`, `PASSWORD` | IBM i user profile and password. |
| `PORT` | **Not supported** (raises an error). The driver uses the database host server port: 9471 with TLS, 8471 without. |
| `TIME_ZONE` | As in Django. With `USE_TZ = True`, datetimes are stored in this time zone (UTC if not set), see [Known limitations](Known-Limitations.md). |

## OPTIONS

| Option | Default | Meaning |
|---|---|---|
| `ssl` | `True` | TLS for the whole connection (port 9471). `False` uses port 8471 and sends the password unencrypted. |
| `isolation_level` | `"*CS"` | Commitment control level: `*NONE`, `*CHG`, `*CS`, `*ALL`, `*RR`, or the SQL names (`"read committed"`, `"repeatable read"`, `"serializable"`, ...). Only `*CS` has been tested. |
| `login_timeout` | `10` | Seconds to wait for the connection. |
| `driver` | `"pyodbc"` | Driver implementation; `pyodbc` is the only one. |
| `driver_attributes` | `{}` | Extra ODBC connection keywords, e.g. `{"XDYNAMIC": "1"}`. Keywords the backend sets itself (credentials, `DBQ`, `SSL`, `CMT`) cannot be overridden. |
| `capabilities` | detected | What the server can do; detected from the server version on connect. A profile name (`"7.5"`) or a mapping with `"profile"` and single overrides. Mainly for tests without a server. |

Unknown option names raise `ImproperlyConfigured`, so typos do not go
unnoticed.

## Connection defaults

The backend connects with these IBM i Access ODBC keywords:

| Keyword | Value | Why |
|---|---|---|
| `NAM` | `0` | SQL naming (`schema.table`). |
| `DBQ` | `NAME` | Default schema. |
| `CMT` | from `isolation_level` | Commitment control. |
| `TRUEAUTOCOMMIT` | `1` | A failing statement in autocommit mode leaves no partial changes (Django assumes this). Requires journaled tables, see [IBM i requirements](IBM-i-Requirements.md). |
| `XDYNAMIC` | `0` | No extended dynamic SQL packages (`*SQLPKG` objects in `QGPL`). |
| `DFT` / `TFT` | `5` / `2` | ISO date and time formats. |
| `SSL` | from `ssl` | TLS. |

## Test database (`TEST`)

The backend does not create test schemas yet. Tests run in an **existing,
journaled library** that holds nothing but test data:

```python
DATABASES = {
    "default": {
        # ...
        "TEST": {"NAME": "MYTESTLIB", "CREATE_DB": False},
    }
}
```

| Key | Meaning |
|---|---|
| `CREATE_DB` | Must be `False` (reuse an existing library; never `CREATE SCHEMA` / `DROP SCHEMA`). Without it, running tests raises `NotSupportedError`. |
| `NAME` | **Required.** System name of the test library (1 to 10 characters). It may equal the database `NAME`, but a warning is logged: only do that for a library used for nothing but tests. |
| `MODULE_SET` | Optional. Names the test modules of a run (for example `"basic"`); stored in the marker table. With `--keepdb`, tables left by a run for another module set are dropped instead of reused. Used by the project's own test tooling. |

How the backend protects your data:

- Before the tests, it checks that the library exists and has an active
  `QSQJRN` journal, see [IBM i requirements](IBM-i-Requirements.md).
- It creates a marker table, `DJDB2I_TEST_MARKER`, that identifies the
  library as a test library and records each run.
- A library **without** the marker must not contain any table or view
  (system catalog views such as `SYSCST` are ignored). Otherwise the tests do
  not start, also not with `--noinput`, because the library might be a
  production library.
- A library **with** the marker may contain tables from an earlier (for
  example crashed) test run. They are dropped after you confirm, or with
  `--noinput`; with `--keepdb` they are reused.
- After the tests, only tables created by test runs are dropped, then the
  marker. With `--keepdb` nothing is dropped.
- It never opens a second database connection for this.

Failures are reported as `TestDatabaseRefused` with an explanation; see
[Troubleshooting](Troubleshooting.md#test-library-refused).
