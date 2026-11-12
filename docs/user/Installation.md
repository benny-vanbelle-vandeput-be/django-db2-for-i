# Installation

> **Beta, not on PyPI.** Releases are published as
> [GitHub releases](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/releases)
> from signed tags; pip installs them from the tag.

## Requirements

- Python 3.12, 3.13 or 3.14; Python 3.15 with Django 6.1.3 or later only
  (6.0 and 5.2 do not support it; pip installs a 6.1 release on 3.15)
- Django 5.2 LTS (5.2.12 or later), 6.0 (6.0.3 or later) or 6.1; always use
  the latest security release of your Django version
- [pyodbc](https://pypi.org/project/pyodbc/) 5.3 or later (installed
  automatically)
- unixODBC (Linux) and the IBM i Access ODBC Driver, see
  [ODBC driver setup](ODBC-Driver-Setup.md)
- An IBM i 7.5 (or later) system you can reach on the database host server
  port (8471, or 9471 with TLS), see [IBM i requirements](IBM-i-Requirements.md)

## Install

A release (replace the version with the one you want):

```sh
pip install "django-db2-for-i @ git+https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i.git@v0.1.0b3"
```

The latest development state (unreleased, may break):

```sh
pip install "django-db2-for-i @ git+https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i.git"
```

Upgrading from an earlier beta: see [Upgrading](Upgrading.md).

## First steps

1. **A journaled library** for your tables: one created with `CREATE SCHEMA`,
   or a `CRTLIB` library with a `QSQJRN` journal, see
   [IBM i requirements](IBM-i-Requirements.md#journaling-required).
2. **The settings**: `ENGINE`, `NAME` (that library), `HOST`, `USER` and
   `PASSWORD`, see [Configuration](Configuration.md). Keep the password out of
   your settings file, for example in an environment variable.
3. **Check the connection** (below).
4. **Check the library**: `python manage.py check --database default` warns
   (`django_db2_for_i.W001`) when new tables there would not be journaled.
5. **`python manage.py migrate`**.
6. For your test suite: a second, empty journaled library as
   `TEST["NAME"]`, see [Configuration](Configuration.md#test-database-test).

## Check the connection

```sh
python manage.py shell -c "from django.db import connection; c = connection.cursor(); c.execute('SELECT 1 FROM SYSIBM.SYSDUMMY1'); print(c.fetchone())"
```

This prints `(1,)`. If it fails, see [Troubleshooting](Troubleshooting.md).

## Check your own IBM i

The backend is tested on PUB400, a shared IBM i 7.5. To see that it works on
your system too, run the **smoke set**: 37 of the project's own IBM i tests,
the most common patterns (the connection, inserts, queries, lookups,
aggregates, functions, foreign keys, schema changes). It runs from a checkout
of the repository, in its development container, not from your project. It
is available from the release after 0.1.0b3 on.

**What you need**

- Docker with the `docker compose` plugin (on Apple Silicon the container
  runs as amd64 under emulation, see [ODBC driver setup](ODBC-Driver-Setup.md)).
- A **test library** of at most 10 characters that is **journaled** (a
  `QSQJRN` journal, see [IBM i requirements](IBM-i-Requirements.md#journaling-required))
  and **empty**: a library without the test marker table that holds any
  table or view is refused, so it never touches a library with data. Never
  use a production library.
- A user profile that may create and drop tables in that library.

**Run it**

```sh
git clone https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i.git
cd django-db2-for-i
git switch --detach v<version>   # the release you installed
bin/setup                        # in your own terminal
bin/ibmi-test --smoke
```

`bin/setup` builds the containers and clones Django's sources for the
project's other tests (once, several minutes), and asks for the
IBM i user, the password (hidden), two libraries and the host; it writes them
to a local `.env` (mode 600, gitignored, never printed). The smoke set uses
only the first library (`DB2I_DEFAULT_LIBRARY`); the second is for the
project's full IBM i tests. The connection uses TLS (port 9471); add
`DB2I_SSL=0` to `.env` for port 8471. The scripts call the system "PUB400"
in their messages, whatever the host.

**What it does on your IBM i**

- One connection, one job. In the test library it creates the marker table
  `DJDB2I_TEST_MARKER` first, then the tables of the test models (with
  their indexes and constraints), and drops them all at the end,
  marker included. Db2 for i adds its catalog views (`SYSCST`, ...) to the
  library with the first constraint; they stay.
- Outside the library at most the job's own `QTEMP` is used (the copy of
  the query options that schema changes may need, see
  [ALTER TABLE that may lose data](IBM-i-Requirements.md#alter-table-that-may-lose-data)).
  No system values, no reply list entries, no other libraries.
- If a run is interrupted, tables can stay behind; the next run refuses the
  library until they are gone. `bin/ibmi-cleanup` lists them,
  `bin/ibmi-cleanup --yes` drops them (only tables a test run created, only
  in a library with the marker table).

**How long:** about 5 minutes on PUB400, plus the container build and the
first installation of Django in the container on the first run. It ends with
`37 passed`; a failure shows the test and the SQLCODE (see
[Troubleshooting](Troubleshooting.md)). Please report it as an issue, with
your IBM i release and the output (it contains no password; remove names
you want to keep private).
