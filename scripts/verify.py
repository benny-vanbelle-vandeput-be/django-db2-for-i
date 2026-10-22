"""The offline side of bin/verify and bin/ibmi-test --affected (runs in the container).

    python scripts/verify.py triage <django>
    python scripts/verify.py select <django> [--base origin/main] [--max-labels 60] [--max-runs 20]
    python scripts/verify.py finish <django> [--updated] [--no-stamp]

``triage`` reads the JUnit reports of the offline run and the corpus replay
(test-results/verify/<django>/{offline,corpus}.xml) and sorts the failures:
SQL that changed (a golden that differs or is missing, a corpus module that
writes different SQL now) or anything else. Exit 0: nothing failed; 4: only
SQL changed (bin/verify then writes the new SQL with --update-goldens /
--update-corpus); 1: another failure (bin/verify stops, nothing touches
PUB400).

``select`` decides what runs on IBM i and writes it to
test-results/verify/<django>/runs.txt, one run per line (tab-separated):

- ``goldens <file>``: every unverified golden of the series and the create
  goldens it depends on (names in <file>, for --goldens-from);
- ``own full`` or ``own <node id> ...``: own IBM i tests that are new or
  changed against the merge base with ``--base`` (working tree included).
  A change to shared own-test code (fixtures, helpers, the test models, the
  IBM i settings) or to what needs the full tier cannot be mapped to single
  tests: then the full own IBM i tier runs;
- ``django <label> ...``: at most three Django test labels per line: one test
  id per unverified corpus entry, and the test ids that left the skip or
  expected-failure lists. Many ids of one class (module, app) are collapsed
  into one label; more than ``--max-labels`` labels or ``--max-runs`` lines
  are refused (exit 5), to protect the shared system.

``finish`` stamps the corpus entries whose exact statement (compiler, SQL,
params, settings) a passing test sent in this run's captures, then writes
test-results/verify/<django>/report.txt from the run results bin/verify
recorded (results.txt). Exit 0: everything selected passed and is verified;
3: something failed or is still unverified.

Standard library and the project's tests/ helpers only; never connects to an IBM i.
"""

from __future__ import annotations

import argparse
import ast
import datetime as dt
import importlib.util
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.corpus import store  # noqa: E402
from tests.golden import GOLDEN_ROOT, UNVERIFIED, VERIFIED_PATTERN, new_stamp, read  # noqa: E402


