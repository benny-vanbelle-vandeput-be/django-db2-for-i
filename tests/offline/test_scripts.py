"""scripts/run_django_tests.py and scripts/update_test_status.py (no server needed)."""

import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

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
        ("6.1", ["a", "b", "c", "d"], "at most 3 labels"),
        (
            "6.1",
            ["basic", "basic.tests.A.test_a", "basic.tests.A.test_b", "basic.tests.B"],
            "at most 3",
        ),
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


def test_labels_share_the_module_set_and_log_apart(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    assert runner.top_module("basic.tests.ModelTest.test_x") == "basic"
    assert runner.top_module("basic") == "basic"
    assert runner.log_path("6.1", "basic") == tmp_path / "test-results/6.1/basic.log"
    assert (
        runner.log_path("6.1", "basic.tests.ModelTest.test_x")
        == tmp_path / "test-results/6.1/labels/basic.tests.ModelTest.test_x.log"
    )


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
    assert "--debug-sql" not in runner.runtests_command("basic", keepdb=False, verbosity=2)


def test_debug_sql_is_passed_to_runtests() -> None:
    command = runner.runtests_command("basic.tests.T.test_x", False, 2, debug_sql=True)
    assert command[-2:] == ["--debug-sql", "basic.tests.T.test_x"]


def test_debug_sql_output_is_scrubbed_and_recorded(monkeypatch, tmp_path, capsys) -> None:
    """The SQL lines --debug-sql adds go through the scrubber like all output, and
    the header records the option."""
    import io

    secret = "S3cret!pw"

    class FakeProcess:
        stdout = io.StringIO(
            "FAIL: test_x\n"
            f"(0.001) SELECT 1 FROM T WHERE X = '{secret}'; args=('{secret}',)\n"
            "FAILED (failures=1)\n"
        )

        def __init__(self, command, **kwargs):
            assert "--debug-sql" in command

        def wait(self):
            return 1

    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "git_commit", lambda path: "abc1234 2026-10-19")
    monkeypatch.setattr(runner.subprocess, "Popen", FakeProcess)
    scrub = runner.make_scrubber([secret])
    assert runner.run_label("6.1", "basic.tests.T.test_x", False, 2, scrub, debug_sql=True) == 1
    log = (tmp_path / "test-results/6.1/labels/basic.tests.T.test_x.log").read_text()
    assert "# debug-sql: yes" in log
    assert "SELECT 1 FROM T WHERE X = '***'" in log
    assert secret not in log
    assert secret not in capsys.readouterr().out


def test_debug_sql_option_is_accepted() -> None:
    import subprocess as sp

    script = Path(__file__).resolve().parents[2] / "scripts" / "runtests.sh"
    text = script.read_text()
    assert "--clean|--debug-sql|--capture) ;;" in text
    result = sp.run(["sh", str(script), "6.1", "--debug-sql"], capture_output=True, text=True)
    assert result.returncode == 2
    assert "name the test modules" in result.stderr


def test_pub400_script_accepts_only_pub400_sessions_and_keeps_the_mac_awake() -> None:
    import subprocess as sp

    script = Path(__file__).resolve().parents[2] / "scripts" / "pub400.sh"
    for session in ("offline", "lint", "corpus"):
        result = sp.run(["sh", str(script), session], capture_output=True, text=True)
        assert result.returncode == 2
        assert f"refused: {session} does not connect to PUB400" in result.stderr
    result = sp.run(["sh", str(script)], capture_output=True, text=True)
    assert result.returncode == 2
    assert "usage:" in result.stderr
    text = script.read_text()
    assert "pub400|django_tests|release_run|probe|probe_*|ibmi_cleanup) ;;" in text
    assert "caffeinate -i -s" in text
    runtests = (script.parent / "runtests.sh").read_text()
    assert 'exec "$(dirname "$0")/pub400.sh" django_tests "$version" "$@"' in runtests


def test_the_backend_commit_comes_from_the_host_when_given(monkeypatch) -> None:
    monkeypatch.setenv("DB2I_BACKEND_COMMIT", "abc1234 2026-10-20")
    assert runner.backend_commit() == "abc1234 2026-10-20"
    monkeypatch.delenv("DB2I_BACKEND_COMMIT")
    monkeypatch.setattr(runner, "git_commit", lambda path: f"read {path.name}")
    assert runner.backend_commit() == f"read {runner.ROOT.name}"
    script = (SCRIPTS / "pub400.sh").read_text()
    assert "commit=$(git log -1 --format='%h %cs'" in script
    assert 'docker compose run --rm -e DB2I_BACKEND_COMMIT="$commit"' in script


