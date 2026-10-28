"""scripts/classify_pr.py: the classes of changed files and the push check (no server needed)."""

import gzip
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.golden import UNVERIFIED

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "classify_pr.py"
spec = importlib.util.spec_from_file_location("scripts_classify_pr", SCRIPT)
cp = importlib.util.module_from_spec(spec)
sys.modules["scripts_classify_pr"] = cp
spec.loader.exec_module(cp)

STAMP = "IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.2, 2026-10-19"


def golden(stamp: str, sql: str = 'SELECT 1 FROM "T";') -> bytes:
    return f"-- golden: q/x\n-- django: 6.1\n-- verified: {stamp}\n{sql}\n".encode()


def corpus(*stamps: str, sql: str = "SELECT 1") -> bytes:
    lines = [
        json.dumps({"compiler": "SQLCompiler", "sql": sql, "n": i, "verified": s})
        for i, s in enumerate(stamps)
    ]
    return gzip.compress("\n".join(lines).encode(), mtime=0)


def run(files: dict[str, tuple[bytes | None, bytes | None]]) -> "cp.Classification":
    """files: path -> (old content, new content); None means absent."""
    changes = [
        cp.Change("A" if old is None else "D" if new is None else "M", path)
        for path, (old, new) in files.items()
    ]
    return cp.classify(changes, lambda p: files[p][0], lambda p: files[p][1])


def test_the_unverified_marker_matches_the_goldens() -> None:
    assert cp.UNVERIFIED == UNVERIFIED


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("django_db2_for_i/drivers/pyodbc.py", cp.FULL),
        ("django_db2_for_i/base.py", cp.FULL),
        ("django_db2_for_i/creation.py", cp.FULL),
        ("django_db2_for_i/capabilities.py", cp.FULL),
        ("django_db2_for_i/compiler.py", cp.FULL),
        ("django_db2_for_i/schema.py", cp.FULL),
        ("django_db2_for_i/compat.py", cp.FULL),
        ("django_db2_for_i/introspection.py", cp.FULL),
        ("django_db2_for_i/operations.py", cp.FULL),
        ("django_db2_for_i/features.py", cp.FULL),
        ("django_db2_for_i/expressions.py", cp.FULL),
        ("django_db2_for_i/client.py", cp.SQL),
        ("django_db2_for_i/validation.py", cp.SQL),
        ("django_db2_for_i/inquiry.py", cp.SQL),
        ("docs/IBMI_NOTES.md", cp.DOCS),
        ("tests/offline/test_schema.py", cp.DOCS),
        ("scripts/update_test_status.py", cp.DOCS),
        (".github/workflows/offline.yml", cp.DOCS),
    ],
)
def test_class_by_path(path, expected) -> None:
    assert run({path: (b"a = 1\n", b"a = 2\n")}).cls == expected


@pytest.mark.parametrize(
    "path",
    [
        "bin/new-tool",
        "newdir/module.py",
        "tests/newsuite/test_x.py",
        "tests/django_settings/settings_other.py",
        "scripts/new_tool.py",
        "Makefile",
        "tests/corpus/new_hook.py",
    ],
)
def test_unknown_paths_fail_closed(path) -> None:
    for old, new in ((None, b"a"), (b"a", b"b"), (b"a", None)):
        result = run({path: (old, new)})
        assert result.cls == cp.FULL, (path, old, new)
        assert "fail closed" in result.findings[0].reason


