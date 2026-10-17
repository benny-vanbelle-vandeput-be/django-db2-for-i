"""DatabaseIntrospection: reading tables, columns, constraints from the catalog.

Implemented in phase 1 (minimal); completed in phase 4.
"""

from django.db.backends.base.introspection import BaseDatabaseIntrospection


class DatabaseIntrospection(BaseDatabaseIntrospection):
    def identifier_converter(self, name: str) -> str:
        """Catalog names are uppercase (see quote_name); Django's are lowercase."""
        return name.lower()
