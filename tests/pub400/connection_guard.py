"""Teardown helper: replace a connection the driver marked unusable."""

from django.db import connection


def replace_if_unusable(conn=connection) -> None:
    """Close the connection if the driver marked it unusable (drivers/pyodbc.py), so
    the next statement opens a new one: at most one reconnect per failure, and still
    one connection at a time. Teardowns call it before cleaning up, so no test tables
    are left behind."""
    if conn.connection is not None and not conn.connection.usable:
        conn.close()