@pytest.mark.parametrize(
    ("path", "cls", "labels"),
    [
        ("docker/Dockerfile", cp.FULL, ["needs-full-tier"]),
        ("docker/odbcinst.ini", cp.FULL, ["needs-full-tier"]),
        ("compose.yaml", cp.FULL, ["needs-full-tier"]),
        (".dockerignore", cp.FULL, ["needs-full-tier"]),
        ("scripts/pub400.sh", cp.DOCS, ["run-ibmi"]),
        ("scripts/runtests.sh", cp.DOCS, ["run-ibmi"]),
        ("scripts/run_django_tests.py", cp.DOCS, ["run-ibmi"]),
        ("scripts/release_run.py", cp.DOCS, ["run-ibmi"]),
        ("tests/django_settings/settings_pub400.py", cp.DOCS, ["run-ibmi"]),
        ("tests/django_settings/settings_runtests_pub400.py", cp.DOCS, ["run-ibmi"]),
        ("tests/django_settings/settings_offline.py", cp.DOCS, []),
        ("tests/django_settings/settings_corpus.py", cp.DOCS, []),
        ("tests/corpus/capture.py", cp.DOCS, ["run-ibmi"]),
        ("tests/conftest.py", cp.DOCS, ["run-ibmi"]),
        ("probes/qtemp_drop_column.py", cp.DOCS, []),
    ],
)
def test_ibmi_related_paths(path, cls, labels) -> None:
    result = run({path: (b"a = 1\n", b"a = 2\n")})
    assert (result.cls, result.labels) == (cls, labels)


def test_nox_sessions_need_a_targeted_run_unless_the_versions_change() -> None:
    nox = 'DJANGO_PYTHONS = {\n    "6.1": ["3.14"],\n}\n'
    result = run({"noxfile.py": (nox.encode(), (nox + "X = 1\n").encode())})
    assert (result.cls, result.labels) == (cp.DOCS, ["run-ibmi"])


def test_pyproject_beyond_tool_settings_fails_closed() -> None:
    project = '[project]\nname = "a"\ndependencies = []\n[tool.ruff]\nline-length = 99\n'
    build = project + '[build-system]\nrequires = ["hatchling"]\n'
    assert run({"pyproject.toml": (project.encode(), build.encode())}).cls == cp.FULL


def test_the_tooling_needs_no_ibmi_run() -> None:
    """The dev and test tooling: the lock and pyproject's dependency groups (#190)."""
    lock = run({"uv.lock": (b"a", b"b")})
    assert (lock.cls, lock.labels) == (cp.DOCS, [])
    project = '[project]\nname = "a"\ndependencies = []\n'
    groups = project + '[dependency-groups]\ntest = ["pytest>=9"]\n'
    newer = groups.replace("pytest>=9", "pytest>=9.2")
    result = run({"pyproject.toml": (groups.encode(), newer.encode())})
    assert (result.cls, result.labels) == (cp.DOCS, [])


def test_every_tracked_file_is_listed() -> None:
    """New files are classified on purpose, not by the fail-closed default."""
    root = SCRIPT.parents[1]
    listed = subprocess.run(["git", "-C", str(root), "ls-files"], capture_output=True, text=True)
    if listed.returncode != 0:
        pytest.skip("not a git checkout (the wheel session tests a copy)")
    unlisted = [
        path
        for path in listed.stdout.splitlines()
        if "fail closed" in cp.judge(cp.Change("M", path), lambda p: None, lambda p: None).reason
    ]
    assert unlisted == [], "list these in scripts/classify_pr.py"


def test_the_most_demanding_class_wins_and_labels_combine() -> None:
    result = run(
        {
            "docs/x.md": (b"a", b"b"),
            "django_db2_for_i/client.py": (b"a", b"b"),
            "django_db2_for_i/drivers/base.py": (b"a", b"b"),
        }
    )
    assert result.cls == cp.FULL
    assert result.labels == ["needs-full-tier", "run-ibmi"]


def test_the_core_backend_needs_the_full_tier_and_says_why() -> None:
    """#176 broke an own IBM i test its targeted run did not pick (#179)."""
    result = run({"django_db2_for_i/schema.py": (b"a", b"b"), "docs/x.md": (b"a", b"b")})
    assert (result.cls, result.labels) == (cp.FULL, ["needs-full-tier"])
    text = cp.as_markdown(result, None)
    assert "| `django_db2_for_i/schema.py` | needs full tier | core backend (schema.py)" in text
    assert set(cp.CORE_PATHS) == {
        f"django_db2_for_i/{name}.py"
        for name in (
            "schema", "introspection", "compiler", "operations", "features", "expressions",
            "compat",
        )
    }  # fmt: skip


