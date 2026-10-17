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

## Known limitations

- **`TimeField` has no fractional seconds.** Db2 for i `TIME` stores whole
  seconds only; the backend truncates microseconds before saving and in
  lookups, so `filter(t=value)` matches what was stored. Use a
  `DateTimeField` if you need sub-second precision.
- **Identifiers are uppercased.** Table and column names are created in
  uppercase; mixed-case `db_table` / `db_column` names are not preserved.
- **Every table Django writes to must be journaled.** Libraries created with
  `CREATE SCHEMA` are; libraries created with `CRTLIB` need a `QSQJRN`
  journal (see `docs/IBMI_NOTES.md`).

## IBM i Access ODBC Driver

The backend connects through pyodbc and the IBM i Access ODBC Driver. The driver
is IBM software under IBM's license terms. It is **not** part of this project and
is never redistributed. The development container installs it from IBM's
repository at build time. Container images that contain the driver must be
built locally or in private CI, and **never pushed to a public registry**.

## Development

All development and test runs happen in a container. The host only needs
Docker (e.g. Docker Desktop) with the `docker compose` plugin.

```sh
cp .env.example .env          # then fill in DB2I_* (never commit .env)
docker compose build          # builds the "offline" and "full" images
docker compose run --rm tests nox --list
docker compose run --rm tests nox -s offline
```

| Service | Build target | Contents | Use |
|---|---|---|---|
| `tests` | `full` | uv, Python 3.12–3.14, nox, unixODBC, IBM i Access ODBC Driver | all tiers, probes |
| `offline` | `offline` | same, without the IBM driver | offline tier, lint, CI |

- **Apple Silicon:** IBM publishes the Linux ODBC driver for amd64, i386 and
  ppc64el, not arm64. The `tests` service sets `platform: linux/amd64`, so it
  runs under emulation on arm64 hosts.
- **Licensing:** the `full` image contains the IBM i Access ODBC Driver.
  Build it locally or in private CI only, and **never push it to a public
  registry**. The `offline` image contains no IBM software.
- The devcontainer (`.devcontainer/`) attaches to the `tests` service.

## License

[BSD 3-Clause](LICENSE), the same license as Django. See
[CONTRIBUTING.md](CONTRIBUTING.md) for contribution terms.
