"""bin/release-prepare and scripts/release_prepare.py (no server, nothing on GitHub)."""

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
BIN = ROOT / "bin"
needs_bin = pytest.mark.skipif(not BIN.is_dir(), reason="bin/ is not part of this copy")
needs_status_data = pytest.mark.skipif(
    not (ROOT / "docs" / "status.toml").exists(), reason="docs/ is not part of this copy"
)

spec = importlib.util.spec_from_file_location(
    "scripts_release_prepare", ROOT / "scripts" / "release_prepare.py"
)
prepare = importlib.util.module_from_spec(spec)
sys.modules["scripts_release_prepare"] = prepare
spec.loader.exec_module(prepare)

# What bin/release-prepare must never do itself (CONTRIBUTING.md, "Releases").
FORBIDDEN = re.compile(
    r"git\b[^\n]*\btag\b|gh\s+release|gh\s+workflow|gh\s+run\b|--tags|push[^\n]*--delete"
    r"|push[^\n]*\bv\$?\{?version|release\.yml"
)


def run_prepare(*args: str, script: Path = BIN / "release-prepare", tmp_path: Path):
    fake = tmp_path / "fakebin"
    fake.mkdir(exist_ok=True)
    for tool in ("docker", "gh", "git"):
        (fake / tool).write_text(f'#!/bin/sh\necho "{tool} $*" >> "{tmp_path}/called"\n')
        (fake / tool).chmod(0o755)
    env = {**os.environ, "PATH": f"{fake}:{os.environ['PATH']}"}
    return subprocess.run(["bash", str(script), *args], capture_output=True, text=True, env=env)


# --- bin/release-prepare -----------------------------------------------------------------


@needs_bin
def test_it_never_tags_or_releases_and_prints_the_manual_steps(tmp_path) -> None:
    result = run_prepare("--dry-run", "0.1.0a5", tmp_path=tmp_path)
    assert result.returncode == 0, result.stderr
    commands = [line for line in result.stdout.splitlines() if line.startswith("+ ")]
    assert commands and not [line for line in commands if FORBIDDEN.search(line)]
    assert commands[-1].startswith("+ gh pr create --base main --head chore/release-0.1.0a5")
    steps = result.stdout.split("What the maintainer does by hand", 1)[1]
    assert 'git tag -s v0.1.0a5 -m "v0.1.0a5"' in steps
    assert "git push origin v0.1.0a5" in steps
    assert (
        "3. Create the GitHub release yourself (the release workflow is parked, see #94)." in steps
    )
    called = (tmp_path / "called").read_text() if (tmp_path / "called").exists() else ""
    # A dry run only reads (container() asks git for the shared git directory).
    assert all(
        " rev-parse --path-format=absolute --git-common-dir" in line for line in called.splitlines()
    ), called


@needs_bin
def test_its_code_has_no_tag_or_release_command() -> None:
    """Only the closing text (a here-document the script prints) names those commands."""
    text = (BIN / "release-prepare").read_text()
    code = text.split("cat <<EOF", 1)[0]
    lines = [line for line in code.splitlines() if not line.lstrip().startswith("#")]
    assert not [line for line in lines if FORBIDDEN.search(line)]
    executed = "\n".join(lines)
    assert "pub400" not in executed and ".env" not in executed  # offline: no IBM i, no .env


@needs_bin
def test_it_refuses_in_a_subagent_worktree(tmp_path) -> None:
    worktree = tmp_path / "repo" / ".claude" / "worktrees" / "agent-x"
    (worktree / "bin").mkdir(parents=True)
    for name in ("_common.sh", "release-prepare"):
        shutil.copy(BIN / name, worktree / "bin" / name)
    result = run_prepare("0.1.0a5", script=worktree / "bin" / "release-prepare", tmp_path=tmp_path)
    assert result.returncode == 2
    assert "refused in a subagent worktree" in result.stderr
    assert not (tmp_path / "called").exists()


@needs_bin
def test_it_needs_exactly_one_version(tmp_path) -> None:
    for args, message in [((), "name the version"), (("1", "2"), "name the version")]:
        result = run_prepare(*args, tmp_path=tmp_path)
        assert result.returncode == 2 and message in result.stderr
    result = run_prepare("--fast", tmp_path=tmp_path)
    assert result.returncode == 2 and "unknown argument: --fast" in result.stderr


# --- scripts/release_prepare.py ----------------------------------------------------------


def test_versions_compare_as_releases_and_pre_releases() -> None:
    order = ["0.1.0a4", "0.1.0a5", "0.1.0a10", "0.1.0b1", "0.1.0rc1", "0.1.0", "0.1.1", "1.0.0"]
    keys = [prepare.version_key(v) for v in order]
    assert keys == sorted(keys) and len(set(keys)) == len(keys)
    for invalid in ("v0.1.0", "0.1", "0.1.0.dev1", "0.1.0a", "latest"):
        assert prepare.version_key(invalid) is None