def test_docs_only_has_no_labels() -> None:
    result = run({"docs/x.md": (b"a", b"b"), "README.md": (b"a", b"b")})
    assert (result.cls, result.labels) == (cp.DOCS, [])


@pytest.mark.parametrize(
    "path",
    [
        "tests/pub400/test_schema.py",
        "tests/testapp/models.py",
        "tests/django_settings/settings_pub400.py",
    ],
)
def test_new_or_changed_ibmi_tests_need_a_targeted_run(path) -> None:
    for old in (None, b"a"):
        result = run({path: (old, b"b")})
        assert (result.cls, result.labels) == (cp.DOCS, ["run-ibmi"])


def test_removed_ibmi_tests_need_no_run() -> None:
    assert run({"tests/pub400/test_old.py": (b"a", None)}).labels == []


def test_a_version_bump_alone_is_not_backend_code() -> None:
    old = b'"""Doc."""\n\n__version__ = "0.1.0a3"\n'
    assert run({"django_db2_for_i/__init__.py": (old, old.replace(b"a3", b"a4"))}).cls == cp.DOCS
    changed = old.replace(b"a3", b"a4") + b"import os\n"
    assert run({"django_db2_for_i/__init__.py": (old, changed)}).cls == cp.SQL


def test_goldens_by_stamp() -> None:
    path = "tests/offline/golden/6.1/7.5/queries/x.sql"
    assert run({path: (None, golden(UNVERIFIED))}).cls == cp.SQL
    assert run({path: (golden(STAMP), golden(UNVERIFIED, "SELECT 2;"))}).cls == cp.SQL
    assert run({path: (golden(UNVERIFIED), golden(STAMP))}).cls == cp.DOCS
    assert run({path: (golden(STAMP), None)}).cls == cp.DOCS


def test_corpus_entries_by_stamp() -> None:
    path = "tests/offline/corpus/6.1/7.5/queries/basic.jsonl.gz"
    assert run({path: (None, corpus(STAMP, STAMP))}).cls == cp.DOCS
    result = run({path: (corpus(STAMP), corpus(STAMP, UNVERIFIED))})
    assert result.cls == cp.SQL
    assert "1 corpus entries" in result.findings[0].reason


def test_a_new_pinned_django_commit_needs_the_full_tier() -> None:
    path = "tests/offline/corpus/6.1/7.5/manifest.toml"
    old = b'django = "6.1"\ndjango_commit = "1e01021"\n'
    assert run({path: (old, old.replace(b"1e01021", b"abcdef0"))}).cls == cp.FULL
    assert run({path: (old, old + b"\n[modules.basic]\nunique = 1\n")}).cls == cp.DOCS
    assert run({path: (None, old)}).cls == cp.DOCS  # a new version's corpus: see pyproject


def test_supported_django_versions() -> None:
    nox = 'DJANGO_PYTHONS = {\n    "6.0": ["3.14"],\n    "6.1": ["3.14"],\n}\n'
    more = nox.replace('"6.1": ["3.14"],', '"6.1": ["3.14"],\n    "6.2": ["3.14"],')
    assert run({"noxfile.py": (nox.encode(), more.encode())}).cls == cp.FULL
    pythons = nox.replace('"6.1": ["3.14"]', '"6.1": ["3.13", "3.14"]')
    assert run({"noxfile.py": (nox.encode(), pythons.encode())}).cls == cp.DOCS
    project = '[project]\ndependencies = ["Django>=6.0,<6.2"]\n[tool.ruff]\nline-length = 99\n'
    assert (
        run({"pyproject.toml": (project.encode(), project.replace("6.2", "6.3").encode())}).cls
        == cp.FULL
    )
    assert (
        run({"pyproject.toml": (project.encode(), project.replace("99", "100").encode())}).cls
        == cp.DOCS
    )