def _script(name: str):
    spec = importlib.util.spec_from_file_location(
        f"scripts_{name}", ROOT / "scripts" / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


classify_pr = _script("classify_pr")
build_corpus = _script("build_corpus")

EXIT_FAILED, EXIT_UNVERIFIED, EXIT_SQL_CHANGED, EXIT_TOO_MANY = 1, 3, 4, 5
MAX_LABELS, MAX_RUNS = 60, 20
LABELS_PER_RUN = 3  # scripts/runtests.sh refuses more
COLLAPSE_ABOVE = 3  # more ids (labels) than this in one class (module, app): one label

OWN_TESTS = "tests/pub400/"
# Own-test code shared by many tests: a change runs the full own IBM i tier.
SHARED_OWN_TEST_PATHS = (
    "tests/conftest.py",
    "tests/testapp/",
    "tests/golden.py",
    "tests/redaction.py",
    "tests/results_summary.py",
    "tests/table_registry.py",
    "tests/boolean_condition_scenarios.py",
    "tests/tuple_lookup_scenarios.py",
    "tests/django_settings/settings_pub400.py",
)
# Where the skip and expected-failure lists live.
SKIP_LIST_FILES = ("django_db2_for_i/features.py", "django_db2_for_i/compat.py")
TEST_ID = re.compile(r"^[a-z_][a-z0-9_]*(?:\.[A-Za-z_]\w*){2,}$")


def verify_dir(django: str) -> Path:
    return ROOT / "test-results" / "verify" / django


# --- triage ------------------------------------------------------------------------------


@dataclass
class Failure:
    test: str  # "<classname>::<name>"
    message: str


def junit_failures(path: Path) -> list[Failure]:
    """Failed and errored test cases of a JUnit report (a missing report is a failure)."""
    if not path.exists():
        return [Failure(path.name, "no report: the run did not finish")]
    failures = []
    for case in ET.parse(path).getroot().iter("testcase"):
        for kind in ("failure", "error"):
            element = case.find(kind)
            if element is not None:
                test = f"{case.get('classname', '')}::{case.get('name', '')}"
                failures.append(Failure(test, element.get("message") or kind))
    return failures


def is_sql_change(failure: Failure) -> bool:
    """A failure that only says "the SQL is not the stored SQL" (goldens, corpus)."""
    test = failure.test
    if test.startswith("tests.offline.test_goldens::test_golden["):
        return True
    if test == "tests.offline.test_goldens::test_every_case_has_a_golden":
        return "cases without a golden" in failure.message
    if test.startswith("tests.corpus.test_replay::test_corpus_module_replays["):
        return "write different SQL now" in failure.message
    return False


def triage(django: str) -> int:
    directory = verify_dir(django)
    failures = junit_failures(directory / "offline.xml")
    if any(store.CORPUS_ROOT.joinpath(django).glob("*/manifest.toml")):
        failures += junit_failures(directory / "corpus.xml")
    other = [f for f in failures if not is_sql_change(f)]
    if other:
        print(
            f"verify: {len(other)} offline failures that are not changed SQL;"
            " nothing runs on IBM i:"
        )
        for failure in other:
            print(f"  {failure.test}: {failure.message.splitlines()[0][:200]}")
        return EXIT_FAILED
    if failures:
        print(f"verify: {len(failures)} offline failures, all changed SQL:")
        for failure in failures:
            print(f"  {failure.test}")
        return EXIT_SQL_CHANGED
    print("verify: the offline tests and the replay pass")
    return 0


# --- select: goldens and corpus ----------------------------------------------------------


def unverified_goldens(django: str, unverifiable: Iterable[str] = ()) -> list[str]:
    """Unverified goldens of the series (allow-listed ones excepted) and their create goldens."""
    goldens = {}
    for path in sorted((GOLDEN_ROOT / django).rglob("*.sql")):
        golden = read(path)
        goldens[golden.name] = golden
    skip = set(unverifiable)
    wanted = {name for name, g in goldens.items() if g.verified == UNVERIFIED and name not in skip}
    pending = list(wanted)
    while pending:
        golden = goldens.get(pending.pop())
        for dependency in golden.depends if golden else ():
            if dependency not in wanted:
                wanted.add(dependency)
                pending.append(dependency)
    return sorted(wanted)


def is_unverified(django: str, name: str) -> bool:
    return any(
        read(path).verified == UNVERIFIED for path in (GOLDEN_ROOT / django).glob(f"*/{name}.sql")
    )


def corpus_test_ids(django: str) -> list[str]:
    """One test id per unverified corpus entry, preferring ids that already cover another."""
    directory = store.corpus_dir(django)
    pending = [
        entry
        for module in store.modules(directory)
        for entry in store.read_module(directory, module)
        if entry.verified == UNVERIFIED and entry.tests
    ]
    chosen: set[str] = set()
    while pending:
        counts: dict[str, int] = defaultdict(int)
        for entry in pending:
            for test in entry.tests:
                counts[test] += 1
        best = max(sorted(counts), key=lambda test: counts[test])
        chosen.add(best)
        pending = [entry for entry in pending if best not in entry.tests]
    return sorted(chosen)


# --- select: git -------------------------------------------------------------------------


def git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True
    ).stdout


def merge_base(base: str) -> str:
    return git("merge-base", base, "HEAD").strip()


def changed_paths(base_commit: str) -> list[str]:
    """Files that differ between the merge base and the working tree, untracked ones included."""
    tracked = git("diff", "--name-only", base_commit).splitlines()
    untracked = git("ls-files", "--others", "--exclude-standard").splitlines()
    return sorted(set(tracked) | set(untracked))


def text_at(base_commit: str, path: str) -> str:
    try:
        return git("show", f"{base_commit}:{path}")
    except subprocess.CalledProcessError:
        return ""  # new file


def current_text(path: str) -> str:
    file = ROOT / path
    return file.read_text(encoding="utf-8") if file.exists() else ""


# --- select: own IBM i tests -------------------------------------------------------------


def needs_full_own_tier(path: str) -> str | None:
    """Why a changed path cannot be mapped to single own IBM i tests, or None."""
    if path.startswith(OWN_TESTS) and not Path(path).name.startswith("test_"):
        return "shared own-test code"
    for shared in SHARED_OWN_TEST_PATHS:
        if path == shared or (shared.endswith("/") and path.startswith(shared)):
            return "shared own-test code"
    for prefix, why in {**classify_pr.FULL_TIER_PATHS, **classify_pr.ENVIRONMENT_PATHS}.items():
        if path == prefix or (prefix.endswith("/") and path.startswith(prefix)):
            return why
    return None


