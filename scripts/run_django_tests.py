"""Run modules of Django's own test suite against IBM i (inside the container).

Called by the ``django_tests`` nox session (see scripts/runtests.sh):

    python scripts/run_django_tests.py <django-version> [--clean] <module> [<module> ...]

- One ``runtests.py`` call per module, with ``--parallel=1 --noinput`` and,
  unless ``--clean`` is given, ``--keepdb`` (the test library is reused; the
  marker table records the module, so another module's tables are dropped).
- Safety for shared systems: refuses to run without modules (that would be
  the full suite) and with more than MAX_MODULES modules.
- Output goes to the terminal and to test-results/<version>/<module>.log, with
  the password from DB2I_PASSWORD replaced by ``***`` in both. The log starts
  with a header (module, Django and backend commits, keepdb, start time) and
  ends with the exit code and end time.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = "tests.django_settings.settings_runtests_pub400"
MAX_MODULES = 3
# A test module, optionally followed by .Class or .Class.test (no paths).
LABEL = re.compile(r"^[a-z_][a-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")
VERSION = re.compile(r"^\d+\.\d+$")


class RunRefused(Exception):
    """The requested run is not allowed; nothing was started."""


def validate(version: str, modules: Sequence[str]) -> None:
    if not VERSION.match(version):
        raise RunRefused(f"invalid Django version {version!r} (expected e.g. 6.1)")
    if not modules:
        raise RunRefused(
            "no test modules given: running the full Django test suite against a shared "
            "system is not allowed; name the modules (e.g. basic transactions)"
        )
    if len(modules) > MAX_MODULES:
        raise RunRefused(f"at most {MAX_MODULES} modules per run on a shared system")
    bad = [module for module in modules if not LABEL.match(module)]
    if bad:
        raise RunRefused(f"not a test module label: {', '.join(bad)}")


def make_scrubber(secrets: Sequence[str]) -> Callable[[str], str]:
    secrets = [secret for secret in secrets if secret]

    def scrub(text: str) -> str:
        for secret in secrets:
            text = text.replace(secret, "***")
        return text

    return scrub


def git_commit(path: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "log", "-1", "--format=%h %cs"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def runtests_command(module: str, keepdb: bool, verbosity: int) -> list[str]:
    command = [
        sys.executable,
        "runtests.py",
        f"--settings={SETTINGS}",
        "--parallel=1",
        "--noinput",
        f"--verbosity={verbosity}",
    ]
    if keepdb:
        command.append("--keepdb")
    return [*command, module]


def run_module(version: str, module: str, keepdb: bool, verbosity: int, scrub) -> int:
    django_dir = ROOT / "vendor" / f"django-{version}"
    log_path = ROOT / "test-results" / version / f"{module}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    environment = os.environ | {"PYTHONPATH": str(ROOT), "DB2I_TEST_MODULES": module}
    now = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    header = [
        f"# module: {module}",
        f"# django: {version} ({git_commit(django_dir)})",
        f"# backend: {git_commit(ROOT)}",
        f"# keepdb: {'yes' if keepdb else 'no'}",
        f"# started: {now}",
    ]
    with log_path.open("w") as log:
        for line in header:
            print(line)
            log.write(line + "\n")
        process = subprocess.Popen(
            runtests_command(module, keepdb, verbosity),
            cwd=django_dir / "tests",
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert process.stdout is not None
        for line in process.stdout:
            clean = scrub(line)
            sys.stdout.write(clean)
            log.write(clean)
        code = process.wait()
        end = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
        for line in (f"# exit: {code}", f"# finished: {end}"):
            print(line)
            log.write(line + "\n")
    print(f"log written to {log_path.relative_to(ROOT)}")
    return code


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("version", help="Django feature release, e.g. 6.1")
    parser.add_argument("modules", nargs="*", help="Django test modules (labels)")
    parser.add_argument("--clean", action="store_true", help="do not reuse the test library")
    parser.add_argument("-v", "--verbosity", type=int, default=2)
    args = parser.parse_args(argv)
    try:
        validate(args.version, args.modules)
    except RunRefused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    django_dir = ROOT / "vendor" / f"django-{args.version}"
    if not (django_dir / "tests" / "runtests.py").exists():
        print(
            f"refused: {django_dir.relative_to(ROOT)} is missing; clone it with\n"
            f"  git clone --branch stable/{args.version}.x --depth 1 "
            f"https://github.com/django/django.git vendor/django-{args.version}",
            file=sys.stderr,
        )
        return 2
    scrub = make_scrubber([os.environ.get("DB2I_PASSWORD", "")])
    codes = [
        run_module(args.version, module, not args.clean, args.verbosity, scrub)
        for module in args.modules
    ]
    return max(codes, default=0)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
