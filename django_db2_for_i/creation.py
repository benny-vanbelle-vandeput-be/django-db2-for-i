"""DatabaseCreation: test database setup and teardown.

Supports a "use existing schema" mode that never runs CREATE/DROP SCHEMA
and cleans up its own tables (needed for PUB400). Implemented in phase 1.

Requirement for that mode: it must not open the extra ``_nodb_cursor()``
connection Django uses for CREATE/DROP DATABASE; it works on the alias's own
single connection (PUB400 limits connections per client).
"""

from django.db.backends.base.creation import BaseDatabaseCreation


class DatabaseCreation(BaseDatabaseCreation):
    pass
