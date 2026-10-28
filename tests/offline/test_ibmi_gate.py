"""scripts/ibmi_gate.py and .github/workflows/ibmi-gate.yml: the IBM i gate (no server needed)."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import classify_pr as cp  # noqa: E402
import ibmi_gate as gate  # noqa: E402

A, B, C = ("a" * 40, "b" * 40, "c" * 40)
SQL_CHANGE = {"django_db2_for_i/client.py": (b"a", b"b")}
FULL_CHANGE = {"django_db2_for_i/base.py": (b"a", b"b")}
DOCS_CHANGE = {"docs/x.md": (b"a", b"b")}


def classification(files: dict[str, tuple[bytes | None, bytes | None]]) -> cp.Classification:
    changes = [cp.Change("M", path) for path in files]
    return cp.classify(changes, lambda p: files[p][0], lambda p: files[p][1])


def comment(body: str, author: str = gate.MACHINE_ACCOUNT) -> dict:
    return {"user": {"login": author}, "body": body}


def result_comment(sha: str, tier: str = "targeted", author: str = gate.MACHINE_ACCOUNT) -> dict:
    return comment(f"{gate.marker(sha, tier)}\n## IBM i runs\n...", author)


NO_NEW_RUN = cp.PushCheck(False, "the push changes only docs/tests")
NEW_RUN = cp.PushCheck(True, "the push changes the pull request")


# --- The markers ------------------------------------------------------------------------


def test_results_by_the_machine_account_and_the_maintainer() -> None:
    found = gate.results(
        [
            result_comment(A),
            result_comment(B, "full", gate.MAINTAINER),
            comment(f"<!-- ibmi-run sha={C} waived -->", gate.MAINTAINER),
        ]
    )
    assert found == [
        gate.Result(A, "targeted", gate.MACHINE_ACCOUNT),
        gate.Result(B, "full", gate.MAINTAINER),
        gate.Result(C, None, gate.MAINTAINER),
    ]
    assert found[2].waived


@pytest.mark.parametrize(
    "item",
    [
        result_comment(A, author="someone-else"),  # not a trusted author
        comment(f"<!-- ibmi-run sha={A} waived -->"),  # only the maintainer waives
        comment(f"text\n{gate.marker(A, 'targeted')}"),  # only on the first line
        comment("<!-- ibmi-run sha=abc1234 tier=targeted -->"),  # a full SHA only
        comment(f"<!-- ibmi-run sha={A} tier=partial -->"),  # an unknown tier
        {"user": None, "body": gate.marker(A, "targeted")},
        {"user": {"login": gate.MACHINE_ACCOUNT}, "body": None},
    ],
)
def test_other_comments_are_no_results(item) -> None:
    assert gate.results([item]) == []


def test_the_marker_is_what_results_reads() -> None:
    assert gate.marker(A, "full") == f"<!-- ibmi-run sha={A} tier=full -->"
    assert gate.results([comment(gate.marker(A, "full"))]) == [
        gate.Result(A, "full", gate.MACHINE_ACCOUNT)
    ]


# --- The decision -----------------------------------------------------------------------


def decide(files, head, posted, checks=None):
    checks = checks or {}
    return gate.decide(
        classification(files), head, posted, lambda before, _head: checks.get(before, NEW_RUN)
    )


def test_docs_only_needs_no_run() -> None:
    verdict = decide(DOCS_CHANGE, A, [])
    assert verdict == gate.Verdict("success", "docs/tests only: no IBM i run needed")


def test_no_result_is_red() -> None:
    verdict = decide(SQL_CHANGE, A, [])
    assert verdict.state == "failure"
    assert verdict.description == (
        "needs a targeted IBM i run (run-ibmi); no posted result covers it"
    )


def test_a_result_on_the_head_is_green() -> None:
    verdict = decide(SQL_CHANGE, A, gate.results([result_comment(A)]))
    assert verdict == gate.Verdict("success", f"targeted run on {A[:7]}: covers this commit")


def test_a_result_on_an_older_head_covers_a_push_that_needs_no_new_run() -> None:
    verdict = decide(SQL_CHANGE, B, gate.results([result_comment(A)]), {A: NO_NEW_RUN})
    assert verdict.state == "success"
    assert verdict.description == f"targeted run on {A[:7]}: {NO_NEW_RUN.reason}"


def test_a_result_on_an_older_head_does_not_cover_a_changed_pull_request() -> None:
    assert decide(SQL_CHANGE, B, gate.results([result_comment(A)])).state == "failure"


def test_the_newest_covering_result_wins() -> None:
    posted = gate.results([result_comment(A), result_comment(B)])
    verdict = decide(SQL_CHANGE, C, posted, {A: NO_NEW_RUN, B: NO_NEW_RUN})
    assert B[:7] in verdict.description


def test_a_targeted_result_does_not_cover_the_full_tier() -> None:
    verdict = decide(FULL_CHANGE, A, gate.results([result_comment(A)]))
    assert verdict.state == "failure"
    assert verdict.description.startswith("needs a full IBM i run (needs-full-ibmi-run)")
    assert decide(FULL_CHANGE, A, gate.results([result_comment(A, "full")])).state == "success"


def test_a_full_result_covers_a_targeted_run() -> None:
    assert decide(SQL_CHANGE, A, gate.results([result_comment(A, "full")])).state == "success"


def test_a_foreign_marker_does_not_count() -> None:
    posted = gate.results([result_comment(A, author="someone-else")])
    assert decide(SQL_CHANGE, A, posted).state == "failure"


def test_the_maintainer_waives_also_the_full_tier() -> None:
    posted = gate.results([comment(f"<!-- ibmi-run sha={A} waived -->", gate.MAINTAINER)])
    verdict = decide(FULL_CHANGE, A, posted)
    assert verdict == gate.Verdict(
        "success", f"waived by the maintainer {A[:7]}: covers this commit"
    )


def test_a_cancelled_run_posts_nothing_so_the_gate_stays_red() -> None:
    """A run that never finished posted no result: nothing covers the head,
    whatever the labels say (#158)."""
    assert decide(SQL_CHANGE, B, []).state == "failure"


# --- On a real (temporary) repository ---------------------------------------------------


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "commit.gpgsign=false", *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _commit(repo: Path, files: dict[str, bytes], message: str) -> str:
    for path, content in files.items():
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_bytes(content)
    _git(repo, "add", *files)
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path, monkeypatch) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "Test")
    _commit(tmp_path, {"docs/a.md": b"a\n", "django_db2_for_i/client.py": b"x = 1\n"}, "init")
    _git(tmp_path, "switch", "-q", "-c", "pr")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _verdict(capsys, tmp_path, head: str, comments: list[dict]) -> dict:
    path = tmp_path / "comments.json"
    path.write_text(json.dumps(comments))
    assert gate.main(["--base", "main", "--head", head, "--comments", str(path)]) == 0
    return json.loads(capsys.readouterr().out)


