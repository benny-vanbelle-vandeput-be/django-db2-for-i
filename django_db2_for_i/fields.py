"""IBM i system names for columns (phase 7, section 6; #253).

Every column on IBM i has, next to its SQL name (up to 128 characters), a
system name of at most 10 characters: the name RPG and CL programs, ``DSPFD`` and
most IBM i tools use. Without one, IBM i derives it (``LONG_COLUMN_NAME`` becomes
something like ``LONG_00001``). A field with this mixin sets it::

    from django.db import models
    from django_db2_for_i.fields import SystemNameMixin, with_system_name

    class CustomerCharField(SystemNameMixin, models.CharField):
        pass

    SystemNameIntegerField = with_system_name(models.IntegerField, __name__)

    class Customer(models.Model):
        delivery_address = CustomerCharField(max_length=100, db_system_name="DLVADDR")

The schema editor writes ``"DELIVERY_ADDRESS" FOR COLUMN DLVADDR NVARCHAR(100)``
(probe ``qtemp_system_names``). It reads ``db_system_name`` from any field that has
it, so a project's own mixin with the same attribute works too. A plain Django
field gets no system name, as before.
"""

from __future__ import annotations

import re
from typing import Any

from django.core.exceptions import ImproperlyConfigured
from django.db import models

# An undelimited system name: a letter first, then letters, digits or _, at most
# 10 in all. #, @ and $ are refused undelimited (SQL0113), a digit first is
# SQL0103, delimited names keep their quotes (probe qtemp_system_names).
SYSTEM_NAME = re.compile(r"[A-Z][A-Z0-9_]{0,9}")


def normalize_system_name(name: str, *, owner: str = "") -> str:
    """The system name in upper case; ImproperlyConfigured if it is not one."""
    normalized = name.strip().upper()
    if not SYSTEM_NAME.fullmatch(normalized):
        where = f" ({owner})" if owner else ""
        raise ImproperlyConfigured(
            f"db_system_name {name!r}{where} is not a valid IBM i system name: at most 10 "
            "characters, letters, digits or _, starting with a letter."
        )
    return normalized


def system_name(field: Any) -> str:
    """The column's system name, or "" when the field sets none."""
    name = getattr(field, "db_system_name", "") or ""
    return normalize_system_name(name, owner=str(field)) if name else ""


class SystemNameMixin(models.Field):
    """Adds ``db_system_name`` (the column's IBM i system name) to a field type,
    kept in migrations through ``deconstruct()``."""

    def __init__(self, *args: Any, db_system_name: str = "", **kwargs: Any) -> None:
        self.db_system_name = normalize_system_name(db_system_name) if db_system_name else ""
        super().__init__(*args, **kwargs)

    def deconstruct(self) -> tuple[str, str, list[Any], dict[str, Any]]:
        name, path, args, kwargs = super().deconstruct()
        if self.db_system_name:
            kwargs["db_system_name"] = self.db_system_name
        return name, path, args, kwargs


def with_system_name(field_class: type[models.Field], module: str) -> type:
    """A field type with ``db_system_name``: ``with_system_name(models.CharField,
    __name__)``, assigned to a module-level name. ``module`` is the module that
    defines that name, so migrations can import the type from it; the class is
    named ``SystemName<Field>``, so assign it to that name, e.g.
    ``SystemNameCharField = with_system_name(models.CharField, __name__)``."""
    return type(
        f"SystemName{field_class.__name__}",
        (SystemNameMixin, field_class),
        {"__module__": module},
    )
