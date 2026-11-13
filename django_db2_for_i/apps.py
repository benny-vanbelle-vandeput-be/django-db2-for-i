"""The app config: ``"django_db2_for_i"`` in ``INSTALLED_APPS`` (#253).

It only adds ``db_system_name`` to the ``Meta`` options Django accepts, so a model
can give its table an IBM i system name::

    class Customer(models.Model):
        class Meta:
            db_table = "customer_addresses"
            db_system_name = "CUSTADDR"

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

META_OPTIONS = ("db_system_name",)


def allow_meta_options() -> None:
    for module in (options, state):
        missing = tuple(name for name in META_OPTIONS if name not in module.DEFAULT_NAMES)
        if missing:
            module.DEFAULT_NAMES = (*module.DEFAULT_NAMES, *missing)


allow_meta_options()


class Db2ForIConfig(AppConfig):
    name = "django_db2_for_i"
    verbose_name = "Db2 for i"
