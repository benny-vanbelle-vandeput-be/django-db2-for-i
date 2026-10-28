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
    (directory / lock.HOLDER_NAME).write_text("pid 1: nox -s ibmi (in /x, since then)\n")
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
        assert capsys.readouterr().err == ("PUB400 busy: pid 1: nox -s ibmi (in /x, since then)\n")
        assert lock.status(tmp_path).startswith("PUB400 busy: pid 1: nox -s ibmi")
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
    assert 'exec python3 scripts/pub400_lock.py $wait --container "$container" -- "$@"' in text
    assert 'container="db2i-pub400-$$"' in text
    assert 'docker compose run --rm --name "$container"' in text
    assert 'if [ "${1:-}" = --wait ]; then' in text
    assert 'if [ "${DB2I_LOCK_WAIT:-}" = 1 ]; then' in text


def test_pub400_sh_gives_runs_the_cleanup_list_outside_the_checkout() -> None:
    text = (ROOT / "scripts" / "pub400.sh").read_text()
    assert "state=$(python3 scripts/pub400_lock.py --dir)" in text
    assert '-v "$state:/db2i-state" -e DB2I_TABLE_LIST=/db2i-state/created-objects.txt' in text


# --- The lock stops the run's container before it is released --------------------------

FAKE_DOCKER = """#!/bin/sh
# A fake docker: one container, running while $STATE exists. Every call is
# logged with whether the PUB400 lock was held at that moment.
held=$(python3 - "$DB2I_LOCK_DIR/pub400.lock" <<'PY'
import fcntl, sys
with open(sys.argv[1], "a") as handle:
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        print("free")
    except OSError:
        print("held")
PY
)
echo "$1 $2 lock=$held" >> "$LOG"
case "$1 $2" in
    "ps -a") [ -f "$EARLIER" ] && cat "$EARLIER" ;;
    "ps -q") [ -f "$STATE" ] && echo 0123456789ab ;;
    "stop -t") [ -n "$STOP_FAILS" ] || rm -f "$STATE" ;;
    "kill "*) rm -f "$STATE" ;;
    "rm -f") rm -f "$EARLIER" ;;
esac
exit 0
"""


def _locked_run(tmp_path, *, running=True, stop_fails=False, command=("sleep", "30"), earlier=""):
    fake = tmp_path / "fakebin"
    fake.mkdir()
    (fake / "docker").write_text(FAKE_DOCKER)
    (fake / "docker").chmod(0o755)
    state, log = tmp_path / "running", tmp_path / "docker.log"
    if running:
        state.touch()
    if earlier:
        (tmp_path / "earlier").write_text(earlier)
    env = {
        **os.environ,
        "PATH": f"{fake}:{os.environ['PATH']}",
        "DB2I_LOCK_DIR": str(tmp_path),
        "STATE": str(state),
        "LOG": str(log),
        "EARLIER": str(tmp_path / "earlier"),
        "STOP_FAILS": "1" if stop_fails else "",
    }
    process = subprocess.Popen(
        [sys.executable, str(LOCK_SCRIPT), "--container", "db2i-pub400-1", "--", *command],
        env=env,
        stderr=subprocess.PIPE,
        text=True,
    )
    return process, state, log


def _wait_for_holder(tmp_path) -> None:
    holder = tmp_path / lock.HOLDER_NAME
    for _ in range(100):
        if holder.exists() and holder.read_text().strip():
            return
        time.sleep(0.05)
    raise AssertionError("the lock was not taken")


def _calls(log) -> list[str]:
    return log.read_text().split("\n")[:-1] if log.exists() else []


@pytest.mark.parametrize("signum", [signal.SIGTERM, signal.SIGHUP])
def test_a_stopped_run_stops_its_container_before_the_lock_is_released(tmp_path, signum):
    process, state, log = _locked_run(tmp_path)
    _wait_for_holder(tmp_path)
    process.send_signal(signum)
    process.wait(timeout=30)
    assert _calls(log) == [
        "ps -a lock=held",
        "ps -q lock=held",
        "stop -t lock=held",
        "ps -q lock=held",
    ]
    assert not state.exists()
    assert "stopping container db2i-pub400-1" in process.stderr.read()
    assert lock.status(tmp_path) == "PUB400 lock: free"