def test_scrubber_removes_the_password() -> None:
    scrub = runner.make_scrubber(["S3cret!pw", ""])
    assert scrub("error: S3cret!pw rejected, S3cret!pw") == "error: *** rejected, ***"
    assert runner.make_scrubber([""])("unchanged") == "unchanged"


def test_missing_checkout_is_refused(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    assert runner.main(["6.1", "basic"]) == 2
    assert "git clone --branch stable/6.1.x" in capsys.readouterr().err


def test_log_header_records_the_python_version(monkeypatch, tmp_path, capsys) -> None:
    import io
    import platform

    class FakeProcess:
        stdout = io.StringIO("Ran 0 tests in 0.000s\n\nOK\n")

        def __init__(self, command, **kwargs):
            # runtests.py runs on this interpreter, so its version is the one recorded.
            assert command[0] == sys.executable

        def wait(self):
            return 0

    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "git_commit", lambda path: "abc1234 2026-10-19")
    monkeypatch.setattr(runner.subprocess, "Popen", FakeProcess)
    assert runner.run_label("6.1", "basic", True, 2, lambda text: text) == 0
    header = (tmp_path / "test-results/6.1/basic.log").read_text().splitlines()[:6]
    assert f"# python: {platform.python_version()}" in header
    capsys.readouterr()


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
    # True by Django's default too, but enabled explicitly by the backend.
    assert "`uses_savepoints`" in text
    assert "identity restart deferred in TestCase (SQL0910)" in text
    assert "goldens," in text
    assert "unverifiable on PUB400: 3" in text


def test_collect_ignores_logs_outside_the_run_set(tmp_path, capsys) -> None:
    (tmp_path / "6.1").mkdir()
    (tmp_path / "6.1" / "basic.log").write_text(OK_LOG)
    (tmp_path / "6.1" / "pub400.log").write_text("an old tier log without a header")
    (tmp_path / "6.1" / "schema.log").write_text(OK_LOG.replace("basic", "schema"))
    status_toml = {"modules": [{"module": "basic"}, {"module": "queries", "labels": ["q.a"]}]}
    assert status.run_set(status_toml) == {"basic"}
    results = status.collect(tmp_path, modules=status.run_set(status_toml))
    assert [r.module for r in results] == ["basic"]
    assert "ignored (not in the run set): 6.1/pub400.log, 6.1/schema.log" in capsys.readouterr().err


def test_render_without_runs() -> None:
    assert "No Django test modules have been run yet." in status.render([])


# --- Badges, README status and the TEST_STATUS header --------------------------------

STATUS = {
    "versions": {"test_system": "PUB400"},
    "ibmi": [{"version": "7.5", "state": "supported"}],
    "python": [
        {"version": "3.13", "state": "supported"},
        {"version": "3.14", "state": "supported"},
    ],
    "django": [
        {"version": "5.2", "state": "development", "eol": "2028-04"},
        {"version": "6.0", "state": "supported", "eol": "2027-04"},
        {"version": "6.1", "state": "supported"},
        {"version": "6.2", "state": "planned"},
    ],
    "releases": [{"tag": "v0.1.0a2", "date": "2026-10-18", "summary": "Encoding fixes."}],
    "phases": [
        {"phase": "2", "content": "Queries & pagination", "status": "done"},
        {
            "phase": "3",
            "content": "Django 6.0 and 5.2 support",
            "status": "in progress",
            "steps": [
                {"step": "A: 6.1 → 6.0", "status": "done", "prs": [107, 110]},
                {"step": "Close-out", "status": "planned", "prs": []},
            ],
        },
        {"phase": "Encoding track", "content": "CCSID", "status": "done"},
    ],
    "modules": [{"module": "basic", "status": "done"}],
    "tracks": [{"text": "Verify the column order (#23)."}],
}
TODAY = dt.date(2026, 10, 21)

README_TEXT = (
    "# Title\n\n<!-- badges:start -->\nold badges\n<!-- badges:end -->\n\n"
    "<!-- tests:start -->\nold tests\n<!-- tests:end -->\n\nBy hand.\n\n"
    "<!-- status:start -->\nold status\n<!-- status:end -->\n\n## Install\n"
)


