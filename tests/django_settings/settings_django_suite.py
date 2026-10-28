"""Settings for Django's own test suite (runtests.py) against PUB400.

Used by scripts/django_suite.sh. Django's test settings must define two databases,
``default`` and ``other`` (docs/internals/contributing/writing-code/
unit-tests.txt); a test class that uses an undefined alias fails with
ImproperlyConfigured instead of being skipped. Both are existing, journaled
PUB400 libraries (TEST['CREATE_DB'] = False, guarded by the marker table).
``other`` only opens a (second) connection when a selected test uses it.

Library names come from the DB2I_* environment variables (.env), never from
this file. DB2I_TEST_MODULES (set by the runner) is recorded in the marker
table, so a --keepdb run for another module set cleans up the old tables.

The backend's DEBUG log goes to stderr, so it lands in the runner's log next
to the test that caused it (e.g. deferred identity restarts).
"""

import os

from django.core.exceptions import ImproperlyConfigured

from tests import table_registry


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
# No DEFAULT_AUTO_FIELD: Django's own default per version, as in Django's
# reference test settings (AutoField on 5.2, BigAutoField from 6.0 on).
# As in Django's reference settings (tests/test_sqlite.py): the test suite
# assumes naive datetimes, and runtests.py turns the RuntimeWarning for a
# naive datetime under USE_TZ = True (the default since Django 5.0) into an
# error. Tests that need time zones enable USE_TZ themselves.
USE_TZ = False

# The offline query corpus capture (scripts/run_django_tests.py --capture sets
# DB2I_CORPUS_CAPTURE): Django's runner with a result that records the
# statements of passing tests (tests/corpus/capture.py).
if os.environ.get("DB2I_CORPUS_CAPTURE"):
    TEST_RUNNER = "tests.corpus.capture.CaptureRunner"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"backend": {"format": "[%(name)s] %(levelname)s %(message)s"}},
    "handlers": {"stderr": {"class": "logging.StreamHandler", "formatter": "backend"}},
    "loggers": {"django_db2_for_i": {"handlers": ["stderr"], "level": "DEBUG", "propagate": False}},
}

# Every object a run creates goes on the cleanup list first (bin/ibmi-cleanup,
# tests/table_registry.py; DB2I_TABLE_LIST is set by scripts/pub400.sh).
table_registry.install()
