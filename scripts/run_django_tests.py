"""Run modules of Django's own test suite against IBM i (inside the container).

Called by the ``django_tests`` nox session (see scripts/runtests.sh):

    python scripts/run_django_tests.py <django-version> [--clean] <label> [<label> ...]

- A label is a test module (``basic``) or a dotted label inside one
  (``basic.tests.ModelTest.test_x``).
- One ``runtests.py`` call per label, with ``--parallel=1 --noinput`` and,
  unless ``--clean`` is given, ``--keepdb`` (the test library is reused; the
  marker table records the top-level module, so labels of the same module
  reuse its tables and another module's tables are dropped).
- Safety for shared systems: refuses to run without labels (that would be
  the full suite) and with more than MAX_LABELS labels; each label counts.
- Output goes to the terminal and to test-results/<version>/<module>.log for
  a whole module, or test-results/<version>/labels/<label>.log for a dotted
  label (not counted in TEST_STATUS.md), with the password from DB2I_PASSWORD
  replaced by ``***`` in both. The log starts with a header (label, Django
  and backend commits, the Python version that runs ``runtests.py``, keepdb,
  start time) and ends with the exit code and end time.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import platform
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = "tests.django_settings.settings_runtests_pub400"
MAX_LABELS = 3
# A test module, optionally followed by .Class or .Class.test (no paths).
LABEL = re.compile(r"^[a-z_][a-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")
VERSION = re.compile(r"^\d+\.\d+$")


class RunRefused(Exception):
    """The requested run is not allowed; nothing was started."""


def validate(version: str, labels: Sequence[str]) -> None:
    if not VERSION.match(version):
        raise RunRefused(f"invalid Django version {version!r} (expected e.g. 6.1)")
    if not labels:
        raise RunRefused(
            "no test modules given: running the full Django test suite against a shared "
            "system is not allowed; name the modules (e.g. basic transactions)"
        )
    if len(labels) > MAX_LABELS:
        raise RunRefused(f"at most {MAX_LABELS} labels per run on a shared system")
    bad = [label for label in labels if not LABEL.match(label)]
    if bad:
        raise RunRefused(f"not a test module label: {', '.join(bad)}")


def make_scrubber(secrets: Sequence[str]) -> Callable[[str], str]:
    secrets = [secret for secret in secrets if secret]

    def scrub(text: str) -> str:
        for secret in secrets:
            text = text.replace(secret, "***")
        return text

    return scrub


def top_module(label: str) -> str:
    """``basic.tests.ModelTest.test_x`` -> ``basic``."""
    return label.split(".", 1)[0]


def log_path(version: str, label: str) -> Path:
    """Whole modules feed TEST_STATUS.md; single labels go to labels/."""
    directory = ROOT / "test-results" / version
    if label != top_module(label):
        directory = directory / "labels"
    return directory / f"{label}.log"


def git_commit(path: Path) -> str:
    try:
        result = subprocess.run(
            # safe.directory: in the container the checkout belongs to the host user,
            # and git refuses it ("dubious ownership"); this read is all we do.
            [
                "git",
                "-c",
                f"safe.directory={path}",
                "-C",
                str(path),
                "log",
                "-1",
                "--format=%h %cs",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def runtests_command(label: str, keepdb: bool, verbosity: int) -> list[str]:
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
    return [*command, label]


def run_label(version: str, label: str, keepdb: bool, verbosity: int, scrub) -> int:
    django_dir = ROOT / "vendor" / f"django-{version}"
    path = log_path(version, label)
    path.parent.mkdir(parents=True, exist_ok=True)
    environment = os.environ | {"PYTHONPATH": str(ROOT), "DB2I_TEST_MODULES": top_module(label)}
    now = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    header = [
        f"# module: {label}",
        f"# django: {version} ({git_commit(django_dir)})",
        f"# backend: {git_commit(ROOT)}",
        # runtests.py is started with sys.executable (runtests_command), so this
        # interpreter's version is the one the tests ran on.
        f"# python: {platform.python_version()}",
        f"# keepdb: {'yes' if keepdb else 'no'}",
        f"# started: {now}",
    ]
    with path.open("w") as log:
        for line in header:
            print(line)
            log.write(line + "\n")
        process = subprocess.Popen(
            runtests_command(label, keepdb, verbosity),
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
    print(f"log written to {path.relative_to(ROOT)}")
    return code


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("version", help="Django feature release, e.g. 6.1")
    parser.add_argument("labels", nargs="*", help="Django test modules or dotted labels")
    parser.add_argument("--clean", action="store_true", help="do not reuse the test library")
    parser.add_argument("-v", "--verbosity", type=int, default=2)
    args = parser.parse_args(argv)
    try:
        validate(args.version, args.labels)
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
        run_label(args.version, label, not args.clean, args.verbosity, scrub)
        for label in args.labels
    ]
    return max(codes, default=0)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
