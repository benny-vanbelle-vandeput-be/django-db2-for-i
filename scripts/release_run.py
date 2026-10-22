"""The release run for one Django version (CLAUDE.md section 6; DECISIONS 2026-10-19).

    nox -s release_run -- <django-version> [--restart] [--limit N]

Before every release, for each supported Django version (newest Python):
every supported Django test module, then the pub400 tier. The modules and
their labels are the ``[[modules]]`` of docs/status.toml, the same list the
README's module table is generated from, so there is one list.

Every label runs with ``--capture``, so each release run also refreshes the
offline query corpus (docs/OFFLINE_CORPUS.md; DECISIONS 2026-10-19, "Refresh:
... release runs ... refresh it"): the raw captures land in
test-results/<version>/corpus/, and scripts/build_corpus.py turns them into
the corpus afterwards.

Shared-system rules (PUB400): sequential, one connection at a time, each label
in its own runtests.py call (``--clean``, ``--parallel=1``), never the full
Django suite. A plain TCP check of the database host server port comes first,
so an unreachable system fails within seconds and nothing else runs; a label
that fails does not stop the run, the summary lists it and the exit code is
non-zero. Logs: test-results/<version>/ (runtests.py, by
scripts/run_django_tests.py) and test-results/<version>/tiers/pub400.log (the tier).

Resumable (bin/release-run): the result of every label and of the tier is
written to test-results/<version>/release-run/state.json as soon as it is
known, with the backend commit and the Django commit. A later run on the same
two commits skips what passed and runs what failed or is missing, so the run
can be spread over several nights; another commit, or ``--restart``, starts
over and first deletes the raw captures of earlier runs of this version
(bin/verify writes single-test captures there too). ``--limit N`` stops after
N runs (a short run; the rest stays for the next start).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tomllib
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS_DATA = ROOT / "docs" / "status.toml"
for path in (ROOT / "scripts", ROOT / "probes"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import run_django_tests  # noqa: E402
from _common import DATABASE_PORT, ProbeError, Settings, tcp_check  # noqa: E402


def labels(status: Path = STATUS_DATA) -> list[str]:
    """The release run's Django test labels, in docs/status.toml order."""
    modules = tomllib.loads(status.read_text(encoding="utf-8"))["modules"]
    return [label for module in modules for label in module.get("labels", [module["module"]])]


def reachable() -> str | None:
    """None when the database host server port answers, else why not (no secrets)."""
    try:
        settings = Settings.from_env(need_credentials=False)
    except ProbeError as exc:
        return str(exc)
    port = DATABASE_PORT[settings.ssl]
    result = tcp_check(settings.host, port)
    return None if result["open"] else f"port {port} not reachable: {result['error']}"


def run_tier(version: str) -> int:
    """The pub400 tier, fully clean, its output also in test-results/<version>/tiers/.

    Not next to the module logs: scripts/update_test_status.py reads every
    test-results/<version>/*.log as a Django test module's log.
    """
    log = ROOT / "test-results" / version / "tiers" / "pub400.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    scrub = run_django_tests.make_scrubber([os.environ.get("DB2I_PASSWORD", "")])
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-m",
        "pub400",
        "--ds=tests.django_settings.settings_pub400",
        "--tb=short",
        "--create-db",
        "-p",
        "no:cacheprovider",
        f"--results-summary={ROOT / 'test-results' / version / 'sets' / 'pub400.json'}",
    ]
    with log.open("w", encoding="utf-8") as out:
        process = subprocess.Popen(
            command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        for line in process.stdout:
            line = scrub(line)
            sys.stdout.write(line)
            out.write(line)
        return process.wait()


TIER = "pub400 tier"


def state_path(version: str) -> Path:
    return ROOT / "test-results" / version / "release-run" / "state.json"


def read_state(version: str) -> dict:
    path = state_path(version)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def write_state(version: str, state: dict) -> None:
    path = state_path(version)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)  # never a half-written state


def start_state(version: str, backend: str, django: str, restart: bool) -> tuple[dict, str]:
    """The state to continue from, and why: resumed, or started over."""
    state = read_state(version)
    same = state.get("backend") == backend and state.get("django") == django
    if state and same and not restart:
        return state, "resumed"
    why = "--restart" if restart and state else ("new commits" if state else "first run")
    for capture in (ROOT / "test-results" / version / "corpus").glob("*.jsonl"):
        capture.unlink()
    state = {"backend": backend, "django": django, "results": {}}
    write_state(version, state)
    return state, f"started over ({why})"


def complete(state: dict, run: Sequence[str]) -> bool:
    """Every label and the tier passed."""
    return all(state.get("results", {}).get(name) == "passed" for name in [*run, TIER])


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="nox -s release_run --", add_help=False)
    parser.add_argument("version")
    parser.add_argument("--restart", action="store_true")
    parser.add_argument("--limit", type=int)
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        print(
            "usage: nox -s release_run -- <django-version> [--restart] [--limit N]",
            file=sys.stderr,
        )
        return 2
    version = args.version
    run = labels()
    try:
        run_django_tests.validate(version, run[:1])
    except run_django_tests.RunRefused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    django_dir = ROOT / "vendor" / f"django-{version}"
    if not (django_dir / "tests" / "runtests.py").exists():
        missing = f"vendor/django-{version} is missing (see scripts/runtests.sh)"
        print(f"refused: {missing}", file=sys.stderr)
        return 2
    problem = reachable()
    if problem:
        print(f"refused: PUB400 is not reachable, nothing was run ({problem})", file=sys.stderr)
        return 2
    backend = run_django_tests.backend_commit()
    state, how = start_state(
        version, backend, run_django_tests.git_full_commit(django_dir), args.restart
    )
    results = state["results"]
    passed = [name for name in [*run, TIER] if results.get(name) == "passed"]
    print(f"release run, Django {version}, backend {backend}: {how}")
    if passed:
        print(f"skipped, passed before on the same commits: {', '.join(passed)}")
    budget = args.limit
    for name in [*run, TIER]:
        if results.get(name) == "passed":
            continue
        if budget is not None and budget <= 0:
            print(f"stopped by --limit {args.limit}; the next start continues here ({name})")
            break
        if name == TIER:
            status = run_tier(version)
        else:
            status = run_django_tests.main([version, "--clean", "--capture", name])
        results[name] = "passed" if status == 0 else "failed"
        write_state(version, state)
        if budget is not None:
            budget -= 1
    failed = [name for name in [*run, TIER] if results.get(name) == "failed"]
    missing = [name for name in [*run, TIER] if name not in results]
    print(f"\nrelease run, Django {version}: {len(run) + 1} runs, ", end="")
    if complete(state, run):
        print("all passed")
        return 0
    print(
        f"failed: {', '.join(failed) or 'none'}; not run yet: {len(missing)}"
        if missing
        else f"failed: {', '.join(failed)}"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
