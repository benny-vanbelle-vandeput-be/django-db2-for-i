# Installation

> **Not yet on PyPI.** The backend is in early development; install it from
> the repository.

## Requirements

- Python 3.12, 3.13 or 3.14
- Django 6.1
- [pyodbc](https://pypi.org/project/pyodbc/) 5.3 or later (installed
  automatically)
- unixODBC (Linux) and the IBM i Access ODBC Driver, see
  [ODBC driver setup](ODBC-Driver-Setup.md)
- An IBM i 7.5 (or later) system you can reach on the database host server
  port (8471, or 9471 with TLS), see [IBM i requirements](IBM-i-Requirements.md)

## Install

```sh
pip install "django-db2-for-i @ git+https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i.git"
```

Then configure a database, see [Configuration](Configuration.md).

## Check the connection

```sh
python manage.py shell -c "from django.db import connection; c = connection.cursor(); c.execute('SELECT 1 FROM SYSIBM.SYSDUMMY1'); print(c.fetchone())"
```

This prints `(1,)`. If it fails, see [Troubleshooting](Troubleshooting.md).
