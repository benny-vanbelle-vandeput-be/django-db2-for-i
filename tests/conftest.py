"""Shared pytest configuration.

Tests are marked with their tier based on their directory (tests/offline/ ->
``offline``, tests/pub400/ -> ``pub400``).

Offline tests must never open a database connection: for them,
``pyodbc.connect`` is replaced with a function that fails loudly.

Every report is scrubbed of the password (tests/redaction.py).
"""

from pathlib import Path

import pytest

pytest_plugins = ["tests.redaction", "pytester"]

TESTS_DIR = Path(__file__).parent
TIER_DIRS = {
    "offline": TESTS_DIR / "offline",
    "pub400": TESTS_DIR / "pub400",
    # Only the replay; tests/corpus/store.py and capture.py are tested offline.
    "corpus": TESTS_DIR / "corpus",
}


class OfflineConnectionError(AssertionError):
    """Raised when an offline test tries to open a database connection."""


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        for marker, directory in TIER_DIRS.items():
            if item.path.is_relative_to(directory):
                item.add_marker(marker)


@pytest.fixture(autouse=True)
def _forbid_connections_offline(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    if (
        request.node.get_closest_marker("offline") is None
        and request.node.get_closest_marker("corpus") is None
    ):
        return

    def refuse(*args: object, **kwargs: object) -> None:
        # Never include the arguments: they may contain the connection string.
        raise OfflineConnectionError("offline tests must not open a database connection")

    monkeypatch.setattr("pyodbc.connect", refuse)


# --- Golden files (tests/golden.py) ----------------------------------------------


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("goldens")
    group.addoption(
        "--update-goldens",
        action="store_true",
        help="rewrite golden files from the current SQL (offline tier; never in CI)",
    )
    group.addoption(
        "--update-corpus",
        action="store_true",
        help="rewrite offline query corpus entries from the current SQL (never in CI)",
    )
    group.addoption(
        "--record-verification",
        action="store_true",
        help="mark goldens accepted by IBM i as verified (pub400 tier)",
    )


def pytest_configure(config: pytest.Config) -> None:
    import os

    if config.getoption("--update-goldens") and os.environ.get("CI"):
        raise pytest.UsageError("--update-goldens must not be used in CI")
    if config.getoption("--update-corpus") and os.environ.get("CI"):
        raise pytest.UsageError("--update-corpus must not be used in CI")


def pytest_terminal_summary(terminalreporter, exitstatus, config: pytest.Config) -> None:
    from tests.golden import UNVERIFIED, all_golden_paths, read

    if "corpus" in (config.option.markexpr or ""):
        _corpus_summary(terminalreporter)
        return
    if "offline" not in (config.option.markexpr or ""):
        return
    goldens = [read(path) for path in all_golden_paths()]
    unverified = sorted(
        f"{g.django}/{g.profile}/{g.name}" for g in goldens if g.verified == UNVERIFIED
    )
    terminalreporter.write_sep("-", f"goldens: {len(goldens)}, unverified: {len(unverified)}")
    for name in unverified:
        terminalreporter.write_line(f"  unverified: {name}")


def _corpus_summary(terminalreporter) -> None:
    """Coverage of the corpus, per module: what the capture recorded or skipped
    (manifest) and what the replay could replay."""
    import sys

    from tests.corpus import store

    replay = sys.modules.get("tests.corpus.test_replay")
    coverage = getattr(replay, "COVERAGE", {})
    manifest = store.read_manifest(replay.DIRECTORY) if replay else {}
    captured = manifest.get("modules", {})
    total = sum(c["entries"] for c in coverage.values())
    replayed = sum(c["replayed"] for c in coverage.values())
    terminalreporter.write_sep("-", f"corpus: {replayed} of {total} entries replayed")
    for module, c in sorted(coverage.items()):
        m = captured.get(module, {})
        terminalreporter.write_line(
            f"  {module}: capture {m.get('recorded', '?')} recorded, "
            f"{m.get('unique', '?')} unique, {m.get('unpicklable', 0)} unpicklable, "
            f"{m.get('needs_database', 0)} needs database, "
            f"{m.get('no_sql', 0)} no SQL, {m.get('not_compiled', 0)} not compiled, "
            f"{m.get('volatile', 0)} volatile "
            f"(pickle format {m.get('pickle_format', 1)}); "
            f"replay {c['replayed']}/{c['entries']} replayed, {c['not_loadable']} not loadable, "
            f"{c.get('not_replayable', 0)} not replayable, {c['unverified']} unverified"
        )
