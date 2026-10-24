"""Classify a pull request from its changed files, and decide whether a push needs a new IBM i run.

    python scripts/classify_pr.py [--base origin/main] [--head HEAD]
                                  [--before SHA | --previous-comment FILE [--print-before]]
                                  [--format text|markdown|json]

The changed files are those of ``git diff <merge-base of base and head> <head>``.
Every file gets one of three classes; the pull request gets the most demanding:

- **needs full tier**: the driver layer (``django_db2_for_i/drivers/``),
  ``base.py``, ``creation.py``, the capabilities, the pinned Django commit
  (``django_commit`` of a corpus manifest; ``vendor/`` itself is not in git) or
  the supported Django versions (``DJANGO_PYTHONS`` in noxfile.py, the
  dependencies in pyproject.toml). Label ``needs-full-tier``.
- **SQL-affecting**: any other backend code, a golden without a verification
  stamp, or corpus entries without one (new or changed SQL). Label ``run-ibmi``.
- **docs/tests only**: the paths listed in ``DOCS_PATHS`` and
  ``IBMI_RUN_PATHS``. Those of ``IBMI_RUN_PATHS`` (own IBM i tests, the test
  models, the IBM i settings, the IBM i run tooling, the nox sessions) and the
  supported Django test modules in docs/status.toml still need a targeted IBM i
  run: label ``run-ibmi``.

It **fails closed**: a path matched by no rule (a new file or directory) is
"needs full tier", like the container image (``docker/``, ``compose.yaml``).

With ``--before`` (the previous head of the pull request) the push from
``before`` to ``head`` is checked as well (CLAUDE.md, "Git workflow"). It needs
no new IBM i run when it only adds verification stamps and files generated from
them, when its own files are docs/tests that need no label and are no goldens or
corpus entries (a stamp is only trusted from the run itself; e.g. a renamed
changelog fragment), or when it is a rebase whose own changes are identical
(``git range-diff``) and whose new base commits are docs/tests only. Otherwise
the labels apply again.

In CI the previous head is not the push's ``before`` but the head the last
*completed* classification handled: the PR comment's marker names it
(``<!-- classify-pr head=<sha> -->``, ``--previous-comment``). A run that was
cancelled (a newer push) never wrote its comment, so the next run checks the
push from the last head whose labels were really applied; without such a
comment the whole pull request is classified and its labels are added.

The script only reads git; it never connects to an IBM i and needs no project
dependencies (the CI job runs it with the runner's Python). The labels are
added by CI and removed by the main session only, after the run
(``.github/workflows/classify.yml``).
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
import gzip
import json
import re
import subprocess
import sys
import tomllib
from collections.abc import Callable, Iterable

DOCS, SQL, FULL = "docs/tests only", "SQL-affecting", "needs full tier"
RANK = {DOCS: 0, SQL: 1, FULL: 2}
FULL_TIER_LABEL, RUN_IBMI_LABEL = "needs-full-tier", "run-ibmi"
# The comment's first line; it names the head the classification handled.
COMMENT_MARKER = "<!-- classify-pr -->"
COMMENT_PREFIX = "<!-- classify-pr"
_COMMENT_HEAD = re.compile(r"\A<!-- classify-pr head=(?P<sha>[0-9a-f]{40}) -->")

BACKEND = "django_db2_for_i/"
FULL_TIER_PATHS = {
    "django_db2_for_i/drivers/": "the driver layer",
    "django_db2_for_i/base.py": "the connection (base.py)",
    "django_db2_for_i/creation.py": "the test database setup (creation.py)",
    "django_db2_for_i/capabilities.py": "the server capabilities",
}
# The environment of every IBM i run: the image with the ODBC driver.
ENVIRONMENT_PATHS = {
    "docker/": "the container image (ODBC driver)",
    "compose.yaml": "the container setup",
    ".dockerignore": "the image build context",
}
# docs/tests only, but they run on IBM i (or drive the IBM i runs): a targeted run.
IBMI_RUN_PATHS = {
    "tests/pub400/": "own IBM i tests",
    "tests/testapp/": "the test models",
    "tests/conftest.py": "the shared test fixtures",
    "tests/golden.py": "the golden format (executed on IBM i)",
    "tests/golden_cases/": "the golden cases (executed on IBM i)",
    "tests/offline/golden/unverifiable.toml": "the expected failures of the IBM i golden check",
    "tests/verification_gate.py": "the unverifiable list (read by the IBM i golden check)",
    "tests/results_summary.py": "the results summary plugin",
    "tests/redaction.py": "the log redaction",
    "tests/boolean_condition_scenarios.py": "scenarios of the IBM i tests",
    "tests/tuple_lookup_scenarios.py": "scenarios of the IBM i tests",
    "tests/corpus/capture.py": "the corpus capture (runs on IBM i)",
    "tests/corpus/store.py": "the corpus format (used by the capture)",
    "tests/django_settings/settings_pub400.py": "the IBM i test settings",
    "tests/django_settings/settings_runtests_pub400.py": "the IBM i Django test settings",
    "scripts/pub400.sh": "the IBM i run wrapper",
    "scripts/pub400_lock.py": "the PUB400 lock",
    "scripts/probe_approval.py": "the approval check of lib_ probes (bin/probe)",
    "bin/_common.sh": "the shared part of the bin/ scripts (PUB400 runs)",
    "bin/doctor": "the environment check (one PUB400 connection)",
    "bin/probe": "the probe runner",
    "bin/ibmi-test": "targeted IBM i runs",
    "bin/verify": "targeted IBM i runs and the stamps they write",
    "scripts/verify.py": "the selection of targeted IBM i runs (bin/verify)",
    "bin/ibmi-cleanup": "the cleanup of leftover test objects",
    "scripts/ibmi_cleanup.py": "the cleanup of leftover test objects",
    "tests/table_registry.py": "the list of objects test runs create",
    "scripts/runtests.sh": "the Django test runner on IBM i",
    "scripts/run_django_tests.py": "the Django test runner on IBM i",
    "scripts/release_run.py": "the release run",
    "bin/release-run": "the release run",
}
# docs/tests only: nothing here runs on IBM i. Everything matched by no rule in
# judge() is "needs full tier" (fails closed): a new file or directory is never
# waved through, it is listed here (or above) when it is added.
DOCS_PATHS = {
    "docs/": "docs",
    "changelog.d/": "changelog fragment",
    "probes/": "probes (run on request, with their own rules)",
    "tests/offline/": "offline tests",
    "tests/__init__.py": "test package",
    "tests/corpus/__init__.py": "test package",
    "tests/corpus/test_replay.py": "the offline replay",
    "tests/django_settings/__init__.py": "test package",
    "tests/django_settings/settings_offline.py": "the offline test settings",
    "tests/django_settings/settings_corpus.py": "the offline replay settings",
    "scripts/assemble_changelog.py": "offline tooling",
    "scripts/build_corpus.py": "offline tooling",
    "scripts/changelog_section.py": "offline tooling",
    "scripts/classify_pr.py": "offline tooling",
    "scripts/features.py": "offline tooling",
    "scripts/update_test_status.py": "offline tooling",
    "scripts/verify_release_tag.py": "offline tooling",
    "bin/check": "offline tooling (what CI does)",
    "bin/status": "offline tooling (status pages)",
    "bin/setup": "first-time setup (images, .env template, vendor/ checkouts)",
    "bin/help": "the workflow guide (reads docs/WORKFLOW.md)",
    "bin/worktree-remove": "offline tooling (removes a merged worktree, keeps its results)",
    "scripts/publish_probe_result.py": "offline tooling (a probe result without names)",
    "bin/release-prepare": "offline tooling (the release pull request)",
    "scripts/release_prepare.py": "offline tooling (the release pull request)",
    ".github/": "CI (never connects to an IBM i)",
    ".devcontainer/": "editor setup",
    ".claude/": "editor setup",
    "README.md": "docs",
    "CHANGELOG.md": "docs",
    "CONTRIBUTING.md": "docs",
    "CLAUDE.md": "docs",
    "LICENSE": "docs",
    ".gitignore": "repository settings",
    ".gitleaks.toml": "repository settings",
    ".env.example": "settings template",
    "django-db2-for-i.code-workspace": "editor setup",
}
GOLDEN_DIR = "tests/offline/golden/"
CORPUS_DIR = "tests/offline/corpus/"
# tests/golden.py: UNVERIFIED (an offline test keeps the two equal).
UNVERIFIED = "unverified"
VERIFIED_LINE = re.compile(r"^-- verified: (?P<stamp>.*)$", re.MULTILINE)
VERSION_LINE = re.compile(r'^__version__ = "[^"]*"$')
# Written only by the runs that write the stamps (nox -s test_status, the
# verification record), so a push of nothing else adds no new SQL.
GENERATED = (
    "docs/TEST_STATUS.md",
    "README.md",
    "docs/badges/",
    f"{GOLDEN_DIR}last-verification.txt",
)
# The manifest keys a capture on another level or day changes.
STAMP_KEYS = {"captured", "level"}
RANGE_DIFF_LINE = re.compile(r"^\s*(?:\d+|-):\s+\S+\s+(?P<mark>[=!<>])\s+(?:\d+|-):")

Reader = Callable[[str], bytes | None]


@dataclasses.dataclass(frozen=True)
class Change:
    status: str  # "A", "M" or "D" (renames are a deletion and an addition)
    path: str


@dataclasses.dataclass(frozen=True)
class Finding:
    path: str
    cls: str
    reason: str
    ibmi_run: bool = False  # docs/tests only, but it runs on IBM i

    @property
    def labels(self) -> set[str]:
        if self.cls == FULL:
            return {FULL_TIER_LABEL}
        if self.cls == SQL or self.ibmi_run:
            return {RUN_IBMI_LABEL}
        return set()


@dataclasses.dataclass
class Classification:
    findings: list[Finding]

    @property
    def cls(self) -> str:
        return max((f.cls for f in self.findings), key=RANK.__getitem__, default=DOCS)

    @property
    def labels(self) -> list[str]:
        return sorted(set().union(*(f.labels for f in self.findings)))


@dataclasses.dataclass(frozen=True)
class PushCheck:
    new_run_needed: bool
    reason: str


# --- Per file -------------------------------------------------------------------------


def _text(data: bytes | None) -> str | None:
    return None if data is None else data.decode("utf-8", errors="replace")


def _under(path: str, prefixes: Iterable[str]) -> str | None:
    return next(
        (p for p in prefixes if path == p or (p.endswith("/") and path.startswith(p))), None
    )


def _changed_lines(old: str, new: str) -> tuple[set[str], set[str]]:
    old_lines, new_lines = old.splitlines(), new.splitlines()
    return set(old_lines) - set(new_lines), set(new_lines) - set(old_lines)


def only_version_changed(old: str | None, new: str | None) -> bool:
    """``__init__.py`` with nothing but ``__version__`` changed (a release)."""
    if old is None or new is None:
        return False
    removed, added = _changed_lines(old, new)
    return bool(removed | added) and all(VERSION_LINE.match(line) for line in removed | added)


def golden_stamp(text: str) -> str | None:
    match = VERIFIED_LINE.search(text)
    return match["stamp"].strip() if match else None


def django_versions(noxfile: str | None) -> set[str] | None:
    """The keys of ``DJANGO_PYTHONS`` in noxfile.py, or None if not found."""
    if noxfile is None:
        return None
    for node in ast.parse(noxfile).body:
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "DJANGO_PYTHONS" for t in node.targets)
            and isinstance(node.value, ast.Dict)
        ):
            return {ast.literal_eval(key) for key in node.value.keys}
    return None


def dependencies(pyproject: str | None) -> tuple | None:
    if pyproject is None:
        return None
    project = tomllib.loads(pyproject).get("project", {})
    return tuple(project.get("dependencies", [])), project.get("requires-python")


def without_tool_settings(pyproject: str | None) -> dict | None:
    """pyproject.toml without its ``[tool.*]`` tables (linters, pytest, ...)."""
    if pyproject is None:
        return None
    data = tomllib.loads(pyproject)
    data.pop("tool", None)
    return data


def _manifest(text: str | None) -> dict:
    return tomllib.loads(text) if text else {}


def corpus_entries(data: bytes | None) -> list[dict]:
    if data is None:
        return []
    return [
        json.loads(line) for line in gzip.decompress(data).decode().splitlines() if line.strip()
    ]


def judge(change: Change, old: Reader, new: Reader) -> Finding:
    path, deleted = change.path, change.status == "D"
    before, after = _text(old(path)), _text(new(path))
    if prefix := _under(path, FULL_TIER_PATHS):
        return Finding(path, FULL, FULL_TIER_PATHS[prefix])
    if path == f"{BACKEND}__init__.py" and only_version_changed(before, after):
        return Finding(path, DOCS, "only `__version__`")
    if path.startswith(BACKEND):
        return Finding(path, SQL, "backend code")
    if prefix := _under(path, ENVIRONMENT_PATHS):
        return Finding(path, FULL, ENVIRONMENT_PATHS[prefix])
    if path == "pyproject.toml":
        if dependencies(before) != dependencies(after):
            return Finding(path, FULL, "the dependencies (supported Django versions)")
        if without_tool_settings(before) != without_tool_settings(after):
            return Finding(path, FULL, "the project metadata or build settings")
        return Finding(path, DOCS, "tool settings only")
    if path == "noxfile.py":
        if django_versions(before) != django_versions(after):
            return Finding(path, FULL, "the Django versions of the matrix")
        return Finding(path, DOCS, "the nox sessions, the IBM i ones included", ibmi_run=True)
    if path.startswith(GOLDEN_DIR) and path.endswith(".sql"):
        if deleted:
            return Finding(path, DOCS, "golden removed")
        if golden_stamp(after or "") in (None, UNVERIFIED):
            return Finding(path, SQL, "golden without a verification stamp")
        return Finding(path, DOCS, "golden with a verification stamp")
    if path.startswith(CORPUS_DIR) and path.endswith("/manifest.toml"):
        old_manifest, new_manifest = _manifest(before), _manifest(after)
        if (
            old_manifest
            and new_manifest
            and old_manifest.get("django_commit") != new_manifest.get("django_commit")
        ):
            return Finding(path, FULL, "the pinned Django commit")
        return Finding(path, DOCS, "corpus manifest")
    if path.startswith(CORPUS_DIR) and path.endswith(".jsonl.gz"):
        if deleted:
            return Finding(path, DOCS, "corpus module removed")
        unstamped = sum(
            1 for e in corpus_entries(new(path)) if e.get("verified", UNVERIFIED) == UNVERIFIED
        )
        if unstamped:
            return Finding(path, SQL, f"{unstamped} corpus entries without a verification stamp")
        return Finding(path, DOCS, "corpus entries with verification stamps")
    if path == "docs/status.toml" and _manifest(before).get("modules") != _manifest(after).get(
        "modules"
    ):
        return Finding(path, DOCS, "the supported Django test modules", ibmi_run=True)
    if prefix := _under(path, IBMI_RUN_PATHS):
        if deleted:
            return Finding(path, DOCS, f"{IBMI_RUN_PATHS[prefix]}, removed")
        return Finding(path, DOCS, f"{IBMI_RUN_PATHS[prefix]}: runs on IBM i", ibmi_run=True)
    if prefix := _under(path, DOCS_PATHS):
        return Finding(path, DOCS, DOCS_PATHS[prefix])
    return Finding(path, FULL, "not listed in scripts/classify_pr.py (unknown paths fail closed)")


def classify(changes: Iterable[Change], old: Reader, new: Reader) -> Classification:
    return Classification([judge(c, old, new) for c in sorted(changes, key=lambda c: c.path)])


# --- Pushes ---------------------------------------------------------------------------


def _without_stamps(entries: list[dict]) -> list[dict]:
    return [{k: v for k, v in entry.items() if k != "verified"} for entry in entries]


def _manifest_without_stamps(text: str | None) -> dict:
    data = _manifest(text)
    data["modules"] = {
        name: {k: v for k, v in module.items() if k not in STAMP_KEYS}
        for name, module in data.get("modules", {}).items()
    }
    return data


def stamps_only(changes: Iterable[Change], old: Reader, new: Reader) -> bool:
    """True if every change is a verification stamp or a file generated from them."""
    changes = list(changes)
    if not changes:
        return False
    for change in changes:
        path = change.path
        if _under(path, GENERATED):
            continue
        if change.status != "M":
            return False
        if path.startswith(GOLDEN_DIR) and path.endswith(".sql"):
            before, after = _text(old(path)) or "", _text(new(path)) or ""
            removed, added = _changed_lines(before, after)
            if not all(VERIFIED_LINE.match(line) for line in removed | added):
                return False
            if golden_stamp(after) in (None, UNVERIFIED):
                return False
        elif path.startswith(CORPUS_DIR) and path.endswith(".jsonl.gz"):
            after = corpus_entries(new(path))
            if _without_stamps(corpus_entries(old(path))) != _without_stamps(after):
                return False
            if any(e.get("verified", UNVERIFIED) == UNVERIFIED for e in after):
                return False
        elif path.startswith(CORPUS_DIR) and path.endswith("/manifest.toml"):
            if _manifest_without_stamps(_text(old(path))) != _manifest_without_stamps(
                _text(new(path))
            ):
                return False
        else:
            return False
    return True


def docs_only(changes: Iterable[Change], old: Reader, new: Reader) -> bool:
    """Files that need no label, goldens and corpus entries excluded: a golden whose
    SQL changes keeps its old stamp, so only stamps_only() may accept one."""
    changes = list(changes)
    return not any(c.path.startswith((GOLDEN_DIR, CORPUS_DIR)) for c in changes) and not (
        classify(changes, old, new).labels
    )


def range_diff_identical(output: str) -> bool:
    """``git range-diff`` output in which every commit pair is marked ``=``."""
    marks = [m["mark"] for line in output.splitlines() if (m := RANGE_DIFF_LINE.match(line))]
    return bool(marks) and all(mark == "=" for mark in marks)


# --- Git ------------------------------------------------------------------------------


def git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def is_ancestor(older: str, newer: str) -> bool:
    return subprocess.run(["git", "merge-base", "--is-ancestor", older, newer]).returncode == 0


def reader(ref: str) -> Reader:
    def read(path: str) -> bytes | None:
        result = subprocess.run(["git", "show", f"{ref}:{path}"], capture_output=True)
        return result.stdout if result.returncode == 0 else None

    return read


def changes_between(old_ref: str, new_ref: str) -> list[Change]:
    out = git("diff", "--name-status", "--no-renames", old_ref, new_ref)
    return [
        Change(status[0], path)
        for status, path in (line.split("\t", 1) for line in out.splitlines())
    ]


def classify_refs(old_ref: str, new_ref: str) -> Classification:
    return classify(changes_between(old_ref, new_ref), reader(old_ref), reader(new_ref))


def check_push(before: str, head: str, base: str) -> PushCheck:
    if subprocess.run(["git", "cat-file", "-e", f"{before}^{{commit}}"]).returncode != 0:
        return PushCheck(True, "the previous head is not available")
    if is_ancestor(before, head):
        if stamps_only(changes_between(before, head), reader(before), reader(head)):
            return PushCheck(
                False, "the push only adds verification stamps and files generated from them"
            )
        if docs_only(changes_between(before, head), reader(before), reader(head)):
            return PushCheck(False, "the push changes only docs/tests that do not run on IBM i")
        return PushCheck(True, "the push changes the pull request")
    old_base, new_base = (
        git("merge-base", before, base).strip(),
        git("merge-base", head, base).strip(),
    )
    if not range_diff_identical(
        git("range-diff", "--no-color", f"{old_base}..{before}", f"{new_base}..{head}")
    ):
        return PushCheck(True, "a rewrite whose own changes differ (git range-diff)")
    main = classify_refs(old_base, new_base)
    if main.labels:
        return PushCheck(True, f"a rebase onto main commits that need an IBM i run ({main.cls})")
    return PushCheck(
        False, "a rebase with identical changes (git range-diff) onto docs/tests-only commits"
    )


# --- Output ---------------------------------------------------------------------------


def as_json(result: Classification, push: PushCheck | None) -> str:
    data = {
        "class": result.cls,
        "labels": result.labels,
        "files": [dataclasses.asdict(f) for f in result.findings],
        "push": dataclasses.asdict(push) if push else None,
    }
    return json.dumps(data, indent=2)


def run_verdict(result: Classification, push: PushCheck | None) -> str:
    """Whether the pull request needs an IBM i run now, and why."""
    if not result.labels:
        return "no (docs/tests only, nothing that runs on IBM i)"
    if push and not push.new_run_needed:
        return f"no new run ({push.reason}); the labels stay as they are"
    labels = ", ".join(result.labels)
    return f"yes, {labels}" + (f" ({push.reason})" if push else "")


def as_text(result: Classification, push: PushCheck | None) -> str:
    lines = [f"class: {result.cls}", f"labels: {', '.join(result.labels) or 'none'}"]
    lines.append(f"IBM i run needed: {run_verdict(result, push)}")
    lines += [f"  {f.cls:<16} {f.path}: {f.reason}" for f in result.findings]
    return "\n".join(lines)


def comment_marker(head_sha: str | None) -> str:
    return f"<!-- classify-pr head={head_sha} -->" if head_sha else COMMENT_MARKER


def previous_head(comment: str) -> str | None:
    """The head the last completed classification handled, from its PR comment;
    None for no comment, or one written before the marker named the head."""
    match = _COMMENT_HEAD.match(comment)
    return match["sha"] if match else None


def as_markdown(result: Classification, push: PushCheck | None, head_sha: str | None = None) -> str:
    labels = ", ".join(f"`{label}`" for label in result.labels) or "none"
    lines = [
        comment_marker(head_sha),
        f"### Classification: **{result.cls}**",
        "",
        f"Labels: {labels}",
    ]
    lines.append(f"IBM i run needed: **{run_verdict(result, push)}**.")
    lines += ["", "| File | Class | Why |", "|---|---|---|"]
    lines += [
        f"| `{f.path}` | {f.cls} | {f.reason} |"
        for f in result.findings
        if f.cls != DOCS or f.ibmi_run
    ]
    shown = sum(1 for f in result.findings if f.cls != DOCS or f.ibmi_run)
    if shown < len(result.findings):
        lines.append(f"| {len(result.findings) - shown} more | {DOCS} | no IBM i run |")
    lines += [
        "",
        'Written by `scripts/classify_pr.py` (CLAUDE.md, "Git workflow"); '
        "`bin/check` shows the same.",
    ]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--head", default="HEAD")
    previous = parser.add_mutually_exclusive_group()
    previous.add_argument("--before", help="the previous head, to check the push")
    previous.add_argument(
        "--previous-comment",
        metavar="FILE",
        help="the PR's classification comment (empty: none); its head is the previous head",
    )
    parser.add_argument(
        "--print-before",
        action="store_true",
        help="with --previous-comment: print the previous head (or nothing) and stop",
    )
    parser.add_argument("--format", choices=["text", "markdown", "json"], default="text")
    args = parser.parse_args(argv)
    before = args.before
    if args.previous_comment is not None:
        with open(args.previous_comment, encoding="utf-8") as handle:
            before = previous_head(handle.read())
    if args.print_before:
        print(before or "")
        return 0
    try:
        merge_base = git("merge-base", args.base, args.head).strip()
        result = classify_refs(merge_base, args.head)
        push = check_push(before, args.head, args.base) if before else None
        head_sha = git("rev-parse", args.head).strip()
    except subprocess.CalledProcessError as exc:
        print(f"error: git {' '.join(exc.cmd[1:])}: {(exc.stderr or '').strip()}", file=sys.stderr)
        return 2
    if args.format == "markdown":
        print(as_markdown(result, push, head_sha))
    else:
        print({"text": as_text, "json": as_json}[args.format](result, push))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
