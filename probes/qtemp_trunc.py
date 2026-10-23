"""Probe 11: truncating dates, times and timestamps (Django's Trunc*).

Read-only (SYSDUMMY1). For timestamps around week and year edges, evaluates
TRUNC_TIMESTAMP with each candidate format element per Django kind and
compares the result with Django's convention (computed in Python): year,
quarter, month, week (the Monday of the ISO week), day, hour, minute,
second. Also checks DATE and TIME arguments, typed parameter markers, and
the type of the result. Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

from _common import Settings

NEEDS_CONNECTION = True

DUMMY = "FROM SYSIBM.SYSDUMMY1"
_SQLCODE = re.compile(r"\((-\d+)\)")

TIMESTAMPS = [
    dt.datetime(2005, 7, 28, 13, 45, 30, 123456),  # Thursday
    dt.datetime(2021, 1, 1, 0, 0, 1),  # Friday, ISO week starts 2020-12-28
    dt.datetime(2024, 12, 30, 23, 59, 59, 999999),  # Monday
    dt.datetime(2023, 1, 1, 12, 0, 0),  # Sunday, ISO week starts 2022-12-26
    dt.datetime(2026, 10, 17, 6, 7, 8),  # Saturday
]

# Django kind -> candidate TRUNC_TIMESTAMP format elements
CANDIDATES: dict[str, list[str]] = {
    "year": ["YEAR", "YYYY"],
    "quarter": ["Q"],
    "month": ["MONTH", "MM"],
    "week": ["IW", "WW", "W", "DAY", "D"],
    "day": ["DD", "DDD", "J"],
    "hour": ["HH", "HH24"],
    "minute": ["MI"],
    "second": ["SS"],
}
DATE_KINDS = ("year", "quarter", "month", "week", "day")
TIME_KINDS = ("hour", "minute", "second")


def expected(value: dt.datetime, kind: str) -> dt.datetime:
    """Django's truncation of ``value`` (TruncBase semantics)."""
    if kind == "year":
        return value.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    if kind == "quarter":
        month = 3 * ((value.month - 1) // 3) + 1
        return value.replace(month=month, day=1, hour=0, minute=0, second=0, microsecond=0)
    if kind == "month":
        return value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if kind == "week":
        monday = value - dt.timedelta(days=value.weekday())
        return monday.replace(hour=0, minute=0, second=0, microsecond=0)
    if kind == "day":
        return value.replace(hour=0, minute=0, second=0, microsecond=0)
    if kind == "hour":
        return value.replace(minute=0, second=0, microsecond=0)
    if kind == "minute":
        return value.replace(second=0, microsecond=0)
    return value.replace(microsecond=0)


def attempt(conn, sql: str, params: tuple) -> tuple[bool, Any]:
    import pyodbc

    cursor = conn.cursor()
    try:
        cursor.execute(sql, params)
        return True, cursor.fetchone()[0]
    except pyodbc.Error as exc:
        message = str(exc.args[1] if len(exc.args) > 1 else exc)
        code = _SQLCODE.search(message)
        text = re.sub(r"^(\[[^\]]*\]\s*)+", "", message)
        return False, f"{code.group(1) if code else exc.args[0]}: {text[:100]}"
    finally:
        cursor.close()


def _line(ok: bool, value: Any, want: Any) -> str:
    if not ok:
        return f"error {value}"
    verdict = "ok" if value == want else f"WRONG (want {want!r})"
    return f"{verdict}: {value!r} ({type(value).__name__})"


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {}
    print("\n# TRUNC_TIMESTAMP(TIMESTAMP, format) per kind, against Django's convention")
    for kind, formats in CANDIDATES.items():
        for fmt in formats:
            outcomes = []
            for value in TIMESTAMPS:
                ok, got = attempt(
                    conn, f"SELECT TRUNC_TIMESTAMP(CAST(? AS TIMESTAMP), '{fmt}') {DUMMY}", (value,)
                )
                outcomes.append(
                    "ok"
                    if ok and got == expected(value, kind)
                    else _line(ok, got, expected(value, kind))
                )
            verdict = (
                "all ok" if set(outcomes) == {"ok"} else "; ".join(o for o in outcomes if o != "ok")
            )
            results[f"timestamp {kind} '{fmt}'"] = verdict
            print(f"  {kind:<8} '{fmt}': {verdict}")

    print("\n# DATE argument: DATE(TRUNC_TIMESTAMP(DATE, format))")
    for kind in DATE_KINDS:
        fmt = CANDIDATES[kind][0] if kind != "week" else "IW"
        for value in TIMESTAMPS:
            day = value.date()
            ok, got = attempt(
                conn, f"SELECT DATE(TRUNC_TIMESTAMP(CAST(? AS DATE), '{fmt}')) {DUMMY}", (day,)
            )
            line = _line(ok, got, expected(value, kind).date())
            results[f"date {kind} {day}"] = line
            print(f"  {kind:<8} {day}: {line}")
        ok, got = attempt(conn, f"SELECT TRUNC_TIMESTAMP(CAST(? AS DATE), '{fmt}') {DUMMY}", (day,))
        results[f"date {kind}: result type without DATE()"] = _line(ok, got, got)
        print(f"  {kind:<8} without DATE(): {_line(ok, got, got)}")

    print("\n# TIME argument: TIME(TRUNC_TIMESTAMP(TIMESTAMP(DATE('0001-01-01'), TIME), format))")
    for kind in TIME_KINDS:
        fmt = CANDIDATES[kind][0]
        value = dt.time(13, 45, 30)
        want = expected(dt.datetime.combine(dt.date(1, 1, 1), value), kind).time()
        ok, got = attempt(
            conn,
            "SELECT TIME(TRUNC_TIMESTAMP(TIMESTAMP(DATE('0001-01-01'), CAST(? AS TIME)), "
            f"'{fmt}')) {DUMMY}",
            (value,),
        )
        line = _line(ok, got, want)
        results[f"time {kind}"] = line
        print(f"  {kind:<8}: {line}")
        ok, got = attempt(
            conn, f"SELECT TRUNC_TIMESTAMP(CAST(? AS TIME), '{fmt}') {DUMMY}", (value,)
        )
        results[f"time {kind}: TRUNC_TIMESTAMP(TIME) directly"] = _line(ok, got, got)
        print(f"  {kind:<8} TRUNC_TIMESTAMP(TIME) directly: {_line(ok, got, got)}")

    print("\n# TIME() first: a TIME and a TIMESTAMP argument (TimeField output)")
    for label, value in (("TIME", dt.time(13, 45, 30)), ("TIMESTAMP", TIMESTAMPS[0])):
        sql_type = "TIME" if label == "TIME" else "TIMESTAMP"
        ok, got = attempt(
            conn,
            "SELECT TIME(TRUNC_TIMESTAMP(TIMESTAMP(DATE('0001-01-01'), "
            f"TIME(CAST(? AS {sql_type}))), 'HH')) {DUMMY}",
            (value,),
        )
        results[f"time hour via TIME() of a {label}"] = _line(ok, got, dt.time(13, 0))
        print(f"  {label:<9} {_line(ok, got, dt.time(13, 0))}")

    print("\n# casts")
    value = TIMESTAMPS[0]
    for label, sql, want in (
        ("DATE(TIMESTAMP)", f"SELECT DATE(CAST(? AS TIMESTAMP)) {DUMMY}", value.date()),
        (
            "TIME(TIMESTAMP)",
            f"SELECT TIME(CAST(? AS TIMESTAMP)) {DUMMY}",
            value.time().replace(microsecond=0),
        ),
        (
            "TRUNC_TIMESTAMP(?) untyped",
            f"SELECT TRUNC_TIMESTAMP(?, 'MM') {DUMMY}",
            expected(value, "month"),
        ),
        (
            "TRUNC_TIMESTAMP(NULL)",
            f"SELECT TRUNC_TIMESTAMP(CAST(NULL AS TIMESTAMP), 'MM') {DUMMY}",
            None,
        ),
    ):
        ok, got = attempt(conn, sql, (value,) if "?" in sql else ())
        results[label] = _line(ok, got, want)
        print(f"  {label:<28} {_line(ok, got, want)}")
    return results
