"""The PUB400 lock: one PUB400 job at a time on this machine (phase 4 decision 17).

    python3 scripts/pub400_lock.py [--wait] [--container <name>] -- <command> [<arg> ...]
    python3 scripts/pub400_lock.py --status
    python3 scripts/pub400_lock.py --dir      (the state directory, for scripts/pub400.sh)

An OS file lock (``fcntl.flock``) on ``pub400.lock`` in
``~/.local/state/django-db2-for-i/`` (``DB2I_LOCK_DIR`` overrides the
directory), outside every checkout, so it holds across worktrees and clones.
It is held while <command> runs; the OS releases it when the process ends,
also after a crash, so it never goes stale. ``pub400.holder`` next to it
records who holds it (PID, command, worktree, start time), and ``--status``
prints it. A second job stops at once with "PUB400 busy: <holder>" (exit
75), or with ``--wait`` waits until the lock is free.

With ``--container <name>`` (scripts/pub400.sh names its ``docker compose
run`` container) the lock is released only after that container is gone: the
container belongs to the Docker daemon, so stopping <command> (SIGTERM, SIGHUP,
SIGINT, also a task that is stopped) leaves it running with its PUB400
connection. Before the lock is released, the container is stopped (``docker
stop``, then ``docker kill`` after a timeout). Before a run starts, an exited
container of an earlier run (``db2i-pub400-*``, e.g. after a crash) is
removed, and a running one refuses the run: it still holds a PUB400
connection (a SIGKILL, which cannot be caught, leaves one behind).

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
CONTAINER_PREFIX = "db2i-pub400-"  # scripts/pub400.sh: db2i-pub400-<pid>
STOP_TIMEOUT = 10  # seconds docker stop waits before it kills the container
KILL_TIMEOUT = 30  # seconds for docker kill and the check that the container is gone
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


def _docker(*args: str, timeout: int) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(["docker", *args], 1, "", str(exc))


def earlier_containers() -> list[tuple[str, str]]:
    """(name, state) of every PUB400 run container that still exists."""
    found = _docker(
        "ps",
        "-a",
        "--filter",
        f"name=^{CONTAINER_PREFIX}",
        "--format",
        "{{.Names}}\t{{.State}}",
        timeout=KILL_TIMEOUT,
    )
    return [
        (name, state)
        for name, _, state in (line.partition("\t") for line in found.stdout.splitlines())
        if name.startswith(CONTAINER_PREFIX)
    ]


def clear_earlier_containers() -> str | None:
    """Remove exited containers of earlier runs; the name of a running one, if any."""
    running = None
    for name, state in earlier_containers():
        if state == "running":
            running = running or name
        else:
            _docker("rm", "-f", name, timeout=KILL_TIMEOUT)
    return running


def container_running(name: str) -> bool:
    found = _docker("ps", "-q", "--filter", f"name=^{name}$", timeout=KILL_TIMEOUT)
    return bool(found.stdout.strip())


def stop_container(name: str) -> bool:
    """Stop the run's container (docker stop, then docker kill); True when it is gone."""
    if not container_running(name):
        return True
    print(f"pub400 lock: stopping container {name}", file=sys.stderr, flush=True)
    _docker("stop", "-t", str(STOP_TIMEOUT), name, timeout=STOP_TIMEOUT + KILL_TIMEOUT)
    gone = not container_running(name)
    if not gone:
        _docker("kill", name, timeout=KILL_TIMEOUT)
        gone = not container_running(name)
    if not gone:
        print(
            f"pub400 lock: container {name} still runs; stop it (docker stop {name}) "
            "before the next PUB400 job",
            file=sys.stderr,
        )
    return gone


def run(
    command: list[str],
    wait: bool = False,
    directory: Path | None = None,
    container: str | None = None,
) -> int:
    directory = directory or lock_dir()
    with _open(directory) as handle:
        if not _try_lock(handle):
            holder = read_holder(directory)
            if not wait:
                print(f"PUB400 busy: {holder}", file=sys.stderr)
                return BUSY
            print(f"PUB400 busy: {holder}; waiting (--wait)", file=sys.stderr, flush=True)
            fcntl.flock(handle, fcntl.LOCK_EX)
        # Signals are handled from here on, while the lock is held: one that
        # arrives before the command starts skips it, and the container is
        # still cleaned up below (a stopped task sends SIGTERM or SIGHUP to the
        # whole process group, possibly before the child exists).
        received: list[int] = []
        child: subprocess.Popen | None = None

        def on_signal(signum, _frame) -> None:
            received.append(signum)
            # Ctrl-C (SIGINT) reaches the whole process group: the child
            # handles it itself; SIGTERM and SIGHUP are passed on.
            if child is not None and signum != signal.SIGINT:
                child.terminate()

        handled = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
        previous = {signum: signal.signal(signum, on_signal) for signum in handled}
        holder_path = directory / HOLDER_NAME
        try:
            if container and (running := clear_earlier_containers()):
                print(
                    f"PUB400 busy: a PUB400 container from an earlier run still runs: "
                    f"{running}; stop it (docker stop {running}), then run bin/ibmi-cleanup",
                    file=sys.stderr,
                )
                return BUSY
            holder_path.write_text(describe(command) + "\n")
            if received:
                return 128 + received[0]
            try:
                child = subprocess.Popen(command)
            except FileNotFoundError:
                print(f"error: command not found: {command[0]}", file=sys.stderr)
                return 127
            if any(signum != signal.SIGINT for signum in received):
                child.terminate()  # a signal arrived while the child started
            return child.wait()
        finally:
            # The lock is still held here: the container goes first.
            for signum in (signal.SIGTERM, signal.SIGHUP):
                signal.signal(signum, signal.SIG_IGN)
            try:
                if container:
                    stop_container(container)
                holder_path.write_text("")
            finally:
                for signum, handler in previous.items():
                    signal.signal(signum, handler)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--wait", action="store_true", help="wait while another job holds it")
    parser.add_argument(
        "--container", help="the run's docker container, stopped before the lock is released"
    )
    parser.add_argument("--status", action="store_true", help="print who holds the lock")
    parser.add_argument("--dir", action="store_true", help="print the state directory")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if args.status:
        print(status(lock_dir()))
        return 0
    if args.dir:
        print(lock_dir())
        return 0
    if not command:
        parser.error("no command given")
    return run(command, wait=args.wait, container=args.container)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
