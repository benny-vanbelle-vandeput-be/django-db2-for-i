"""Shared pytest configuration.

Tests are marked with their tier based on their directory (tests/offline/ ->
``offline``, tests/pub400/ -> ``pub400``).

Offline tests must never open a database connection: for them,
``pyodbc.connect`` is replaced with a function that fails loudly.
"""

from pathlib import Path

import pytest

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
