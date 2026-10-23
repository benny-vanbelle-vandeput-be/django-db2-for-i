"""Probe 08: extracting date/time parts (Django's Extract lookups).

Read-only (SYSDUMMY1). For timestamps, dates and times chosen around ISO week
edges, evaluates the candidate SQL for each Django lookup type (EXTRACT and
the scalar functions YEAR, QUARTER, WEEK_ISO, DAYOFWEEK, DAYOFWEEK_ISO, ...)
and records the value and Python type, or the SQLCODE when Db2 for i rejects
the expression. Also checks the functions on a parameter (CAST(? AS ...)).

Expected values (Python's isocalendar / Django's conventions):
week_day 1 = Sunday .. 7 = Saturday; iso_week_day 1 = Monday .. 7 = Sunday;
week = ISO-8601 week number; iso_year = ISO-8601 week-numbering year.
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
    dt.datetime(2021, 1, 1, 0, 0, 1),  # Friday, ISO 2020-W53
    dt.datetime(2024, 12, 30, 23, 59, 59, 999999),  # Monday, ISO 2025-W01
    dt.datetime(2023, 1, 1, 12, 0, 0),  # Sunday, ISO 2022-W52
    dt.datetime(2026, 10, 17, 6, 7, 8),  # Saturday
]

# lookup type -> candidate SQL templates ({x} is the value expression)
CANDIDATES: dict[str, list[str]] = {
    "year": ["EXTRACT(YEAR FROM {x})", "YEAR({x})"],
    "iso_year": [
        "YEAR({x} + (4 - DAYOFWEEK_ISO({x})) DAYS)",
        "INTEGER(VARCHAR_FORMAT({x}, 'IYYY'))",
    ],
    "quarter": ["QUARTER({x})", "EXTRACT(QUARTER FROM {x})"],
    "month": ["EXTRACT(MONTH FROM {x})", "MONTH({x})"],
    "week": ["WEEK_ISO({x})", "EXTRACT(WEEK FROM {x})"],
    "week_day": ["DAYOFWEEK({x})", "EXTRACT(DOW FROM {x})"],
    "iso_week_day": ["DAYOFWEEK_ISO({x})", "EXTRACT(ISODOW FROM {x})"],
    "day": ["EXTRACT(DAY FROM {x})", "DAY({x})"],
    "hour": ["EXTRACT(HOUR FROM {x})", "HOUR({x})"],
    "minute": ["EXTRACT(MINUTE FROM {x})", "MINUTE({x})"],
    "second": ["EXTRACT(SECOND FROM {x})", "SECOND({x})"],
}
TIME_LOOKUPS = ("hour", "minute", "second")


def expected(value: dt.datetime | dt.date | dt.time, lookup: str) -> int:
    if lookup in TIME_LOOKUPS:
        return getattr(value, lookup)
    iso = value.isocalendar()
    return {
        "year": value.year,
        "iso_year": iso.year,
        "quarter": (value.month - 1) // 3 + 1,
        "month": value.month,
        "week": iso.week,
        "week_day": value.isoweekday() % 7 + 1,
        "iso_week_day": value.isoweekday(),
        "day": value.day,
    }[lookup]


def attempt(conn, sql: str, params: tuple) -> tuple[bool, Any]:
    import pyodbc

    cursor = conn.cursor()
    try:
        cursor.execute(sql, params)
        return True, cursor.fetchone()[0]
    except pyodbc.Error as exc:
        message = str(exc.args[1] if len(exc.args) > 1 else exc)
        code = _SQLCODE.search(message)
        return False, code.group(1) if code else message[:80]
    finally:
        cursor.close()


def run(settings: Settings, conn) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    summary: dict[str, str] = {}
    for lookup, templates in CANDIDATES.items():
        for template in templates:
            mismatches, errors, types = [], [], set()
            for stamp in TIMESTAMPS:
                values = [
                    ("timestamp literal", f"TIMESTAMP('{stamp.isoformat(sep=' ')}')", (), stamp),
                    ("timestamp parameter", "CAST(? AS TIMESTAMP(6))", (stamp,), stamp),
                ]
                if lookup in TIME_LOOKUPS:
                    time = stamp.time().replace(microsecond=0)
                    values.append(("time parameter", "CAST(? AS TIME)", (time,), time))
                else:
                    values.append(
                        ("date parameter", "CAST(? AS DATE)", (stamp.date(),), stamp.date())
                    )
                for kind, expression, params, source in values:
                    sql = f"SELECT {template.format(x=expression)} {DUMMY}"
                    ok, value = attempt(conn, sql, params * template.count("{x}"))
                    want = expected(source, lookup)
                    record = {
                        "lookup": lookup,
                        "template": template,
                        "kind": kind,
                        "source": source.isoformat(),
                        "ok": ok,
                        "value": repr(value),
                        "type": type(value).__name__ if ok else None,
                        "expected": want,
                    }
                    results.append(record)
                    if not ok:
                        errors.append(f"{kind}: {value}")
                    else:
                        types.add(type(value).__name__)
                        if value != want:
                            mismatches.append(f"{kind} {source.isoformat()}: {value!r} != {want}")
            if errors:
                state = "rejected " + ", ".join(sorted(set(errors)))[:90]
            elif mismatches:
                state = f"WRONG ({len(mismatches)}): {mismatches[0]}"
            else:
                state = f"ok ({', '.join(sorted(types))})"
            summary[f"{lookup}: {template}"] = state
            print(f"  {lookup:<13} {template:<42} {state}")
    return {"results": results, "summary": summary}
