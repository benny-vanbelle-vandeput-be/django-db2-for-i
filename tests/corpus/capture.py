"""Capture hook for the offline query corpus (docs/proposals/offline-query-corpus.md).

Enabled only by the environment variable DB2I_CORPUS_CAPTURE (a file path),
which ``scripts/run_django_tests.py --capture`` sets; the runner settings then
use ``CaptureRunner`` (tests/django_settings/settings_runtests_pub400.py).
Never part of the backend package.

Before Django executes a statement (``SQLCompiler.execute_sql`` and
``SQLInsertCompiler.execute_sql``), the hook pickles the compiler's query and
compiles a fresh copy of it (``pickle.loads`` + ``get_compiler`` + ``as_sql``),
exactly as the offline replay does; the live compiler is never touched. It
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

import datetime as dt
import json
import os
import pickle
import unittest
from collections import defaultdict
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
        self.counts = {"recorded": 0, "unpicklable": 0, "not_compiled": 0, "unencodable": 0}
        self.level = "unknown"

    # -- recording ------------------------------------------------------------------------

    def record(self, compiler: Any) -> None:
        if self.context is None:
            return
        try:
            self._record(compiler)
        except Exception:  # the hook never changes a test's outcome
            self.counts["not_compiled"] += 1

    def _record(self, compiler: Any) -> None:
        from django.conf import settings

        from tests.corpus.store import encode_query, encode_statements

        try:
            pickled = pickle.dumps(compiler.query, protocol=PICKLE_PROTOCOL)
        except Exception:
            self.counts["unpicklable"] += 1
            return
        try:
            copy = pickle.loads(pickled)
            fresh = copy.get_compiler(using=compiler.using, connection=compiler.connection)
            compiled = fresh.as_sql()
        except Exception:
            self.counts["not_compiled"] += 1
            return
        statements = compiled if isinstance(compiled, list) else [compiled]
        try:
            sql = encode_statements(statements)
        except (TypeError, ValueError):
            self.counts["unencodable"] += 1
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
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as out:
            out.write(json.dumps({"header": header}, sort_keys=True) + "\n")
            for record in self.kept:
                out.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")


RECORDER: Recorder | None = None


def install(path: Path) -> Recorder:
    """Wrap the compilers and TestCase.setUpClass; idempotent."""
    global RECORDER
    if RECORDER is not None:
        return RECORDER
    from django.db.models.sql import compiler
    from django.test import TestCase

    RECORDER = recorder = Recorder(path)

    def wrap(cls: type) -> None:
        original = cls.__dict__["execute_sql"]

        def execute_sql(self, *args, **kwargs):
            recorder.record(self)
            return original(self, *args, **kwargs)

        execute_sql.__wrapped__ = original
        cls.execute_sql = execute_sql

    wrap(compiler.SQLCompiler)
    wrap(compiler.SQLInsertCompiler)

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