@pytest.fixture
def release_repo(tmp_path, monkeypatch):
    """A repository copy for check(): version 0.1.0a4, one fragment, two Django versions."""
    (tmp_path / "django_db2_for_i").mkdir()
    (tmp_path / "django_db2_for_i" / "__init__.py").write_text('__version__ = "0.1.0a4"\n')
    (tmp_path / "noxfile.py").write_text('DJANGO_PYTHONS = {"6.0": ["3.14"], "6.1": ["3.14"]}\n')
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "status.toml").write_text(
        '[[modules]]\nmodule = "basic"\n\n[[modules]]\nmodule = "queries"\n'
        'labels = ["queries.tests"]\n'
    )
    monkeypatch.setattr(prepare, "ROOT", tmp_path)
    monkeypatch.setattr(prepare, "VERSION_FILE", tmp_path / "django_db2_for_i" / "__init__.py")
    fragments = [tmp_path / "changelog.d" / "131.added.md"]
    changelog = SimpleNamespace(fragment_paths=lambda: fragments, check=lambda paths: [])
    monkeypatch.setattr(
        prepare, "_script", lambda name: changelog if name == "assemble_changelog" else None
    )
    changes = {}
    monkeypatch.setattr(prepare, "backend_changes", lambda commit: changes.get(commit, []))
    state = SimpleNamespace(root=tmp_path, fragments=fragments, changes=changes)

    def run(django, results, backend="abc1234 2026-10-22"):
        path = tmp_path / "test-results" / django / "release-run" / "state.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"backend": backend, "django": "d" * 40, "results": results}))

    state.run = run
    return state


PASSED = {"basic": "passed", "queries.tests": "passed", "pub400 tier": "passed"}


def test_check_passes_when_every_precondition_holds(release_repo) -> None:
    release_repo.run("6.0", PASSED)
    release_repo.run("6.1", PASSED)
    assert prepare.check("0.1.0a5") == []
    assert prepare.main(["check", "0.1.0a5"]) == 0


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"version": "0.1.0a4"}, "0.1.0a4 is not newer than __version__ 0.1.0a4"),
        ({"version": "0.1.0a3"}, "is not newer"),
        ({"version": "v0.1.0a5"}, "is not a release or pre-release version"),
        ({"fragments": []}, "changelog.d/ has no fragments"),
        ({"missing": "6.0"}, "Django 6.0: no release run (bin/release-run --django 6.0)"),
        ({"failed": "queries.tests"}, "Django 6.1: the release run is not complete and passed"),
        ({"not_run": "pub400 tier"}, "(failed: none; not run: 1)"),
        ({"changed": True}, "Django 6.1: changed since its release run (abc1234)"),
    ],
)
def test_check_refuses_each_unmet_precondition(release_repo, change, message) -> None:
    release_repo.run("6.0", PASSED)
    results = dict(PASSED)
    if "failed" in change:
        results[change["failed"]] = "failed"
    if "not_run" in change:
        del results[change["not_run"]]
    release_repo.run("6.1", results)
    if "missing" in change:
        (
            release_repo.root / "test-results" / change["missing"] / "release-run" / "state.json"
        ).unlink()
    if "fragments" in change:
        release_repo.fragments.clear()
    if change.get("changed"):
        release_repo.changes["abc1234"] = ["django_db2_for_i/operations.py: backend code"]
    problems = prepare.check(change.get("version", "0.1.0a5"))
    assert any(message in problem for problem in problems), problems
    assert prepare.main(["check", change.get("version", "0.1.0a5")]) == 1


def test_backend_changes_use_the_classification(monkeypatch) -> None:
    monkeypatch.setattr(prepare, "git", lambda *args: "f" * 40)
    finding = SimpleNamespace(
        path="django_db2_for_i/operations.py", reason="backend", labels={"run-ibmi"}
    )
    docs = SimpleNamespace(path="docs/x.md", reason="docs", labels=set())
    classify = SimpleNamespace(
        classify_refs=lambda old, new: SimpleNamespace(
            labels=sorted(set().union(*(f.labels for f in results))), findings=results
        )
    )
    monkeypatch.setattr(prepare, "_script", lambda name: classify)
    results = [docs]
    assert prepare.backend_changes("abc1234") == []
    results = [docs, finding]
    assert prepare.backend_changes("abc1234") == ["django_db2_for_i/operations.py: backend"]

    def unknown(*args):
        raise subprocess.CalledProcessError(1, ["git"])

    monkeypatch.setattr(prepare, "git", unknown)
    assert prepare.backend_changes("abc1234") == ["abc1234 is unknown or not an ancestor of HEAD"]


def test_body_lists_the_runs_and_the_corpus(release_repo) -> None:
    release_repo.run("6.0", PASSED)
    release_repo.run("6.1", {"basic": "passed"})
    manifest = release_repo.root / "tests" / "offline" / "corpus" / "6.1" / "7.5" / "manifest.toml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text('django = "6.1"\n\n[modules.basic]\nunique = 187\nlevel = "IBM i 7.5"\n')
    text = prepare.body("0.1.0a5")
    assert "| 6.0 | `abc1234 2026-10-22` | 3 of 3 | all passed |" in text
    assert "| 6.1 | `abc1234 2026-10-22` | 1 of 3 | NOT complete |" in text
    assert "| 6.1 | basic | 187 | IBM i 7.5 |" in text
    assert "never tags and never creates releases" in text


@needs_status_data
def test_the_real_lists_are_read() -> None:
    assert "6.1" in prepare.supported_django()
    assert "basic" in prepare.release_labels()
    assert prepare.version_key(prepare.current_version()) is not None
