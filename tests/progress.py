"""The own IBM i tests save their results as they go, so an interruption does not lose hours.

``pytest --progress=PATH`` (the ``ibmi`` nox session passes it) appends one JSON
line per finished test to PATH, after a line that starts the run's part. With
``--resume`` (the session passes it too), a new run on **the same code** continues
an earlier run that did not fully pass: the tests that **passed** are skipped;
every other test runs again (failed, errored, skipped, expected failures, and the
ones not reached). Its counts for ``--results-summary`` add the passed tests of
the earlier parts, and the summary says the run was resumed, in how many parts, and
on which commit (all parts on the same one).

"The same code" (the run's key):
- the same commit (``DB2I_RUN_COMMIT``, read on the host by scripts/pub400.sh:
  in a git worktree the container cannot read the repository);
- no uncommitted or new files (``DB2I_RUN_TREE=clean``, the same way);
- the same Django version (``django.__version__``, not only the series);
- the same settings: the settings module and the ``DB2I_*`` connection settings,
  the password and anything named like a secret left out entirely (``is_secret``:
  nothing derived from them, not even a hash; only the key's hash is stored);
- the same selection (the marker expression and the arguments).
Anything missing or different starts afresh, and says why.

Before a resumed part runs, the leftover tables of the interrupted test are dropped
(tests/ibmi/conftest.py, the same logic as bin/ibmi-cleanup under its standing
approval: only tables on the cleanup list, only in the marked library).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path

import pytest

# The only outcome a resumed part skips: every other test runs again.
SKIPPED_ON_RESUME = "passed"
# Never part of the key, not even hashed: the password and anything named like a secret.
SECRET_NAME_PARTS = ("PASSWORD", "PWD", "SECRET", "TOKEN", "KEY")


def is_secret(name: str) -> bool:
    return any(part in name.upper() for part in SECRET_NAME_PARTS)


class Progress:
    """One run of the own IBM i tests, possibly in several parts."""

    def __init__(self, path: Path, key: str | None, why: str, resume: bool):
        self.path = path
        records = load(path)
        self.passed, self.parts = resumable(records, key) if resume else ({}, 0)
        self.part = self.parts + 1
        self.key, self.why = key, why
        path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = path.open("a" if self.parts else "w")
        self._write({"part": self.part, "key": key, "why": why, "started": now()})

    @property
    def resuming(self) -> bool:
        return self.parts > 0

    def _write(self, record: dict) -> None:
        self.handle.write(json.dumps(record) + "\n")
        self.handle.flush()

    def record(self, nodeid: str, outcome: str) -> None:
        if not self.handle.closed:
            self._write({"nodeid": nodeid, "outcome": outcome})

    def end(self, all_passed: bool) -> None:
        self._write({"end": "all passed" if all_passed else "not all passed"})
        self.handle.close()

    def summary(self, commit: str | None) -> dict:
        return {"parts": self.part, "commit": commit, "resumed": self.resuming}


def now() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def run_key(environ: dict, django_version: str, settings_module: str, selection: str):
    """(key, why): the key of "the same code", or None and why there is none."""
    commit = environ.get("DB2I_RUN_COMMIT", "")
    if len(commit) != 40:
        return None, "the commit is unknown (not run through scripts/pub400.sh)"
    if environ.get("DB2I_RUN_TREE") != "clean":
        return None, "the working tree has uncommitted or new files"
    settings = sorted(
        (name, value)
        for name, value in environ.items()
        if name.startswith("DB2I_")
        and not is_secret(name)
        and name not in ("DB2I_RUN_COMMIT", "DB2I_RUN_TREE")
    )
    digest = hashlib.sha256(
        json.dumps([commit, django_version, settings_module, settings, selection]).encode()
    )
    return digest.hexdigest(), f"commit {commit[:12]}, clean, Django {django_version}"


def load(path: Path) -> list[dict]:
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return []
    records = []
    for line in lines:
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            break  # a line cut off by the interruption: what came before counts
    return records


def resumable(records: list[dict], key: str | None) -> tuple[dict[str, str], int]:
    """({passed node id: "passed"}, the number of earlier parts) of an earlier run
    with this key that did not fully pass; ({}, 0) if there is nothing to resume."""
    parts = [r for r in records if "part" in r]
    if key is None or not parts or any(p.get("key") != key for p in parts):
        return {}, 0
    if any(r.get("end") == "all passed" for r in records):
        return {}, 0
    outcomes: dict[str, str] = {}
    for record in records:
        if "nodeid" in record:
            outcomes[record["nodeid"]] = record["outcome"]  # the latest part wins
    passed = {node: o for node, o in outcomes.items() if o == SKIPPED_ON_RESUME}
    return passed, len(parts)


def outcome_of(report: pytest.TestReport) -> str | None:
    """One outcome per test: the call, a setup that did not pass, a failed teardown."""
    if report.when == "call" or (report.when == "setup" and not report.passed):
        if hasattr(report, "wasxfail"):
            return "xfailed" if report.skipped else "failed"
        if report.when == "setup" and report.failed:
            return "error"
        return report.outcome
    if report.when == "teardown" and report.failed:
        return "error"
    return None


_ACTIVE: Progress | None = None  # one pytest session per process


def active() -> Progress | None:
    return _ACTIVE


def earlier_counts() -> dict[str, int]:
    """The passed tests of the earlier parts (for --results-summary)."""
    passed = len(_ACTIVE.passed) if _ACTIVE else 0
    return {"passed": passed, "skipped": 0, "expected_failures": 0, "failed": 0}


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("progress")
    group.addoption("--progress", metavar="PATH", help="append each finished test to PATH")
    group.addoption(
        "--resume",
        action="store_true",
        help="with --progress: continue an earlier run on the same code that did not fully pass",
    )


def pytest_configure(config: pytest.Config) -> None:
    global _ACTIVE
    path = config.getoption("--progress")
    if not path:
        return
    import django

    selection = " ".join([config.option.markexpr or "", *config.invocation_params.args])
    settings_module = config.getoption("ds", None) or os.environ.get("DJANGO_SETTINGS_MODULE", "")
    key, why = run_key(os.environ, django.__version__, settings_module, selection)
    _ACTIVE = Progress(Path(path), key, why, config.getoption("--resume"))
    config._progress_owner = True
    if not _ACTIVE.resuming:
        print(f"\nprogress: a new run ({why})")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if not _ACTIVE or not _ACTIVE.resuming:
        return
    done = [item for item in items if item.nodeid in _ACTIVE.passed]
    items[:] = [item for item in items if item.nodeid not in _ACTIVE.passed]
    if done:
        config.hook.pytest_deselected(items=done)
    print(
        f"\nprogress: resumed, part {_ACTIVE.part}; {len(done)} tests that passed in the "
        f"earlier part(s) are skipped, {len(items)} run ({_ACTIVE.why})"
    )


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    outcome = outcome_of(report)
    if _ACTIVE and outcome:
        _ACTIVE.record(report.nodeid, outcome)


def pytest_terminal_summary(terminalreporter, exitstatus, config: pytest.Config) -> None:
    if _ACTIVE and _ACTIVE.resuming:
        commit = os.environ.get("DB2I_RUN_COMMIT", "")
        terminalreporter.write_sep(
            "-",
            f"resumed run: {_ACTIVE.part} parts, all on commit {commit[:12]} "
            f"(clean tree, Django {_ACTIVE.why.rsplit('Django ', 1)[-1]})",
        )


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if _ACTIVE:
        _ACTIVE.end(all_passed=exitstatus == 0)  # the object stays for the summary


def pytest_unconfigure(config: pytest.Config) -> None:
    global _ACTIVE
    if _ACTIVE is not None and getattr(config, "_progress_owner", False):
        _ACTIVE = None
