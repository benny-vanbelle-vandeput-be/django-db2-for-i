"""The release run for one Django version (CLAUDE.md section 6; DECISIONS 2026-10-19).

    nox -s release_run -- <django-version>

Before every release, for each supported Django version (newest Python):
every supported Django test module, then the pub400 tier. The modules and
their labels are the ``[[modules]]`` of docs/status.toml, the same list the
README's module table is generated from, so there is one list.

Shared-system rules (PUB400): sequential, one connection at a time, each label
in its own runtests.py call (``--clean``, ``--parallel=1``), never the full
Django suite. A plain TCP check of the database host server port comes first,
so an unreachable system fails within seconds and nothing else runs; a label
that fails does not stop the run, the summary lists it and the exit code is
non-zero. Logs: test-results/<version>/ (runtests.py, by
scripts/run_django_tests.py) and test-results/<version>/tiers/pub400.log (the tier).
"""

from __future__ import annotations

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


def main(argv: Sequence[str]) -> int:
    if len(argv) != 1:
        print("usage: nox -s release_run -- <django-version>", file=sys.stderr)
        return 2
    (version,) = argv
    run = labels()
    try:
        run_django_tests.validate(version, run[:1])
    except run_django_tests.RunRefused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    if not (ROOT / "vendor" / f"django-{version}" / "tests" / "runtests.py").exists():
        missing = f"vendor/django-{version} is missing (see scripts/runtests.sh)"
        print(f"refused: {missing}", file=sys.stderr)
        return 2
    problem = reachable()
    if problem:
        print(f"refused: PUB400 is not reachable, nothing was run ({problem})", file=sys.stderr)
        return 2
    failed = []
    for label in run:
        if run_django_tests.main([version, "--clean", label]) != 0:
            failed.append(label)
    if run_tier(version) != 0:
        failed.append("pub400 tier")
    print(f"\nrelease run, Django {version}: {len(run) + 1} runs, ", end="")
    print(f"failed: {', '.join(failed)}" if failed else "all passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
