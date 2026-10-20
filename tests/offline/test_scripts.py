"""scripts/run_django_tests.py and scripts/update_test_status.py (no server needed)."""

import importlib.util
import json
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
    assert "pub400|django_tests|release_run|probe|probe_*) ;;" in text
    assert "caffeinate -i -s" in text
    runtests = (script.parent / "runtests.sh").read_text()
    assert 'exec "$(dirname "$0")/pub400.sh" django_tests "$version" "$@"' in runtests


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


def test_render_without_runs() -> None:
    assert "No Django test modules have been run yet." in status.render([])


# --- Badges, README status and the TEST_STATUS header --------------------------------

STATUS = {
    "versions": {"django": "6.1 | 5.2 planned", "ibmi": "7.5", "test_system": "PUB400"},
    "releases": [{"tag": "v0.1.0a2", "date": "2026-10-18", "summary": "Encoding fixes."}],
    "phases": [{"phase": "2", "content": "Queries & pagination", "status": "in progress"}],
    "modules": [
        {"module": "basic", "status": "done"},
        {"module": "transactions", "status": "in progress"},
        {"module": "queries", "status": "planned", "note": "split into labels"},
    ],
    "tracks": [{"text": "Verify the column order (#23)."}],
}

README_TEXT = (
    "# Title\n\n<!-- badges:start -->\nold badges\n<!-- badges:end -->\n\nBy hand.\n\n"
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


def test_badge_json_counts_and_colours(tmp_path) -> None:
    written = status.write_badges(results_ok_and_failed(), STATUS, tmp_path, tmp_path / "vendor")
    assert sorted(p.name for p in written) == [
        "failed.json",
        "modules.json",
        "passed.json",
        "skipped.json",
        "xfail.json",
    ]
    data = {p.stem: json.loads(p.read_text()) for p in written}
    assert all(d["schemaVersion"] == 1 for d in data.values())
    # The logs record no Python version: the label leaves it out.
    assert {data[name]["label"] for name in ("passed", "failed", "skipped", "xfail")} == {
        "Django 6.1 on PUB400"
    }
    assert (data["modules"]["label"], data["modules"]["message"]) == ("Django 6.1 modules", "2 run")
    assert (data["passed"]["message"], data["passed"]["color"]) == ("122 passed", "brightgreen")
    assert (data["failed"]["message"], data["failed"]["color"]) == ("6 failed", "red")
    assert (data["skipped"]["message"], data["skipped"]["color"]) == ("8 skipped", "lightgrey")
    assert data["xfail"]["message"] == "4 expected failures"
    assert data["xfail"]["color"] == "blue"


def test_zero_failed_badge_is_green() -> None:
    data = status.badge_data(status.totals([status.parse_log(OK_LOG, "basic", "6.1")]), "x")
    assert (data["failed"]["message"], data["failed"]["color"]) == ("0 failed", "brightgreen")


def test_badge_lines() -> None:
    text = "\n".join(status.badge_lines(STATUS, "docs/TEST_STATUS.md"))
    assert "https://img.shields.io/badge/Django-6.1%20%7C%205.2%20planned-" in text
    assert "https://img.shields.io/badge/license-BSD--3--Clause-blue)](LICENSE)" in text
    assert "workflow/status/benny-vanbelle-vandeput-be/django-db2-for-i/offline.yml" in text
    assert "include_prereleases" in text
    for name in ("passed", "failed", "skipped", "xfail"):
        assert (
            "endpoint?url=https://raw.githubusercontent.com/benny-vanbelle-vandeput-be/"
            f"django-db2-for-i/main/docs/badges/{name}.json)](docs/TEST_STATUS.md)"
        ) in text
    assert "](../LICENSE)" in "\n".join(status.badge_lines(STATUS, "#x", root="../"))


def test_readme_rendering_between_markers() -> None:
    results = results_ok_and_failed()
    text = status.render_readme(README_TEXT, STATUS, results)
    assert text.startswith("# Title\n\n<!-- badges:start -->\n[![Django]")
    assert "old badges" not in text and "old status" not in text
    assert "\n\nBy hand.\n\n" in text
    assert text.endswith("<!-- status:end -->\n\n## Install\n")
    assert "- **`v0.1.0a2`** (2026-10-18): Encoding fixes." in text
    assert "| 2 | Queries & pagination | in progress |" in text
    assert "| basic | 60 | OK (3 skipped, 2 expected failures) | done |" in text
    assert (
        "| transactions | 80 | FAILED (4 failures, 1 errors, 5 skipped, 2 expected failures,"
        " 1 unexpected successes) | in progress |"
    ) in text
    assert "| queries |  | not run yet | planned (split into labels) |" in text
    assert "- Verify the column order (#23)." in text
    # Idempotent.
    assert status.render_readme(text, STATUS, results) == text


def test_readme_modules_per_django_version() -> None:
    """With [modules_section] django, one column per version: the run's tests and
    result, or "planned" without a run; the title comes from the data."""
    data = dict(STATUS, modules_section={"title": "Phase 3: per version", "django": ["6.1", "5.2"]})
    text = status.render_readme(README_TEXT, data, results_ok_and_failed())
    assert "### Phase 3: per version" in text
    assert "| Module | Django 6.1 | Django 5.2 | Status |" in text
    assert "| basic | 60 tests, OK (3 skipped, 2 expected failures) | planned | done |" in text
    assert "| queries | planned | planned | planned (split into labels) |" in text
    # Without the section: the single-column table under a neutral title.
    assert "### Modules" in status.render_readme(README_TEXT, STATUS, results_ok_and_failed())


@pytest.mark.parametrize(
    "readme",
    [
        README_TEXT.replace("<!-- status:end -->", ""),
        README_TEXT.replace("<!-- badges:start -->", ""),
        README_TEXT + "<!-- status:start -->\n",
        "<!-- badges:end -->\n<!-- badges:start -->\n<!-- status:start -->\n<!-- status:end -->",
    ],
    ids=["missing-end", "missing-start", "duplicate", "wrong-order"],
)
def test_readme_rendering_refuses_bad_markers(readme) -> None:
    with pytest.raises(status.MarkerError):
        status.render_readme(readme, STATUS, [])


def _redirect(monkeypatch, tmp_path, collected):
    readme = tmp_path / "README.md"
    monkeypatch.setattr(status, "ROOT", tmp_path)
    monkeypatch.setattr(status, "README", readme)
    monkeypatch.setattr(status, "OUTPUT", tmp_path / "TEST_STATUS.md")
    monkeypatch.setattr(status, "BADGES_DIR", tmp_path / "badges")
    monkeypatch.setattr(status, "VENDOR", tmp_path / "vendor")
    monkeypatch.setattr(status, "load_status", lambda: STATUS)
    monkeypatch.setattr(status, "collect", lambda: collected)
    return readme


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
    assert json.loads((tmp_path / "badges" / "passed.json").read_text())["message"] == "122 passed"
    assert "| basic | 60 |" in readme.read_text()
    assert "- **IBM i:** 7.5 on PUB400" in (tmp_path / "TEST_STATUS.md").read_text()


def test_test_status_header() -> None:
    later = status.parse_log(
        FAILED_LOG.replace("2026-10-17 18:00:00", "2026-10-18 09:30:00"), "transactions", "6.1"
    )
    text = status.render([status.parse_log(OK_LOG, "basic", "6.1"), later], STATUS)
    assert text.startswith("# Test status\n\n[![Django]")
    assert "docs/badges/failed.json)](#django-test-modules)" in text
    assert "- **Runs:** 2026-10-17 18:00:00 UTC to 2026-10-18 09:30:00 UTC" in text
    assert "- **Django:** 6.1 (1e01021 2026-10-12)" in text
    assert "- **IBM i:** 7.5 on PUB400" in text
    # Without status data (and without runs) the header still renders.
    bare = status.render([])
    assert "- **Runs:** none recorded" in bare
    assert "- **IBM i:** unknown" in bare


def test_committed_status_data_parses() -> None:
    path = SCRIPTS.parent / "docs" / "status.toml"
    if not path.exists():  # the wheel session tests a copy without docs/
        pytest.skip("docs/status.toml is not part of this copy of the tests")
    data = status.load_status(path)
    allowed = {"done", "in progress", "planned"}
    assert {p["status"] for p in data["phases"]} <= allowed
    assert {m["status"] for m in data["modules"]} <= allowed
    assert data["versions"]["ibmi"]


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


# --- Badge labels, the modules badge and one badge set per Django version -------------


def with_python(log: str, python: str) -> str:
    return log.replace("# keepdb:", f"# python: {python}\n# keepdb:", 1)


def test_label_names_the_python_version_when_all_logs_agree() -> None:
    results = [
        status.parse_log(with_python(OK_LOG, "3.14.0"), "basic", "6.1"),
        status.parse_log(with_python(FAILED_LOG, "3.14.1"), "transactions", "6.1"),
    ]
    assert results[0].python == "3.14.0"
    label = status.combination_label(results, "6.1", "PUB400")
    assert label == "Django 6.1 · Python 3.14 on PUB400"


def test_label_without_python_headers() -> None:
    label = status.combination_label(results_ok_and_failed(), "6.1", "PUB400")
    assert label == "Django 6.1 on PUB400"


@pytest.mark.parametrize(
    "pythons",
    [("3.14.0", "3.13.7"), ("3.14.0", None)],
    ids=["different-versions", "one-log-without"],
)
def test_label_omits_python_when_the_logs_disagree(pythons) -> None:
    logs = [OK_LOG, FAILED_LOG]
    results = [
        status.parse_log(with_python(log, python) if python else log, name, "6.1")
        for log, python, name in zip(logs, pythons, ["basic", "transactions"], strict=True)
    ]
    assert status.combination_label(results, "6.1", "PUB400") == "Django 6.1 on PUB400"


def test_label_ignores_other_django_versions_and_logs_without_summary() -> None:
    results = [
        status.parse_log(with_python(OK_LOG, "3.14.0"), "basic", "6.1"),
        # No summary: not counted in the badges, so its missing version does not matter.
        status.parse_log(CRASHED_LOG.replace("basic", "ordering"), "ordering", "6.1"),
        status.parse_log(OK_LOG.replace("6.1 (", "5.2 ("), "basic", "5.2"),
    ]
    assert status.combination_label(results, "6.1", "X") == "Django 6.1 · Python 3.14 on X"
    assert status.combination_label(results, "5.2", "X") == "Django 5.2 on X"


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


def make_django_tests(root, modules=(), others=()):
    tests = root / "tests"
    tests.mkdir(parents=True)
    (tests / "runtests.py").write_text("")
    for name in modules:
        (tests / name).mkdir()
        (tests / name / "__init__.py").write_text("")
    for name in others:
        (tests / name).mkdir(parents=True)
    return tests


def test_module_count_mirrors_runtests(tmp_path) -> None:
    tests = make_django_tests(
        tmp_path,
        modules=["basic", "queries", "import_error_package", "test_runner_apps", "gis_tests"],
        others=["templates", "no_init"],
    )
    (tests / "with.dot").mkdir()
    (tests / "with.dot" / "__init__.py").write_text("")
    (tests / "urls.py").write_text("")
    # basic and queries only: the rest has no __init__.py, a dot, is a file, or
    # is skipped by runtests.py.
    assert status.count_test_modules(tests) == 2
    assert status.count_test_modules(tmp_path / "missing" / "tests") is None


def test_modules_badge_counts_a_module_run_as_labels_once(tmp_path) -> None:
    root = write_labels(
        tmp_path,
        {
            "q.a": label_log("q.a", "a7ca5f8 2026-10-19", "OK"),
            "q.b": label_log("q.b", "a7ca5f8 2026-10-19", "OK"),
        },
    )
    results = [*results_ok_and_failed(), *status.collect_label_groups(LABEL_STATUS, root)]
    make_django_tests(tmp_path / "vendor" / "django-6.1", modules=["basic", "b", "c", "d", "e"])
    status.write_badges(results, STATUS, tmp_path / "badges", tmp_path / "vendor")
    data = json.loads((tmp_path / "badges" / "modules.json").read_text())
    assert (data["label"], data["message"]) == ("Django 6.1 modules", "3/5")


def test_modules_badge_keeps_the_total_without_the_checkout(tmp_path) -> None:
    badges = tmp_path / "badges"
    badges.mkdir()
    previous = {"schemaVersion": 1, "label": "Django 6.1 modules", "message": "1/210"}
    (badges / "modules.json").write_text(json.dumps(previous))
    status.write_badges(results_ok_and_failed(), STATUS, badges, tmp_path / "vendor")
    assert json.loads((badges / "modules.json").read_text())["message"] == "2/210"


def test_modules_badge_never_takes_another_versions_total(tmp_path) -> None:
    badges = tmp_path / "badges"
    badges.mkdir()
    previous = {"schemaVersion": 1, "label": "Django 6.0 modules", "message": "1/200"}
    (badges / "modules.json").write_text(json.dumps(previous))
    status.write_badges(results_ok_and_failed(), STATUS, badges, tmp_path / "vendor")
    assert json.loads((badges / "modules.json").read_text())["message"] == "2 run"
    assert status.previous_total(tmp_path / "absent.json", "Django 6.1 modules") is None


def two_versions():
    old = with_python(OK_LOG.replace("6.1 (", "5.2 ("), "3.13.5")
    return [*results_ok_and_failed(), status.parse_log(old, "basic", "5.2")]


def test_one_badge_set_per_django_version(tmp_path) -> None:
    badges = tmp_path / "badges"
    status.write_badges(two_versions(), STATUS, badges, tmp_path / "vendor")
    names = ["failed", "modules", "passed", "skipped", "xfail"]
    for directory in (badges, badges / "6.1", badges / "5.2"):
        assert sorted(p.stem for p in directory.glob("*.json")) == names
    old = json.loads((badges / "5.2" / "passed.json").read_text())
    assert (old["label"], old["message"]) == ("Django 5.2 · Python 3.13 on PUB400", "55 passed")
    new = json.loads((badges / "6.1" / "passed.json").read_text())
    assert (new["label"], new["message"]) == ("Django 6.1 on PUB400", "122 passed")
    # The top-level files stay the newest version's (their URLs keep working).
    assert json.loads((badges / "passed.json").read_text()) == new
    assert json.loads((badges / "5.2" / "modules.json").read_text())["message"] == "1 run"
    # Back to one version: the per-version directories go.
    status.write_badges(results_ok_and_failed(), STATUS, badges, tmp_path / "vendor")
    assert not (badges / "6.1").exists()
    assert not (badges / "5.2").exists()


def test_no_logs_write_no_badges(tmp_path) -> None:
    assert status.write_badges([], STATUS, tmp_path / "badges", tmp_path / "vendor") == []
    assert not (tmp_path / "badges").exists()


def test_badge_rows_per_django_version() -> None:
    url = "https://raw.githubusercontent.com/benny-vanbelle-vandeput-be/django-db2-for-i/main"
    single = "\n".join(status.badge_lines(STATUS, "x", versions=["6.1"]))
    assert f"{url}/docs/badges/modules.json)](x)" in single
    assert "/docs/badges/6.1/" not in single
    lines = status.badge_lines(STATUS, "x", versions=["6.1", "5.2"])
    text = "\n".join(lines)
    assert f"{url}/docs/badges/6.1/passed.json)](x)" in text
    assert f"{url}/docs/badges/5.2/modules.json)](x)" in text
    assert text.index("/6.1/passed") < text.index("/5.2/modules")
    # Each row is its own paragraph.
    assert lines.count("") == 2


def test_readme_and_test_status_show_one_row_per_version() -> None:
    results = two_versions()
    readme = status.render_readme(README_TEXT, STATUS, results)
    assert "docs/badges/5.2/passed.json)](docs/TEST_STATUS.md)" in readme
    page = status.render(results, STATUS)
    assert "docs/badges/5.2/xfail.json)](#django-test-modules)" in page
    assert "- **Python:** 3.13.5 (not recorded in every log)" in page


REQUIRED_STATEMENTS = [
    "Django's own test modules",
    "one Python × Django combination per row",
    "shared PUB400 system",
    "full version matrix",
    "only on a dedicated IBM i",
    "for every Python × Django combination, with no IBM i",
    "pub400 tier (`tests/pub400/`) is separate and not counted",
    "**Django modules** `<run>/<total>`",
    "counts once",
]


def _flat(text: str) -> str:
    return " ".join(text.split())


def test_badge_definitions_state_what_is_counted() -> None:
    text = _flat("\n".join(status.BADGE_DEFINITIONS))
    for statement in REQUIRED_STATEMENTS:
        assert statement in text
    assert text in _flat(status.render([]))


def test_readme_states_what_is_counted() -> None:
    readme = Path(__file__).resolve().parents[2] / "README.md"
    if not readme.exists():  # the wheel session copies no README.md
        pytest.skip("README.md not available")
    text = _flat(readme.read_text(encoding="utf-8"))
    for statement in REQUIRED_STATEMENTS:
        assert statement in text


# --- release run -------------------------------------------------------------------------

release = load("release_run")


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
    assert calls == [["6.1", "--clean", label] for label in run] + [["tier", "6.1"]]
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
