"""Settings for Django's own test suite (runtests.py) against PUB400.

Used by scripts/runtests.sh. Django's test settings must define two databases,
``default`` and ``other`` (docs/internals/contributing/writing-code/
unit-tests.txt); a test class that uses an undefined alias fails with
ImproperlyConfigured instead of being skipped. Both are existing, journaled
PUB400 libraries (TEST['CREATE_DB'] = False, guarded by the marker table).
``other`` only opens a (second) connection when a selected test uses it.

Library names come from the DB2I_* environment variables (.env), never from
this file. DB2I_TEST_MODULES (set by the runner) is recorded in the marker
table, so a --keepdb run for another module set cleans up the old tables.
"""

import os

from django.core.exceptions import ImproperlyConfigured


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if not value:
        raise ImproperlyConfigured(f"{name} is not set (copy .env.example to .env)")
    return value


def database(library_variable: str) -> dict:
    library = env(library_variable)
    return {
        "ENGINE": "django_db2_for_i",
        "NAME": library,
        "HOST": env("DB2I_HOST"),
        "USER": env("DB2I_USER"),
        "PASSWORD": env("DB2I_PASSWORD"),
        "OPTIONS": {"ssl": env("DB2I_SSL", "1") == "1"},
        "TEST": {
            "NAME": library,
            "CREATE_DB": False,
            "MODULE_SET": os.environ.get("DB2I_TEST_MODULES", ""),
        },
    }


DATABASES = {
    "default": database("DB2I_DEFAULT_LIBRARY"),
    "other": database("DB2I_OTHER_LIBRARY"),
}

SECRET_KEY = "django_tests_secret_key"
# Faster password hashing in tests, as in Django's own test settings.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"
