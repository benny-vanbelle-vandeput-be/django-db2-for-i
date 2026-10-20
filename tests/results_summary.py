"""The counts of a test run as JSON, for scripts/update_test_status.py.

``pytest --results-summary=test-results/<django>/sets/<set>.json`` (the nox
sessions pass it) writes one file per run: the four counts of README's test
status tables, when the run finished and with which Python and Django. The
file name says which test set it is (scripts/update_test_status.py, SETS).
"""

from __future__ import annotations

import datetime as dt
import json
import platform
from pathlib import Path


def counts_from(stats: dict) -> dict[str, int]:
    """pytest's terminal stats -> passed / skipped / expected failures / failed."""

    def count(key: str) -> int:
        return len([report for report in stats.get(key, []) if report.when in ("call", "setup")])

    return {
        "passed": count("passed"),
        "skipped": count("skipped"),
        "expected_failures": count("xfailed"),
        # An unexpected pass of a strict xfail is reported as failed already.
        "failed": count("failed") + count("error") + count("xpassed"),
    }


def counts_from_coverage(coverage: dict[str, dict[str, int]]) -> dict[str, int]:
    """The corpus replay per entry: identical SQL passed, not replayed skipped."""
    replayed = sum(c["replayed"] for c in coverage.values())
    mismatches = sum(c.get("mismatches", 0) for c in coverage.values())
    return {
        "passed": replayed - mismatches,
        "skipped": sum(c["not_loadable"] + c.get("not_replayable", 0) for c in coverage.values()),
        "expected_failures": 0,
        "failed": mismatches,
    }


def write(path: Path, counts: dict[str, int], now: dt.datetime | None = None) -> None:
    from django_db2_for_i.compat import DJANGO_SERIES

    finished = (now or dt.datetime.now(dt.UTC)).strftime("%Y-%m-%d %H:%M:%S UTC")
    data = {
        **counts,
        "django": DJANGO_SERIES,
        "python": platform.python_version(),
        "finished": finished,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
