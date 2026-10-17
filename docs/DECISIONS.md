# Decision records

Lightweight records of non-obvious decisions: date, decision, why, alternatives.

## 2026-10-16: Container base image and Python provisioning
- **Decision:** `debian:trixie-slim` with Python 3.12/3.13/3.14 installed by `uv`
  (pinned uv version), plus `nox` as a uv tool.
- **Why:** one image serves every Python version in the matrix; uv is also nox's
  venv backend, so interpreter and environment handling come from one tool.
- **Alternatives:** official `python:*` images (one Python per image, so a matrix
  of images); Ubuntu base (larger, no benefit for the driver).

## 2026-10-16: Install the IBM i Access ODBC Driver from a pinned, checksummed .deb
- **Decision:** download `ibm-iaccess-<version>.amd64.deb` from IBM's repository,
  verify its SHA256, and install it with apt. Version and checksum are build args.
- **Why:** IBM's apt repository is unsigned (no `Release.gpg`/`InRelease`; IBM's own
  `.list` file uses `[trusted=yes]`). A pinned checksum gives integrity and
  reproducible builds.
- **Alternatives:** IBM's `.list` with `[trusted=yes]` (no integrity check, version
  drifts silently).

## 2026-10-16: Own odbcinst.ini with a 64-bit-only entry
- **Decision:** `docker/odbcinst.ini` replaces the package's registration; the
  common name `IBM i Access ODBC Driver` points to `lib64/libcwbodbc.so`.
- **Why:** the package registers `Driver=` with a 32-bit `lib/` path that the amd64
  package does not ship, relying on unixODBC's `Driver64` handling. An explicit
  entry is unambiguous; the build fails if the library is missing or unresolved.
- **Alternatives:** keep the package registration; use the
  `IBM i Access ODBC Driver 64-bit` name in connection strings.

## 2026-10-16: pyodbc is a required dependency
- **Decision:** `pyodbc` is in `dependencies`, not an extra.
- **Why:** it is the only driver; with an extra, a plain
  `pip install django-db2-for-i` would not work.
- **Revisit:** when a second driver (Mapepire, `ibm_db`) is added, move each driver
  to its own extra.

## 2026-10-16: TLS by default, no automatic fallback
- **Decision:** `DB2I_SSL=1` (port 9471) is the default. Plain connections (8471)
  only with an explicit `DB2I_SSL=0`. Probes report certificate problems as such
  and never fall back automatically.
- **Why:** the password crosses the public internet when using PUB400.
- **Alternatives:** plain by default (credentials unencrypted); automatic fallback
  (silently downgrades security).

## 2026-10-16: Secrets handling
- **Decision:** all connection settings use the `DB2I_` prefix and live in `.env`
  (gitignored, excluded from the Docker build context). compose injects them into
  the `tests` container. `.claude/settings.json` denies Claude Code access to `.env`.
- **Why:** enforce "never read or print `.env`" instead of relying on convention.
- **Limitation:** Bash deny rules are prefix-based and not exhaustive; the
  Read/Edit/Write rules are exact.

## 2026-10-16: compose services have no image name
- **Decision:** `tests` and `offline` only have a `build:` section.
- **Why:** with an explicit `image:` name, compose would either rebuild on every run
  (`pull_policy: build`) or try to pull that name from Docker Hub, where anyone
  could publish it. The `full` image must also never be pushed.

## 2026-10-16: Probes use pyodbc directly
- **Decision:** `probes/` talk to pyodbc directly, not through `django_db2_for_i.drivers`.
- **Why:** the driver interface is designed in phase 1; probes must not depend on
  it, and they must keep working as an independent check of IBM i behaviour.

## 2026-10-16: Full module layout as stubs in phase 0
- **Decision:** every backend module exists from phase 0 as a docstring-only stub
  stating its responsibility and the phase that implements it.
- **Why:** makes the three-axis architecture visible from the start.

## 2026-10-16: Build backend and CI
- **Decision:** hatchling as build backend. CI (GitHub Actions) builds the `offline`
  image target and runs `nox -s lint offline` inside it.
- **Why:** hatchling supports SPDX `license` and `license-files` and is widely used.
  Running CI in the same image as local development keeps one environment.
- **Alternatives:** `uv_build`, setuptools; running nox directly on the runner.

## 2026-10-17: CharField maps to NVARCHAR (CCSID 1200)
- **Decision:** `CharField(max_length=n)` (and the other `max_length` string
  fields) map to `NVARCHAR(n)`, i.e. UTF-16 (CCSID 1200).
- **Why:** probes `session` and `probe_write` (docs/IBMI_NOTES.md) show that
  `NVARCHAR(n)` counts UTF-16 code units. That equals Django's `max_length`
  (code points) for every BMP character: `é` × 10 fits in `NVARCHAR(10)`,
  `é` × 11 is rejected. `VARCHAR(n) CCSID 1208` counts bytes, so `é` × 10
  does not fit in `VARCHAR(10)`. The job CCSID (273) cannot store emoji at all.
- **Known deviation:** a non-BMP character (emoji) takes 2 of the `n` units, so
  a value that passes Django's `max_length` validation can be rejected by the
  driver (`22001`, never truncated). Example: 6 emoji fit `max_length=10` in
  Django but not `NVARCHAR(10)`.
- **Row length impact:** Db2 for i limits a row to 32,766 bytes (LOB columns
  excepted). `NVARCHAR(n)` uses 2 bytes per unit plus a 2-byte length, so
  `CharField(max_length=255)` takes 512 bytes; about 63 such columns fill a
  row. With `VARCHAR CCSID 1208` sized in bytes the same column could take
  half (ASCII) but would not enforce `max_length`.
- **Alternatives:** `VARCHAR(n) CCSID 1208` (byte length, rejects non-ASCII
  values at `max_length`); `VARCHAR(4n) CCSID 1208` (no length enforcement,
  wastes row length); `VARCHAR(n)` in the job CCSID (no emoji, CCSID-dependent).
- **Revisit:** if the emoji deviation shows up in Django's test suite, consider
  `NVARCHAR(2n)` plus a `CHARACTER_LENGTH` check constraint.