def results_ok_and_failed():
    return [
        status.parse_log(OK_LOG, "basic", "6.1"),
        status.parse_log(FAILED_LOG, "transactions", "6.1"),
    ]


def test_totals_sum_the_newest_django_version() -> None:
    old = status.parse_log(OK_LOG.replace("6.1 (", "5.2 ("), "basic", "5.2")
    crashed = status.parse_log(CRASHED_LOG.replace("basic", "ordering"), "ordering", "6.1")
    total = status.totals([old, crashed, *results_ok_and_failed()])
    # basic: 55 passed, 3 skipped, 2 xfail; transactions: 67 passed, 4+1+1 failed, 5, 2.
    assert total == status.Totals(passed=122, failed=6, skipped=8, expected_failures=4)
    assert status.totals([]) == status.Totals()


def test_zero_failed_badge_is_green() -> None:
    data = status.badge_data(status.totals([status.parse_log(OK_LOG, "basic", "6.1")]), "x")
    assert (data["failed"]["message"], data["failed"]["color"]) == ("0 failed", "brightgreen")


def _redirect(monkeypatch, tmp_path, collected):
    readme = tmp_path / "README.md"
    monkeypatch.setattr(status, "ROOT", tmp_path)
    monkeypatch.setattr(status, "README", readme)
    monkeypatch.setattr(status, "OUTPUT", tmp_path / "TEST_STATUS.md")
    monkeypatch.setattr(status, "BADGES_DIR", tmp_path / "badges")
    monkeypatch.setattr(status, "RESULTS", tmp_path / "results")
    monkeypatch.setattr(status, "load_status", lambda: STATUS)
    monkeypatch.setattr(status, "collect", lambda modules=None: collected)
    return readme


def write_summary(root: Path, version: str, name: str, **counts) -> None:
    data = {"passed": 0, "skipped": 0, "expected_failures": 0, "failed": 0, **counts}
    data["finished"] = "2026-10-21 08:00:00 UTC"
    path = root / version / "sets" / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


TIER_LOG = (
    "tests/pub400/test_schema.py ....\n"
    "=========================== short test summary info ============================\n"
    "XFAIL tests/pub400/test_inquiry.py::test_drop - no entry\n"
    "==== 240 passed, 3 skipped, 2240 deselected, 2 xfailed in 746.19s (0:12:26) ====\n"
)


def test_version_states_and_end_of_life() -> None:
    assert status.version_state({"state": "supported", "eol": "2027-04"}, TODAY) == "supported"
    assert status.version_state({"eol": "2027-04"}, dt.date(2027, 4, 30)) == "supported"
    assert status.version_state({"eol": "2027-04"}, dt.date(2027, 5, 1)) == "eol"
    assert status.version_state({"eol": "2027-12"}, dt.date(2028, 1, 1)) == "eol"
    assert status.version_state({"state": "planned", "eol": "2020-01"}, TODAY) == "planned"
    assert status.shown_django_versions(STATUS, TODAY) == ["6.1", "6.0", "5.2"]


def test_general_badges_have_symbol_and_colour_per_state() -> None:
    text = "\n".join(status.general_badge_lines(STATUS, today=TODAY))
    assert (
        "github/v/release/benny-vanbelle-vandeput-be/django-db2-for-i?include_prereleases" in text
    )
    assert "https://img.shields.io/badge/license-BSD--3--Clause-blue)](LICENSE)" in text
    assert "actions/workflow/status/benny-vanbelle-vandeput-be/django-db2-for-i/offline.yml" in text
    assert "/badge/IBM%20i-7.5%20%E2%9C%85-brightgreen)" in text  # ✅
    assert "/badge/Python-3.14%20%E2%9C%85-brightgreen)" in text
    assert "/badge/Django-5.2%20%F0%9F%9A%A7-yellow)" in text  # 🚧
    assert "/badge/Django-6.2%20%F0%9F%97%93%EF%B8%8F-blue)" in text  # 🗓️
    assert "![Django 6.0 ✅]" in text
    assert "✅ supported · 🚧 in development · 🗓️ planned" in text
    later = "\n".join(status.general_badge_lines(STATUS, today=dt.date(2027, 5, 1)))
    assert "/badge/Django-6.0%20%E2%9A%A0%EF%B8%8F-orange)" in later  # ⚠️ after April 2027


