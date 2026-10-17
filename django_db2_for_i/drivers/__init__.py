"""Driver axis: how the backend talks to the server.

Driver modules know nothing about Django. ``get_driver(name)`` returns a
driver instance by its ``OPTIONS["driver"]`` name.
"""

from __future__ import annotations

import importlib

from .base import Driver

# Driver name -> "module:class", imported on demand.
DRIVERS = {
    "pyodbc": "django_db2_for_i.drivers.pyodbc:Driver",
}


def get_driver(name: str) -> Driver:
    try:
        path = DRIVERS[name]
    except KeyError:
        raise ValueError(f"unknown driver {name!r}; known: {', '.join(sorted(DRIVERS))}") from None
    module, _, cls = path.partition(":")
    return getattr(importlib.import_module(module), cls)()
