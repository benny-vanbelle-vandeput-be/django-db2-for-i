# django-db2-for-i

A Django database backend for **Db2 for IBM i** (AS/400, iSeries).

> **Status: early development (phase 0, skeleton).** The backend is not usable yet.

## Target usage

```python
DATABASES = {
    "default": {
        "ENGINE": "django_db2_for_i",
        # connection settings: to be documented in phase 1
    }
}
```

## Supported versions

| Component | Versions |
|---|---|
| Django | 5.2 LTS, 6.1 (development currently targets 6.1 only) |
| Python | 3.12, 3.13, 3.14 (subject to each Django version's own support) |
| IBM i | 7.5 and later |

## IBM i Access ODBC Driver

The backend connects through pyodbc and the IBM i Access ODBC Driver. The driver
is IBM software under IBM's license terms. It is **not** part of this project and
is never redistributed. The development container installs it from IBM's
repository at build time. Container images that contain the driver must be
built locally or in private CI, and **never pushed to a public registry**.

## Development

Setup instructions for the containerized environment will follow in phase 0.

## License

[BSD 3-Clause](LICENSE), the same license as Django. See
[CONTRIBUTING.md](CONTRIBUTING.md) for contribution terms.
