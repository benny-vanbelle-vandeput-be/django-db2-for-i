"""The offline checks and the pull request text of bin/release-prepare (runs in the container).

    python scripts/release_prepare.py check <version>
    python scripts/release_prepare.py body <version>

``check`` refuses (exit 1, one line per problem) unless:

- ``<version>`` is a release or pre-release version (``0.1.0a5``, ``0.1.0``)
  newer than ``__version__``;
- ``changelog.d/`` has fragments and they pass ``assemble_changelog.py check``;
- every supported Django version (noxfile.py) has a status run
  (test-results/<version>/status-run/state.json) in which every label and the
  own IBM i tier passed;
- the backend is unchanged since each run: the classification of the run's
  commit to HEAD is "docs/tests only" without labels (no IBM i run needed).

``body`` prints the release pull request's description: the status runs and
the corpus counts per Django version.

Never connects to an IBM i; never tags, never touches GitHub releases
(CONTRIBUTING.md, "Releases").
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
import subprocess
import sys
import tomllib
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "django_db2_for_i" / "__init__.py"
_VERSION = re.compile(r'^__version__ = "([^"]+)"$', re.MULTILINE)
# Release and pre-release versions only: 1.2.3, 1.2.3a4, 1.2.3b1, 1.2.3rc2.
_RELEASE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:(a|b|rc)(\d+))?$")
_PRE_RANK = {"a": 0, "b": 1, "rc": 2, None: 3}
TIER = "IBM i tests"


def _script(name: str):
    spec = importlib.util.spec_from_file_location(
        f"scripts_{name}", ROOT / "scripts" / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def version_key(version: str) -> tuple[int, ...] | None:
    match = _RELEASE.match(version)
    if not match:
        return None
    major, minor, patch, pre, number = match.groups()
    return (int(major), int(minor), int(patch), _PRE_RANK[pre], int(number or 0))


def current_version() -> str:
    match = _VERSION.search(VERSION_FILE.read_text(encoding="utf-8"))
    return match.group(1) if match else ""


def supported_django() -> list[str]:
    """The Django versions of DJANGO_PYTHONS in noxfile.py, oldest first."""
    for node in ast.parse((ROOT / "noxfile.py").read_text()).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "DJANGO_PYTHONS" for t in node.targets
        ):
            return list(ast.literal_eval(node.value))
    return []


def release_labels() -> list[str]:
    modules = tomllib.loads((ROOT / "docs" / "status.toml").read_text(encoding="utf-8"))["modules"]
    return [label for module in modules for label in module.get("labels", [module["module"]])]


def run_state(django: str) -> dict:
    path = ROOT / "test-results" / django / "status-run" / "state.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def backend_changes(run_commit: str) -> list[str]:
    """Why the backend counts as changed since ``run_commit`` (empty: unchanged)."""
    try:
        full = git("rev-parse", "--verify", f"{run_commit}^{{commit}}")
        git("merge-base", "--is-ancestor", full, "HEAD")  # exit 1: not an ancestor
    except subprocess.CalledProcessError:
        return [f"{run_commit} is unknown or not an ancestor of HEAD"]
    result = _script("classify_pr").classify_refs(full, "HEAD")
    if not result.labels:
        return []
    return [f"{finding.path}: {finding.reason}" for finding in result.findings if finding.labels]


def check(version: str) -> list[str]:
    problems = []
    current = current_version()
    new, old = version_key(version), version_key(current)
    if new is None:
        problems.append(f"{version} is not a release or pre-release version (e.g. 0.1.0a5)")
    elif old is not None and new <= old:
        problems.append(f"{version} is not newer than __version__ {current}")
    changelog = _script("assemble_changelog")
    fragments = changelog.fragment_paths()
    if not fragments:
        problems.append("changelog.d/ has no fragments: nothing to release")
    problems += [f"changelog.d/: {problem}" for problem in changelog.check(fragments)]
    labels = [*release_labels(), TIER]
    for django in supported_django():
        state = run_state(django)
        if not state:
            problems.append(f"Django {django}: no status run (bin/status-run --django {django})")
            continue
        results = state.get("results", {})
        missing = [name for name in labels if name not in results]
        failed = [name for name in labels if results.get(name) == "failed"]
        if failed or missing:
            problems.append(
                f"Django {django}: the status run is not complete and passed "
                f"(failed: {', '.join(failed) or 'none'}; not run: {len(missing)})"
            )
            continue
        run_commit = state.get("backend", "").split()[0] if state.get("backend") else ""
        changes = backend_changes(run_commit) if run_commit else ["no backend commit recorded"]
        problems += [
            f"Django {django}: changed since its status run ({run_commit}): {change}"
            for change in changes
        ]
    return problems


def body(version: str) -> str:
    lines = [
        f"Release {version}, prepared by `bin/release-prepare`.",
        "",
        "## Status runs (IBM i, PUB400)",
        "",
        "| Django | Backend commit | Runs | Result |",
        "|---|---|---|---|",
    ]
    labels = [*release_labels(), TIER]
    for django in supported_django():
        state = run_state(django)
        passed = sum(state.get("results", {}).get(name) == "passed" for name in labels)
        lines.append(
            f"| {django} | `{state.get('backend', '?')}` | {passed} of {len(labels)} | "
            f"{'all passed' if passed == len(labels) else 'NOT complete'} |"
        )
    lines += ["", "## Offline query corpus", "", "| Django | Module | Unique entries | Level |"]
    lines.append("|---|---|---|---|")
    for manifest in sorted((ROOT / "tests" / "offline" / "replay").glob("*/*/manifest.toml")):
        data = tomllib.loads(manifest.read_text(encoding="utf-8"))
        for module, counts in sorted(data.get("modules", {}).items()):
            lines.append(
                f"| {data.get('django', '?')} | {module} | {counts.get('unique', '?')} | "
                f"{counts.get('level', '?')} |"
            )
    lines += [
        "",
        "After merging, the maintainer signs and pushes the tag and creates the GitHub "
        'release by hand (CONTRIBUTING.md, "Releases"). `bin/release-prepare` never '
        "tags and never creates releases.",
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2 or args[0] not in ("check", "body"):
        print("usage: release_prepare.py check|body <version>", file=sys.stderr)
        return 2
    command, version = args
    if command == "body":
        print(body(version))
        return 0
    problems = check(version)
    for problem in problems:
        print(f"refused: {problem}")
    if not problems:
        print(f"release {version}: the offline preconditions hold")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