def test_a_container_that_does_not_stop_is_killed_before_the_lock_is_released(tmp_path):
    process, state, log = _locked_run(tmp_path, stop_fails=True)
    _wait_for_holder(tmp_path)
    process.send_signal(signal.SIGTERM)
    process.wait(timeout=30)
    assert _calls(log) == [
        "ps -a lock=held",
        "ps -q lock=held",
        "stop -t lock=held",
        "ps -q lock=held",
        "kill db2i-pub400-1 lock=held",
        "ps -q lock=held",
    ]
    assert not state.exists()


def test_a_finished_run_whose_container_is_gone_only_checks(tmp_path):
    process, _state, log = _locked_run(tmp_path, running=False, command=("true",))
    assert process.wait(timeout=30) == 0
    assert _calls(log) == ["ps -a lock=held", "ps -q lock=held"]


def test_an_exited_container_of_an_earlier_run_is_removed_first(tmp_path):
    """A crash can leave db2i-pub400-<pid> behind; a reused PID must not
    collide with it."""
    process, _state, log = _locked_run(
        tmp_path, running=False, command=("true",), earlier="db2i-pub400-1\texited\n"
    )
    assert process.wait(timeout=30) == 0
    assert _calls(log) == ["ps -a lock=held", "rm -f lock=held", "ps -q lock=held"]


def test_a_running_container_of_an_earlier_run_refuses_the_run(tmp_path):
    """It still holds a PUB400 connection (e.g. after a SIGKILL)."""
    marker = tmp_path / "ran"
    process, _state, log = _locked_run(
        tmp_path,
        running=False,
        command=("touch", str(marker)),
        earlier="db2i-pub400-77\trunning\n",
    )
    assert process.wait(timeout=30) == lock.BUSY
    assert "a PUB400 container from an earlier run still runs: db2i-pub400-77" in (
        process.stderr.read()
    )
    assert not marker.exists()
    # Before the lock is released its own container is checked too (never started).
    assert _calls(log) == ["ps -a lock=held", "ps -q lock=held"]


@pytest.mark.parametrize("signum", [signal.SIGTERM, signal.SIGHUP, signal.SIGINT])
def test_a_signal_before_the_command_starts_skips_it_and_still_cleans_up(
    tmp_path, monkeypatch, signum
):
    """The race #167's test found: a stopped task signals the whole process
    group, possibly right after the lock was taken and before the command
    started. The handlers are in place from then on: the command does not
    start, and the container is still checked and stopped before the lock
    is released."""
    calls = []
    marker = tmp_path / "ran"

    def signal_now():
        os.kill(os.getpid(), signum)  # arrives in the window
        return None

    monkeypatch.setattr(lock, "clear_earlier_containers", signal_now)
    monkeypatch.setattr(lock, "container_running", lambda name: calls.append(name) or False)
    before = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT)}
    code = lock.run(["touch", str(marker)], directory=tmp_path, container="db2i-pub400-1")
    assert code == 128 + signum
    assert not marker.exists()
    assert calls == ["db2i-pub400-1"]  # stop_container() ran
    assert lock.status(tmp_path) == "PUB400 lock: free"
    assert (tmp_path / lock.HOLDER_NAME).read_text() == ""
    assert {s: signal.getsignal(s) for s in before} == before


