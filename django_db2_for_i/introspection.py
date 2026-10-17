"""DatabaseIntrospection: reading tables, columns, constraints from the catalog.

Implemented in phase 1 (minimal: what migrate, flush and test database
creation need); completed in phase 4.

All queries are limited to the connection's ``CURRENT SCHEMA`` (the
database's NAME). Catalog names are uppercase; ``identifier_converter``
returns them in lowercase, Django's form (see operations.quote_name).
"""

from django.db.backends.base.introspection import BaseDatabaseIntrospection, FieldInfo, TableInfo

# QSYS2.SYSTABLES.TABLE_TYPE -> Django's TableInfo type.
TABLE_TYPES = {
    "T": "t",  # table
    "P": "t",  # physical file
    "V": "v",  # view
}


class DatabaseIntrospection(BaseDatabaseIntrospection):
    def identifier_converter(self, name: str) -> str:
        """Catalog names are uppercase (see quote_name); Django's are lowercase."""
        return name.lower()

    def get_table_list(self, cursor) -> list[TableInfo]:
        types = ", ".join(f"'{code}'" for code in TABLE_TYPES)
        # SYSTEM_TABLE = 'N': leave out the SQL catalog views (SYSCST, ...)
        # that Db2 for i creates in a library with constraints.
        cursor.execute(
            "SELECT TABLE_NAME, TABLE_TYPE FROM QSYS2.SYSTABLES "
            f"WHERE TABLE_SCHEMA = CURRENT SCHEMA AND TABLE_TYPE IN ({types}) "
            "AND SYSTEM_TABLE = 'N' ORDER BY TABLE_NAME"
        )
        return [
            TableInfo(self.identifier_converter(name.rstrip()), TABLE_TYPES[kind.rstrip()])
            for name, kind in cursor.fetchall()
        ]

    def get_table_description(self, cursor, table_name: str) -> list[FieldInfo]:
        """Columns in table order. Completed in phase 4 (types, defaults)."""
        cursor.execute(
            "SELECT COLUMN_NAME, DATA_TYPE, LENGTH, NUMERIC_PRECISION, NUMERIC_SCALE, "
            "IS_NULLABLE, COLUMN_DEFAULT FROM QSYS2.SYSCOLUMNS "
            "WHERE TABLE_SCHEMA = CURRENT SCHEMA AND TABLE_NAME = %s "
            "ORDER BY ORDINAL_POSITION",
            [table_name.upper()],
        )
        return [
            FieldInfo(
                name=self.identifier_converter(name.rstrip()),
                type_code=data_type.rstrip(),
                display_size=None,
                internal_size=length,
                precision=precision,
                scale=scale,
                null_ok=nullable.rstrip() == "Y",
                default=default,
                collation=None,
            )
            for name, data_type, length, precision, scale, nullable, default in cursor.fetchall()
        ]

    def get_sequences(self, cursor, table_name: str, table_fields=()) -> list[dict]:
        """Identity columns of ``table_name``."""
        cursor.execute(
            "SELECT COLUMN_NAME FROM QSYS2.SYSCOLUMNS "
            "WHERE TABLE_SCHEMA = CURRENT SCHEMA AND TABLE_NAME = %s AND IS_IDENTITY = 'YES'",
            [table_name.upper()],
        )
        return [
            {"table": table_name, "column": self.identifier_converter(column.rstrip())}
            for (column,) in cursor.fetchall()
        ]