def test_supported_django_test_modules_need_a_targeted_run() -> None:
    old = b'[[modules]]\nmodule = "basic"\n'
    result = run({"docs/status.toml": (old, old + b'[[modules]]\nmodule = "schema"\n')})
    assert (result.cls, result.labels) == (cp.DOCS, ["run-ibmi"])
    assert run({"docs/status.toml": (old, old + b'[versions]\nibmi = "7.5"\n')}).labels == []


@pytest.mark.parametrize(
    ("files", "expected"),
    [
        ({"tests/offline/golden/6.1/7.5/q/x.sql": (golden(UNVERIFIED), golden(STAMP))}, True),
        (
            {
                "tests/offline/golden/6.1/7.5/q/x.sql": (golden(UNVERIFIED), golden(STAMP)),
                "docs/TEST_STATUS.md": (b"a", b"b"),
                "tests/offline/golden/last-verification.txt": (b"a", b"b"),
            },
            True,
        ),
        (
            {
                "tests/offline/golden/6.1/7.5/q/x.sql": (
                    golden(UNVERIFIED),
                    golden(STAMP, "SELECT 2;"),
                )
            },
            False,
        ),
        ({"tests/offline/golden/6.1/7.5/q/x.sql": (golden(STAMP), golden(UNVERIFIED))}, False),
        ({"tests/offline/golden/6.1/7.5/q/x.sql": (None, golden(STAMP))}, False),
        (
            {
                "tests/offline/corpus/6.1/7.5/queries/b.jsonl.gz": (
                    corpus(UNVERIFIED),
                    corpus(STAMP),
                )
            },
            True,
        ),
        (
            {
                "tests/offline/corpus/6.1/7.5/queries/b.jsonl.gz": (
                    corpus(UNVERIFIED),
                    corpus(STAMP, sql="X"),
                )
            },
            False,
        ),
        (
            {
                "tests/offline/corpus/6.1/7.5/manifest.toml": (
                    b'[modules.b]\nlevel = "a"\nunique = 1\n',
                    b'[modules.b]\nlevel = "b"\nunique = 1\n',
                )
            },
            True,
        ),
        (
            {
                "tests/offline/corpus/6.1/7.5/manifest.toml": (
                    b'[modules.b]\nlevel = "a"\nunique = 1\n',
                    b'[modules.b]\nlevel = "a"\nunique = 2\n',
                )
            },
            False,
        ),
        ({"docs/TEST_STATUS.md": (b"a", b"b"), "docs/x.md": (b"a", b"b")}, False),
        ({}, False),
    ],
)
def test_stamps_only(files, expected) -> None:
    changes = [cp.Change("A" if old is None else "M", path) for path, (old, _) in files.items()]
    assert cp.stamps_only(changes, lambda p: files[p][0], lambda p: files[p][1]) is expected


RANGE_DIFF_SAME = """\
1:  1111111 = 1:  2222222 feat: one
2:  3333333 = 2:  4444444 test: two
"""
RANGE_DIFF_CHANGED = """\
1:  1111111 = 1:  2222222 feat: one
2:  3333333 ! 2:  4444444 test: two
    @@ tests/x.py
    -    a = 1
    +    a = 2
"""


def test_range_diff_identical() -> None:
    assert cp.range_diff_identical(RANGE_DIFF_SAME)
    assert not cp.range_diff_identical(RANGE_DIFF_CHANGED)
    assert not cp.range_diff_identical("1:  1111111 < -:  ------- feat: dropped\n")
    assert not cp.range_diff_identical("")


