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
