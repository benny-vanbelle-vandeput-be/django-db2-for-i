"""Settings for the offline tier: no IBM i, capabilities from a profile.

The DatabaseWrapper must never connect with these settings; HOST is a
reserved, unresolvable name and the conftest guard refuses connections.
"""

SECRET_KEY = "offline-tests-not-secret"
USE_TZ = True
INSTALLED_APPS = ["tests.testapp"]
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

DATABASES = {
    "default": {
        "ENGINE": "django_db2_for_i",
        "NAME": "DJTEST",
        "HOST": "offline.invalid",
        "USER": "DJUSER",
        "PASSWORD": "offline-not-a-password",
        "OPTIONS": {"capabilities": "7.5"},
    }
}