def test_markdown_lists_only_files_that_need_a_run() -> None:
    result = run({"docs/x.md": (b"a", b"b"), "django_db2_for_i/client.py": (b"a", b"b")})
    text = cp.as_markdown(result, cp.PushCheck(True, "the push changes the pull request"))
    assert text.startswith(cp.COMMENT_MARKER)
    assert "**SQL-affecting**" in text and "`run-ibmi`" in text
    assert "`django_db2_for_i/client.py`" in text and "`docs/x.md`" not in text
    assert "| 1 more |" in text
    assert "IBM i run needed: **yes, run-ibmi (the push changes the pull request)**." in text
    assert json.loads(cp.as_json(result, None))["labels"] == ["run-ibmi"]


# --- The push check on a real (temporary) repository ------------------------------------


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
    monkeypatch.chdir(tmp_path)
    return tmp_path


GOLDEN = "tests/offline/golden/6.1/7.5/q/x.sql"


def test_push_of_stamps_only_needs_no_new_run(repo) -> None:
    _git(repo, "switch", "-q", "-c", "pr")
    before = _commit(repo, {GOLDEN: golden(UNVERIFIED)}, "test: golden")
    head = _commit(repo, {GOLDEN: golden(STAMP), "docs/TEST_STATUS.md": b"1\n"}, "test: stamps")
    assert cp.check_push(before, head, "main") == cp.PushCheck(
        False, "the push only adds verification stamps and files generated from them"
    )
    fixed = _commit(repo, {GOLDEN: golden(STAMP, "SELECT 2;")}, "fix")
    assert cp.check_push(head, fixed, "main").new_run_needed


def test_push_of_docs_only_needs_no_new_run(repo) -> None:
    _git(repo, "switch", "-q", "-c", "pr")
    before = _commit(repo, {"django_db2_for_i/client.py": b"x = 2\n"}, "feat")
    (repo / "changelog.d").mkdir()
    _git(repo, "mv", "docs/a.md", "changelog.d/1.added.md")
    _git(repo, "commit", "-q", "-m", "docs: changelog fragment")
    head = _git(repo, "rev-parse", "HEAD")
    assert cp.check_push(before, head, "main") == cp.PushCheck(
        False, "the push changes only docs/tests that do not run on IBM i"
    )
    test = _commit(repo, {"tests/pub400/test_x.py": b"def test(): pass\n"}, "test")
    assert cp.check_push(head, test, "main").new_run_needed
    fixed = _commit(repo, {"django_db2_for_i/client.py": b"x = 3\n"}, "fix")
    assert cp.check_push(test, fixed, "main").new_run_needed
    stamped = _commit(repo, {GOLDEN: golden(STAMP)}, "test: a golden with a stamp")
    assert cp.check_push(fixed, stamped, "main").new_run_needed


def test_rebase_onto_docs_commits_needs_no_new_run(repo) -> None:
    _git(repo, "switch", "-q", "-c", "pr")
    before = _commit(repo, {"django_db2_for_i/client.py": b"x = 2\n"}, "feat: x")
    _git(repo, "switch", "-q", "main")
    _commit(repo, {"docs/a.md": b"b\n"}, "docs: a")
    _git(repo, "switch", "-q", "pr")
    _git(repo, "rebase", "-q", "main")
    head = _git(repo, "rev-parse", "HEAD")
    check = cp.check_push(before, head, "main")
    assert check == cp.PushCheck(
        False, "a rebase with identical changes (git range-diff) onto docs/tests-only commits"
    )


def test_rebase_onto_gate_commits_needs_no_new_run(repo) -> None:
    """The gate's files are the strictest class in their own pull request
    (#163 needed a full run again after #161), not for a rebase over them."""
    _git(repo, "switch", "-q", "-c", "pr")
    before = _commit(repo, {"django_db2_for_i/client.py": b"x = 2\n"}, "feat: x")
    _git(repo, "switch", "-q", "main")
    _commit(repo, {"scripts/ibmi_gate.py": b"g = 1\n", "docs/a.md": b"b\n"}, "ci: gate")
    _git(repo, "switch", "-q", "pr")
    _git(repo, "rebase", "-q", "main")
    check = cp.check_push(before, _git(repo, "rev-parse", "HEAD"), "main")
    assert check == cp.PushCheck(
        False,
        "a rebase with identical changes (git range-diff) onto docs/tests-only commits "
        "and IBM i gate changes",
    )


