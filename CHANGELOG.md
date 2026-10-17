# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Phase 0: project skeleton.
  - BSD-3-Clause license, contributing guide, README, changelog.
  - `pyproject.toml` (Django 6.1, pyodbc required) and the backend package
    layout as documented stubs.
  - Container environment: `docker/Dockerfile` with `offline` and `full`
    targets (IBM i Access ODBC Driver pinned by version and SHA256),
    `compose.yaml`, devcontainer, `.env.example`.
  - nox sessions `lint`, `offline` (Python 3.12–3.14 × Django 6.1), `pub400`,
    `probe`; pytest tier markers and an offline connection guard.
  - GitHub Actions workflow for the offline tier.
  - Read-only IBM i probes (`reachability`, `connect`, `sysinfo`, `libraries`).
  - Docs: `DECISIONS.md`, `DJANGO_VERSIONS.md`, `IBMI_NOTES.md` with the
    PUB400 findings, `TEST_STATUS.md`.
- Claude Code project settings deny access to `.env`.

### Added (backend)
- `OPTIONS["inquiry_message_reply"]` (opt-in): the IBM i job's inquiry message
  reply for the connection, restored to the original value at close, plus
  `connection.set_inquiry_message_reply()` / `restore_inquiry_message_reply()`.
  With `"*SYSRPYL"` and an administrator's `ADDRPYLE MSGID(CPA32B2) RPY('I')`,
  `DROP COLUMN` and narrowing column changes are allowed.
- An `ALTER TABLE` cancelled by inquiry message CPA32B2 (HY008) raises an
  `OperationalError` that explains the cause and the fix.

### Enabled features
- Savepoints (`uses_savepoints`, `can_release_savepoints`): nested `atomic()`
  blocks use `SAVEPOINT ... ON ROLLBACK RETAIN CURSORS`. Django's
  `transactions` tests: 85 passed, 3 skipped, no failures.

### Fixed
- Date and datetime lookups and `Extract()` (`__year`, `__month`, `__day`,
  `__week_day`, `__iso_week_day`, `__week`, `__quarter`, `__iso_year`,
  `__hour`, `__minute`, `__second`) are implemented. They run in the
  database's time zone; another current time zone raises `NotSupportedError`
  (see docs/user/Known-Limitations.md).
- Column defaults (`db_default`, and Python defaults when a migration adds a
  NOT NULL column) are written as bare literals with one rule per type;
  `CAST(...)` in a DEFAULT was rejected (SQL0574). Strings with quotes or
  non-ASCII characters use `UX'...'` constants, because Db2 for i stores
  escaped quotes in DEFAULT constants wrongly. Unsupported values raise
  `NotSupportedError`.
