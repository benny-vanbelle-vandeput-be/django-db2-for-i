"""bin/setup in a temporary copy of the repository, with fake docker and git (no server).

Only test values: the interactive path runs on a pseudo-terminal in tmp_path.
"""

import os
import pty
import shutil
import stat
import subprocess
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PINNED = "1e01021325e7207a19c73f11150f545c749f07d8"
needs_bin = pytest.mark.skipif(not (ROOT / "bin").is_dir(), reason="bin/ is not part of this copy")

FAKE_GIT = """#!/bin/sh
echo "git $*" >> "$CALLS"
if [ "$1" = clone ]; then
    for last; do :; done
    mkdir -p "$last/.git"
    exit 0
fi
case "$*" in
    *"rev-parse HEAD"*) echo "${FAKE_HEAD:-}" ;;
    *"status --porcelain"*) printf '%s' "${FAKE_DIRTY:-}" ;;
esac
exit 0
"""


@pytest.fixture
def repo(tmp_path):
    """A repository copy with bin/setup, a stub bin/doctor, one corpus manifest."""
    root = tmp_path / "repo"
    (root / "bin").mkdir(parents=True)
    for name in ("_common.sh", "setup"):
        shutil.copy(ROOT / "bin" / name, root / "bin" / name)
    (root / "bin" / "doctor").write_text('#!/bin/sh\necho "doctor $*" >> "$CALLS"\n')
    (root / "bin" / "doctor").chmod(0o755)
    shutil.copy(ROOT / ".env.example", root / ".env.example")
    manifest = root / "tests" / "offline" / "replay" / "6.1" / "7.5" / "manifest.toml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(f'django = "6.1"\ndjango_commit = "{PINNED}"\n')
    fake = tmp_path / "fakebin"
    fake.mkdir()
    (fake / "git").write_text(FAKE_GIT)
    (fake / "docker").write_text('#!/bin/sh\necho "docker $*" >> "$CALLS"\n')
    for tool in fake.iterdir():
        tool.chmod(0o755)
    env = {**os.environ, "PATH": f"{fake}:{os.environ['PATH']}", "CALLS": str(tmp_path / "calls")}
    return root, env, tmp_path / "calls"


def setup(root: Path, env: dict, *args: str, **extra) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(root / "bin" / "setup"), *args],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        env={**env, **extra},
    )


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


@needs_bin
def test_without_a_terminal_env_is_only_the_template(repo) -> None:
    root, env, calls = repo
    result = setup(root, env)
    assert result.returncode == 0, result.stderr
    assert (root / ".env").read_text() == (root / ".env.example").read_text()
    assert mode(root / ".env") == 0o600
    assert "no terminal" in result.stdout
    log = calls.read_text().splitlines()
    assert log[0] == f"docker compose --project-directory {root} build tests offline"
    assert log[1].startswith("git clone --quiet --branch stable/6.1.x --single-branch ")
    assert log[1].endswith(f" {root}/vendor/django-6.1")
    assert log[2] == f"git -C {root}/vendor/django-6.1 checkout --quiet -B stable/6.1.x {PINNED}"
    assert log[3] == "doctor --offline"


@needs_bin
def test_an_existing_env_is_never_read_or_changed(repo) -> None:
    root, env, _calls = repo
    (root / ".env").write_text("left alone\n")
    (root / ".env").chmod(0o640)
    result = setup(root, env, "--no-build")
    assert result.returncode == 0, result.stderr
    assert (root / ".env").read_text() == "left alone\n"
    assert mode(root / ".env") == 0o640
    assert ".env exists; left as it is" in result.stdout


def interactive(root: Path, env: dict, answers: list[str]) -> tuple[int, str]:
    """Run bin/setup --no-build on a pseudo-terminal, typing the answers."""
    primary, secondary = pty.openpty()
    process = subprocess.Popen(
        ["bash", str(root / "bin" / "setup"), "--no-build"],
        stdin=secondary,
        stdout=secondary,
        stderr=secondary,
        env=env,
        close_fds=True,
    )
    os.close(secondary)
    output = b""
    for answer in answers:
        time.sleep(0.3)
        os.write(primary, answer.encode() + b"\n")
    while True:
        try:
            chunk = os.read(primary, 4096)
        except OSError:
            break
        if not chunk:
            break
        output += chunk
    status = process.wait(timeout=30)
    os.close(primary)
    return status, output.decode(errors="replace")


@needs_bin
def test_in_a_terminal_the_values_go_into_a_private_env(repo) -> None:
    root, env, _calls = repo
    password = "test-only-pw-91"
    status, output = interactive(root, env, ["tester", password, "LIBA", "LIBB", ""])
    assert status == 0, output
    written = (root / ".env").read_text()
    for line in (
        "DB2I_USER=tester",
        f"DB2I_PASSWORD={password}",
        "DB2I_DEFAULT_LIBRARY=LIBA",
        "DB2I_OTHER_LIBRARY=LIBB",
        "DB2I_HOST=pub400.com",
        "DB2I_SSL=1",
    ):
        assert line in written.splitlines()
    assert written.startswith("# Copy to .env")  # the template's comments stay
    assert mode(root / ".env") == 0o600
    assert password not in output  # hidden input, nothing printed


@needs_bin
def test_a_too_long_library_writes_nothing(repo) -> None:
    root, env, _calls = repo
    status, output = interactive(root, env, ["tester", "pw", "LIBRARY_TOO_LONG", "LIBB", ""])
    assert status == 2
    assert "nothing was written" in output
    assert not (root / ".env").exists()


@needs_bin
def test_a_checkout_with_local_changes_is_refused_not_reset(repo) -> None:
    root, env, calls = repo
    (root / ".env").write_text("x\n")
    (root / "vendor" / "django-6.1" / ".git").mkdir(parents=True)
    result = setup(root, env, "--no-build", FAKE_HEAD="0" * 40, FAKE_DIRTY=" M tests/x.py\n")
    assert result.returncode == 1
    assert "has local changes; not switched" in result.stderr
    assert not [line for line in calls.read_text().splitlines() if " checkout --quiet" in line]
    at_pin = setup(root, env, "--no-build", FAKE_HEAD=PINNED)
    assert at_pin.returncode == 0 and "at the pinned commit 1e01021" in at_pin.stdout


@needs_bin
def test_dry_run_asks_and_writes_nothing(repo) -> None:
    root, env, calls = repo
    result = setup(root, env, "--dry-run")
    assert result.returncode == 0, result.stderr
    assert "copy .env.example to .env" in result.stdout
    assert not (root / ".env").exists() and not (root / "vendor").exists()
    assert not calls.exists()


@needs_bin
def test_the_help_says_claude_never_runs_it_interactively() -> None:
    text = (ROOT / "bin" / "setup").read_text()
    assert "Claude never runs it interactively and never enters values" in text
