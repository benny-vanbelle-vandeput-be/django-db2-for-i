"""Probe 07: long string parameters and the maximum NVARCHAR length in a cast.

Read-only (VALUES / SYSDUMMY1). Prints one compact line per statement (no
values):

1. ``CAST(? AS NVARCHAR(n))`` with a one-character parameter for n around
   the expected limits: accepted, or the SQLCODE.
2. For parameter lengths around 16K and 32K units, ASCII ('x') and a
   two-byte UTF-8 character ('é'): the CHARACTER_LENGTH the server sees
   through ``CAST(? AS DBCLOB(1M))`` and through ``CAST(? AS NVARCHAR(n))``,
   compared with the length sent; and whether the value read back equals it.
"""

from __future__ import annotations

import re
from typing import Any

from _common import Settings

NEEDS_CONNECTION = True

DUMMY = "FROM SYSIBM.SYSDUMMY1"
CAST_LENGTHS = (16000, 16368, 16369, 16370, 16371, 16380, 16381, 16382, 16383, 16384, 32739, 32740)
PARAM_LENGTHS = (8000, 16000, 16368, 16370, 16371, 16381, 16382, 16383, 16384, 16385, 20000, 32768)
_SQLCODE = re.compile(r"\((-\d+)\)")


def attempt(conn, sql: str, params: tuple) -> tuple[str, Any]:
    import pyodbc

    cursor = conn.cursor()
    try:
        cursor.execute(sql, params)
        return "ok", cursor.fetchone()
    except pyodbc.Error as exc:
        message = str(exc.args[1] if len(exc.args) > 1 else exc)
        match = _SQLCODE.search(message)
        code = match.group(1) if match else (exc.args[0] if exc.args else "?")
        return f"error {code}", re.sub(r"^\[[^\]]*\]\s*(\[[^\]]*\])*", "", message)[:90]
    finally:
        cursor.close()


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {"casts": {}, "params": {}}
    print("\n# CAST(? AS NVARCHAR(n)) with a 1-character parameter")
    for n in CAST_LENGTHS:
        state, detail = attempt(
            conn, f"SELECT CHARACTER_LENGTH(CAST(? AS NVARCHAR({n}))) {DUMMY}", ("x",)
        )
        results["casts"][n] = state if state == "ok" else f"{state}: {detail}"
        print(f"  NVARCHAR({n}): {results['casts'][n]}")

    print("\n# parameter length sent vs CHARACTER_LENGTH seen by the server")
    for char in ("x", "é"):
        for length in PARAM_LENGTHS:
            text = char * length
            for target in ("DBCLOB(1M)", "NVARCHAR(16370)"):
                state, row = attempt(
                    conn,
                    f"SELECT CHARACTER_LENGTH(CAST(? AS {target})), CAST(? AS {target}) {DUMMY}",
                    (text, text),
                )
                if state == "ok":
                    seen, value = row
                    line = f"seen {seen}, round trip {'equal' if value == text else 'DIFFERENT'}"
                else:
                    line = f"{state}: {row}"
                key = f"{char!r} x {length} as {target}"
                results["params"][key] = line
                print(f"  {key}: {line}")
    return results