def test_test_set_table_totals_and_badges(tmp_path) -> None:
    results_dir = tmp_path / "results"
    write_summary(results_dir, "6.1", "offline-py3.13", passed=1, skipped=9)
    write_summary(results_dir, "6.1", "offline-py3.14", passed=100, skipped=2, failed=1)
    write_summary(results_dir, "6.1", "pub400", passed=20, expected_failures=1)
    write_summary(results_dir, "6.1", "corpus", passed=50, skipped=3)
    sets = status.set_results(results_ok_and_failed(), "6.1", results_dir)
    assert sets[status.SET_OFFLINE].totals.passed == 100  # the newest Python's file
    assert sets[status.SET_DJANGO].totals == status.Totals(122, 6, 8, 4)
    assert status.version_totals(sets) == status.Totals(
        passed=100 + 20 + 122 + 50, failed=1 + 6, skipped=2 + 8 + 3, expected_failures=1 + 4
    )
    table = status.set_table(sets, "6.1")
    assert table[:2] == [
        "| Test set | Passed | Skipped | Expected failures | Failed | Last run |",
        "|---|---|---|---|---|---|",
    ]
    assert "| Offline · own tests | 100 | 2 | 0 | 1 | 2026-10-21 08:00:00 UTC |" in table
    assert "| IBM i · Django test suite | 122 | 8 | 4 | 6 | 2026-10-17 18:00:00 UTC |" in table
    empty = status.set_table(status.set_results([], "5.2", results_dir), "5.2")
    none = " | ".join([status.NONE] * 4)
    assert f"| IBM i · own tests | {none} | not run yet |" in empty
    written = status.write_badges(
        STATUS, results_ok_and_failed(), tmp_path / "b", results_dir, TODAY
    )
    assert sorted({p.parent.name for p in written}) == ["5.2", "6.0", "6.1"]
    data = json.loads((tmp_path / "b" / "6.1" / "passed.json").read_text())
    assert data == {
        "schemaVersion": 1,
        "label": "Django 6.1",
        "message": "292 passed",
        "color": "brightgreen",
    }
    failed = json.loads((tmp_path / "b" / "6.1" / "failed.json").read_text())
    assert (failed["message"], failed["color"]) == ("7 failed", "red")
    assert (
        json.loads((tmp_path / "b" / "5.2" / "failed.json").read_text())["color"] == "brightgreen"
    )


def test_stale_badges_are_removed(tmp_path) -> None:
    badges = tmp_path / "b"
    (badges / "6.1").mkdir(parents=True)
    (badges / "4.2").mkdir()
    for path in (
        badges / "passed.json",
        badges / "6.1" / "modules.json",
        badges / "4.2" / "x.json",
    ):
        path.write_text("{}")
    status.write_badges(STATUS, [], badges, tmp_path / "results", TODAY)
    assert not (badges / "passed.json").exists()
    assert not (badges / "6.1" / "modules.json").exists()
    assert not (badges / "4.2").exists()
    assert sorted(p.name for p in (badges / "6.1").iterdir()) == [
        "failed.json",
        "passed.json",
        "skipped.json",
        "xfail.json",
    ]


def test_the_tier_log_counts_when_there_is_no_summary(tmp_path) -> None:
    log = tmp_path / "results" / "5.2" / "tiers" / "pub400.log"
    log.parent.mkdir(parents=True)
    log.write_text(TIER_LOG)
    sets = status.set_results([], "5.2", tmp_path / "results")
    assert sets[status.SET_PUB400].totals == status.Totals(
        passed=240, failed=0, skipped=3, expected_failures=2
    )
    write_summary(tmp_path / "results", "5.2", "pub400", passed=7)
    assert status.set_results([], "5.2", tmp_path / "results")[status.SET_PUB400].totals.passed == 7


