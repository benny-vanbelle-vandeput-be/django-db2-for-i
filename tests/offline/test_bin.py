"""bin/ scripts and the PUB400 lock (scripts/pub400_lock.py): no server needed."""

import ast
import fcntl
import importlib.util
import os
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BIN = ROOT / "bin"
LOCK_SCRIPT = ROOT / "scripts" / "pub400_lock.py"

spec = importlib.util.spec_from_file_location("scripts_pub400_lock", LOCK_SCRIPT)
lock = importlib.util.module_from_spec(spec)
sys.modules["scripts_pub400_lock"] = lock
spec.loader.exec_module(lock)

# The wheel session tests a copy without bin/.
needs_bin = pytest.mark.skipif(not BIN.is_dir(), reason="bin/ is not part of this copy")
SCRIPTS = sorted(p for p in BIN.glob("*") if not p.name.startswith("_")) if BIN.is_dir() else []


# --- The PUB400 lock ---------------------------------------------------------------------


def hold(directory: Path):
    """Take the lock in this process, as another job would."""
    directory.mkdir(parents=True, exist_ok=True)
    handle = open(directory / lock.LOCK_NAME, "a+")  # noqa: SIM115 (held until the caller closes it)
    fcntl.flock(handle, fcntl.LOCK_EX)
    (directory / lock.HOLDER_NAME).write_text("pid 1: nox -s pub400 (in /x, since then)\n")
    return handle


def test_a_free_lock_runs_the_command_and_clears_the_holder(tmp_path) -> None:
    assert lock.run([sys.executable, "-c", "raise SystemExit(4)"], directory=tmp_path) == 4
    assert (tmp_path / lock.HOLDER_NAME).read_text() == ""
    assert lock.status(tmp_path) == "PUB400 lock: free"


