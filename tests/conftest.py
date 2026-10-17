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
    if request.node.get_closest_marker("offline") is None:
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
        "--record-verification",
        action="store_true",
        help="mark goldens accepted by IBM i as verified (pub400 tier)",
    )


def pytest_configure(config: pytest.Config) -> None:
    import os

    if config.getoption("--update-goldens") and os.environ.get("CI"):
        raise pytest.UsageError("--update-goldens must not be used in CI")


def pytest_terminal_summary(terminalreporter, exitstatus, config: pytest.Config) -> None:
    from tests.golden import UNVERIFIED, all_golden_paths, read

    if "offline" not in (config.option.markexpr or ""):
        return
    goldens = [read(path) for path in all_golden_paths()]
    unverified = sorted(
        f"{g.django}/{g.profile}/{g.name}" for g in goldens if g.verified == UNVERIFIED
    )
    terminalreporter.write_sep("-", f"goldens: {len(goldens)}, unverified: {len(unverified)}")
    for name in unverified:
        terminalreporter.write_line(f"  unverified: {name}")
