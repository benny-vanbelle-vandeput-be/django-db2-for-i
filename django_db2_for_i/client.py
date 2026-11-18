"""DatabaseClient: ``manage.py dbshell`` is not available.

The backend does not start a command-line SQL client. ``runshell()`` says so
with a clear message, instead of Django's generic ``NotImplementedError``
(docs/user/Known-Limitations.md).
"""

from django.core.management.base import CommandError
from django.db.backends.base.client import BaseDatabaseClient

MESSAGE = (
    "dbshell is not available for Db2 for i: the backend starts no command-line "
    "SQL client. Use IBM i Access Client Solutions (Run SQL Scripts) or "
    "manage.py shell with django.db.connection.cursor()."
)


class DatabaseClient(BaseDatabaseClient):
    executable_name = None

    def runshell(self, parameters):
        raise CommandError(MESSAGE)