def _stamped_rebase(repo, extra: dict[str, bytes]) -> tuple[str, str]:
    """A pull request with an unverified golden; its run, then main moves on
    (docs only), then the PR is rebased and a commit with ``extra`` follows."""
    _git(repo, "switch", "-q", "-c", "pr")
    before = _commit(
        repo,
        {"django_db2_for_i/client.py": b"x = 2\n", GOLDEN: golden(UNVERIFIED)},
        "feat: x",
    )
    _git(repo, "switch", "-q", "main")
    _commit(repo, {"docs/a.md": b"b\n"}, "docs: a")
    _git(repo, "switch", "-q", "pr")
    _git(repo, "rebase", "-q", "main")
    head = _commit(repo, extra, "after the run")
    return before, head


def test_a_rebase_may_carry_the_runs_stamps(repo) -> None:
    """#164: the run's stamps commit and a rebase onto docs-only commits, each
    an exception on its own, also together."""
    before, head = _stamped_rebase(repo, {GOLDEN: golden(STAMP)})
    assert cp.check_push(before, head, "main") == cp.PushCheck(
        False,
        "a rebase with identical changes (git range-diff) plus the run's verification "
        "stamps onto docs/tests-only commits",
    )


def test_a_rebase_with_another_extra_commit_needs_a_new_run(repo) -> None:
    before, head = _stamped_rebase(repo, {"django_db2_for_i/client.py": b"x = 3\n"})
    check = cp.check_push(before, head, "main")
    assert check == cp.PushCheck(True, "a rewrite whose own changes differ (git range-diff)")


def test_an_extra_commit_with_stamps_and_more_needs_a_new_run(repo) -> None:
    before, head = _stamped_rebase(repo, {GOLDEN: golden(STAMP), "docs/c.md": b"c\n"})
    assert cp.check_push(before, head, "main").new_run_needed


def test_range_diff_extra_commits() -> None:
    same = "1:  1111111 = 1:  2222222 feat: x\n"
    extra = same + "-:  ------- > 2:  3333333 test(golden): stamps\n"
    dropped = same + "2:  4444444 < -:  ------- feat: dropped\n"
    assert cp.range_diff_identical(same)
    assert not cp.range_diff_identical(extra)
    assert cp.range_diff_identical(extra, extra_allowed=lambda sha: sha == "3333333")
    assert not cp.range_diff_identical(extra, extra_allowed=lambda sha: False)
    assert not cp.range_diff_identical(dropped, extra_allowed=lambda sha: True)


def test_classify_pr_is_a_gate_file() -> None:
    """It decides the gate's verdict: the strictest class, flagged for review."""
    result = run({"scripts/classify_pr.py": (b"a", b"b")})
    assert (result.cls, result.labels) == (cp.FULL, [cp.FULL_TIER_LABEL])
    assert "**Changes the IBM i gate (`scripts/classify_pr.py`)" in cp.as_markdown(result, None)


def test_rebase_onto_gate_and_backend_commits_needs_a_new_run(repo) -> None:
    _git(repo, "switch", "-q", "-c", "pr")
    before = _commit(repo, {"docs/b.md": b"b\n"}, "docs: b")
    _git(repo, "switch", "-q", "main")
    _commit(
        repo,
        {".github/workflows/ibmi-gate.yml": b"on: {}\n", "django_db2_for_i/client.py": b"y\n"},
        "mixed",
    )
    _git(repo, "switch", "-q", "pr")
    _git(repo, "rebase", "-q", "main")
    check = cp.check_push(before, _git(repo, "rev-parse", "HEAD"), "main")
    assert check == cp.PushCheck(
        True, f"a rebase onto main commits that need an IBM i run ({cp.SQL})"
    )


