"""DatabaseIntrospection: reading tables, columns, constraints from the catalog.

Implemented in phase 1 (minimal: what migrate, flush and test database
creation need); completed in phase 4.

All queries are limited to the connection's ``CURRENT SCHEMA`` (the
database's NAME). Catalog names are uppercase; ``identifier_converter``
returns them in lowercase, Django's form (see operations.quote_name).
"""

from collections import namedtuple

from django.db import DatabaseError
from django.db.backends.base.introspection import BaseDatabaseIntrospection, TableInfo
from django.db.backends.base.introspection import FieldInfo as BaseFieldInfo
from django.db.models import Index

from django_db2_for_i import compat

# QSYS2.SYSKEYS.ORDERING (column text: "A-Ascending, D-Descending", probe 25).
ORDERS = {"A": "ASC", "D": "DESC"}
# QSYS2.SYSINDEXES.IS_UNIQUE: "D" is an index that allows duplicate keys
# (probe lib_constraints); every other value is a unique kind.
DUPLICATES_ALLOWED = "D"

# The constraints of a table with their columns in key order: the key
# columns (SYSKEYCST) for primary, unique and foreign keys, the referenced
# columns (SYSCSTCOL) for checks. Only the constraint name and the table go
# in as parameters.
# A foreign key Db2 for i enforces: SET DATA TYPE on one of its columns
# while it exists leaves it in SYSCST with ENABLED and CHECK_PENDING empty,
# and rows without a parent are then accepted (docs/IBMI_NOTES.md, "Foreign
# keys through the schema editor", fact b). Such a foreign key is not reported
# as one: get_constraints() marks it "enforced": False, get_relations() and
# the foreign_key of get_constraints() leave it out.
ENFORCED_FK = "C.ENABLED = 'YES' AND COALESCE(C.CHECK_PENDING, 'NO') <> 'YES'"
CONSTRAINTS_SQL = (
    "SELECT C.CONSTRAINT_NAME, C.CONSTRAINT_TYPE, K.COLUMN_NAME, K.ORDINAL_POSITION, "
    f"CASE WHEN C.CONSTRAINT_TYPE <> 'FOREIGN KEY' OR ({ENFORCED_FK}) THEN 'Y' ELSE 'N' END "
    "FROM QSYS2.SYSCST C LEFT JOIN QSYS2.SYSKEYCST K "
    "ON K.CONSTRAINT_SCHEMA = C.CONSTRAINT_SCHEMA AND K.CONSTRAINT_NAME = C.CONSTRAINT_NAME "
    "WHERE C.TABLE_SCHEMA = CURRENT SCHEMA AND C.TABLE_NAME = %s "
    "AND C.CONSTRAINT_TYPE IN ('PRIMARY KEY', 'UNIQUE', 'FOREIGN KEY') "
    "UNION ALL "
    "SELECT C.CONSTRAINT_NAME, C.CONSTRAINT_TYPE, S.COLUMN_NAME, 0, 'Y' "
    "FROM QSYS2.SYSCST C LEFT JOIN QSYS2.SYSCSTCOL S "
    "ON S.CONSTRAINT_SCHEMA = C.CONSTRAINT_SCHEMA AND S.CONSTRAINT_NAME = C.CONSTRAINT_NAME "
    "WHERE C.TABLE_SCHEMA = CURRENT SCHEMA AND C.TABLE_NAME = %s "
    "AND C.CONSTRAINT_TYPE = 'CHECK' "
    "ORDER BY 1, 4, 3"
)
# For each foreign key of a table: the referenced table and the first column of
# the referenced key (Django's ``foreign_key`` is one (table, column) pair).
FOREIGN_KEYS_SQL = (
    "SELECT C.CONSTRAINT_NAME, P.TABLE_NAME, PK.COLUMN_NAME "
    "FROM QSYS2.SYSCST C "
    "JOIN QSYS2.SYSREFCST R "
    "ON R.CONSTRAINT_SCHEMA = C.CONSTRAINT_SCHEMA AND R.CONSTRAINT_NAME = C.CONSTRAINT_NAME "
    "JOIN QSYS2.SYSCST P "
    "ON P.CONSTRAINT_SCHEMA = R.UNIQUE_CONSTRAINT_SCHEMA "
    "AND P.CONSTRAINT_NAME = R.UNIQUE_CONSTRAINT_NAME "
    "JOIN QSYS2.SYSKEYCST PK "
    "ON PK.CONSTRAINT_SCHEMA = P.CONSTRAINT_SCHEMA AND PK.CONSTRAINT_NAME = P.CONSTRAINT_NAME "
    "WHERE C.TABLE_SCHEMA = CURRENT SCHEMA AND C.TABLE_NAME = %s "
    f"AND C.CONSTRAINT_TYPE = 'FOREIGN KEY' AND {ENFORCED_FK} "
    "ORDER BY C.CONSTRAINT_NAME, PK.ORDINAL_POSITION"
)
# Each foreign key column of a table with the referenced table, the referenced
# column at the same key position, and the delete rule.
RELATIONS_SQL = (
    "SELECT K.COLUMN_NAME, P.TABLE_NAME, PK.COLUMN_NAME, R.DELETE_RULE "
    "FROM QSYS2.SYSCST C "
    "JOIN QSYS2.SYSREFCST R "
    "ON R.CONSTRAINT_SCHEMA = C.CONSTRAINT_SCHEMA AND R.CONSTRAINT_NAME = C.CONSTRAINT_NAME "
    "JOIN QSYS2.SYSKEYCST K "
    "ON K.CONSTRAINT_SCHEMA = C.CONSTRAINT_SCHEMA AND K.CONSTRAINT_NAME = C.CONSTRAINT_NAME "
    "JOIN QSYS2.SYSCST P "
    "ON P.CONSTRAINT_SCHEMA = R.UNIQUE_CONSTRAINT_SCHEMA "
    "AND P.CONSTRAINT_NAME = R.UNIQUE_CONSTRAINT_NAME "
    "JOIN QSYS2.SYSKEYCST PK "
    "ON PK.CONSTRAINT_SCHEMA = P.CONSTRAINT_SCHEMA AND PK.CONSTRAINT_NAME = P.CONSTRAINT_NAME "
    "AND PK.ORDINAL_POSITION = K.ORDINAL_POSITION "
    "WHERE C.TABLE_SCHEMA = CURRENT SCHEMA AND C.TABLE_NAME = %s "
    f"AND C.CONSTRAINT_TYPE = 'FOREIGN KEY' AND {ENFORCED_FK} "
    "ORDER BY C.CONSTRAINT_NAME, K.ORDINAL_POSITION"
)
# The SQL indexes of a table with their key columns in order. The access
# paths that constraints use are not listed in SYSINDEXES (probe lib_constraints), so a
# constraint does not show up twice.
INDEXES_SQL = (
    "SELECT I.INDEX_NAME, I.IS_UNIQUE, K.COLUMN_NAME, K.ORDERING "
    "FROM QSYS2.SYSINDEXES I JOIN QSYS2.SYSKEYS K "
    "ON K.INDEX_SCHEMA = I.INDEX_SCHEMA AND K.INDEX_NAME = I.INDEX_NAME "
    "WHERE I.TABLE_SCHEMA = CURRENT SCHEMA AND I.TABLE_NAME = %s "
    "ORDER BY I.INDEX_NAME, K.ORDINAL_POSITION"
)

