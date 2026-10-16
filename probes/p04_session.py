"""Probe 04: session behaviour with the connection attributes planned for the backend.

Read-only (VALUES / SYSDUMMY1 only). Uses its own connection attributes, so it
cannot share a run with the other probes:

    nox -s probe -- session

Connection: SQL naming (NAM=0), default library list DBQ=<DB2I_DEFAULT_LIBRARY>,
commit mode *CS (CMT=1), ISO date format (DFT=5), ISO time format (TFT=2),
autocommit off. Reports:
- CURRENT SCHEMA and CURRENT PATH with DBQ set,
- date/time values: the Python types pyodbc returns, and CHAR() renderings,
- which date/time string formats CAST accepts, as literals and as parameters,
- the isolation level of the session (best effort; several sources tried),
- Unicode round trips through NVARCHAR(10), VARCHAR(10) CCSID 1208 and
  VARCHAR(10) CCSID 273 casts: an emoji and exactly 10 / 11 accented
  characters. Note: CAST truncates with a warning, while INSERT into a too
  short column raises an error; the INSERT behaviour is covered by the
  write probe w01_commitment.py.

The transaction is rolled back at the end.
"""

from __future__ import annotations

from typing import Any

from _common import ProbeError, Settings

NEEDS_CONNECTION = True


def connection_attributes(settings: Settings) -> dict[str, str]:
    if not settings.default_library:
        raise ProbeError("config", "DB2I_DEFAULT_LIBRARY is not set", 1)
    return {"NAM": "0", "DBQ": settings.default_library, "CMT": "1", "DFT": "5", "TFT": "2"}


AUTOCOMMIT = False

ACCENTED_10 = "é" * 10
ACCENTED_11 = "é" * 11
EMOJI = "\U0001f600"
UNICODE_CASES = {
    "accented x10": ACCENTED_10,
    "accented x11": ACCENTED_11,
    "emoji x1": EMOJI,
    "emoji x5": EMOJI * 5,
    "emoji x10": EMOJI * 10,
    "mixed a+e-acute+emoji": "aé" + EMOJI,
}
UNICODE_TARGETS = ("NVARCHAR(10)", "VARCHAR(10) CCSID 1208", "VARCHAR(10) CCSID 273")


def values(conn, label: str, sql: str, params: tuple = ()) -> dict[str, Any]:
    """Run one read-only query; record values (repr), Python types and driver messages."""
    import pyodbc

    result: dict[str, Any] = {"label": label, "sql": sql, "params": list(params)}
    cursor = conn.cursor()
    try:
        cursor.execute(sql, params)
        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()
        result.update(
            ok=True,
            rows=[
                {
                    c: {"repr": repr(v), "type": type(v).__name__}
                    for c, v in zip(columns, row, strict=True)
                }
                for row in rows
            ],
            messages=[str(m) for m in getattr(cursor, "messages", []) or []],
        )
    except pyodbc.Error as exc:
        args = exc.args
        result.update(
            ok=False,
            sqlstate=str(args[0]) if len(args) > 1 else "",
            message=str(args[1] if len(args) > 1 else exc),
        )
    finally:
        cursor.close()
    print(f"\n# {label}")
    if not result["ok"]:
        print(f"  error: {result['sqlstate']} {result['message']}")
    else:
        for row in result["rows"]:
            print("  " + ", ".join(f"{c}={d['repr']} ({d['type']})" for c, d in row.items()))
        for message in result["messages"]:
            print(f"  message: {message}")
    return result


def run(settings: Settings, conn) -> dict[str, Any]:
    dummy = "FROM SYSIBM.SYSDUMMY1"
    results = [
        values(
            conn,
            "schema and path",
            f"SELECT CURRENT SCHEMA AS CURRENT_SCHEMA, CURRENT PATH AS CURRENT_PATH {dummy}",
        ),
        values(
            conn,
            "date/time values",
            "SELECT CURRENT DATE AS D, CURRENT TIME AS T, CURRENT TIMESTAMP AS TS, "
            f"CHAR(CURRENT DATE) AS D_CHAR, CHAR(CURRENT TIME) AS T_CHAR, "
            f"CHAR(CURRENT TIMESTAMP) AS TS_CHAR {dummy}",
        ),
        values(
            conn,
            "string to date/time, literals",
            "SELECT CAST('2026-10-17' AS DATE) AS D_ISO, "
            "CAST('13.45.30' AS TIME) AS T_DOTS, CAST('13:45:30' AS TIME) AS T_COLONS, "
            "CAST('2026-10-17 13:45:30.123456' AS TIMESTAMP) AS TS_SPACE, "
            f"CAST('2026-10-17-13.45.30.123456' AS TIMESTAMP) AS TS_DB2 {dummy}",
        ),
        values(
            conn,
            "string to date/time, parameters",
            "SELECT CAST(? AS DATE) AS D_ISO, CAST(? AS TIME) AS T_COLONS, "
            f"CAST(? AS TIMESTAMP) AS TS_SPACE {dummy}",
            ("2026-10-17", "13:45:30", "2026-10-17 13:45:30.123456"),
        ),
        values(conn, "isolation: CURRENT ISOLATION", f"SELECT CURRENT ISOLATION AS ISO {dummy}"),
        values(
            conn,
            "isolation: QSYS2.DB_TRANSACTION_INFO",
            "SELECT * FROM QSYS2.DB_TRANSACTION_INFO WHERE JOB_NAME = QSYS2.JOB_NAME",
        ),
    ]
    # One cast per query, so one failing target does not hide the others.
    for label, text in UNICODE_CASES.items():
        for target in UNICODE_TARGETS:
            results.append(
                values(
                    conn,
                    f"unicode cast {target}: {label}",
                    f"SELECT CAST(? AS {target}) AS V, "
                    f"CHARACTER_LENGTH(CAST(? AS {target})) AS CHARS {dummy}",
                    (text, text),
                )
            )
    conn.rollback()
    return {
        "connection_attributes": {
            k: ("<DB2I_DEFAULT_LIBRARY>" if k == "DBQ" else v)
            for k, v in connection_attributes(settings).items()
        },
        "autocommit": AUTOCOMMIT,
        "unicode_cases": {label: repr(text) for label, text in UNICODE_CASES.items()},
        "queries": results,
    }