def test_a_gate_file_in_the_pull_request_itself_stays_the_strictest_class() -> None:
    result = run({"scripts/ibmi_gate.py": (b"a", b"b")})
    assert (result.cls, result.labels) == (cp.FULL, [cp.FULL_TIER_LABEL])


def test_rebase_onto_backend_commits_needs_a_new_run(repo) -> None:
    _git(repo, "switch", "-q", "-c", "pr")
    before = _commit(repo, {"docs/b.md": b"b\n"}, "docs: b")
    _git(repo, "switch", "-q", "main")
    _commit(repo, {"django_db2_for_i/base.py": b"y = 1\n"}, "fix: base")
    _git(repo, "switch", "-q", "pr")
    _git(repo, "rebase", "-q", "main")
    check = cp.check_push(before, _git(repo, "rev-parse", "HEAD"), "main")
    assert check.new_run_needed and cp.FULL in check.reason


def test_rewrite_with_other_changes_needs_a_new_run(repo) -> None:
    _git(repo, "switch", "-q", "-c", "pr")
    before = _commit(repo, {"django_db2_for_i/client.py": b"x = 2\n"}, "feat: x")
    (repo / "django_db2_for_i/client.py").write_bytes(b"x = 3\n")
    _git(repo, "commit", "-q", "-a", "--amend", "-m", "feat: x")
    check = cp.check_push(before, _git(repo, "rev-parse", "HEAD"), "main")
    assert check == cp.PushCheck(True, "a rewrite whose own changes differ (git range-diff)")


def test_an_unknown_previous_head_needs_a_new_run(repo) -> None:
    check = cp.check_push("0" * 40, "HEAD", "main")
    assert check == cp.PushCheck(True, "the previous head is not available")