def _units(source: str) -> tuple[str, dict[str, str], dict[str, str]]:
    """(module rest, {class: class rest}, {node id suffix: test dump}) of a test module."""
    tree = ast.parse(source) if source else ast.Module(body=[], type_ignores=[])
    module_rest, classes, tests = [], {}, {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith(
            "test"
        ):
            tests[node.name] = ast.dump(node)
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            rest = []
            for item in node.body:
                if isinstance(
                    item, ast.FunctionDef | ast.AsyncFunctionDef
                ) and item.name.startswith("test"):
                    tests[f"{node.name}::{item.name}"] = ast.dump(item)
                else:
                    rest.append(ast.dump(item))
            classes[node.name] = "\n".join(
                [*rest, *(ast.dump(d) for d in node.decorator_list), *map(ast.dump, node.bases)]
            )
        else:
            module_rest.append(ast.dump(node))
    return "\n".join(module_rest), classes, tests


def changed_tests(path: str, before: str, after: str) -> list[str]:
    """Node ids of the tests of one test module that are new or changed (none removed)."""
    if not after:
        return []
    old_rest, old_classes, old_tests = _units(before)
    new_rest, new_classes, new_tests = _units(after)
    if before and old_rest != new_rest:
        return [path]  # module-level code (fixtures, helpers, marks): the whole module
    ids = []
    changed_classes = {
        name
        for name, rest in new_classes.items()
        if name in old_classes and old_classes[name] != rest
    }
    ids += [f"{path}::{name}" for name in sorted(changed_classes)]
    for suffix, dump in new_tests.items():
        if suffix.split("::")[0] in changed_classes:
            continue
        if old_tests.get(suffix) != dump:
            ids.append(f"{path}::{suffix}")
    return ids


@dataclass
class OwnSelection:
    full: str | None = None  # the reason the full own tier runs
    tests: list[str] = field(default_factory=list)


def own_selection(paths: Sequence[str], before, after) -> OwnSelection:
    for path in paths:
        why = needs_full_own_tier(path)
        if why:
            return OwnSelection(full=f"{path}: {why}")
    tests = []
    for path in paths:
        if path.startswith(OWN_TESTS) and Path(path).name.startswith("test_"):
            tests += changed_tests(path, before(path), after(path))
    return OwnSelection(tests=tests)


# --- select: Django test labels ----------------------------------------------------------


def listed_test_ids(source: str) -> set[str]:
    """The Django test ids written as string literals in a module."""
    if not source:
        return set()
    return {
        node.value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and TEST_ID.match(node.value)
        and any(part.startswith("test") for part in node.value.split(".")[1:])
    }


def unlisted_test_ids(before, after, django_tests: Path | None) -> list[str]:
    """Test ids that left the skip / expected-failure lists (they should pass now),
    restricted to tests that exist in this Django version's checkout when it is there."""
    # Across the files: an id that moves from one list file to another stays listed.
    removed = set().union(*(listed_test_ids(before(path)) for path in SKIP_LIST_FILES))
    removed -= set().union(*(listed_test_ids(after(path)) for path in SKIP_LIST_FILES))
    if django_tests is not None and django_tests.is_dir():
        removed = {test for test in removed if _exists(django_tests, test)}
    return sorted(removed)


def _exists(django_tests: Path, test: str) -> bool:
    parts = test.split(".")
    return any(
        (django_tests.joinpath(*parts[:n]).with_suffix(".py")).exists()
        or (django_tests.joinpath(*parts[:n]) / "__init__.py").exists()
        for n in range(2, len(parts))
    )


def collapse(ids: Iterable[str], above: int = COLLAPSE_ABOVE) -> list[str]:
    """Test ids as few labels: when more than ``above`` labels lie under one
    parent (a class, a test module, an app), they become that parent; the
    deepest such parent first, repeatedly."""
    labels = set(ids)
    while True:
        under: dict[str, set[str]] = defaultdict(set)
        for label in labels:
            parts = label.split(".")
            for depth in range(1, len(parts)):
                under[".".join(parts[:depth])].add(label)
        crowded = [parent for parent, kids in under.items() if len(kids) > above]
        if not crowded:
            break
        parent = max(sorted(crowded), key=lambda name: name.count("."))
        labels = (labels - under[parent]) | {parent}
    # A label inside another label runs with it.
    return sorted(
        label for label in labels if not any(label.startswith(other + ".") for other in labels)
    )


def django_runs(labels: Sequence[str]) -> list[list[str]]:
    return [list(labels[i : i + LABELS_PER_RUN]) for i in range(0, len(labels), LABELS_PER_RUN)]


# --- select ------------------------------------------------------------------------------


def unverifiable_names(django: str) -> list[str]:
    from tests.verification_gate import reasons

    return list(reasons(django))


def select(django: str, base: str, max_labels: int = MAX_LABELS, max_runs: int = MAX_RUNS) -> int:
    directory = verify_dir(django)
    directory.mkdir(parents=True, exist_ok=True)
    base_commit = merge_base(base)
    paths = changed_paths(base_commit)

    goldens = unverified_goldens(django, unverifiable_names(django))
    unverified = [name for name in goldens if is_unverified(django, name)]
    own = own_selection(paths, lambda p: text_at(base_commit, p), current_text)
    corpus_ids = corpus_test_ids(django)
    unlisted = unlisted_test_ids(
        lambda p: text_at(base_commit, p),
        current_text,
        ROOT / "vendor" / f"django-{django}" / "tests",
    )
    labels = collapse([*corpus_ids, *unlisted])
    runs = django_runs(labels)

    lines = []
    if goldens:
        names = directory / "goldens.txt"
        names.write_text("".join(f"{name}\n" for name in goldens))
        lines.append(["goldens", str(names.relative_to(ROOT))])
    if own.full:
        lines.append(["own", "full"])
    elif own.tests:
        lines.append(["own", *own.tests])
    lines += [["django", *run] for run in runs]
    (directory / "runs.txt").write_text("".join("\t".join(line) + "\n" for line in lines))
    (directory / "selection.json").write_text(
        json.dumps(
            {
                "django": django,
                "base": base,
                "merge_base": base_commit,
                "goldens": goldens,
                "unverified_goldens": unverified,
                "own_full": own.full,
                "own_tests": own.tests,
                "corpus_test_ids": corpus_ids,
                "unlisted_test_ids": unlisted,
                "django_labels": labels,
            },
            indent=2,
        )
        + "\n"
    )

    print(f"verify: against {base} ({base_commit[:10]}), Django {django}")
    print(f"  goldens: {len(goldens)} (unverified, with their create goldens)")
    if own.full:
        print(f"  own IBM i tests: the full tier ({own.full})")
    else:
        print(f"  own IBM i tests: {len(own.tests)} new or changed")
    print(
        f"  Django test labels: {len(labels)} in {len(runs)} runs "
        f"({len(corpus_ids)} for unverified corpus entries, {len(unlisted)} no longer skipped)"
    )
    if len(labels) > max_labels or len(runs) > max_runs:
        print(
            f"verify: refused: {len(labels)} Django test labels in {len(runs)} runs, more than "
            f"{max_labels} labels or {max_runs} runs on a shared system; run the modules with "
            "bin/ibmi-test django, or capture them in a release run"
        )
        return EXIT_TOO_MANY
    if not lines:
        print("verify: nothing to run on IBM i")
    return 0


# --- finish ------------------------------------------------------------------------------


def read_results(django: str) -> list[tuple[str, str, int]]:
    """(kind, arguments, exit status) per run, as bin/verify recorded them."""
    path = verify_dir(django) / "results.txt"
    if not path.exists():
        return []
    results = []
    for line in path.read_text().splitlines():
        kind, args, status = line.split("\t")
        results.append((kind, args, int(status)))
    return results


def stamp_corpus(django: str, captures: Sequence[Path]) -> tuple[int, int]:
    """Stamp unverified corpus entries a passing test sent in ``captures``.

    Returns (stamped, still unverified). Only exact statements count: same
    compiler, SQL, params and settings (the corpus key).
    """
    seen: dict[str, tuple[str, str]] = {}
    for path in captures:
        header, records = build_corpus.read_capture(path)
        for record in records:
            entry = store.Entry(
                compiler=record["compiler"],
                sql=record["sql"],
                query=record["query"],
                tests=list(record["tests"]),
                settings=dict(record.get("settings", {})),
            )
            seen[entry.key] = (header["level"], header["date"])
    directory = store.corpus_dir(django)
    stamped = remaining = 0
    for module in store.modules(directory):
        entries = store.read_module(directory, module)
        changed = False
        for entry in entries:
            if entry.verified != UNVERIFIED:
                continue
            if entry.key in seen:
                level, date = seen[entry.key]
                entry.verified = new_stamp(UNVERIFIED, level, date)
                stamped += 1
                changed = True
            else:
                remaining += 1
        if changed:
            store.write_module(directory, module, entries)
    return stamped, remaining


def run_captures(django: str, results: Sequence[tuple[str, str, int]], since: float) -> list[Path]:
    """This run's capture files (written after ``since``) of the Django labels that ran."""
    paths = []
    for kind, args, _status in results:
        if kind != "django":
            continue
        for label in args.split():
            path = ROOT / "test-results" / django / "corpus" / f"{label}.jsonl"
            if path.exists() and path.stat().st_mtime >= since:
                paths.append(path)
    return paths


def golden_status(django: str, names: Iterable[str]) -> dict[str, str]:
    status = {}
    for name in names:
        for path in (GOLDEN_ROOT / django).glob(f"*/{name}.sql"):
            verified = read(path).verified
            status[name] = "verified" if VERIFIED_PATTERN.match(verified) else verified
    return status


def finish(django: str, updated: bool, stamp: bool = True) -> int:
    directory = verify_dir(django)
    selection = json.loads((directory / "selection.json").read_text())
    results = read_results(django)
    since = (directory / "selection.json").stat().st_mtime
    stamped = remaining = 0
    if stamp:
        stamped, remaining = stamp_corpus(django, run_captures(django, results, since))
    goldens = golden_status(django, selection["goldens"])
    unverified_goldens_left = sorted(n for n, s in goldens.items() if s != "verified")
    failed = [(kind, args) for kind, args, status in results if status != 0]
    planned = (directory / "runs.txt").read_text().splitlines()
    not_run = len(planned) - len(results)

    lines = [
        f"bin/verify report, Django {django}, {dt.datetime.now(dt.UTC):%Y-%m-%d %H:%M} UTC",
        "",
    ]
    problem = bool(failed or not_run or (stamp and (unverified_goldens_left or remaining)))
    if problem and updated:
        lines += [
            "WARNING: new SQL was written to the goldens / corpus (--update-goldens,",
            "--update-corpus) but it is NOT verified on IBM i. Review it before committing:",
            "git diff tests/offline/golden tests/offline/corpus",
            "",
        ]
    lines.append(f"IBM i runs: {len(results)} of {len(planned)}, {len(failed)} failed")
    for kind, args in failed:
        lines.append(f"  FAILED: {kind} {args}")
    if not_run:
        lines.append(f"  not run: {not_run} (stopped after a failure or interrupted)")
    if stamp:
        lines.append(
            f"goldens: {len(goldens) - len(unverified_goldens_left)} of {len(goldens)} verified"
        )
        lines += [f"  unverified: {name}" for name in unverified_goldens_left]
        lines.append(f"corpus entries: {stamped} stamped, {remaining} still unverified")
        lines.append("")
        # The goldens that were unverified when selected and are verified now got a stamp.
        unverified_before = selection.get("unverified_goldens", selection["goldens"])
        written = stamped or any(goldens.get(name) == "verified" for name in unverified_before)
        if written:
            lines.append(
                "The new stamps are in the working tree; review them (git diff) and commit"
                " them yourself: bin/verify never commits."
            )
        else:
            lines.append("No stamps were written; nothing was committed.")
    report = "\n".join(lines) + "\n"
    (directory / "report.txt").write_text(report)
    print(report, end="")
    return EXIT_UNVERIFIED if problem else 0


# --- main --------------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("triage").add_argument("django")
    selecting = commands.add_parser("select")
    selecting.add_argument("django")
    selecting.add_argument("--base", default="origin/main")
    selecting.add_argument("--max-labels", type=int, default=MAX_LABELS)
    selecting.add_argument("--max-runs", type=int, default=MAX_RUNS)
    finishing = commands.add_parser("finish")
    finishing.add_argument("django")
    finishing.add_argument("--updated", action="store_true", help="the offline step wrote new SQL")
    finishing.add_argument("--no-stamp", action="store_true", help="report only (--affected)")
    args = parser.parse_args(argv)
    if args.command == "triage":
        return triage(args.django)
    if args.command == "select":
        return select(args.django, args.base, args.max_labels, args.max_runs)
    return finish(args.django, args.updated, stamp=not args.no_stamp)


if __name__ == "__main__":
    sys.exit(main())