def test_readme_sections_between_markers(monkeypatch, tmp_path) -> None:
    (tmp_path / "docs" / "phases").mkdir(parents=True)
    (tmp_path / "docs" / "phases" / "phase-2.md").write_text("# Phase 2\n")
    monkeypatch.setattr(status, "ROOT", tmp_path)  # phase links: only to existing records
    features = tmp_path / "features"
    features.mkdir()
    (features / "6.1.json").write_text(
        json.dumps({"django": "6.1", "flags": {"a": True, "b": False}})
    )
    results = results_ok_and_failed()
    text = status.render_readme(README_TEXT, STATUS, results, tmp_path / "r", features, TODAY)
    assert "old badges" not in text and "old tests" not in text and "old status" not in text
    assert "\n\nBy hand.\n\n" in text and text.endswith("<!-- status:end -->\n\n## Install\n")
    assert "### Django 6.1 ✅" in text and "### Django 5.2 🚧" in text
    assert "### Django 6.2" not in text  # planned: only a badge
    assert (
        text.index("### Django 6.1") < text.index("### Django 6.0") < text.index("### Django 5.2")
    )
    assert "main/docs/badges/6.0/xfail.json)](docs/TEST_STATUS.md)" in text
    assert "### About the tests" in text
    assert "limited to the modules that use" in text and "`basic`, `transactions`" in text
    assert "[docs/OFFLINE_CORPUS.md](docs/OFFLINE_CORPUS.md)" in text
    assert "[docs/FEATURES.md](docs/FEATURES.md) (1 enabled on Django 6.1)" in text
    assert "**Phase 3: Django 6.0 and 5.2 support** (in progress)" in text
    assert "| A: 6.1 → 6.0 | done | [#107](https://github.com/" in text
    assert "| Close-out | planned |  |" in text
    assert "| [2](docs/phases/phase-2.md) | Queries & pagination | done |" in text
    assert "Encoding track" not in text  # phases 0-7 only
    assert "Latest release: **`v0.1.0a2`** (2026-10-18): Encoding fixes." in text
    assert "- Verify the column order (#23)." in text
    # Idempotent.
    assert status.render_readme(text, STATUS, results, tmp_path / "r", features, TODAY) == text


@pytest.mark.parametrize(
    "readme",
    [
        README_TEXT.replace("<!-- status:end -->", ""),
        README_TEXT.replace("<!-- tests:start -->", ""),
        README_TEXT + "<!-- badges:start -->\n",
        README_TEXT.replace("<!-- tests:start -->", "<!-- tmp -->")
        .replace("<!-- tests:end -->", "<!-- tests:start -->")
        .replace("<!-- tmp -->", "<!-- tests:end -->"),
    ],
    ids=["missing-end", "missing-start", "duplicate", "wrong-order"],
)
def test_readme_rendering_refuses_bad_markers(readme) -> None:
    with pytest.raises(status.MarkerError):
        status.render_readme(readme, STATUS, [], today=TODAY)


def test_main_reports_missing_markers_and_writes_nothing(monkeypatch, tmp_path, capsys) -> None:
    readme = _redirect(monkeypatch, tmp_path, [])
    readme.write_text("# No markers\n")
    assert status.main() == 1
    assert "<!-- badges:start -->" in capsys.readouterr().err
    assert not (tmp_path / "TEST_STATUS.md").exists()
    assert not (tmp_path / "badges").exists()
    assert readme.read_text() == "# No markers\n"


def test_main_writes_everything(monkeypatch, tmp_path) -> None:
    readme = _redirect(monkeypatch, tmp_path, results_ok_and_failed())
    readme.write_text(README_TEXT)
    assert status.main() == 0
    passed = json.loads((tmp_path / "badges" / "6.1" / "passed.json").read_text())
    assert passed["message"] == "122 passed"
    assert "| IBM i · Django test suite | 122 |" in readme.read_text()
    page = (tmp_path / "TEST_STATUS.md").read_text()
    assert "- **IBM i:** 7.5 on PUB400" in page
    assert (
        "## Django 6.1 ✅" in page and "docs/badges/6.1/passed.json)](#django-test-modules)" in page
    )
    assert "| Offline · own tests | offline tier (`nox -s offline`, `tests/offline/`) |" in page


def test_committed_status_data_parses() -> None:
    path = SCRIPTS.parent / "docs" / "status.toml"
    if not path.exists():  # the wheel session tests a copy without docs/
        pytest.skip("docs/status.toml is not part of this copy of the tests")
    data = status.load_status(path)
    allowed = {"done", "in progress", "planned"}
    assert {p["status"] for p in data["phases"]} <= allowed
    assert {s["status"] for p in data["phases"] for s in p.get("steps", [])} <= allowed
    assert {m["status"] for m in data["modules"]} <= allowed
    for key in ("ibmi", "python", "django"):
        assert data[key], key
        assert {e["state"] for e in data[key]} <= set(status.STATES), key
    assert data["versions"]["test_system"]


def test_the_committed_readme_has_the_four_test_sets() -> None:
    readme = SCRIPTS.parent / "README.md"
    if not readme.exists():  # the wheel session copies no README.md
        pytest.skip("README.md not available")
    text = readme.read_text(encoding="utf-8")
    for name in status.TEST_SETS:
        assert f"| {name} |" in text
    assert "/modules.json" not in text  # the old "Django modules" badge
    assert "docs/badges/passed.json" not in text


