"""The own IBM i tests save their results as they go and resume on the same code
(tests/progress.py, phase 7, section 9); no IBM i needed: small pytest runs in a
temporary directory."""

import contextlib
import json
import types

import pytest

from tests import progress

pytestmark = pytest.mark.offline

COMMIT = "a" * 40
TESTS = """
import os
import pytest

def test_pass():
    pass

def test_fail():
    assert os.environ.get("FIXED") == "1"

@pytest.fixture
def broken():
    assert os.environ.get("FIXED") == "1"

def test_error(broken):
    pass

def test_skip():
    pytest.skip("not here")

@pytest.mark.xfail(reason="known")
def test_xfail():
    assert False
"""


def outcomes(path) -> dict[str, str]:
    seen = {}
    for record in map(json.loads, path.read_text().splitlines()):
        if "nodeid" in record:
            seen[record["nodeid"].split("::")[-1]] = record["outcome"]
    return seen


@pytest.fixture
def run(pytester, tmp_path, monkeypatch):
    pytester.makepyfile(test_five=TESTS)
    path = tmp_path / "progress.jsonl"
    monkeypatch.setenv("DB2I_RUN_COMMIT", COMMIT)
    monkeypatch.setenv("DB2I_RUN_TREE", "clean")
    monkeypatch.setenv("DB2I_DEFAULT_LIBRARY", "LIBA")
    monkeypatch.setenv("DB2I_PASSWORD", "one")

    def run(*extra, fixed=False):
        monkeypatch.setenv("FIXED", "1" if fixed else "0")
        return pytester.runpytest_inprocess(
            "-p", "no:django", "-p", "tests.progress", f"--progress={path}", "--resume", *extra
        )

    run.path = path
    return run


def test_each_finished_test_is_saved_with_its_outcome(run) -> None:
    run().assert_outcomes(passed=1, failed=1, errors=1, skipped=1, xfailed=1)
    assert outcomes(run.path) == {
        "test_pass": "passed",
        "test_fail": "failed",
        "test_error": "error",
        "test_skip": "skipped",
        "test_xfail": "xfailed",
    }


def test_a_resumed_part_skips_only_the_passed_tests(run) -> None:
    """Failed, errored, skipped and expected-failure tests run again."""
    run()
    result = run(fixed=True)
    result.assert_outcomes(passed=2, skipped=1, xfailed=1, deselected=1)
    assert "resumed, part 2; 1 tests that passed in the earlier part(s) are skipped" in (
        result.stdout.str()
    )


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("DB2I_RUN_COMMIT", "b" * 40),  # another commit
        ("DB2I_RUN_TREE", "changed"),  # uncommitted or new files
        ("DB2I_DEFAULT_LIBRARY", "LIBB"),  # other settings
    ],
)
def test_other_code_or_settings_start_afresh(run, monkeypatch, variable, value) -> None:
    run()
    monkeypatch.setenv(variable, value)
    result = run(fixed=True)
    result.assert_outcomes(passed=3, skipped=1, xfailed=1)
    assert "resumed" not in result.stdout.str()


def test_another_password_is_the_same_settings(run, monkeypatch) -> None:
    run()
    monkeypatch.setenv("DB2I_PASSWORD", "two")
    run(fixed=True).assert_outcomes(passed=2, skipped=1, xfailed=1, deselected=1)


PASSWORD = "Pw-7f3e9c2a"


def derived(secret: str) -> list[str]:
    """The secret and the forms a careless implementation could store."""
    import base64
    import hashlib

    raw = secret.encode()
    return [
        secret,
        hashlib.sha256(raw).hexdigest(),
        hashlib.sha1(raw).hexdigest(),
        hashlib.md5(raw).hexdigest(),
        base64.b64encode(raw).decode(),
    ]


def test_the_key_does_not_depend_on_the_password_at_all() -> None:
    env = {"DB2I_RUN_COMMIT": COMMIT, "DB2I_RUN_TREE": "clean", "DB2I_HOST": "h"}
    without = progress.run_key(env, "6.1.3", "s", "-m ibmi")
    assert progress.run_key({**env, "DB2I_PASSWORD": PASSWORD}, "6.1.3", "s", "-m ibmi") == without
    assert progress.run_key({**env, "DB2I_PASSWORD": "other"}, "6.1.3", "s", "-m ibmi") == without
    # Anything named like a secret is left out the same way.
    for name in ("DB2I_PWD", "DB2I_API_TOKEN", "DB2I_SECRET", "DB2I_KEY_FILE"):
        assert progress.run_key({**env, name: PASSWORD}, "6.1.3", "s", "-m ibmi") == without
    # A non-secret setting does count.
    assert progress.run_key({**env, "DB2I_HOST": "x"}, "6.1.3", "s", "-m ibmi") != without


