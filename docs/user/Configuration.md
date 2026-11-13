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
| `TIME_ZONE` | As in Django. With `USE_TZ = True`, datetimes are stored in this time zone (UTC if not set). Date lookups and functions require Django's current time zone to be the same, see [Known limitations](Known-Limitations.md#time-zones). |

## OPTIONS

| Option | Default | Meaning |
|---|---|---|
| `ssl` | `True` | TLS for the whole connection (port 9471). `False` uses port 8471 and sends the password unencrypted. |
| `isolation_level` | `"*CS"` | Commitment control level: `*NONE`, `*CHG`, `*CS`, `*ALL`, `*RR`, or the SQL names (`"read committed"`, `"repeatable read"`, `"serializable"`, ...). Only `*CS` has been tested. |
| `login_timeout` | `10` | Seconds to wait for the connection. |
| `driver` | `"pyodbc"` | Driver implementation; `pyodbc` is the only one. |
| `driver_attributes` | `{}` | Extra ODBC connection keywords, e.g. `{"XDYNAMIC": "1"}`. Keywords the backend sets itself (credentials, `DBQ`, `SSL`, `CMT`, `UNICODESQL`, `CCSID`) cannot be overridden. |
| `capabilities` | detected | What the server can do; detected from the server version on connect. A profile name (`"7.5"`) or a mapping with `"profile"` and single overrides. Mainly for tests without a server. One capability is checked with a statement at the first connection to a server: `has_generate_uuid` (`GENERATE_UUID()`, for `UUID4()`; IBM i 7.5 Db2 PTF Group SF99950 level 8). The `"7.5"` profile assumes it; on an older PTF Group with a configured profile, add `"has_generate_uuid": False`. |
| `suppress_inquiry_messages` | `True` | While a migration or schema editor removes or alters a field, the job does not send inquiry message CPA32B2, so `DROP COLUMN`, narrowing column changes and `SET NOT NULL` work without a system reply list entry; a narrowing change that would truncate or round a value is refused first. `False` keeps CPA32B2 for migrations too. See [IBM i requirements](IBM-i-Requirements.md#alter-table-that-may-lose-data). |
| `inquiry_message_reply` | not set | `"*SYSRPYL"`, `"*DFT"` or `"*RQD"`: the IBM i job's inquiry message reply (`INQMSGRPY`) for the whole connection. The fallback where `suppress_inquiry_messages` cannot be used (`OVERRIDE_QAQQINI` not allowed or failing). With `"*SYSRPYL"` (plus a system reply list entry) CPA32B2 is answered outside migrations too, or with `suppress_inquiry_messages` set to `False`, see [IBM i requirements](IBM-i-Requirements.md#alter-table-that-may-lose-data). The value the job had is read at connect and restored at close. Not set: the backend never changes the job attribute. |

Unknown option names raise `ImproperlyConfigured`, so typos do not go
unnoticed.

## IBM i system names

A guide with a full example: [Names and libraries](Names-and-Libraries.md).

Every table and column on IBM i has, next to its SQL name, a **system name** of at
most 10 characters: the name RPG and CL programs, `DSPFD` and most IBM i tools
use. A name of at most 10 characters (letters, digits, `_`) is its own system
name. For a longer one, IBM i makes one up (`DELIVERY_ADDRESS` becomes
something like `DELIV00001`), unless you set it.

**Columns:** give the field type the mixin from `django_db2_for_i.fields` and
pass `db_system_name`:

```python
from django.db import models
from django_db2_for_i.fields import SystemNameMixin, with_system_name


class AddressField(SystemNameMixin, models.CharField):
    pass


SystemNameIntegerField = with_system_name(models.IntegerField, __name__)


class Customer(models.Model):
    delivery_address = AddressField(max_length=100, db_system_name="DLVADDR")
    amount = SystemNameIntegerField(db_system_name="QTY")
```

- The backend writes `"DELIVERY_ADDRESS" FOR COLUMN DLVADDR ...` in
  `CREATE TABLE` and `ALTER TABLE ... ADD COLUMN`. The name is kept in
  migrations (`deconstruct()`), so define the field type in a module of your
  own, at module level.
- A system name has at most 10 characters: letters, digits or `_`, starting
  with a letter; it is stored in upper case. Any field with a `db_system_name`
  attribute counts, also a mixin of your own.
- Plain Django fields get no system name from the backend, as before.
- The checks (`manage.py check --database default`, `migrate`) report an
  invalid name (`django_db2_for_i.E001`) and two columns of one table with the
  same system name (`django_db2_for_i.E002`); a short column name counts as
  its own system name.
- Changing `db_system_name` of an existing column gives an `AlterField`
  migration that changes nothing in the database: Db2 for i has no statement
  to rename a column (see
  [Known limitations](Known-Limitations.md#renaming-a-column)).

**Tables:** add `"django_db2_for_i"` to `INSTALLED_APPS` (anywhere in the list)
and set `db_system_name` in the model's `Meta`:

```python
INSTALLED_APPS = [
    ...,
    "django_db2_for_i",  # Meta.db_system_name
]


class Customer(models.Model):
    class Meta:
        db_table = "customer_addresses"
        db_system_name = "CUSTADDR"
```

- The backend writes `CREATE TABLE "CUSTOMER_ADDRESSES" FOR SYSTEM NAME CUSTADDR (...)`;
  `CreateModel` migrations keep the option.
- Only for a `db_table` longer than 10 characters: a shorter name is its own
  system name, and Db2 for i refuses another one (SQL7029).
- Renaming the table (`AlterModelTable`) keeps the system name. Changing only
  `db_system_name` later is not picked up by `makemigrations` (see
  [Known limitations](Known-Limitations.md#changing-the-system-name-of-a-table)).

**Indexes:** declare the index in `Meta.indexes` with
`django_db2_for_i.indexes.SystemNameIndex`:

```python
from django_db2_for_i.indexes import SystemNameIndex


class Customer(models.Model):
    city = models.CharField(max_length=50)

    class Meta:
        indexes = [
            SystemNameIndex(fields=["city"], name="customer_city_idx", db_system_name="CUSTCITY"),
        ]
```

- The backend writes `CREATE INDEX "CUSTOMER_CITY_IDX" FOR SYSTEM NAME CUSTCITY ON ...`;
  the name is kept in migrations, and changing it gives a migration that
  creates the index again. Any index with a `db_system_name` attribute
  counts, also a subclass of your own.
- Indexes Django names itself (`db_index=True`, foreign keys, `unique=True`)
  keep the system name IBM i makes up; declare the index in `Meta.indexes` to
  choose it. Unique and other constraints are not `*FILE` objects and have no
  system name.
- The checks report an invalid name or one for a name of at most 10
  characters (`django_db2_for_i.E003`), and two tables or indexes with the
  same system name (`django_db2_for_i.E004`): both are `*FILE` objects in
  one library, so Db2 for i would refuse the second (SQL0601).

## Tables in another library

A guide with a full example: [Names and libraries](Names-and-Libraries.md#tables-in-another-library).

A model's table is in the library given as `NAME`, unless the model names
another one. Two ways, with the same result:

```python
class Order(models.Model):
    class Meta:
        db_table = 'SALES"."orders'  # Django's form of a qualified name


class Invoice(models.Model):
    class Meta:
        db_library = "SALES"  # needs "django_db2_for_i" in INSTALLED_APPS
        db_table = "invoices"  # optional: Django's default name otherwise
```

- `Meta.db_library` is the clearer spelling: when the model class is ready,
  the backend turns it into `db_table = 'SALES"."invoices'`. It needs
  `"django_db2_for_i"` in `INSTALLED_APPS`, as `Meta.db_system_name` does.
  The check `django_db2_for_i.E005` reports a library name that is not
  valid, and a model that names two different libraries (`db_library` and a
  `db_table` with another library).
- The backend qualifies the name of every constraint and index on such a
  table with its library: unqualified, Db2 for i would put the name into
  the `NAME` library and refuse a constraint (SQL5051) or create the index
  in the wrong library.
- Queries, migrations and introspection of the table (Django's
  `get_constraints()` and friends) use the library. The connection's current
  schema stays `NAME`.
- The library must exist and be journaled (a `QSQJRN` journal), as the
  `NAME` library: tables in it need commitment control too.

What this does not cover is in
[Known limitations](Known-Limitations.md#tables-in-another-library).

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
| `UNICODESQL` | `1` | Statements reach the server as Unicode, so any character can appear in SQL text. |
| `CCSID` | `1208` | The driver's client code page is UTF-8, whatever the process locale. |

Statement text and string parameters are sent as UTF-8 (pyodbc
`setencoding("utf-8", SQL_CHAR)`), and long strings in one piece (pyodbc
`maxwrite`). `UNICODESQL` and `CCSID` belong to this setup and cannot be
overridden.

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
