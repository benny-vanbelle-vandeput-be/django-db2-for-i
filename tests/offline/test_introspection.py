"""DatabaseIntrospection on catalog rows (no server needed)."""

import django
import pytest
from django.db import connections, models

from django_db2_for_i import compat, introspection


class CatalogCursor:
    """Answers each catalog query with the rows given for it, and records it."""

    def __init__(self, rows: dict[str, list[tuple]]) -> None:
        self.rows = rows
        self.executed: list[tuple[str, list]] = []
        self._result: list[tuple] = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        self._result = self.rows.get(sql, [])

    def fetchall(self):
        return self._result


def get_constraints(rows: dict[str, list[tuple]]) -> tuple[dict, CatalogCursor]:
    cursor = CatalogCursor(rows)
    result = connections["default"].introspection.get_constraints(cursor, "testapp_book")
    return result, cursor


def test_constraints_of_every_kind() -> None:
    # Catalog values are padded CHAR columns, as Db2 for i returns them.
    constraints, _ = get_constraints(
        {
            introspection.CONSTRAINTS_SQL: [
                ("Q_TESTAPP_BOOK_ID_00001", "PRIMARY KEY", "ID        ", 1),
                ("TESTAPP_BOOK_AUTHOR_ID_FK", "FOREIGN KEY", "AUTHOR_ID", 1),
                ("TESTAPP_BOOK_PAGES_CHECK", "CHECK      ", "PAGES", 0),
                ("TESTAPP_BOOK_UNIQ", "UNIQUE", "TITLE", 1),
                ("TESTAPP_BOOK_UNIQ", "UNIQUE", "AUTHOR_ID", 2),
            ],
            introspection.FOREIGN_KEYS_SQL: [
                ("TESTAPP_BOOK_AUTHOR_ID_FK", "TESTAPP_AUTHOR  ", "ID  "),
            ],
            introspection.INDEXES_SQL: [
                ("TESTAPP_BOOK_IDX", "D", "PUBLISHED", "D"),
                ("TESTAPP_BOOK_IDX", "D", "TITLE", "A"),
                ("TESTAPP_BOOK_UIDX", "U", "ISBN", "A"),
            ],
        }
    )
    assert constraints == {
        "q_testapp_book_id_00001": {
            "columns": ["id"],
            "primary_key": True,
            "unique": True,
            "foreign_key": None,
            "check": False,
            "index": False,
        },
        "testapp_book_author_id_fk": {
            "columns": ["author_id"],
            "primary_key": False,
            "unique": False,
            "foreign_key": ("testapp_author", "id"),
            "check": False,
            "index": False,
        },
        "testapp_book_pages_check": {
            "columns": ["pages"],
            "primary_key": False,
            "unique": False,
            "foreign_key": None,
            "check": True,
            "index": False,
        },
        "testapp_book_uniq": {
            "columns": ["title", "author_id"],
            "primary_key": False,
            "unique": True,
            "foreign_key": None,
            "check": False,
            "index": False,
        },
        "testapp_book_idx": {
            "columns": ["published", "title"],
            "orders": ["DESC", "ASC"],
            "primary_key": False,
            "unique": False,
            "foreign_key": None,
            "check": False,
            "index": True,
            "type": "idx",
        },
        "testapp_book_uidx": {
            "columns": ["isbn"],
            "orders": ["ASC"],
            "primary_key": False,
            "unique": True,
            "foreign_key": None,
            "check": False,
            "index": True,
            "type": "idx",
        },
    }


def test_check_without_columns() -> None:
    # A check that references no column (LEFT JOIN: no SYSCSTCOL row).
    constraints, _ = get_constraints(
        {introspection.CONSTRAINTS_SQL: [("TESTAPP_BOOK_TRUE", "CHECK", None, 0)]}
    )
    assert constraints["testapp_book_true"]["columns"] == []
    assert constraints["testapp_book_true"]["check"] is True


def test_composite_foreign_key_takes_the_first_referenced_column() -> None:
    constraints, _ = get_constraints(
        {
            introspection.CONSTRAINTS_SQL: [
                ("FK", "FOREIGN KEY", "A", 1),
                ("FK", "FOREIGN KEY", "B", 2),
            ],
            introspection.FOREIGN_KEYS_SQL: [("FK", "T", "X"), ("FK", "T", "Y")],
        }
    )
    assert constraints["fk"]["columns"] == ["a", "b"]
    assert constraints["fk"]["foreign_key"] == ("t", "x")


def test_queries_take_the_uppercase_table_name() -> None:
    _, cursor = get_constraints({})
    assert [sql for sql, _ in cursor.executed] == [
        introspection.CONSTRAINTS_SQL,
        introspection.FOREIGN_KEYS_SQL,
        introspection.INDEXES_SQL,
    ]
    assert [params for _, params in cursor.executed] == [
        ["TESTAPP_BOOK", "TESTAPP_BOOK"],
        ["TESTAPP_BOOK"],
        ["TESTAPP_BOOK"],
    ]
    for sql, _ in cursor.executed:
        assert "TABLE_SCHEMA = CURRENT SCHEMA" in sql


def test_relations() -> None:
    cursor = CatalogCursor(
        {
            introspection.RELATIONS_SQL: [
                ("AUTHOR_ID ", "TESTAPP_AUTHOR  ", "ID  ", "NO ACTION  "),
                ("EDITOR_ID", "TESTAPP_AUTHOR", "ID", "SET NULL"),
                ("SHELF_ID", "TESTAPP_SHELF", "ID", "RESTRICT"),
            ]
        }
    )
    relations = connections["default"].introspection.get_relations(cursor, "testapp_book")
    assert cursor.executed == [(introspection.RELATIONS_SQL, ["TESTAPP_BOOK"])]
    assert relations == {
        "author_id": compat.relation("id", "testapp_author", "DO_NOTHING"),
        "editor_id": compat.relation("id", "testapp_author", "DB_SET_NULL"),
        "shelf_id": compat.relation("id", "testapp_shelf", None),
    }


def test_relation_shape_per_django_version(monkeypatch) -> None:
    monkeypatch.setattr(django, "VERSION", (6, 0, 0, "final", 0))
    assert compat.relation("id", "t", "DB_CASCADE") == ("id", "t")
    monkeypatch.setattr(django, "VERSION", (6, 1, 0, "final", 0))
    if not hasattr(models, "DB_CASCADE"):
        pytest.skip("the db_on_delete constants exist from Django 6.1 on")
    assert compat.relation("id", "t", "DB_CASCADE") == ("id", "t", models.DB_CASCADE)
    assert compat.relation("id", "t", None) == ("id", "t", None)


def test_delete_rules_name_django_constants() -> None:
    assert set(introspection.DELETE_RULES.values()) == {
        "DO_NOTHING",
        "DB_CASCADE",
        "DB_SET_NULL",
        "DB_SET_DEFAULT",
    }
