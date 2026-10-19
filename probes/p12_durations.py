"""Probe 12: durations (DurationField as BIGINT microseconds).

Read-only (SYSDUMMY1). Checks:
- TIMESTAMP + n MICROSECONDS for large n (10000 days, ~31 years, ~300 years,
  the BIGINT maximum) and whether splitting into DAYS + MICROSECONDS lifts a
  limit; near year 1 and year 9999; negative n;
- exact subtraction in microseconds with DAYS() / MIDNIGHT_SECONDS() /
  MICROSECOND() for timestamps, dates and times, over multi-month and
  multi-year spans, negative results and the timestamp range edges;
  compared with Python's own arithmetic;
- TIMESTAMPDIFF for comparison only (the backend must not use it).
Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

from _common import Settings

NEEDS_CONNECTION = True

DUMMY = "FROM SYSIBM.SYSDUMMY1"
_SQLCODE = re.compile(r"\((-\d+)\)")
DAY_US = 86_400_000_000
BIGINT_MAX = 2**63 - 1


def us(delta: dt.timedelta) -> int:
    return (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds


def plus_microseconds(n: str) -> str:
    return f"CAST(? AS TIMESTAMP) + {n} MICROSECONDS"


def plus_split(n: str) -> str:
    """Whole days and the remaining microseconds (same sign, truncated division)."""
    return f"CAST(? AS TIMESTAMP) + INTEGER({n} / {DAY_US}) DAYS + MOD({n}, {DAY_US}) MICROSECONDS"


def timestamp_diff(a: str, b: str) -> str:
    return (
        f"(BIGINT(DAYS({a}) - DAYS({b})) * {DAY_US} "
        f"+ BIGINT(MIDNIGHT_SECONDS({a}) - MIDNIGHT_SECONDS({b})) * 1000000 "
        f"+ (MICROSECOND({a}) - MICROSECOND({b})))"
    )


def date_diff(a: str, b: str) -> str:
    return f"(BIGINT(DAYS({a}) - DAYS({b})) * {DAY_US})"


def time_diff(a: str, b: str) -> str:
    return f"(BIGINT(MIDNIGHT_SECONDS({a}) - MIDNIGHT_SECONDS({b})) * 1000000)"


BASE = dt.datetime(2026, 10, 19, 12, 30, 45, 123456)
ADDITIONS = [
    ("10000 days", BASE, us(dt.timedelta(days=10_000))),
    ("10000 days back", BASE, -us(dt.timedelta(days=10_000))),
    ("1 day + 1 us", BASE, DAY_US + 1),
    ("-1 us", BASE, -1),
    ("10**15 - 1 us", BASE, 10**15 - 1),
    ("~31 years (10**15 us)", BASE, 10**15),
    ("~300 years (10**16 us)", BASE, 10**16),
    ("year 1 + 1 day", dt.datetime(1, 1, 1), DAY_US),
    ("year 9999 - 1 day", dt.datetime(9999, 12, 31, 23, 59, 59, 999999), -DAY_US),
    (
        "year 1 to 9999 (max span)",
        dt.datetime(1, 1, 1),
        us(dt.datetime(9999, 12, 31) - dt.datetime(1, 1, 1)),
    ),
    ("BIGINT max", BASE, BIGINT_MAX),
]
TIMESTAMP_DIFFS = [
    ("multi-month", dt.datetime(2026, 3, 31, 23, 0, 0, 1), dt.datetime(2026, 1, 31, 1, 0, 0, 2)),
    (
        "multi-year with leap days",
        dt.datetime(2028, 3, 1),
        dt.datetime(2019, 2, 28, 0, 0, 0, 500000),
    ),
    ("negative", dt.datetime(2020, 1, 1), dt.datetime(2026, 10, 19, 12, 0, 0, 1)),
    ("year 1 to year 9999", dt.datetime(9999, 12, 31, 23, 59, 59, 999999), dt.datetime(1, 1, 1)),
    ("same day, microseconds", dt.datetime(2026, 1, 1, 0, 0, 0, 1), dt.datetime(2026, 1, 1)),
]
DATE_DIFFS = [
    ("months", dt.date(2026, 5, 31), dt.date(2026, 2, 28)),
    ("negative years", dt.date(2001, 1, 1), dt.date(2026, 10, 19)),
    ("year 1 to 9999", dt.date(9999, 12, 31), dt.date(1, 1, 1)),
]
TIME_DIFFS = [
    ("positive", dt.time(23, 59, 59), dt.time(0, 0, 1)),
    ("negative", dt.time(6, 0), dt.time(18, 30, 15)),
]


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


def line(ok: bool, got: Any, want: Any) -> str:
    if not ok:
        return f"error {got}"
    return ("ok" if got == want else f"WRONG (want {want!r})") + f": {got!r}"


def python_sum(start: dt.datetime, n: int) -> Any:
    try:
        return start + dt.timedelta(microseconds=n)
    except OverflowError:
        return "out of range"


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {}

    def record(key: str, value: str) -> None:
        results[key] = value
        print(f"  {key:<62} {value}")

    print("\n# TIMESTAMP + n MICROSECONDS, and split into DAYS + MICROSECONDS")
    for label, start, n in ADDITIONS:
        want = python_sum(start, n)
        for form, build in (("microseconds", plus_microseconds), ("split", plus_split)):
            sql = f"SELECT {build('CAST(? AS BIGINT)')} {DUMMY}"
            ok, got = attempt(conn, sql, _params(build, start, n))
            record(f"{form}: {label} (n={n})", line(ok, got, want))

    print("\n# DATE / TIME + duration, duration * number")
    split = (
        f"INTEGER(CAST(? AS BIGINT) / {DAY_US}) DAYS "
        f"+ MOD(CAST(? AS BIGINT), {DAY_US}) MICROSECONDS"
    )
    n = us(dt.timedelta(days=40, hours=25, microseconds=7))
    day = dt.date(2026, 1, 31)
    ok, got = attempt(conn, f"SELECT TIMESTAMP(CAST(? AS DATE)) + {split} {DUMMY}", (day, n, n))
    record(
        "TIMESTAMP(DATE) + split",
        line(ok, got, dt.datetime.combine(day, dt.time()) + dt.timedelta(microseconds=n)),
    )
    want = dt.datetime.combine(day, dt.time()) + dt.timedelta(microseconds=n)
    for form in (
        "CAST(CAST(? AS DATE) AS TIMESTAMP(6))",
        "TIMESTAMP(CAST(? AS DATE), TIME('00:00:00'))",
    ):
        ok, got = attempt(conn, f"SELECT {form} + {split} {DUMMY}", (day, n, n))
        record(f"{form} + split", line(ok, got, want))
    ok, got = attempt(conn, f"SELECT CAST(? AS DATE) + {split} {DUMMY}", (day, n, n))
    record("DATE + split (no TIMESTAMP())", line(ok, got, None))
    clock = dt.time(23, 30)
    ok, got = attempt(
        conn,
        f"SELECT TIME(TIMESTAMP(DATE('2000-01-01'), CAST(? AS TIME)) + {split}) {DUMMY}",
        (clock, n, n),
    )
    want = (dt.datetime.combine(dt.date(2000, 1, 1), clock) + dt.timedelta(microseconds=n)).time()
    record(
        "TIME + split (through a timestamp, wraps at 24 h)",
        line(ok, got, want.replace(microsecond=0)),
    )
    ok, got = attempt(conn, f"SELECT CAST(? AS TIME) + {split} {DUMMY}", (clock, n, n))
    record("TIME + split directly", line(ok, got, None))
    for factor, sql_factor in (
        (3.2, "CAST(? AS DOUBLE)"),
        ("2", "CAST(? AS DECIMAL(1, 0))"),
        (2, "CAST(? AS INTEGER)"),
    ):
        ok, got = attempt(
            conn, f"SELECT BIGINT(CAST(? AS BIGINT) * {sql_factor}) {DUMMY}", (n, factor)
        )
        record(f"BIGINT(duration * {factor!r})", line(ok, got, int(n * float(factor))))
        ok, got = attempt(
            conn, f"SELECT BIGINT(CAST(? AS BIGINT) / {sql_factor}) {DUMMY}", (n, factor)
        )
        record(f"BIGINT(duration / {factor!r})", line(ok, got, int(n / float(factor))))

    print("\n# exact subtraction in microseconds")
    for label, a, b in TIMESTAMP_DIFFS:
        ok, got = attempt(
            conn,
            f"SELECT {timestamp_diff('CAST(? AS TIMESTAMP)', 'CAST(? AS TIMESTAMP)')} {DUMMY}",
            (a, b, a, b, a, b),
        )
        record(f"timestamp - timestamp: {label}", line(ok, got, us(a - b)))
        ok, got = attempt(
            conn,
            f"SELECT TIMESTAMPDIFF(1, CHAR(CAST(? AS TIMESTAMP) - CAST(? AS TIMESTAMP))) {DUMMY}",
            (a, b),
        )
        record(f"  (TIMESTAMPDIFF for comparison): {label}", line(ok, got, us(a - b)))
    for label, a, b in DATE_DIFFS:
        ok, got = attempt(
            conn, f"SELECT {date_diff('CAST(? AS DATE)', 'CAST(? AS DATE)')} {DUMMY}", (a, b)
        )
        record(f"date - date: {label}", line(ok, got, us(a - b)))
    for label, a, b in TIME_DIFFS:
        ok, got = attempt(
            conn, f"SELECT {time_diff('CAST(? AS TIME)', 'CAST(? AS TIME)')} {DUMMY}", (a, b)
        )
        want = us(
            dt.datetime.combine(dt.date(2000, 1, 1), a)
            - dt.datetime.combine(dt.date(2000, 1, 1), b)
        )
        record(f"time - time: {label}", line(ok, got, want))
    return results


def _params(build, start: dt.datetime, n: int) -> tuple:
    """One TIMESTAMP marker, then one BIGINT marker per use of n."""
    return (start, *([n] * build("X").count("X")))
