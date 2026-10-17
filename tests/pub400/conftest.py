"""pub400 tier: one connection per run, closed at the end of the session."""

import pytest
from django.db import connections


@pytest.fixture(scope="session", autouse=True)
def _close_connections_at_end(django_db_blocker):
    yield
    with django_db_blocker.unblock():
        connections.close_all()
