"""The app config: ``"django_db2_for_i"`` in ``INSTALLED_APPS`` (#253, #124).

It adds two ``Meta`` options to the ones Django accepts. ``db_system_name`` gives a
table an IBM i system name; ``db_library`` puts it in another library than the
database's ``NAME``::

    class Customer(models.Model):
        class Meta:
            db_table = "customer_addresses"
            db_system_name = "CUSTADDR"
            db_library = "SALES"

``db_library`` is a clearer spelling of Django's own form of a qualified table
name: when the model class is ready (``class_prepared``), ``db_table`` becomes
``'SALES"."customer_addresses'`` (also Django's default table name), the form the
backend handles (operations.quote_name, schema.py). A ``db_table`` that already
names a library is left alone; the system check E005 refuses the two together.

Django refuses an unknown ``Meta`` option when the model class is created; it
imports every app config before any model, so the position in ``INSTALLED_APPS``
does not matter. Django keeps the list in two places: ``models.options`` (the
models) and ``migrations.state`` (the models that migrations render), and both get
the name, so ``CreateModel`` keeps it. A later change of ``db_system_name`` alone is
not detected by ``makemigrations``: Django's ``AlterModelOptions`` has a fixed list
of options (docs/user/Known-Limitations.md).
"""

from __future__ import annotations

from django.apps import AppConfig
from django.db.migrations import state
from django.db.models import options
from django.db.models.signals import class_prepared

META_OPTIONS = ("db_system_name", "db_library")


def allow_meta_options() -> None:
    for module in (options, state):
        missing = tuple(name for name in META_OPTIONS if name not in module.DEFAULT_NAMES)
        if missing:
            module.DEFAULT_NAMES = (*module.DEFAULT_NAMES, *missing)


allow_meta_options()


def apply_db_library(sender, **kwargs) -> None:
    """``db_table = 'LIB"."<table>'`` for a model with ``Meta.db_library = "LIB"``."""
    meta = sender._meta
    library = getattr(meta, "db_library", "") or ""
    if library and '"."' not in meta.db_table:
        meta.db_table = f'{library.strip().upper()}"."{meta.db_table}'


class_prepared.connect(apply_db_library, dispatch_uid="django_db2_for_i.db_library")


class Db2ForIConfig(AppConfig):
    name = "django_db2_for_i"
    verbose_name = "Db2 for i"
