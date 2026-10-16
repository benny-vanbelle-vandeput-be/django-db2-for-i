"""Phase 0 smoke tests: the package imports and the connection guard works."""

import importlib

import pyodbc
import pytest

import django_db2_for_i

BACKEND_MODULES = [
    "base",
    "features",
    "operations",
    "schema",
    "introspection",
    "creation",
    "client",
    "compiler",
    "validation",
    "compat",
    "capabilities",
    "drivers",
    "drivers.base",
    "drivers.pyodbc",
]


def test_package_has_version() -> None:
    assert django_db2_for_i.__version__


@pytest.mark.parametrize("module", BACKEND_MODULES)
def test_backend_module_importable(module: str) -> None:
    importlib.import_module(f"django_db2_for_i.{module}")


def test_offline_guard_refuses_connections() -> None:
    with pytest.raises(AssertionError, match="must not open a database connection"):
        pyodbc.connect("DRIVER={IBM i Access ODBC Driver};SYSTEM=example.invalid")
