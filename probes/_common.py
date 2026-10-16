"""Shared helpers for the read-only IBM i probes.

Rules (see CLAUDE.md):
- Read-only: probes only run SELECT statements against catalog views and
  SQL services. Anything that changes the IBM i is proposed separately.
- At most one ODBC connection per run, no retries.
- The password and the full connection string are never printed or logged.

Settings come from DB2I_* environment variables, which compose injects from
.env into the "tests" container.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import os
import socket
import time
from pathlib import Path
from typing import Any

DRIVER = "IBM i Access ODBC Driver"
LOGIN_TIMEOUT_SECONDS = 10
TCP_TIMEOUT_SECONDS = 5
RESULTS_DIR = Path(__file__).resolve().parent.parent / "test-results" / "probes"

# Database host server ports: as-database (plain) and as-database-s (TLS).
DATABASE_PORT = {False: 8471, True: 9471}

EXIT_CONFIG = 1
EXIT_UNREACHABLE = 2
EXIT_CONNECT_FAILED = 3


class ProbeError(Exception):
    """A probe run cannot continue. The message is safe to print."""

    def __init__(self, category: str, message: str, exit_code: int = EXIT_CONNECT_FAILED):
        super().__init__(message)
        self.category = category
        self.exit_code = exit_code


@dataclasses.dataclass(frozen=True)
class Settings:
    host: str
    user: str
    password: str = dataclasses.field(repr=False)
    ssl: bool
    default_library: str
    other_library: str

    @classmethod
    def from_env(cls, need_credentials: bool) -> Settings:
        env = os.environ
        required = ["DB2I_HOST"] + (["DB2I_USER", "DB2I_PASSWORD"] if need_credentials else [])
        missing = [name for name in required if not env.get(name)]
        if missing:
            raise ProbeError(
                "config",
                f"missing environment variables: {', '.join(missing)} "
                "(copy .env.example to .env and fill it in)",
                EXIT_CONFIG,
            )
        ssl_value = env.get("DB2I_SSL", "1").strip()
        if ssl_value not in ("0", "1"):
            raise ProbeError("config", "DB2I_SSL must be 0 or 1", EXIT_CONFIG)
        return cls(
            host=env["DB2I_HOST"].strip(),
            user=env.get("DB2I_USER", "").strip(),
            password=env.get("DB2I_PASSWORD", ""),
            ssl=ssl_value == "1",
            default_library=env.get("DB2I_DEFAULT_LIBRARY", "").strip().upper(),
            other_library=env.get("DB2I_OTHER_LIBRARY", "").strip().upper(),
        )

    @property
    def database_port(self) -> int:
        return DATABASE_PORT[self.ssl]

    def scrub(self, text: str) -> str:
        """Remove the password from text that may be printed or stored."""
        if self.password:
            text = text.replace(self.password, "***")
        return text


# --- TCP / connection -------------------------------------------------------


def tcp_check(host: str, port: int) -> dict[str, Any]:
    """Open and close a plain TCP connection. No data is sent."""
    start = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=TCP_TIMEOUT_SECONDS):
            pass
    except OSError as exc:
        return {"port": port, "open": False, "error": f"{type(exc).__name__}: {exc}"}
    return {"port": port, "open": True, "ms": round((time.monotonic() - start) * 1000)}


def _odbc_value(value: str) -> str:
    """Brace-quote an ODBC connection string value (handles ';' and '}')."""
    return "{" + value.replace("}", "}}") + "}"


def connect(settings: Settings):
    """Open the run's single ODBC connection. Fails fast; never retries."""
    import pyodbc

    preflight = tcp_check(settings.host, settings.database_port)
    if not preflight["open"]:
        raise ProbeError(
            "unreachable",
            f"{settings.host}:{settings.database_port} is not reachable "
            f"({preflight['error']}). Check the network or run the reachability probe.",
            EXIT_UNREACHABLE,
        )

    # Read-only probes: SQL naming (NAM=0) and commit mode *NONE (CMT=0).
    parts = [
        f"DRIVER={_odbc_value(DRIVER)}",
        f"SYSTEM={settings.host}",
        f"UID={_odbc_value(settings.user)}",
        f"PWD={_odbc_value(settings.password)}",
        f"SSL={int(settings.ssl)}",
        "NAM=0",
        "CMT=0",
    ]
    try:
        return pyodbc.connect(";".join(parts), timeout=LOGIN_TIMEOUT_SECONDS, autocommit=True)
    except pyodbc.Error as exc:
        # "from None": do not chain anything that could carry the connection string.
        raise classify_connect_error(exc, settings) from None


