"""DatabaseClient: ``manage.py dbshell`` support.

Implemented in a later phase.
"""

from django.db.backends.base.client import BaseDatabaseClient


class DatabaseClient(BaseDatabaseClient):
    executable_name = None