def test_the_gate_follows_the_pull_request(repo, tmp_path, capsys) -> None:
    feat = _commit(repo, {"django_db2_for_i/client.py": b"x = 2\n"}, "feat")
    assert _verdict(capsys, tmp_path, feat, [])["state"] == "failure"
    posted = [result_comment(feat)]
    assert _verdict(capsys, tmp_path, feat, posted)["state"] == "success"
    # A renamed changelog fragment: still covered.
    docs = _commit(repo, {"changelog.d/1.added.md": b"x\n"}, "docs: fragment")
    verdict = _verdict(capsys, tmp_path, docs, posted)
    assert verdict["state"] == "success"
    assert verdict["description"].startswith(f"targeted run on {feat[:7]}: ")
    # More backend code: red again until a new result is posted.
    more = _commit(repo, {"django_db2_for_i/client.py": b"x = 3\n"}, "feat: more")
    assert _verdict(capsys, tmp_path, more, posted)["state"] == "failure"


def test_an_unknown_result_commit_does_not_cover(repo, tmp_path, capsys) -> None:
    feat = _commit(repo, {"django_db2_for_i/client.py": b"x = 2\n"}, "feat")
    verdict = _verdict(capsys, tmp_path, feat, [result_comment("0" * 40)])
    assert verdict["state"] == "failure"


def test_the_description_fits_a_status(repo, tmp_path, capsys) -> None:
    feat = _commit(repo, {"django_db2_for_i/client.py": b"x = 2\n"}, "feat")
    assert len(_verdict(capsys, tmp_path, feat, [])["description"]) <= 140


# --- The workflow and the classification -------------------------------------------------

WORKFLOW = (ROOT / ".github/workflows/ibmi-gate.yml").read_text()