def test_the_progress_and_results_files_hold_nothing_derived_from_the_password(
    run, monkeypatch, tmp_path
) -> None:
    from tests import results_summary

    monkeypatch.setenv("DB2I_PASSWORD", PASSWORD)
    run()
    run(fixed=True)
    records = progress.load(run.path)
    summary = tmp_path / "pub400.json"
    run_record = progress.Progress(tmp_path / "again.jsonl", records[0]["key"], "why", False)
    counts = {"passed": 1, "skipped": 0, "expected_failures": 0, "failed": 0}
    results_summary.write(summary, counts, extra=run_record.summary(COMMIT))
    run_record.end(all_passed=True)
    for path in (run.path, summary, tmp_path / "again.jsonl"):
        text = path.read_text()
        assert not [form for form in derived(PASSWORD) if form in text], path.name


def test_after_a_run_that_fully_passed_the_next_run_starts_afresh(run) -> None:
    run("-k", "test_pass", fixed=True)
    run("-k", "test_pass", fixed=True).assert_outcomes(passed=1, deselected=4)


def test_the_resumed_run_says_its_parts_and_its_commit(run) -> None:
    run()
    run()
    result = run(fixed=True)
    assert f"resumed run: 3 parts, all on commit {COMMIT[:12]}" in result.stdout.str()
    records = [json.loads(line) for line in run.path.read_text().splitlines()]
    parts = [r for r in records if "part" in r]
    assert [p["part"] for p in parts] == [1, 2, 3]
    assert len({p["key"] for p in parts}) == 1  # all parts on the same code


def test_run_key_needs_the_commit_a_clean_tree_and_names_the_django_version() -> None:
    env = {"DB2I_RUN_COMMIT": COMMIT, "DB2I_RUN_TREE": "clean", "DB2I_HOST": "h"}
    key, why = progress.run_key(env, "6.1.3", "settings_ibmi", "-m ibmi")
    assert key and "Django 6.1.3" in why
    assert progress.run_key(env, "6.1.4", "settings_ibmi", "-m ibmi")[0] != key
    assert progress.run_key(env, "6.1.3", "other_settings", "-m ibmi")[0] != key
    assert progress.run_key(env, "6.1.3", "settings_ibmi", "-m ibmi -k x")[0] != key
    assert progress.run_key({**env, "DB2I_RUN_COMMIT": ""}, "6.1.3", "s", "")[0] is None
    assert progress.run_key({**env, "DB2I_RUN_TREE": "changed"}, "6.1.3", "s", "")[0] is None


def test_a_line_cut_off_by_the_interruption_is_ignored(tmp_path) -> None:
    path = tmp_path / "p.jsonl"
    path.write_text(
        '{"part": 1, "key": "k"}\n{"nodeid": "t::a", "outcome": "passed"}\n{"nodeid": "t::b", "ou'
    )
    assert progress.resumable(progress.load(path), "k") == ({"t::a": "passed"}, 1)


def test_the_latest_part_decides_a_test_that_ran_twice() -> None:
    records = [
        {"part": 1, "key": "k"},
        {"nodeid": "t::a", "outcome": "passed"},
        {"part": 2, "key": "k"},
        {"nodeid": "t::a", "outcome": "failed"},
    ]
    assert progress.resumable(records, "k") == ({}, 2)


# --- The cleanup before a resumed part (tests/ibmi/conftest.py) ----------------------


@pytest.fixture
def ibmi_conftest():
    from tests.ibmi import conftest

    return conftest


class Blocker:
    def __init__(self):
        self.unblocked = 0

    @contextlib.contextmanager
    def unblock(self):
        self.unblocked += 1
        yield


def test_a_resumed_part_cleans_up_first(ibmi_conftest, monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(progress, "active", lambda: types.SimpleNamespace(resuming=True))
    cleanup = types.SimpleNamespace(clean=lambda yes: calls.append(yes) or 0)
    blocker = Blocker()
    assert ibmi_conftest.clean_if_resuming(blocker, lambda: cleanup) is True
    assert calls == [True] and blocker.unblocked == 1


@pytest.mark.parametrize("active", [None, types.SimpleNamespace(resuming=False)])
def test_a_new_run_does_not_clean_up(ibmi_conftest, monkeypatch, active) -> None:
    monkeypatch.setattr(progress, "active", lambda: active)
    loaded = []
    assert ibmi_conftest.clean_if_resuming(Blocker(), lambda: loaded.append(1)) is False
    assert loaded == []


def test_a_failed_cleanup_stops_the_resumed_run(ibmi_conftest, monkeypatch) -> None:
    monkeypatch.setattr(progress, "active", lambda: types.SimpleNamespace(resuming=True))
    cleanup = types.SimpleNamespace(clean=lambda yes: 1)
    with pytest.raises(pytest.exit.Exception, match="leftover tables"):
        ibmi_conftest.clean_if_resuming(Blocker(), lambda: cleanup)