_ADVICE = {
    "driver_missing": "The ODBC driver is not installed or not registered. "
    "Run probes in the 'tests' container (docker compose run --rm tests ...).",
    "tls_certificate": "TLS certificate not trusted. Options: add the issuing CA to the "
    "image, or set DB2I_SSL=0 deliberately (the password is then sent unencrypted). "
    "Run 'nox -s probe -- reachability' for the certificate details.",
    "tls_handshake": "TLS failed before login; this may be a certificate problem. "
    "Run 'nox -s probe -- reachability' for an independent certificate check before "
    "deciding on DB2I_SSL=0.",
    "auth": "Sign-on rejected. Check DB2I_USER / DB2I_PASSWORD; repeated failures can "
    "disable the user profile, so do not retry blindly.",
    "connection": "The server refused or dropped the connection.",
    "connect_failed": "Connection failed for an unclassified reason.",
}


def classify_connect_error(exc: Exception, settings: Settings) -> ProbeError:
    """Map a pyodbc connect error to a category with advice.

    The keyword heuristics are refined from real driver messages, which are
    recorded in docs/IBMI_NOTES.md. The raw SQLSTATE and (scrubbed) driver
    message are always included so nothing is hidden by a wrong guess.
    """
    args = getattr(exc, "args", ())
    sqlstate = str(args[0]) if len(args) > 1 else ""
    message = settings.scrub(str(args[1] if len(args) > 1 else exc))
    low = message.lower()

    if sqlstate == "IM002" or "can't open lib" in low or "file not found" in low:
        category = "driver_missing"
    elif settings.ssl and any(k in low for k in ("certificate", "cert ", "x509", "x.509")):
        category = "tls_certificate"
    elif settings.ssl and any(k in low for k in ("ssl", "tls", "gsk", "handshake")):
        category = "tls_handshake"
    elif any(k in low for k in ("password", "user id", "user profile", "cwbsy")):
        category = "auth"
    elif sqlstate.startswith("08"):
        category = "connection"
    else:
        category = "connect_failed"

    return ProbeError(
        category,
        f"{_ADVICE[category]}\n  SQLSTATE: {sqlstate or '-'}\n  driver message: {message}",
    )


# --- Queries ----------------------------------------------------------------


def _plain(value: Any) -> Any:
    if isinstance(value, str):
        return value.rstrip()
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)


def run_query(conn, label: str, sql: str, params: tuple = ()) -> dict[str, Any]:
    """Run one read-only query. Errors are captured, never raised."""
    import pyodbc

    result: dict[str, Any] = {"label": label, "sql": sql, "params": list(params)}
    try:
        cursor = conn.cursor()
        try:
            cursor.execute(sql, params)
            columns = [col[0] for col in cursor.description]
            rows = [dict(zip(columns, map(_plain, row), strict=True)) for row in cursor.fetchall()]
        finally:
            cursor.close()
    except pyodbc.Error as exc:
        args = exc.args
        result.update(
            ok=False,
            sqlstate=str(args[0]) if len(args) > 1 else "",
            message=str(args[1] if len(args) > 1 else exc),
        )
        return result
    result.update(ok=True, rows=rows)
    return result


# --- Output -----------------------------------------------------------------


def print_query(result: dict[str, Any]) -> None:
    print(f"\n# {result['label']}")
    if not result["ok"]:
        print(f"  unavailable: {result['sqlstate']} {result['message']}")
        return
    if not result["rows"]:
        print("  (no rows)")
    for row in result["rows"]:
        print("  " + ", ".join(f"{key}={value!r}" for key, value in row.items()))


def write_result(name: str, data: dict[str, Any], settings: Settings) -> Path:
    """Store a probe result as JSON under test-results/probes/ (gitignored)."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    path = RESULTS_DIR / f"{name}-{stamp}.json"
    payload = {"probe": name, "utc": stamp, "host": settings.host, "ssl": settings.ssl, **data}
    path.write_text(settings.scrub(json.dumps(payload, indent=2, ensure_ascii=False)) + "\n")
    return path