FAILED_DEFINITION = "**failed** = failures + errors + unexpected successes"


def test_test_status_defines_failed_explicitly() -> None:
    assert FAILED_DEFINITION in status.render([])


def test_readme_defines_failed_explicitly() -> None:
    readme = Path(__file__).resolve().parents[2] / "README.md"
    if not readme.exists():  # the wheel session copies no README.md
        pytest.skip("README.md not available")
    assert FAILED_DEFINITION in readme.read_text(encoding="utf-8")


# --- Modules run as several labels (queries Q1-Q5) ------------------------------------


def label_log(label: str, commit: str, summary: str, ran: int = 10) -> str:
    return (
        f"# module: {label}\n# django: 6.1 (1e01021 2026-10-12)\n# backend: {commit}\n"
        f"# keepdb: no\n# started: 2026-10-19 08:30:10 UTC\n"
        f"Ran {ran} tests in 1.0s\n\n{summary}\n# exit: 0\n"
    )


def write_labels(tmp_path, logs: dict[str, str]):
    directory = tmp_path / "6.1" / "labels"
    directory.mkdir(parents=True)
    for label, text in logs.items():
        (directory / f"{label}.log").write_text(text)
    return tmp_path


LABEL_STATUS = {
    "modules": [{"module": "queries", "status": "in progress", "labels": ["q.a", "q.b"]}]
}


def test_labels_of_one_run_set_are_summed(tmp_path) -> None:
    root = write_labels(
        tmp_path,
        {
            "q.a": label_log("q.a", "a7ca5f8 2026-10-19", "OK (skipped=2)"),
            "q.b": label_log("q.b", "a7ca5f8 2026-10-19", "FAILED (errors=1)", ran=5),
        },
    )
    (total,) = status.collect_label_groups(LABEL_STATUS, root)
    assert (total.module, total.ran, total.errors, total.skipped) == ("queries", 15, 1, 2)
    assert (total.outcome, total.partial, total.backend) == ("FAILED", "", "a7ca5f8 2026-10-19")


def test_a_missing_label_makes_the_module_partial(tmp_path) -> None:
    root = write_labels(tmp_path, {"q.a": label_log("q.a", "a7ca5f8 2026-10-19", "OK")})
    (total,) = status.collect_label_groups(LABEL_STATUS, root)
    assert total.outcome == "PARTIAL" and total.partial == "missing q.b"
    assert status._result_text(total) == "PARTIAL (missing q.b)"


def test_labels_from_different_commits_are_partial(tmp_path) -> None:
    root = write_labels(
        tmp_path,
        {
            "q.a": label_log("q.a", "a7ca5f8 2026-10-19", "OK"),
            "q.b": label_log("q.b", "efb1c26 2026-10-19", "OK"),
        },
    )
    (total,) = status.collect_label_groups(LABEL_STATUS, root)
    assert total.outcome == "PARTIAL"
    assert total.partial == "different commits a7ca5f8 2026-10-19, efb1c26 2026-10-19"


def test_test_status_records_the_backend_commit(tmp_path) -> None:
    root = write_labels(
        tmp_path,
        {
            "q.a": label_log("q.a", "a7ca5f8 2026-10-19", "OK"),
            "q.b": label_log("q.b", "a7ca5f8 2026-10-19", "OK"),
        },
    )
    text = status.render(status.collect_label_groups(LABEL_STATUS, root), {})
    assert "- **Backend commits:** a7ca5f8 2026-10-19" in text
    assert "| OK | 2026-10-19 08:30:10 UTC | a7ca5f8 2026-10-19 |" in text


def test_the_runner_reads_the_commit_despite_foreign_ownership() -> None:
    import inspect

    source = inspect.getsource(load("run_django_tests").git_commit)
    assert "safe.directory=" in source


def with_python(log: str, python: str) -> str:
    return log.replace("# keepdb:", f"# python: {python}\n# keepdb:", 1)


def test_label_logs_of_one_module_must_agree_on_python(tmp_path) -> None:
    root = write_labels(
        tmp_path,
        {
            "q.a": with_python(label_log("q.a", "a7ca5f8 2026-10-19", "OK"), "3.14.0"),
            "q.b": label_log("q.b", "a7ca5f8 2026-10-19", "OK"),
        },
    )
    (total,) = status.collect_label_groups(LABEL_STATUS, root)
    assert total.python == ""