def test_command_line_on_a_branch(repo, capsys) -> None:
    _git(repo, "switch", "-q", "-c", "pr")
    _commit(repo, {"tests/pub400/test_x.py": b"def test(): pass\n"}, "test: x")
    assert cp.main(["--base", "main", "--format", "json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert (data["class"], data["labels"], data["push"]) == (cp.DOCS, ["run-ibmi"], None)


def test_run_verdict() -> None:
    docs = run({"docs/x.md": (b"a", b"b")})
    sql = run({"django_db2_for_i/client.py": (b"a", b"b")})
    changed, stamps = cp.PushCheck(True, "changed"), cp.PushCheck(False, "stamps only")
    assert cp.run_verdict(docs, changed).startswith("no (docs/tests only")
    assert cp.run_verdict(sql, None) == "yes, run-ibmi"
    assert cp.run_verdict(sql, changed) == "yes, run-ibmi (changed)"
    assert cp.run_verdict(sql, stamps).startswith("no new run (stamps only)")


# --- The previous head from the PR comment (CI) ------------------------------------------


SHA = "0123456789abcdef0123456789abcdef01234567"


@pytest.mark.parametrize(
    ("comment", "expected"),
    [
        (f"<!-- classify-pr head={SHA} -->\n### Classification", SHA),
        ("<!-- classify-pr -->\n### Classification", None),  # written before the head was named
        ("", None),  # no comment yet
        (f"text\n<!-- classify-pr head={SHA} -->", None),  # only as the first line
        ("<!-- classify-pr head=abc123 -->", None),  # a full SHA only
    ],
)
def test_previous_head(comment, expected) -> None:
    assert cp.previous_head(comment) == expected


def test_the_comment_names_the_head_it_classified() -> None:
    result = run({"django_db2_for_i/client.py": (b"a", b"b")})
    comment = cp.as_markdown(result, None, SHA)
    assert comment.splitlines()[0] == f"<!-- classify-pr head={SHA} -->"
    assert comment.startswith(cp.COMMENT_PREFIX)
    assert cp.previous_head(comment) == SHA


def _json(capsys, *args: str) -> dict:
    assert cp.main(["--base", "main", "--format", "json", *args]) == 0
    return json.loads(capsys.readouterr().out)


def test_no_comment_yet_classifies_the_whole_pull_request(repo, tmp_path, capsys) -> None:
    """The first run, or the first run after a cancelled one: no previous
    head, so the labels of the whole pull request are added."""
    _git(repo, "switch", "-q", "-c", "pr")
    _commit(repo, {"django_db2_for_i/client.py": b"x = 2\n"}, "feat")
    _commit(repo, {"changelog.d/1.added.md": b"x\n"}, "docs: fragment")
    empty = tmp_path / "previous.md"
    empty.write_text("")
    assert cp.main(["--previous-comment", str(empty), "--print-before"]) == 0
    assert capsys.readouterr().out == "\n"
    data = _json(capsys, "--previous-comment", str(empty))
    assert (data["labels"], data["push"]) == (["run-ibmi"], None)


def test_a_cancelled_run_does_not_count_as_classified(repo, tmp_path, capsys) -> None:
    """#158: the run for the backend commit was cancelled by a docs-only push
    right after it. The push's own "before" (the cancelled head) would say "no
    new run"; the comment still names the last classified head, so the push
    is checked from there and the labels are added."""
    _git(repo, "switch", "-q", "-c", "pr")
    classified = _commit(repo, {"docs/b.md": b"b\n"}, "docs: b")
    cancelled = _commit(repo, {"django_db2_for_i/client.py": b"x = 2\n"}, "feat")
    _commit(repo, {"changelog.d/1.added.md": b"x\n"}, "docs: fragment")

    from_push = _json(capsys, "--before", cancelled)
    assert from_push["push"]["new_run_needed"] is False  # the gap

    comment = tmp_path / "previous.md"
    comment.write_text(f"<!-- classify-pr head={classified} -->\n### Classification")
    assert cp.main(["--previous-comment", str(comment), "--print-before"]) == 0
    assert capsys.readouterr().out == f"{classified}\n"
    data = _json(capsys, "--previous-comment", str(comment))
    assert data["labels"] == ["run-ibmi"]
    assert data["push"]["new_run_needed"] is True


def test_a_completed_run_on_the_same_head_keeps_the_labels(repo, tmp_path, capsys) -> None:
    _git(repo, "switch", "-q", "-c", "pr")
    head = _commit(repo, {"django_db2_for_i/client.py": b"x = 2\n"}, "feat")
    comment = tmp_path / "previous.md"
    comment.write_text(f"<!-- classify-pr head={head} -->\n")
    data = _json(capsys, "--previous-comment", str(comment))
    assert data["push"]["new_run_needed"] is False


def test_the_markdown_comment_names_the_head(repo, capsys) -> None:
    _git(repo, "switch", "-q", "-c", "pr")
    head = _commit(repo, {"django_db2_for_i/client.py": b"x = 2\n"}, "feat")
    assert cp.main(["--base", "main", "--format", "markdown"]) == 0
    assert capsys.readouterr().out.splitlines()[0] == f"<!-- classify-pr head={head} -->"


def test_before_and_previous_comment_exclude_each_other(tmp_path) -> None:
    comment = tmp_path / "previous.md"
    comment.write_text("")
    with pytest.raises(SystemExit):
        cp.main(["--before", SHA, "--previous-comment", str(comment)])


def test_the_workflow_takes_the_previous_head_from_the_comment() -> None:
    workflow = (Path(__file__).resolve().parents[2] / ".github/workflows/classify.yml").read_text()
    assert "github.event.before" not in workflow
    assert "--previous-comment previous.md" in workflow
    labels = workflow.index('gh api "repos/$REPO/issues/$PR/labels"')
    comment = workflow.index("-F body=@comment.md")
    assert labels < comment  # the labels before the comment that names the head
