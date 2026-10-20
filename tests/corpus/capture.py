"""Capture hook for the offline query corpus (docs/proposals/offline-query-corpus.md).

Enabled only by the environment variable DB2I_CORPUS_CAPTURE (a file path),
which ``scripts/run_django_tests.py --capture`` sets; the runner settings then
use ``CaptureRunner`` (tests/django_settings/settings_runtests_pub400.py).
Never part of the backend package.

Before Django executes a statement (``SQLCompiler.execute_sql`` and
``SQLInsertCompiler.execute_sql``), the hook pickles the compiler's query and
compiles a fresh copy of it (``pickle.loads`` + ``get_compiler`` + ``as_sql``),
exactly as the offline replay does; the live compiler is never touched. While
it compiles that copy, executing anything is blocked: some compilers run SQL
while compiling (an update with related updates selects the pks first), which
would add a statement to the test; such a statement is counted as
``needs_database`` and not recorded, so the hook never executes SQL itself. It
records the test id, the compiler class, that SQL with its tagged params, the
pickle, and the USE_TZ / TIME_ZONE in effect. Statements of a test are kept
only if the test passed; those run by ``TestCase.setUpClass`` (setUpTestData)
are kept if a test of that class passed. Every error of the hook itself is
caught and counted, so it never changes a test's outcome.

The raw capture is one JSON object per line: a header (``{"header": {...}}``:
Django version and commit, label, verification level, date, counts), then the
kept records. ``scripts/build_corpus.py`` turns raw captures into corpus files.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import os
import pickle
import unittest
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path
from typing import Any

ENV = "DB2I_CORPUS_CAPTURE"
COMMIT_ENV = "DB2I_DJANGO_COMMIT"
LABEL_ENV = "DB2I_CORPUS_LABEL"
PICKLE_PROTOCOL = 5


def class_key(cls: type) -> str:
    return f"{cls.__module__}.{cls.__qualname__}"


def test_class_key(test: Any) -> str:
    return class_key(type(test))


class Recorder:
    """Collects the statements of the running test; keeps those of passing tests."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.context: str | None = None  # a test id, or "<class>.setUpTestData"
        self.pending: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.class_records: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.passed_classes: set[str] = set()
        self.kept: list[dict[str, Any]] = []
        self.counts = {
            "recorded": 0,
            "unpicklable": 0,
            "not_compiled": 0,
            "needs_database": 0,
            "unencodable": 0,
        }
        # Why statements were not recorded: "<count kind>: <exception>" -> count.
        self.reasons: dict[str, int] = defaultdict(int)
        self.compiling = False
        self.level = "unknown"

    # -- recording ------------------------------------------------------------------------

    def record(self, compiler: Any) -> None:
        if self.context is None:
            return
        try:
            self._record(compiler)
        except Exception as exc:  # the hook never changes a test's outcome
            self._skip("not_compiled", exc)

    def _skip(self, kind: str, exc: BaseException) -> None:
        self.counts[kind] += 1
        self.reasons[f"{kind}: {type(exc).__name__}: {str(exc)[:120]}"] += 1

    def _record(self, compiler: Any) -> None:
        from django.conf import settings

        from tests.corpus.store import encode_query, encode_statements

        try:
            pickled = pickle.dumps(compiler.query, protocol=PICKLE_PROTOCOL)
        except Exception as exc:
            self._skip("unpicklable", exc)
            return
        self.compiling = True
        try:
            copy = pickle.loads(pickled)
            fresh = copy.get_compiler(using=compiler.using, connection=compiler.connection)
            compiled = fresh.as_sql()
        except NeedsDatabase as exc:
            self._skip("needs_database", exc)
            return
        except Exception as exc:
            self._skip("not_compiled", exc)
            return
        finally:
            self.compiling = False
        statements = compiled if isinstance(compiled, list) else [compiled]
        try:
            sql = encode_statements(statements)
        except (TypeError, ValueError) as exc:
            self._skip("unencodable", exc)
            return
        self.counts["recorded"] += 1
        record = {
            "tests": [self.context],
            "compiler": type(compiler).__name__,
            "sql": sql,
            "query": encode_query(pickled),
            "settings": {"USE_TZ": bool(settings.USE_TZ), "TIME_ZONE": str(settings.TIME_ZONE)},
        }
        if self.context.endswith(".setUpTestData"):
            self.class_records[self.context.removesuffix(".setUpTestData")].append(record)
        else:
            self.pending[self.context].append(record)

    # -- outcomes -------------------------------------------------------------------------

    def start(self, test_id: str) -> None:
        self.context = test_id

    def passed(self, test: Any) -> None:
        self.kept.extend(self.pending.pop(test.id(), []))
        self.passed_classes.add(test_class_key(test))

    def not_passed(self, test: Any) -> None:
        self.pending.pop(test.id(), None)

    def stop(self) -> None:
        self.context = None

    def finish(self) -> None:
        for key, records in self.class_records.items():
            if key in self.passed_classes:
                self.kept.extend(records)
        self.class_records.clear()
        self.write()

    def write(self) -> None:
        import django

        header = {
            "django": django.get_version(),
            "django_commit": os.environ.get(COMMIT_ENV, "unknown"),
            "label": os.environ.get(LABEL_ENV, ""),
            "level": self.level,
            "date": f"{dt.datetime.now(dt.UTC):%Y-%m-%d}",
            "counts": dict(self.counts, kept=len(self.kept)),
            "reasons": dict(sorted(self.reasons.items())),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as out:
            out.write(json.dumps({"header": header}, sort_keys=True) + "\n")
            for record in self.kept:
                out.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")


class NeedsDatabase(Exception):
    """Raised inside the hook's own compile when the compiler would execute SQL."""


def wrapped_execute_sql(original, recorder: Recorder):
    """``execute_sql`` that records first, and never executes during the hook's own compile."""

    def execute_sql(self, *args, **kwargs):
        if recorder.compiling:  # the hook's own compile of a copy: never execute
            raise NeedsDatabase("compiling the query executes SQL")
        recorder.record(self)
        return original(self, *args, **kwargs)

    execute_sql.__wrapped__ = original
    return execute_sql


RECORDER: Recorder | None = None


_ORIGINALS: dict[tuple[type, str], Any] = {}


def install(path: Path) -> Recorder:
    """Wrap the compilers and TestCase.setUpClass; idempotent (see uninstall())."""
    global RECORDER
    if RECORDER is not None:
        return RECORDER
    from django.db.models.sql import compiler
    from django.test import TestCase

    RECORDER = recorder = Recorder(path)

    for cls in (compiler.SQLCompiler, compiler.SQLInsertCompiler):
        _ORIGINALS[(cls, "execute_sql")] = cls.__dict__["execute_sql"]
        cls.execute_sql = wrapped_execute_sql(cls.__dict__["execute_sql"], recorder)

    _ORIGINALS[(TestCase, "setUpClass")] = TestCase.__dict__["setUpClass"]
    original_setup = TestCase.__dict__["setUpClass"].__func__

    def setUpClass(cls):
        previous = recorder.context
        recorder.context = f"{class_key(cls)}.setUpTestData"
        try:
            original_setup(cls)
        finally:
            recorder.context = previous

    TestCase.setUpClass = classmethod(setUpClass)
    return recorder


def uninstall() -> None:
    """Restore what install() wrapped (for tests; a capture run keeps the hook)."""
    global RECORDER
    for (cls, name), original in _ORIGINALS.items():
        setattr(cls, name, original)
    _ORIGINALS.clear()
    RECORDER = None


@contextlib.contextmanager
def installed(path: Path) -> Iterator[Recorder]:
    recorder = install(path)
    try:
        yield recorder
    finally:
        uninstall()


class CaptureResultMixin:
    """unittest result hooks: which test is running, and whether it passed."""

    def startTest(self, test):
        super().startTest(test)
        RECORDER.start(test.id())

    def stopTest(self, test):
        RECORDER.stop()
        super().stopTest(test)

    def addSuccess(self, test):
        super().addSuccess(test)
        RECORDER.passed(test)

    def addError(self, test, err):
        super().addError(test, err)
        RECORDER.not_passed(test)

    def addFailure(self, test, err):
        super().addFailure(test, err)
        RECORDER.not_passed(test)

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        RECORDER.not_passed(test)

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        RECORDER.not_passed(test)

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        RECORDER.not_passed(test)

    def stopTestRun(self):
        super().stopTestRun()
        RECORDER.finish()


def _level() -> str:
    """The verification level of the capture (as the golden stamps; never guessed)."""
    import django
    from django.db import connection

    from tests.golden import verification_level

    capabilities = connection.capabilities
    return verification_level(
        capabilities.release_name,
        getattr(capabilities, "technology_refresh", None) or "unknown",
        getattr(capabilities, "db2_ptf_group", None) or "unknown",
        django.get_version(),
    )


try:
    from django.test.runner import DiscoverRunner
except ImportError:  # pragma: no cover (Django is always installed where this runs)
    DiscoverRunner = object  # type: ignore[assignment,misc]


class CaptureRunner(DiscoverRunner):
    """Django's DiscoverRunner with the capture result; used when DB2I_CORPUS_CAPTURE is set."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        install(Path(os.environ[ENV]))

    def setup_databases(self, **kwargs):
        config = super().setup_databases(**kwargs)
        try:
            RECORDER.level = _level()
        except Exception:
            RECORDER.level = "unknown"
        return config

    def get_resultclass(self):
        base = super().get_resultclass() or unittest.TextTestResult
        return type("CaptureResult", (CaptureResultMixin, base), {})
