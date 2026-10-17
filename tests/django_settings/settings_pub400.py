"""Settings for the pub400 tier: a shared, restricted IBM i.

Connection settings come from DB2I_* environment variables (compose injects
them from .env). Only the ``default`` alias is configured; ``other`` is added
when a test module needs it (PUB400 limits connections per client, and every
alias opens its own connection).
"""

import os

from django.core.exceptions import ImproperlyConfigured


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if not value:
        raise ImproperlyConfigured(f"{name} is not set (copy .env.example to .env)")
    return value


SECRET_KEY = "pub400-tests-not-secret"
USE_TZ = True
INSTALLED_APPS = ["tests.testapp"]
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

DATABASES = {
    "default": {
        "ENGINE": "django_db2_for_i",
        "NAME": env("DB2I_DEFAULT_LIBRARY"),
        "HOST": env("DB2I_HOST"),
        "USER": env("DB2I_USER"),
        "PASSWORD": env("DB2I_PASSWORD"),
        "OPTIONS": {"ssl": env("DB2I_SSL", "1") == "1"},
    }
}
