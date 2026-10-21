"""The PUB400 lock: one PUB400 job at a time on this machine (phase 4 decision 17).

    python3 scripts/pub400_lock.py [--wait] -- <command> [<arg> ...]
    python3 scripts/pub400_lock.py --status

An OS file lock (``fcntl.flock``) on ``pub400.lock`` in
``~/.local/state/django-db2-for-i/`` (``DB2I_LOCK_DIR`` overrides the
directory), outside every checkout, so it holds across worktrees and clones.
It is held while <command> runs; the OS releases it when the process ends,
also after a crash, so it never goes stale. ``pub400.holder`` next to it
records who holds it (PID, command, worktree, start time), and ``--status``
prints it. A second job stops at once with "PUB400 busy: <holder>" (exit
75), or with ``--wait`` waits until the lock is free.

It covers one machine only: two machines behind the same IP (PUB400's
per-IP connection limit) are not covered. ``scripts/pub400.sh`` takes it on
the host before the container starts. Runs with the host's Python (3.9 or
later, standard library only) and prints no environment values.
"""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import IO

BUSY = 75  # EX_TEMPFAIL
LOCK_NAME, HOLDER_NAME = "pub400.lock", "pub400.holder"


def lock_dir() -> Path:
    override = os.environ.get("DB2I_LOCK_DIR")
    return Path(override) if override else Path.home() / ".local" / "state" / "django-db2-for-i"


def describe(command: list[str]) -> str:
    """Who holds the lock: PID, command, worktree, start time."""
    toplevel = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True
    ).stdout.strip()
    # dt.UTC needs Python 3.11; this runs with the host's Python (3.9 on macOS).
    started = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")  # noqa: UP017
    return f"pid {os.getpid()}: {' '.join(command)} (in {toplevel or os.getcwd()}, since {started})"


def read_holder(directory: Path) -> str:
    try:
        text = (directory / HOLDER_NAME).read_text().strip()
    except OSError:
        text = ""
    return text or "unknown holder"


def _open(directory: Path) -> IO[str]:
    directory.mkdir(parents=True, exist_ok=True)
    return open(directory / LOCK_NAME, "a+")


def _try_lock(handle: IO[str]) -> bool:
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return False
    return True


def status(directory: Path) -> str:
    with _open(directory) as handle:
        if _try_lock(handle):
            return "PUB400 lock: free"
        return f"PUB400 busy: {read_holder(directory)}"


def run(command: list[str], wait: bool = False, directory: Path | None = None) -> int:
    directory = directory or lock_dir()
    with _open(directory) as handle:
        if not _try_lock(handle):
            holder = read_holder(directory)
            if not wait:
                print(f"PUB400 busy: {holder}", file=sys.stderr)
                return BUSY
            print(f"PUB400 busy: {holder}; waiting (--wait)", file=sys.stderr, flush=True)
            fcntl.flock(handle, fcntl.LOCK_EX)
        holder_path = directory / HOLDER_NAME
        holder_path.write_text(describe(command) + "\n")
        try:
            try:
                child = subprocess.Popen(command)
            except FileNotFoundError:
                print(f"error: command not found: {command[0]}", file=sys.stderr)
                return 127
            # Ctrl-C reaches the whole process group: the child handles it, and
            # this process stays to clean up; SIGTERM is passed on.
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            signal.signal(signal.SIGTERM, lambda *_: child.terminate())
            return child.wait()
        finally:
            holder_path.write_text("")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--wait", action="store_true", help="wait while another job holds it")
    parser.add_argument("--status", action="store_true", help="print who holds the lock")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if args.status:
        print(status(lock_dir()))
        return 0
    if not command:
        parser.error("no command given")
    return run(command, wait=args.wait)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
