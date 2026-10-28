"""Settings for replaying the offline query corpus (nox -s replay; no IBM i).

The same settings as Django's test runs on PUB400 (settings_django_suite.py:
USE_TZ = False, Django's default TIME_ZONE, AutoField) with the offline
capability profile and no connection. Django's test suite at the corpus's
commit is put on sys.path (DB2I_DJANGO_TESTS) and the corpus modules' apps are
installed (DB2I_CORPUS_MODULES, comma-separated), as runtests.py installs them,
so the pickled queries can be loaded. Entries recorded under other
USE_TZ / TIME_ZONE values are replayed with those (tests/corpus/test_replay.py).
"""

import os
import sys

_tests = os.environ.get("DB2I_DJANGO_TESTS")
if _tests and _tests not in sys.path:
    sys.path.insert(0, _tests)


def _database(name: str) -> dict:
    return {
        "ENGINE": "django_db2_for_i",
        "NAME": name,
        "HOST": "offline.invalid",
        "USER": "DJUSER",
        "PASSWORD": "offline-not-a-password",
        "OPTIONS": {"capabilities": "7.5"},
        "TEST": {"NAME": name, "CREATE_DB": False},
    }


DATABASES = {"default": _database("DJTEST"), "other": _database("DJTESTOTH")}

# runtests.py's ALWAYS_INSTALLED_APPS, then the corpus modules (as runtests.py adds them).
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sites",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.admin.apps.SimpleAdminConfig",
    "django.contrib.staticfiles",
    *[module for module in os.environ.get("DB2I_CORPUS_MODULES", "").split(",") if module],
]

SECRET_KEY = "django_tests_secret_key"
# No DEFAULT_AUTO_FIELD: Django's own default per version, as in Django's
# reference test settings (AutoField on 5.2, BigAutoField from 6.0 on).
USE_TZ = False
SITE_ID = 1
