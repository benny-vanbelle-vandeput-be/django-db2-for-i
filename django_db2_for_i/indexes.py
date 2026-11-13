"""An index with an IBM i system name (#253).

An index is a ``*FILE`` object on IBM i, with a system name of at most 10
characters next to its SQL name. Django names most indexes itself
(``<table>_<column>_<hash>``, longer than 10 characters), and IBM i then makes up
the system name. An index declared in ``Meta.indexes`` can set it::

    from django_db2_for_i.indexes import SystemNameIndex

    class Customer(models.Model):
        city = models.CharField(max_length=50)

        class Meta:
            indexes = [SystemNameIndex(fields=["city"], name="customer_city_idx",
                                       db_system_name="CUSTCITY")]

The schema editor writes ``CREATE INDEX "CUSTOMER_CITY_IDX" FOR SYSTEM NAME CUSTCITY
ON ...`` (probe ``qtemp_system_names``). It reads ``db_system_name`` from any index
that has it, so a project's own ``Index`` subclass with that attribute works too.
"""

from __future__ import annotations

from typing import Any

from django.db.models import Index

from .fields import normalize_system_name


class SystemNameIndex(Index):
    """``Index`` with ``db_system_name``, kept in migrations by ``deconstruct()``."""

    def __init__(self, *args: Any, db_system_name: str = "", **kwargs: Any) -> None:
        self.db_system_name = normalize_system_name(db_system_name) if db_system_name else ""
        super().__init__(*args, **kwargs)

    def deconstruct(self) -> tuple[str, tuple[Any, ...], dict[str, Any]]:
        path, args, kwargs = super().deconstruct()
        if self.db_system_name:
            kwargs["db_system_name"] = self.db_system_name
        return path, args, kwargs