# --- release run -------------------------------------------------------------------------

release = load("release_run")

# The wheel session tests a copy without docs/ (the release run reads docs/status.toml).
needs_status_data = pytest.mark.skipif(
    not (SCRIPTS.parent / "docs" / "status.toml").exists(),
    reason="docs/status.toml is not part of this copy of the tests",
)


@needs_status_data
def test_release_run_labels_come_from_status_toml() -> None:
    import tomllib

    run = release.labels()
    modules = tomllib.loads(release.STATUS_DATA.read_text())["modules"]
    assert run[: len(modules) - 1] == [module["module"] for module in modules[:-1]]
    assert "queries" not in run  # run as its labels
    assert "queries.tests" in run and "queries.test_bulk_update" in run
    assert len(run) == len(set(run))
    for label in run:
        runner.validate("6.1", [label])  # one label per call, each a valid label


@needs_status_data
def test_release_run_refuses_before_connecting(monkeypatch, tmp_path, capsys) -> None:
    calls = []
    monkeypatch.setattr(release.run_django_tests, "main", lambda argv: calls.append(argv) or 0)
    monkeypatch.setattr(release, "run_tier", lambda version: calls.append(version) or 0)
    assert release.main([]) == 2
    assert release.main(["six"]) == 2
    assert "invalid Django version" in capsys.readouterr().err
    monkeypatch.setattr(release, "ROOT", tmp_path)
    assert release.main(["6.1"]) == 2
    assert "vendor/django-6.1 is missing" in capsys.readouterr().err
    (tmp_path / "vendor" / "django-6.1" / "tests").mkdir(parents=True)
    (tmp_path / "vendor" / "django-6.1" / "tests" / "runtests.py").touch()
    monkeypatch.setattr(release, "reachable", lambda: "port 9471 not reachable: timed out")
    assert release.main(["6.1"]) == 2
    assert "PUB400 is not reachable, nothing was run" in capsys.readouterr().err
    assert calls == []


@needs_status_data
def test_release_run_runs_every_label_then_the_tier_and_reports_failures(
    monkeypatch, tmp_path, capsys
) -> None:
    calls = []
    (tmp_path / "vendor" / "django-6.1" / "tests").mkdir(parents=True)
    (tmp_path / "vendor" / "django-6.1" / "tests" / "runtests.py").touch()
    monkeypatch.setattr(release, "ROOT", tmp_path)
    monkeypatch.setattr(release, "reachable", lambda: None)
    monkeypatch.setattr(
        release.run_django_tests,
        "main",
        lambda argv: calls.append(argv) or (1 if argv[-1] == "lookup" else 0),
    )
    monkeypatch.setattr(release, "run_tier", lambda version: calls.append(["tier", version]) or 0)
    assert release.main(["6.1"]) == 1
    run = release.labels()
    # Every label captures: the release run refreshes the offline query corpus.
    assert calls == [["6.1", "--clean", "--capture", label] for label in run] + [["tier", "6.1"]]
    assert f"{len(run) + 1} runs, failed: lookup" in capsys.readouterr().out


def test_release_run_reachability_needs_no_credentials(monkeypatch) -> None:
    for name in ("DB2I_HOST", "DB2I_USER", "DB2I_PASSWORD", "DB2I_SSL"):
        monkeypatch.delenv(name, raising=False)
    assert "DB2I_HOST" in release.reachable()
    monkeypatch.setenv("DB2I_HOST", "example.invalid")
    monkeypatch.setattr(release, "tcp_check", lambda host, port: {"open": True, "port": port})
    assert release.reachable() is None
    monkeypatch.setattr(
        release, "tcp_check", lambda host, port: {"open": False, "error": "timeout", "port": port}
    )
    assert release.reachable() == "port 9471 not reachable: timeout"