def test_the_holder_file_names_the_running_command(tmp_path) -> None:
    script = f"print(open({str(tmp_path / lock.HOLDER_NAME)!r}).read())"
    result = subprocess.run(
        [sys.executable, str(LOCK_SCRIPT), "--", sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env={**os.environ, "DB2I_LOCK_DIR": str(tmp_path)},
    )
    assert result.returncode == 0
    assert result.stdout.startswith("pid ")
    assert f"{sys.executable} -c" in result.stdout and " UTC)" in result.stdout


def test_a_second_job_stops_with_the_holder(tmp_path, capsys) -> None:
    handle = hold(tmp_path)
    try:
        assert lock.run(["true"], directory=tmp_path) == lock.BUSY
        assert capsys.readouterr().err == (
            "PUB400 busy: pid 1: nox -s pub400 (in /x, since then)\n"
        )
        assert lock.status(tmp_path).startswith("PUB400 busy: pid 1: nox -s pub400")
    finally:
        handle.close()


def test_wait_runs_once_the_lock_is_free(tmp_path, capsys) -> None:
    handle = hold(tmp_path)
    threading.Timer(0.5, handle.close).start()
    started = time.monotonic()
    assert lock.run(["true"], wait=True, directory=tmp_path) == 0
    assert time.monotonic() - started >= 0.4
    assert "; waiting (--wait)" in capsys.readouterr().err


def test_a_killed_holder_releases_the_lock(tmp_path) -> None:
    env = {**os.environ, "DB2I_LOCK_DIR": str(tmp_path)}
    job = subprocess.Popen(
        [sys.executable, str(LOCK_SCRIPT), "--", "sleep", "30"], env=env, start_new_session=True
    )
    try:
        for _ in range(100):
            if (tmp_path / lock.HOLDER_NAME).exists() and lock.status(tmp_path) != (
                "PUB400 lock: free"
            ):
                break
            time.sleep(0.05)
        assert lock.status(tmp_path).startswith("PUB400 busy: pid ")
    finally:
        os.killpg(job.pid, signal.SIGKILL)
        job.wait()
    assert lock.status(tmp_path) == "PUB400 lock: free"


def test_an_unknown_command(tmp_path, capsys) -> None:
    assert lock.run(["no-such-command-db2i"], directory=tmp_path) == 127
    assert "command not found: no-such-command-db2i" in capsys.readouterr().err


def test_the_lock_lives_outside_the_checkout(monkeypatch) -> None:
    monkeypatch.delenv("DB2I_LOCK_DIR", raising=False)
    assert lock.lock_dir() == Path.home() / ".local" / "state" / "django-db2-for-i"
    assert not lock.lock_dir().is_relative_to(ROOT)
    monkeypatch.setenv("DB2I_LOCK_DIR", "/elsewhere")
    assert lock.lock_dir() == Path("/elsewhere")


def test_the_lock_runs_with_the_hosts_python_39() -> None:
    ast.parse(LOCK_SCRIPT.read_text(), feature_version=(3, 9))


def test_pub400_sh_runs_every_job_under_the_lock() -> None:
    text = (ROOT / "scripts" / "pub400.sh").read_text()
    assert 'exec python3 scripts/pub400_lock.py $wait -- "$@"' in text
    assert 'if [ "${1:-}" = --wait ]; then' in text
    assert 'if [ "${DB2I_LOCK_WAIT:-}" = 1 ]; then' in text


def test_pub400_sh_gives_runs_the_cleanup_list_outside_the_checkout() -> None:
    text = (ROOT / "scripts" / "pub400.sh").read_text()
    assert "state=$(python3 scripts/pub400_lock.py --dir)" in text
    assert '-v "$state:/db2i-state" -e DB2I_TABLE_LIST=/db2i-state/created-objects.txt' in text


def test_the_state_directory(monkeypatch, capsys) -> None:
    monkeypatch.setenv("DB2I_LOCK_DIR", "/somewhere")
    assert lock.main(["--dir"]) == 0
    assert capsys.readouterr().out == "/somewhere\n"


# Reading .env (or printing the environment): checking that it exists is fine.
READS_ENV = re.compile(
    r"(\bsource\b|^\s*\.\s|\bcat\b|<\s*\S*|\bgrep\b|\bsed\b|\bawk\b|\bhead\b|\btail\b"
    r"|dotenv|open\()[^\n]*\.env\b|printenv"
)


# --- The bin/ scripts --------------------------------------------------------------------


def run_bin(*args: str, tmp_path: Path) -> subprocess.CompletedProcess:
    """Run a bin/ script with a docker that records any call (it must not be called)."""
    fake = tmp_path / "fakebin"
    fake.mkdir(exist_ok=True)
    (fake / "docker").write_text(f'#!/bin/sh\necho called >> "{tmp_path}/docker-called"\n')
    (fake / "docker").chmod(0o755)
    env = {**os.environ, "PATH": f"{fake}:{os.environ['PATH']}"}
    return subprocess.run(["bash", *args], capture_output=True, text=True, env=env, cwd=ROOT)


# The arguments a dry run of each script needs (none: the script's default action).
DRY_RUN_ARGS = {"probe": ["reachability"], "ibmi-test": ["--full-tier"]}


@needs_bin
@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_every_script_has_help_and_dry_run(script, tmp_path) -> None:
    helped = run_bin(str(script), "--help", tmp_path=tmp_path)
    assert helped.returncode == 0
    assert helped.stdout.startswith(f"bin/{script.name}: ")
    assert "--dry-run" in helped.stdout
    dry = run_bin(str(script), "--dry-run", *DRY_RUN_ARGS.get(script.name, []), tmp_path=tmp_path)
    assert dry.returncode == 0, dry.stderr
    assert not (tmp_path / "docker-called").exists()
    assert os.access(script, os.X_OK)


@needs_bin
def test_check_runs_lint_offline_corpus_then_the_gate(tmp_path) -> None:
    result = run_bin(
        str(BIN / "check"), "--dry-run", "--python", "3.14", "--django", "6.1", tmp_path=tmp_path
    )
    lines = result.stdout.splitlines()
    assert lines[0].endswith(
        r"tests nox -s lint offline\(3.14-django6.1\) corpus\(3.14-django6.1\)"
    )
    assert lines[1].endswith("tests nox -s gate")
    assert "scripts/classify_pr.py --base origin/main" in lines[2]


@needs_bin
def test_check_takes_the_combinations_from_the_noxfile(tmp_path) -> None:
    result = run_bin(str(BIN / "check"), "--dry-run", "--django", "6.0", tmp_path=tmp_path)
    first = result.stdout.splitlines()[0]
    assert all(f"offline\\({p}-django6.0\\)" in first for p in ("3.12", "3.13", "3.14"))
    assert "django6.1" not in first
    refused = run_bin(str(BIN / "check"), "--django", "9.9", tmp_path=tmp_path)
    assert refused.returncode == 2 and "no combination" in refused.stderr
    unknown = run_bin(str(BIN / "check"), "--fast", tmp_path=tmp_path)
    assert unknown.returncode == 2 and "unknown argument: --fast" in unknown.stderr


@needs_bin
def test_status_regenerates_then_shows_the_lock(tmp_path) -> None:
    lines = run_bin(str(BIN / "status"), "--dry-run", tmp_path=tmp_path).stdout.splitlines()
    assert lines[0].endswith("tests nox -s test_status features")
    assert lines[1].endswith("scripts/pub400_lock.py --status")
    only = run_bin(str(BIN / "status"), "--dry-run", "--no-write", tmp_path=tmp_path)
    assert "test_status" not in only.stdout


@needs_bin
def test_the_scripts_never_read_the_env_file() -> None:
    texts = [p.read_text() for p in BIN.glob("*")]
    texts += [(ROOT / "scripts" / name).read_text() for name in ("pub400.sh", "pub400_lock.py")]
    for text in texts:
        code = [line for line in text.splitlines() if not line.lstrip().startswith("#")]
        assert not [line for line in code if READS_ENV.search(line)]


@needs_bin
def test_the_ibmi_scripts_go_through_pub400_sh(tmp_path) -> None:
    def dry(*args):
        result = run_bin(*args, tmp_path=tmp_path)
        assert result.returncode == 0, result.stderr
        return result.stdout.splitlines()

    pub400 = f"{ROOT}/scripts/pub400.sh"
    assert dry(str(BIN / "probe"), "--dry-run", "sysinfo", "libraries") == [
        f"+ {pub400} probe sysinfo libraries"
    ]
    assert dry(str(BIN / "ibmi-test"), "--dry-run", "own", "-k", "goldens") == [
        f"+ {pub400} pub400 6.1 --create-db -k goldens"
    ]
    assert dry(
        str(BIN / "ibmi-test"), "--dry-run", "--django", "6.0", "django", "basic", "lookup"
    ) == [
        f"+ {ROOT}/scripts/runtests.sh 6.0 --clean basic",
        f"+ {ROOT}/scripts/runtests.sh 6.0 --clean lookup",
    ]
    assert dry(str(BIN / "ibmi-cleanup"), "--dry-run") == [f"+ {pub400} ibmi_cleanup"]
    assert dry(str(BIN / "ibmi-cleanup"), "--dry-run", "--yes") == [
        f"+ {pub400} ibmi_cleanup --yes"
    ]
    assert dry(str(BIN / "doctor"), "--dry-run")[-1] == f"+ {pub400} probe connect"
    assert dry(str(BIN / "doctor"), "--dry-run", "--offline")[-1].endswith("tests odbcinst -q -d")


@needs_bin
def test_the_ibmi_scripts_refuse_what_is_not_allowed(tmp_path) -> None:
    cases = [
        ((str(BIN / "probe"), "nope"), "unknown probe: nope"),
        ((str(BIN / "probe"),), "name a probe"),
        ((str(BIN / "ibmi-test"), "django"), "never the full suite"),
        ((str(BIN / "ibmi-test"), "--django", "9.9", "own", "x"), "Django 9.9 is not supported"),
        ((str(BIN / "ibmi-test"), "--full-tier", "own", "x"), "no own/django selection"),
        ((str(BIN / "ibmi-cleanup"), "--force"), "unknown argument: --force"),
    ]
    for args, message in cases:
        result = run_bin(*args, tmp_path=tmp_path)
        assert result.returncode == 2 and message in result.stderr, (args, result.stderr)
    assert not (tmp_path / "docker-called").exists()


@needs_bin
def test_wait_reaches_pub400_sh(tmp_path) -> None:
    script = tmp_path / "show.sh"
    script.write_text(
        f'source "{BIN}/_common.sh"\ncommon_args "$@"\necho "wait=${{DB2I_LOCK_WAIT:-}}"\n'
    )
    assert run_bin(str(script), "--wait", tmp_path=tmp_path).stdout == "wait=1\n"


def test_the_env_check_itself() -> None:
    for line in (
        "source .env",
        ". .env",
        "cat .env",
        'x=$(sed -n p "$ROOT/.env")',
        "load_dotenv('.env')",
        "printenv",
    ):
        assert READS_ENV.search(line), line
    assert not READS_ENV.search('if [ -e "$ROOT/.env" ]; then')