def test_the_workflow_runs_mains_files_only() -> None:
    assert "pull_request_target:" in WORKFLOW
    assert "issue_comment:" in WORKFLOW
    assert "\n  pull_request:" not in WORKFLOW
    assert "ref: ${{ github.event.repository.default_branch }}" in WORKFLOW
    assert "persist-credentials: false" in WORKFLOW
    # The pull request's commits are fetched as objects, never checked out.
    assert "head.ref" not in WORKFLOW
    # The head commit from the payload only names where an error status goes.
    [line] = [line for line in WORKFLOW.splitlines() if "head.sha }}" in line]
    assert line.strip() == "EVENT_HEAD_SHA: ${{ github.event.pull_request.head.sha }}"
    assert "git checkout" not in WORKFLOW and "git switch" not in WORKFLOW
    assert 'python3 scripts/ibmi_gate.py --base "origin/$BASE_REF"' in WORKFLOW


def test_the_job_check_is_not_named_like_the_status() -> None:
    """The job's check ("ibmi-gate-check") and the status it sets ("ibmi-gate",
    the required one) have different names, and neither is the verification
    gate (nox -s gate) of the offline workflow."""
    assert "\n  ibmi-gate-check:\n" in WORKFLOW
    assert "\n  gate:\n" not in WORKFLOW


def test_the_status_context_is_the_required_check_name() -> None:
    assert gate.CONTEXT == "ibmi-gate"
    assert "CONTEXT: ibmi-gate\n" in WORKFLOW
    assert WORKFLOW.count('context="$CONTEXT"') == 3  # pending, the verdict, an error


@pytest.mark.parametrize("path", sorted(cp.GATE_PATHS))
def test_gate_files_are_the_strictest_class(path) -> None:
    result = classification({path: (b"a", b"b")})
    assert (result.cls, result.labels) == (cp.FULL, [cp.FULL_TIER_LABEL])
    text = cp.as_markdown(result, None)
    assert f"**Changes the IBM i gate (`{path}`): the maintainer reviews these files.**" in text


def test_other_changes_do_not_mention_the_gate() -> None:
    assert "IBM i gate" not in cp.as_markdown(classification(SQL_CHANGE), None)


# --- workflow_dispatch: the maintainer's re-evaluation of one pull request -----------


def test_a_dispatch_runs_only_from_main() -> None:
    """A dispatch from another branch would run that branch's (modified) gate
    with this token: the job refuses unless the ref is main."""
    job_if = WORKFLOW.split("    if: >-\n", 1)[1].split("    runs-on:", 1)[0]
    conditions = [c.strip().removeprefix("|| ") for c in job_if.strip().splitlines()]
    assert conditions == [
        "github.event_name == 'pull_request_target'",
        "(github.event_name == 'issue_comment' && github.event.issue.pull_request)",
        "(github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main')",
    ]


def test_the_only_input_is_the_pull_request_number() -> None:
    dispatch = WORKFLOW.split("  workflow_dispatch:\n", 1)[1].split("\npermissions:", 1)[0]
    assert dispatch.count("description:") == 1
    assert "      pr:\n" in dispatch and "type: number" in dispatch
    # It selects the pull request (and its concurrency group), nothing else.
    uses = [line.strip() for line in WORKFLOW.splitlines() if "inputs." in line]
    assert uses == [
        "group: ibmi-gate-${{ github.event.pull_request.number || github.event.issue.number"
        " || inputs.pr }}",
        "PR: ${{ github.event.pull_request.number || github.event.issue.number || inputs.pr }}",
    ]
    # The number is checked before it reaches the API.
    assert "''|*[!0-9]*) echo \"not a pull request number: $PR\" >&2; exit 1 ;;" in WORKFLOW


def test_no_input_reaches_the_verdict(monkeypatch) -> None:
    """The verdict depends on the classification, the head and the comments
    only; a waiver stays a comment by the maintainer."""
    import argparse

    seen: list[str] = []
    original = argparse.ArgumentParser.add_argument

    def record(self, *names, **kwargs):
        seen.extend(names)
        return original(self, *names, **kwargs)

    monkeypatch.setattr(argparse.ArgumentParser, "add_argument", record)
    with pytest.raises(SystemExit):
        gate.main(["--help"])
    assert [name for name in seen if name not in ("-h", "--help")] == [
        "--base",
        "--head",
        "--comments",
    ]
    assert (
        'python3 scripts/ibmi_gate.py --base "origin/$BASE_REF" --head "$HEAD_SHA" \\' in WORKFLOW
    )
    assert "--comments comments.json > verdict.json" in WORKFLOW


def test_an_error_status_needs_no_api_call() -> None:
    error_step = WORKFLOW.split("- name: Status on error", 1)[1]
    assert 'sha="${HEAD_SHA:-$EVENT_HEAD_SHA}"' in error_step
    assert 'gh api "repos/$REPO/statuses/$sha" -f state=error' in error_step
