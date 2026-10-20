# django-db2-for-i

A Django database backend for **Db2 for IBM i** (AS/400, iSeries), built from
scratch and tested against Django's own test suite.

```python
DATABASES = {"default": {"ENGINE": "django_db2_for_i", ...}}
```

> **Status: early development, not production ready.**
> The backend connects, creates tables, and runs basic queries, inserts and
> pagination against IBM i 7.5, with transactions and savepoints (nested
> `atomic()`). Many Django features are still switched off
> (foreign key constraints, bulk insert, JSON, window functions,
> ...) and are enabled one at a time as Django's test suite proves them.
> Settings and behaviour may still change without notice.

## Pages

- [Installation](Installation.md)
- [ODBC driver setup](ODBC-Driver-Setup.md)
- [Configuration](Configuration.md): `DATABASES` and `OPTIONS`
- [IBM i requirements](IBM-i-Requirements.md): journaling, authorities
- [Known limitations](Known-Limitations.md)
- [Troubleshooting](Troubleshooting.md): errors by SQLCODE

## Supported versions

| Component | Versions |
|---|---|
| Django | 5.2 LTS (5.2.12+), 6.0 (6.0.3+), 6.1; see [Installation](Installation.md#requirements) |
| Python | 3.12, 3.13, 3.14 |
| IBM i | 7.5 and later |
| Driver | pyodbc 5.3+ with the IBM i Access ODBC Driver |

These pages are generated from `docs/user/` in the
[repository](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i);
the wiki is a read-only mirror.