def test_without_a_container_docker_is_not_called(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(lock, "_docker", lambda *args, **kwargs: calls.append(args))
    assert lock.run(["true"], directory=tmp_path) == 0
    assert calls == []


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
DRY_RUN_ARGS = {
    "probe": ["reachability"],
    "ibmi-test": ["--full-tier"],
    "release-prepare": ["0.1.0a5"],
}
# Scripts whose dry run needs a real fixture; their own tests run it:
# worktree-remove needs a git worktree (tests/offline/test_probe_results.py).
DRY_RUN_ELSEWHERE = {"worktree-remove"}


@needs_bin
@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_every_script_has_help_and_dry_run(script, tmp_path) -> None:
    helped = run_bin(str(script), "--help", tmp_path=tmp_path)
    assert helped.returncode == 0
    assert helped.stdout.startswith(f"bin/{script.name}: ")
    assert "--dry-run" in helped.stdout
    if script.name in DRY_RUN_ELSEWHERE:
        assert os.access(script, os.X_OK)
        return
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
        r"tests nox -s lint offline\(3.14-django6.1\) replay\(3.14-django6.1\)"
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
    approval = (
        "https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/1#issuecomment-2"
    )
    (line,) = dry(str(BIN / "probe"), "--dry-run", "--approved", approval, "lib_drop", "--execute")
    assert line.startswith(f"+ {pub400} probe_lib lib_drop --approved {approval} --approved-by ")
    assert line.endswith(" --execute")
    # A qtemp_ probe with its own entry point: one generic session (#191, item 10).
    assert dry(str(BIN / "probe"), "--dry-run", "qtemp_encoding", "--", "--variant", "x") == [
        f"+ {pub400} probe_qtemp qtemp_encoding --variant x"
    ]
    assert dry(str(BIN / "ibmi-test"), "--dry-run", "own", "-k", "goldens") == [
        f"+ {pub400} ibmi 6.1 --create-db -k goldens"
    ]
    assert dry(
        str(BIN / "ibmi-test"), "--dry-run", "--django", "6.0", "django", "basic", "lookup"
    ) == [
        f"+ {ROOT}/scripts/django_suite.sh 6.0 --clean basic",
        f"+ {ROOT}/scripts/django_suite.sh 6.0 --clean lookup",
    ]
    assert dry(str(BIN / "ibmi-cleanup"), "--dry-run") == [f"+ {pub400} ibmi_cleanup"]
    assert dry(str(BIN / "ibmi-cleanup"), "--dry-run", "--yes") == [
        f"+ {pub400} ibmi_cleanup --yes"
    ]
    assert dry(str(BIN / "doctor"), "--dry-run")[-1] == f"+ {pub400} probe connect journal_check"
    assert dry(str(BIN / "doctor"), "--dry-run", "--offline")[-1].endswith("tests odbcinst -q -d")


@needs_bin
def test_the_ibmi_scripts_refuse_what_is_not_allowed(tmp_path) -> None:
    cases = [
        ((str(BIN / "probe"), "nope"), "unknown probe: nope"),
        ((str(BIN / "probe"),), "name a probe"),
        ((str(BIN / "probe"), "lib_drop"), "lib_drop changes the IBM i outside QTEMP"),
        ((str(BIN / "probe"), "lib_drop", "--execute"), "needs --approved"),
        ((str(BIN / "probe"), "--approved", "x", "reachability"), "for lib_ probes only"),
        ((str(BIN / "probe"), "--approved"), "--approved needs the link"),
        (
            (str(BIN / "probe"), "--approved", "x", "lib_drop", "lib_sequence"),
            "one lib_ probe per run",
        ),
        ((str(BIN / "probe"), "qtemp_catalog"), "qtemp_catalog runs by its short name"),
        ((str(BIN / "probe"), "qtemp_nope"), "unknown probe: qtemp_nope"),
        ((str(BIN / "probe"), "qtemp_locale", "connect"), "runs alone"),
        ((str(BIN / "probe"), "qtemp_locale", "--execute"), "for lib_ probes only"),
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


# --- bin/verify, bin/ibmi-test --affected and the shared IBM i runner -------------------


@needs_bin
def test_verify_runs_offline_first_then_selects_runs_and_finishes(tmp_path) -> None:
    result = run_bin(str(BIN / "verify"), "--dry-run", "--django", "6.0", tmp_path=tmp_path)
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines[0] == f"+ mkdir -p {ROOT}/test-results/verify/6.0"
    assert lines[2].endswith(
        r"tests nox -s offline\(3.14-django6.0\) -- --junitxml=test-results/verify/6.0/offline.xml"
    )
    assert lines[3].endswith(
        r"tests nox -s replay\(3.14-django6.0\) -- --junitxml=test-results/verify/6.0/corpus.xml"
    )
    assert lines[4].endswith("scripts/verify.py triage 6.0")
    assert lines[5].endswith("scripts/verify.py select 6.0 --base origin/main")
    assert lines[6] == (
        "+ (the IBM i runs listed in test-results/verify/6.0/runs.txt,"
        " each through scripts/pub400.sh)"
    )
    assert lines[7].endswith("scripts/verify.py finish 6.0")
    limited = run_bin(
        str(BIN / "verify"), "--dry-run", "--max-labels", "9", "--max-runs", "3", "--base", "x",
        tmp_path=tmp_path,
    )  # fmt: skip
    assert "select 6.1 --base x --max-labels 9 --max-runs 3" in limited.stdout
    for args, message in [
        (("--django", "9.9"), "Django 9.9 is not supported"),
        (("--fast",), "unknown argument: --fast"),
    ]:
        refused = run_bin(str(BIN / "verify"), *args, tmp_path=tmp_path)
        assert refused.returncode == 2 and message in refused.stderr
    assert not (tmp_path / "docker-called").exists()


@needs_bin
def test_ibmi_test_affected_selects_runs_and_reports_without_stamps(tmp_path) -> None:
    lines = run_bin(str(BIN / "ibmi-test"), "--dry-run", "--affected", tmp_path=tmp_path)
    lines = lines.stdout.splitlines()
    assert lines[0].endswith("scripts/verify.py select 6.1")
    assert lines[1].startswith("+ (the IBM i runs listed in test-results/verify/6.1/runs.txt")
    assert lines[2].endswith("scripts/verify.py finish 6.1 --no-stamp")
    refused = run_bin(str(BIN / "ibmi-test"), "--affected", "own", "x", tmp_path=tmp_path)
    assert refused.returncode == 2 and "--affected selects the tests itself" in refused.stderr


@needs_bin
def test_the_container_trusts_only_the_checkouts_mount(tmp_path) -> None:
    lines = run_bin(str(BIN / "check"), "--dry-run", tmp_path=tmp_path).stdout.splitlines()
    containers = [line for line in lines if "docker compose" in line]
    assert containers
    for line in containers:
        assert "-e GIT_CONFIG_KEY_0=safe.directory -e GIT_CONFIG_VALUE_0=/workspace tests" in line
    text = "\n".join(p.read_text() for p in BIN.glob("*"))
    assert "safe.directory=*" not in text and "safe.directory '*'" not in text
    assert "GIT_CONFIG_VALUE_0=\\*" not in "\n".join(lines)


@needs_bin
def test_ibmi_runs_runs_every_line_and_records_the_results(tmp_path) -> None:
    runs = tmp_path / "runs.txt"
    runs.write_text(
        "goldens\ttest-results/verify/6.1/goldens.txt\n"
        "own\tfull\n"
        "own\ttests/ibmi/test_a.py::test_x\ttests/ibmi/test_b.py\n"
        "django\ta.tests.A.test_1\tb.tests\tc\n"
    )
    results = tmp_path / "results.txt"
    script = tmp_path / "runs.sh"
    (tmp_path / ".env").touch()
    script.write_text(
        f'source "{BIN}/_common.sh"\nROOT="$2"\n'
        # The full tier fails; the runs after it still run.
        'pub400() { echo "pub400 $*"; [ "$#" != 3 ] || [ "$3" != --create-db ]; }\n'
        'run() { echo "run $*"; }\n'
        f'ibmi_runs 6.1 "{runs}" "{results}" "$1" < /dev/null || echo "status=$?"\n'
    )
    stamped = run_bin(str(script), "1", str(tmp_path), tmp_path=tmp_path).stdout.splitlines()
    assert stamped == [
        "pub400 ibmi 6.1 tests/ibmi/test_goldens.py --goldens-from "
        "test-results/verify/6.1/goldens.txt --record-verification",
        "pub400 ibmi 6.1 --create-db",
        "pub400 ibmi 6.1 --create-db tests/ibmi/test_a.py::test_x tests/ibmi/test_b.py",
        f"run {tmp_path}/scripts/django_suite.sh 6.1 --clean --capture a.tests.A.test_1 b.tests c",
        "status=1",
    ]
    assert results.read_text().splitlines() == [
        "goldens\ttest-results/verify/6.1/goldens.txt\t0",
        "own\tfull\t1",
        "own\ttests/ibmi/test_a.py::test_x tests/ibmi/test_b.py\t0",
        "django\ta.tests.A.test_1 b.tests c\t0",
    ]
    plain = run_bin(str(script), "0", str(tmp_path), tmp_path=tmp_path).stdout.splitlines()
    assert "--record-verification" not in plain[0]
    assert plain[3] == (
        f"run {tmp_path}/scripts/django_suite.sh 6.1 --clean a.tests.A.test_1 b.tests c"
    )
    # Without .env (checked for existence only) no run starts.
    (tmp_path / ".env").unlink()
    refused = run_bin(str(script), "1", str(tmp_path), tmp_path=tmp_path)
    assert refused.stdout.splitlines() == ["status=1"]
    assert "no .env in this checkout" in refused.stderr


def test_git_never_trusts_every_directory() -> None:
    """safe.directory names exact paths only (the mount, a checkout), never '*'."""
    files = [ROOT / "noxfile.py", ROOT / "compose.yaml", *BIN.glob("*")]
    for pattern in ("scripts/*", "docker/*", "probes/*.py", ".github/workflows/*", "tests/*.py"):
        files += ROOT.glob(pattern)
    star = re.compile(r"safe\.directory\s*[= ]\s*['\"]?\*")
    offenders = [str(p) for p in files if p.is_file() and star.search(p.read_text())]
    assert offenders == []


@needs_bin
def test_status_run_runs_each_version_under_the_lock_then_builds_its_corpus(tmp_path) -> None:
    result = run_bin(
        str(BIN / "status-run"), "--dry-run", "--django", "6.0", "--restart", "--limit", "2",
        tmp_path=tmp_path,
    )  # fmt: skip
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines[0] == f"+ {ROOT}/scripts/pub400.sh status_run 6.0 --restart --limit 2"
    assert lines[1].endswith("tests uv run --no-project python scripts/build_corpus.py 6.0")
    every = run_bin(str(BIN / "status-run"), "--dry-run", tmp_path=tmp_path).stdout
    assert [line.split()[-1] for line in every.splitlines() if "status_run" in line] == [
        "5.2",
        "6.0",
        "6.1",
    ]
    for args, message in [
        (("--limit", "x"), "--limit needs a number"),
        (("--django", "9.9"), "Django 9.9 is not supported"),
        (("--fast",), "unknown argument: --fast"),
    ]:
        refused = run_bin(str(BIN / "status-run"), *args, tmp_path=tmp_path)
        assert refused.returncode == 2 and message in refused.stderr
    assert not (tmp_path / "docker-called").exists()


@needs_bin
def test_ibmi_test_runs_every_django_label_after_a_failure(tmp_path) -> None:
    root = tmp_path / "repo"
    (root / "bin").mkdir(parents=True)
    (root / "scripts").mkdir()
    for name in ("_common.sh", "ibmi-test"):
        (root / "bin" / name).write_text((BIN / name).read_text())
    (root / "noxfile.py").write_text((ROOT / "noxfile.py").read_text())
    # A fake runner: the label "bad" fails, every call is recorded.
    (root / "scripts" / "django_suite.sh").write_text(
        f'#!/bin/sh\necho "$@" >> "{tmp_path}/runs"\nfor last; do :; done\n[ "$last" != bad ]\n'
    )
    (root / "scripts" / "django_suite.sh").chmod(0o755)
    result = run_bin(str(root / "bin" / "ibmi-test"), "django", "a", "bad", "c", tmp_path=tmp_path)
    assert result.returncode == 1
    assert "ibmi-test: failed: bad" in result.stderr
    assert (tmp_path / "runs").read_text().splitlines() == [
        "6.1 --clean a",
        "6.1 --clean bad",
        "6.1 --clean c",
    ]


@needs_bin
def test_probe_publish_runs_the_cleaner_in_the_container(tmp_path) -> None:
    result = run_bin(
        str(BIN / "probe"), "--dry-run", "--publish",
        f"{ROOT}/test-results/probes/catalog-20261022T203029Z.json", tmp_path=tmp_path,
    )  # fmt: skip
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith(
        "scripts/publish_probe_result.py test-results/probes/catalog-20261022T203029Z.json"
    )
    refused = run_bin(str(BIN / "probe"), "--publish", tmp_path=tmp_path)
    assert refused.returncode == 2 and "--publish needs one result file" in refused.stderr


# --- One nox-envs volume per checkout (#190, topic 4) ------------------------------------

NOX_VOLUME = ROOT / "scripts" / "nox_volume.sh"


def nox_volume(checkout: Path) -> str:
    result = subprocess.run(
        ["sh", str(NOX_VOLUME), str(checkout)], capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def test_the_main_checkout_keeps_its_volume_and_a_worktree_gets_its_own(tmp_path) -> None:
    git = [
        "git", "-c", "user.name=t", "-c", "user.email=t@example.com",
        "-c", "commit.gpgsign=false",
    ]  # fmt: skip
    main = tmp_path / "django-db2-for-i"
    main.mkdir()
    subprocess.run([*git, "-C", str(main), "init", "-q"], check=True)
    subprocess.run([*git, "-C", str(main), "commit", "-q", "--allow-empty", "-m", "x"], check=True)
    worktree = tmp_path / "django-db2-for-i-My Topic"
    subprocess.run(
        [*git, "-C", str(main), "worktree", "add", "-q", "-b", "t", str(worktree)], check=True
    )
    assert nox_volume(main) == "django-db2-for-i_nox-envs"
    assert nox_volume(worktree) == "django-db2-for-i_nox-envs-django-db2-for-i-My-Topic"
    # Not a git checkout at all (a copy): the main checkout's volume.
    assert nox_volume(tmp_path) == "django-db2-for-i_nox-envs"


def test_compose_takes_the_volume_name_from_the_environment() -> None:
    text = (ROOT / "compose.yaml").read_text()
    assert "name: ${DB2I_NOX_ENVS:-django-db2-for-i_nox-envs}" in text


@needs_bin
def test_every_container_gets_the_checkouts_own_volume(tmp_path) -> None:
    lines = run_bin(str(BIN / "check"), "--dry-run", tmp_path=tmp_path).stdout.splitlines()
    containers = [line for line in lines if "docker compose" in line]
    assert containers
    expected = f"+ env DB2I_NOX_ENVS={nox_volume(ROOT)} docker compose "
    assert all(line.startswith(expected) for line in containers)
    text = (ROOT / "scripts" / "pub400.sh").read_text()
    assert "DB2I_NOX_ENVS=$(scripts/nox_volume.sh .)\nexport DB2I_NOX_ENVS\n" in text
    remove = (BIN / "worktree-remove").read_text()
    assert 'volume=$("$ROOT/scripts/nox_volume.sh" "$path")' in remove
    assert 'run docker volume rm --force "$volume"' in remove