# get_table_description() rows: Django's fields plus whether the column is an
# identity (get_field_type() turns it into an AutoField), as on PostgreSQL.
FieldInfo = namedtuple("FieldInfo", [*BaseFieldInfo._fields, "is_autofield"])

# QSYS2.SYSTABLES.TABLE_TYPE -> Django's TableInfo type.
TABLE_TYPES = {
    "T": "t",  # table
    "P": "t",  # physical file
    "V": "v",  # view
}


class DatabaseIntrospection(BaseDatabaseIntrospection):
    # QSYS2.SYSCOLUMNS.DATA_TYPE -> Django field, for every type the backend
    # writes (probe w14, IBMI_NOTES "Column types in the catalog").
    data_types_reverse = {
        "BIGINT": "BigIntegerField",
        "BLOB": "BinaryField",
        "BOOLEAN": "BooleanField",
        "CHAR": "CharField",
        "DATE": "DateField",
        "DBCLOB": "TextField",  # NCLOB
        "DECIMAL": "DecimalField",
        "FLOAT": "FloatField",  # DOUBLE
        "INTEGER": "IntegerField",
        "SMALLINT": "SmallIntegerField",
        "TIME": "TimeField",
        "TIMESTMP": "DateTimeField",
        "VARCHAR": "CharField",
        "VARG": "CharField",  # NVARCHAR
        # Types the backend does not write, common in existing IBM i tables
        # (inspectdb, tests/pub400/test_inspectdb.py).
        "CLOB": "TextField",
        "NUMERIC": "DecimalField",
    }
    # An identity column of each integer type.
    AUTO_FIELDS = {
        "IntegerField": "AutoField",
        "BigIntegerField": "BigAutoField",
        "SmallIntegerField": "SmallAutoField",
    }

    def get_field_type(self, data_type: str, description) -> str:
        field_type = super().get_field_type(data_type, description)
        if description.is_autofield:
            return self.AUTO_FIELDS.get(field_type, field_type)
        return field_type

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
        """Columns in table order.

        ``display_size`` is the length in characters of a character or LOB
        column (inspectdb's ``max_length``), ``internal_size`` the catalog's
        ``LENGTH``. ``default`` is ``COLUMN_DEFAULT`` as Db2 for i records it
        (``42``, ``'abc'``, ``CURRENT_TIMESTAMP``, ``NULL`` for an explicit
        ``DEFAULT NULL``); ``None`` without a default clause. A table that does
        not exist raises DatabaseError (the catalog has no rows for it), as
        Django's schema tests expect (e.g. the old through table of a renamed
        ManyToManyField).
        """
        cursor.execute(
            "SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, LENGTH, "
            "NUMERIC_PRECISION, NUMERIC_SCALE, IS_NULLABLE, COLUMN_DEFAULT, IS_IDENTITY "
            "FROM QSYS2.SYSCOLUMNS "
            "WHERE TABLE_SCHEMA = CURRENT SCHEMA AND TABLE_NAME = %s "
            "ORDER BY ORDINAL_POSITION",
            [table_name.upper()],
        )
        rows = cursor.fetchall()
        if not rows:
            raise DatabaseError(f"Table {table_name} does not exist in the current schema.")
        return [
            FieldInfo(
                name=self.identifier_converter(name.rstrip()),
                type_code=data_type.rstrip(),
                display_size=characters,
                internal_size=length,
                precision=precision,
                scale=scale,
                null_ok=nullable.rstrip() == "Y",
                default=default,
                collation=None,
                is_autofield=identity.rstrip() == "YES",
            )
            for (
                name,
                data_type,
                characters,
                length,
                precision,
                scale,
                nullable,
                default,
                identity,
            ) in rows
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

    def get_relations(self, cursor, table_name: str) -> dict[str, tuple]:
        """{column: (referenced column, referenced table[, db_on_delete])}; the
        tuple's shape follows the Django version (compat.relation). The delete
        rule (SYSREFCST.DELETE_RULE) maps with Django 6.1's on_delete_types,
        whose keys are Db2's values. Only NO ACTION occurs on PUB400 (probe
        lib_constraints; the backend writes no ON DELETE); the other rules are
        IBM's documented values, checked when phase 6 switches on
        supports_on_delete_db_*."""
        cursor.execute(RELATIONS_SQL, [table_name.upper()])
        return {
            self.identifier_converter(column.rstrip()): compat.relation(
                self.identifier_converter(target_column.rstrip()),
                self.identifier_converter(target_table.rstrip()),
                rule.rstrip(),
            )
            for column, target_table, target_column, rule in cursor.fetchall()
        }

    def get_constraints(self, cursor, table_name: str) -> dict[str, dict]:
        """Primary keys, unique, foreign key and check constraints, and indexes."""
        table = table_name.upper()
        constraints: dict[str, dict] = {}
        cursor.execute(CONSTRAINTS_SQL, [table, table])
        for name, kind, column, _position, enforced in cursor.fetchall():
            kind = kind.rstrip()
            entry = constraints.setdefault(
                self.identifier_converter(name.rstrip()),
                {
                    "columns": [],
                    "primary_key": kind == "PRIMARY KEY",
                    "unique": kind in ("PRIMARY KEY", "UNIQUE"),
                    "foreign_key": None,
                    "check": kind == "CHECK",
                    "index": False,
                },
            )
            if column is not None:
                entry["columns"].append(self.identifier_converter(column.rstrip()))
            if enforced.rstrip() != "Y":
                entry["enforced"] = False  # a foreign key Db2 for i no longer enforces
        cursor.execute(FOREIGN_KEYS_SQL, [table])
        for name, target_table, target_column in cursor.fetchall():
            entry = constraints.get(self.identifier_converter(name.rstrip()))
            if entry is not None and entry["foreign_key"] is None:
                entry["foreign_key"] = (
                    self.identifier_converter(target_table.rstrip()),
                    self.identifier_converter(target_column.rstrip()),
                )
        cursor.execute(INDEXES_SQL, [table])
        for name, unique, column, ordering in cursor.fetchall():
            entry = constraints.setdefault(
                self.identifier_converter(name.rstrip()),
                {
                    "columns": [],
                    "orders": [],
                    "primary_key": False,
                    "unique": unique.rstrip() != DUPLICATES_ALLOWED,
                    "foreign_key": None,
                    "check": False,
                    "index": True,
                    "type": Index.suffix,
                },
            )
            entry["columns"].append(self.identifier_converter(column.rstrip()))
            entry["orders"].append(ORDERS.get(ordering.rstrip(), "ASC"))
        return constraints