def test_release_run_tier_log_is_not_read_as_a_module_log(monkeypatch, tmp_path, capsys) -> None:
    """scripts/update_test_status.py reads test-results/<version>/*.log as module
    logs; the tier's log goes to tiers/, with the password scrubbed."""
    import io

    class FakeProcess:
        def __init__(self, command, **kwargs):
            self.stdout = io.StringIO("collected 2 items\npassword S3cret!pw\n2 passed\n")

        def wait(self):
            return 0

    monkeypatch.setattr(release, "ROOT", tmp_path)
    monkeypatch.setenv("DB2I_PASSWORD", "S3cret!pw")
    monkeypatch.setattr(release.subprocess, "Popen", FakeProcess)
    assert release.run_tier("6.0") == 0
    log = tmp_path / "test-results" / "6.0" / "tiers" / "pub400.log"
    assert log.read_text() == "collected 2 items\npassword ***\n2 passed\n"
    assert list((tmp_path / "test-results").glob("*/*.log")) == []
    assert "S3cret!pw" not in capsys.readouterr().out


# --- release run: resuming (bin/release-run) ---------------------------------------------


@pytest.fixture
def resumable(monkeypatch, tmp_path):
    """release_run.main() with fake runs: labels a, b, c; results in tmp_path."""
    (tmp_path / "vendor" / "django-6.1" / "tests").mkdir(parents=True)
    (tmp_path / "vendor" / "django-6.1" / "tests" / "runtests.py").touch()
    monkeypatch.setattr(release, "ROOT", tmp_path)
    monkeypatch.setattr(release, "reachable", lambda: None)
    monkeypatch.setattr(release, "labels", lambda: ["basic", "transactions", "ordering"])
    commits = {"backend": "abc1234 2026-10-22"}
    monkeypatch.setattr(release.run_django_tests, "backend_commit", lambda: commits["backend"])
    monkeypatch.setattr(release.run_django_tests, "git_full_commit", lambda path: "d" * 40)
    calls, failing = [], set()

    def fake_label(argv):
        calls.append(argv[-1])
        return 1 if argv[-1] in failing else 0

    monkeypatch.setattr(release.run_django_tests, "main", fake_label)
    monkeypatch.setattr(release, "run_tier", lambda version: calls.append("tier") or 0)
    return SimpleNamespace(root=tmp_path, calls=calls, failing=failing, commits=commits)


def test_a_limited_run_stops_and_the_next_start_skips_what_passed(resumable, capsys) -> None:
    assert release.main(["6.1", "--limit", "1"]) == 1
    assert resumable.calls == ["basic"]
    out = capsys.readouterr().out
    assert "started over (first run)" in out
    assert "stopped by --limit 1; the next start continues here (transactions)" in out
    assert "not run yet: 3" in out
    state = json.loads(release.state_path("6.1").read_text())
    assert state == {
        "backend": "abc1234 2026-10-22",
        "django": "d" * 40,
        "results": {"basic": "passed"},
    }
    assert release.main(["6.1"]) == 0
    assert resumable.calls == ["basic", "transactions", "ordering", "tier"]
    out = capsys.readouterr().out
    assert "resumed" in out and "skipped, passed before on the same commits: basic" in out
    assert "4 runs, all passed" in out


def test_failed_runs_run_again_on_the_next_start(resumable, capsys) -> None:
    resumable.failing.add("transactions")
    assert release.main(["6.1"]) == 1
    assert "failed: transactions" in capsys.readouterr().out
    resumable.failing.clear()
    resumable.calls.clear()
    assert release.main(["6.1"]) == 0
    assert resumable.calls == ["transactions"]


def test_new_commits_or_restart_start_over_and_clear_old_captures(resumable, capsys) -> None:
    captures = resumable.root / "test-results" / "6.1" / "corpus"
    captures.mkdir(parents=True)
    assert release.main(["6.1", "--limit", "1"]) == 1
    (captures / "queries.tests.A.test_x.jsonl").write_text("{}\n")  # e.g. from bin/verify
    assert release.main(["6.1", "--limit", "0"]) == 1
    assert (captures / "queries.tests.A.test_x.jsonl").exists()  # resumed: kept
    resumable.commits["backend"] = "def5678 2026-10-23"
    resumable.calls.clear()
    assert release.main(["6.1", "--limit", "1"]) == 1
    assert "started over (new commits)" in capsys.readouterr().out
    assert resumable.calls == ["basic"]
    assert list(captures.glob("*.jsonl")) == []
    assert release.main(["6.1", "--restart", "--limit", "0"]) == 1
    assert "started over (--restart)" in capsys.readouterr().out
    assert json.loads(release.state_path("6.1").read_text())["results"] == {}


def test_release_run_usage(resumable, capsys) -> None:
    assert release.main(["6.1", "--limit"]) == 2
    assert release.main(["6.1", "--bogus"]) == 2
    assert "usage: nox -s release_run" in capsys.readouterr().err
