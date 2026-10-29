# Installation

> **Beta, not on PyPI.** Releases are published as
> [GitHub releases](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/releases)
> from signed tags; pip installs them from the tag.

## Requirements

- Python 3.12, 3.13 or 3.14
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
pip install "django-db2-for-i @ git+https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i.git@v0.1.0b1"
```

The latest development state (unreleased, may break):

```sh
pip install "django-db2-for-i @ git+https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i.git"
```

Then configure a database, see [Configuration](Configuration.md).

## Check the connection

```sh
python manage.py shell -c "from django.db import connection; c = connection.cursor(); c.execute('SELECT 1 FROM SYSIBM.SYSDUMMY1'); print(c.fetchone())"
```

This prints `(1,)`. If it fails, see [Troubleshooting](Troubleshooting.md).
