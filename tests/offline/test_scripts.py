"""scripts/run_django_tests.py and scripts/update_test_status.py (no server needed)."""

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"scripts_{name}", SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    # Registered first: dataclasses look the module up in sys.modules.
    sys.modules[f"scripts_{name}"] = module
    spec.loader.exec_module(module)
    return module


runner = load("run_django_tests")
status = load("update_test_status")


# --- Runner safety limits ----------------------------------------------------------


@pytest.mark.parametrize(
    ("version", "modules", "message"),
    [
        ("6.1", [], "full Django test suite"),
        ("6.1", ["a", "b", "c", "d"], "at most 3 modules"),
        ("6.1", ["../etc"], "not a test module label"),
        ("6.1", ["basic/tests.py"], "not a test module label"),
        ("6.1", ["."], "not a test module label"),
        ("latest", ["basic"], "invalid Django version"),
    ],
)
def test_runs_that_are_refused(version, modules, message) -> None:
    with pytest.raises(runner.RunRefused, match=message):
        runner.validate(version, modules)


@pytest.mark.parametrize(
    "modules",
    [
        ["basic"],
        ["basic", "transactions"],
        ["basic.tests.ModelTest.test_something"],
        ["a", "b", "c"],
    ],
)
def test_runs_that_are_allowed(modules) -> None:
    runner.validate("6.1", modules)


def test_runtests_command_is_serial_and_noninteractive() -> None:
    command = runner.runtests_command("basic", keepdb=True, verbosity=2)
    assert command[1:] == [
        "runtests.py",
        "--settings=tests.django_settings.settings_runtests_pub400",
        "--parallel=1",
        "--noinput",
        "--verbosity=2",
        "--keepdb",
        "basic",
    ]
    assert "--keepdb" not in runner.runtests_command("basic", keepdb=False, verbosity=2)


def test_scrubber_removes_the_password() -> None:
    scrub = runner.make_scrubber(["S3cret!pw", ""])
    assert scrub("error: S3cret!pw rejected, S3cret!pw") == "error: *** rejected, ***"
    assert runner.make_scrubber([""])("unchanged") == "unchanged"


def test_missing_checkout_is_refused(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    assert runner.main(["6.1", "basic"]) == 2
    assert "git clone --branch stable/6.1.x" in capsys.readouterr().err


def test_main_refuses_without_modules(capsys) -> None:
    assert runner.main(["6.1"]) == 2
    assert "full Django test suite" in capsys.readouterr().err


# --- Log parsing ---------------------------------------------------------------------

HEADER = (
    "# module: basic\n# django: 6.1 (1e01021 2026-10-12)\n# backend: abc1234 2026-10-17\n"
    "# keepdb: yes\n# started: 2026-10-17 18:00:00 UTC\n"
)

OK_LOG = HEADER + (
    "Creating test database for alias 'default'...\n"
    "test_a (basic.tests.ModelTest.test_a) ... ok\n"
    "----------------------------------------------------------------------\n"
    "Ran 60 tests in 12.345s\n\nOK (skipped=3, expected failures=2)\n# exit: 0\n"
)
FAILED_LOG = HEADER.replace("basic", "transactions") + (
    "Ran 80 tests in 30.100s\n\n"
    "FAILED (failures=4, errors=1, skipped=5, expected failures=2, unexpected successes=1)\n"
    "# exit: 1\n"
)
CRASHED_LOG = HEADER + "Traceback (most recent call last):\nImproperlyConfigured: ...\n# exit: 1\n"


def test_parse_ok_summary() -> None:
    result = status.parse_log(OK_LOG, "basic", "6.1")
    assert (result.module, result.django, result.ran, result.outcome) == ("basic", "6.1", 60, "OK")
    assert (result.skipped, result.expected_failures, result.failures) == (3, 2, 0)
    assert result.passed == 55
    assert result.keepdb == "yes" and result.started == "2026-10-17 18:00:00 UTC"


def test_parse_failed_summary() -> None:
    result = status.parse_log(FAILED_LOG, "transactions", "6.1")
    assert result.outcome == "FAILED"
    assert (result.failures, result.errors, result.skipped) == (4, 1, 5)
    assert (result.expected_failures, result.unexpected_successes) == (2, 1)
    assert result.passed == 80 - 4 - 1 - 5 - 2 - 1


def test_parse_log_that_stopped_before_the_summary() -> None:
    result = status.parse_log(CRASHED_LOG, "basic", "6.1")
    assert result.ran is None and result.passed is None
    assert result.outcome == "no summary"


def test_render_and_collect(tmp_path) -> None:
    (tmp_path / "6.1").mkdir()
    (tmp_path / "6.1" / "basic.log").write_text(OK_LOG)
    (tmp_path / "6.1" / "transactions.log").write_text(FAILED_LOG)
    (tmp_path / "probes").mkdir()
    (tmp_path / "probes" / "x.log").write_text("not a test log")
    results = status.collect(tmp_path)
    assert [r.module for r in results] == ["basic", "transactions"]
    text = status.render(results)
    assert "| basic | 6.1 | 60 | 55 | 0 | 0 | 3 | 2 | 0 | OK |" in text
    assert "| transactions | 6.1 | 80 | 67 | 4 | 1 | 5 | 2 | 1 | FAILED |" in text
    assert "`supports_transactions`" in text
    assert "identity restart deferred in TestCase (SQL0910)" in text
    assert "goldens," in text


def test_render_without_runs() -> None:
    assert "No Django test modules have been run yet." in status.render([])
