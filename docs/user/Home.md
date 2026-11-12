# django-db2-for-i

A Django database backend for **Db2 for IBM i** (AS/400, iSeries), built from
scratch and tested against Django's own test suite.

```python
DATABASES = {"default": {"ENGINE": "django_db2_for_i", ...}}
```

> **Status: beta, not production ready.**
> On IBM i 7.5 and Django 5.2, 6.0 and 6.1: transactions and savepoints,
> queries, lookups, aggregation and expressions, the schema editor (migrations,
> foreign keys, check constraints, indexes, introspection, `inspectdb`),
> returning inserts and `bulk_create()` with conflict handling, window
> functions, `JSONField`, the database functions and, on Django 6.1, DB-level
> `on_delete`. Features are enabled one at a time as Django's test suite proves
> them; `select_for_update()` is not available yet. What differs from other
> databases is in [Known limitations](Known-Limitations.md). Settings and
> behaviour may still change between beta releases.

## Pages

- [Installation](Installation.md): install, first steps, check your own IBM i
- [Upgrading](Upgrading.md): what changes between beta releases
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
