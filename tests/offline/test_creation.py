"""Test database creation in an existing library (no server needed)."""

import datetime as dt

import django.db
import pytest
from django.core.exceptions import ImproperlyConfigured
from django.db import NotSupportedError, connections

from django_db2_for_i.base import DatabaseWrapper
from django_db2_for_i.creation import (
    MARKER_TABLE,
    Marker,
    TestDatabaseRefused,
    drop_order,
    marker_statements,
    normalize_module_set,
    plan_setup,
    tables_to_drop,
)
from django_db2_for_i.drivers import base as Database

LIB = "DJTEST"
ALLOWED = {"TESTAPP_AUTHOR", "TESTAPP_BOOK", "DJANGO_MIGRATIONS"}


def never_confirm(remnants):
    raise AssertionError("must not ask")


def plan(
    inventory,
    marker=None,
    *,
    keepdb=False,
    autoclobber=False,
    confirm=never_confirm,
    module_set=None,
):
    return plan_setup(
        LIB,
        inventory,
        ALLOWED,
        marker,
        keepdb=keepdb,
        autoclobber=autoclobber,
        confirm=confirm,
        module_set=module_set,
    )


MARKED = {MARKER_TABLE: "T"}
HEADER_INSERT = (
    f'INSERT INTO "DJTEST"."{MARKER_TABLE}" (RUN_ID, CREATED_AT, MODULE_SET) VALUES (%s, %s, %s)'
)
EMPTY_MARKER = Marker("a" * 32, dt.datetime(2026, 10, 17), frozenset())


# --- plan_setup --------------------------------------------------------------------


def test_empty_library_without_marker_is_fine() -> None:
    result = plan({})
    assert result.drop == ()
    assert result.snapshot == frozenset()


@pytest.mark.parametrize("autoclobber", [False, True])
def test_foreign_objects_are_refused(autoclobber: bool) -> None:
    inventory = {"TESTAPP_AUTHOR": "T", "ORDERS": "T", "ORDERS_V": "V"}
    with pytest.raises(TestDatabaseRefused, match="ORDERS, ORDERS_V") as info:
        plan(inventory, autoclobber=autoclobber)
    assert "Nothing was changed" in str(info.value)


@pytest.mark.parametrize(("keepdb", "autoclobber"), [(False, False), (False, True), (True, True)])
def test_model_tables_without_marker_are_always_refused(keepdb: bool, autoclobber: bool) -> None:
    # A production library with only Django tables must never be touched.
    with pytest.raises(TestDatabaseRefused, match="may be a production library") as info:
        plan(
            {"TESTAPP_AUTHOR": "T", "DJANGO_MIGRATIONS": "T"},
            keepdb=keepdb,
            autoclobber=autoclobber,
        )
    assert "also not with --noinput" in str(info.value)


def test_marker_without_remnants() -> None:
    result = plan(MARKED, EMPTY_MARKER)
    assert result.drop == ()
    assert result.snapshot == frozenset()


def test_marker_remnants_with_keepdb_are_reused() -> None:
    inventory = MARKED | {"TESTAPP_AUTHOR": "T", "DJANGO_MIGRATIONS": "T"}
    assert plan(inventory, EMPTY_MARKER, keepdb=True).drop == ()


def test_marker_remnants_with_autoclobber_are_dropped() -> None:
    marker = Marker("a" * 32, None, frozenset({"KEEP_ME"}))
    inventory = MARKED | {"TESTAPP_AUTHOR": "T", "SCHEMA_DYNAMIC": "T", "KEEP_ME": "T"}
    result = plan(inventory, marker, autoclobber=True)
    # Remnants include tables of dynamic test models; the snapshot stays.
    assert result.drop == ("SCHEMA_DYNAMIC", "TESTAPP_AUTHOR")
    assert result.snapshot == frozenset({"KEEP_ME"})


@pytest.mark.parametrize(("answer", "dropped"), [(True, True), (False, False)])
def test_marker_remnants_ask_for_confirmation(answer: bool, dropped: bool) -> None:
    asked = []

    def confirm(remnants):
        asked.append(remnants)
        return answer

    inventory = MARKED | {"TESTAPP_AUTHOR": "T"}
    if dropped:
        assert plan(inventory, EMPTY_MARKER, confirm=confirm).drop == ("TESTAPP_AUTHOR",)
    else:
        with pytest.raises(TestDatabaseRefused, match="cancelled"):
            plan(inventory, EMPTY_MARKER, confirm=confirm)
    assert asked == [["TESTAPP_AUTHOR"]]


def test_tables_to_drop_keeps_snapshot_and_marker() -> None:
    inventory = MARKED | {"A": "T", "B": "V", "KEEP": "T"}
    assert tables_to_drop(inventory, {"KEEP"}) == ["A", "B"]


def test_drop_order_views_aliases_then_children_first() -> None:
    inventory = {"PARENT": "T", "CHILD": "T", "GRANDCHILD": "T", "V1": "V", "AL": "A"}
    references = {("CHILD", "PARENT"), ("GRANDCHILD", "CHILD")}
    assert drop_order(inventory, inventory, references) == [
        ("VIEW", "V1"),
        ("ALIAS", "AL"),
        ("TABLE", "GRANDCHILD"),
        ("TABLE", "CHILD"),
        ("TABLE", "PARENT"),
    ]


def test_marker_statements() -> None:
    now = dt.datetime(2026, 10, 17, 12, 0)
    statements = marker_statements(LIB, "r" * 32, now, {"KEEP"}, "basic", create=True)
    sql = [s for s, _ in statements]
    assert sql[0].startswith(f'CREATE TABLE "DJTEST"."{MARKER_TABLE}" (RUN_ID CHAR(32) NOT NULL')
    assert "MODULE_SET NVARCHAR(1000)" in sql[0]
    assert statements[1] == (
        HEADER_INSERT,
        ["r" * 32, now, "basic"],
    )
    assert statements[2][1] == ["r" * 32, now, "KEEP"]
    rewrite = [s for s, _ in marker_statements(LIB, "r" * 32, now, (), create=False)]
    assert rewrite == [f'DELETE FROM "DJTEST"."{MARKER_TABLE}"', sql[1]]


def test_marker_statements_recreate_a_legacy_marker() -> None:
    now = dt.datetime(2026, 10, 17, 12, 0)
    sql = [
        s
        for s, _ in marker_statements(LIB, "r" * 32, now, (), "basic", create=False, recreate=True)
    ]
    assert sql[0] == f'DROP TABLE "DJTEST"."{MARKER_TABLE}"'
    assert sql[1].startswith(f'CREATE TABLE "DJTEST"."{MARKER_TABLE}"')
    assert len(sql) == 3


@pytest.mark.parametrize(
    ("value", "normalized"),
    [
        (None, None),
        ("", None),
        ("basic", "basic"),
        ("transactions, basic", "basic,transactions"),
        (["transactions", "basic", "basic"], "basic,transactions"),
        (" , ", None),
    ],
)
def test_normalize_module_set(value, normalized) -> None:
    assert normalize_module_set(value) == normalized


# --- keepdb and the module set ---------------------------------------------------


def marker_for(module_set):
    return Marker("a" * 32, None, frozenset(), module_set)


INVENTORY = MARKED | {"TESTAPP_AUTHOR": "T"}


@pytest.mark.parametrize("module_set", ["basic", None])
def test_keepdb_reuses_tables_of_the_same_module_set(module_set) -> None:
    result = plan(INVENTORY, marker_for("basic"), keepdb=True, module_set=module_set)
    assert result.drop == () and not result.module_set_changed


@pytest.mark.parametrize("old", ["transactions", None])
def test_keepdb_drops_tables_of_another_module_set_without_asking(old) -> None:
    result = plan(INVENTORY, marker_for(old), keepdb=True, module_set="basic")
    assert result.drop == ("TESTAPP_AUTHOR",)
    assert result.module_set_changed


def test_module_set_change_never_bypasses_the_marker_gate() -> None:
    with pytest.raises(TestDatabaseRefused, match="may be a production library"):
        plan({"TESTAPP_AUTHOR": "T"}, None, keepdb=True, module_set="basic")


# --- Settings ----------------------------------------------------------------------


def make_wrapper(test: dict, name: str = "APPLIB") -> DatabaseWrapper:
    settings_dict = dict(connections["default"].settings_dict)
    settings_dict["OPTIONS"] = dict(settings_dict["OPTIONS"])
    settings_dict["NAME"] = name
    settings_dict["TEST"] = {**settings_dict["TEST"], **test}
    return DatabaseWrapper(settings_dict, alias="offline_test")


def test_creating_schemas_is_not_supported() -> None:
    with pytest.raises(NotSupportedError, match="CREATE_DB': False"):
        make_wrapper({"NAME": LIB}).creation._get_test_db_name()


@pytest.mark.parametrize("name", [None, "", "TOOLONGNAME1", "BAD-NAME", "1ABC"])
def test_test_name_must_be_a_library_name(name) -> None:
    with pytest.raises(ImproperlyConfigured, match="system name of an existing library"):
        make_wrapper({"NAME": name, "CREATE_DB": False}).creation._get_test_db_name()


def test_test_name_is_uppercased() -> None:
    creation = make_wrapper({"NAME": "djtest", "CREATE_DB": False}).creation
    assert creation._get_test_db_name() == "DJTEST"


def test_nodb_cursor_is_never_opened() -> None:
    with pytest.raises(NotSupportedError, match="no connection without a database"):
        make_wrapper({"NAME": LIB, "CREATE_DB": False})._nodb_cursor()


# --- Setup and teardown flows with a fake catalog ----------------------------------------


class FakeCatalog:
    """Answers the creation's catalog queries and records every statement."""

    def __init__(
        self, inventory, marker_rows=(), *, library=True, journal="*ACTIVE", fail=(), legacy=False
    ):
        self.legacy = legacy  # marker table without the MODULE_SET column
        self.inventory = dict(inventory)
        self.marker_rows = list(marker_rows)
        self.library = library
        self.journal = journal
        self.fail = dict(fail)  # object name -> sqlcode raised by its DROP
        self.executed: list[tuple[str, list]] = []
        self._rows: list[tuple] = []

    # cursor protocol
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, list(params or [])))
        if self.legacy and "MODULE_SET FROM" in sql:
            error = Database.DatabaseError("column not found", sqlcode=-206)
            raise django.db.DatabaseError("column not found") from error
        if sql.startswith("DROP "):
            name = sql.rsplit(".", 1)[1].strip('"')
            if name in self.fail:
                error = Database.DatabaseError("failed", sqlcode=self.fail[name])
                raise django.db.DatabaseError("failed") from error
            self.inventory.pop(name, None)
        self._rows = self._answer(sql)

    def _answer(self, sql):
        if "QSYS2.SYSSCHEMAS" in sql:
            return [(1,)] if self.library else []
        if "QSYS2.JOURNAL_INFO" in sql:
            return [(self.journal,)] if self.journal else []
        if "QSYS2.SYSTABLES" in sql:
            return [(name, kind) for name, kind in self.inventory.items()]
        if "QSYS2.SYSREFCST" in sql:
            return []
        if sql.startswith("SELECT RUN_ID"):
            return [tuple(row) + (None,) * (4 - len(row)) for row in self.marker_rows]
        return []

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    @property
    def statements(self):
        return [sql for sql, _ in self.executed if not sql.startswith("SELECT")]


@pytest.fixture
def setup_with(monkeypatch):
    def make(catalog, test_name=LIB, name="APPLIB"):
        wrapper = make_wrapper({"NAME": test_name, "CREATE_DB": False}, name=name)
        monkeypatch.setattr(wrapper, "cursor", lambda: catalog)
        monkeypatch.setattr(
            wrapper.creation, "_allowed_tables", lambda: {"TESTAPP_AUTHOR", "DJANGO_MIGRATIONS"}
        )
        return wrapper.creation

    return make


def test_setup_on_empty_library_creates_marker(setup_with) -> None:
    catalog = FakeCatalog({})
    assert setup_with(catalog)._create_test_db(0, autoclobber=False) == LIB
    assert catalog.statements[0].startswith(f'CREATE TABLE "DJTEST"."{MARKER_TABLE}"')
    assert catalog.statements[1:] == [HEADER_INSERT]


def test_setup_with_marker_drops_remnants_and_rewrites_marker(setup_with) -> None:
    catalog = FakeCatalog(
        {MARKER_TABLE: "T", "TESTAPP_AUTHOR": "T", "OLD_VIEW": "V"},
        marker_rows=[("o" * 32, None, None)],
    )
    setup_with(catalog)._create_test_db(0, autoclobber=True)
    assert catalog.statements == [
        'DROP VIEW "DJTEST"."OLD_VIEW"',
        'DROP TABLE "DJTEST"."TESTAPP_AUTHOR"',
        f'DELETE FROM "DJTEST"."{MARKER_TABLE}"',
        HEADER_INSERT,
    ]
    new_run_id = catalog.executed[-1][1][0]
    assert new_run_id != "o" * 32 and len(new_run_id) == 32


def test_setup_refuses_production_like_library_and_changes_nothing(setup_with) -> None:
    catalog = FakeCatalog({"TESTAPP_AUTHOR": "T", "DJANGO_MIGRATIONS": "T"})
    with pytest.raises(TestDatabaseRefused, match="production library"):
        setup_with(catalog)._create_test_db(0, autoclobber=True)
    assert catalog.statements == []


@pytest.mark.parametrize(
    ("catalog", "message"),
    [
        (FakeCatalog({}, library=False), "does not exist"),
        (FakeCatalog({}, journal=None), "(?s)no QSQJRN journal.*CRTJRN JRN\\(DJTEST/QSQJRN\\)"),
        (FakeCatalog({}, journal="*INACTIVE"), "not active"),
    ],
)
def test_setup_checks_library_and_journal(setup_with, catalog, message: str) -> None:
    with pytest.raises(TestDatabaseRefused, match=message):
        setup_with(catalog)._create_test_db(0, autoclobber=True)
    assert catalog.statements == []


def test_setup_warns_when_test_name_equals_name(setup_with, caplog) -> None:
    with caplog.at_level("WARNING", logger="django_db2_for_i"):
        setup_with(FakeCatalog({}), name=LIB)._create_test_db(0, autoclobber=False)
    assert "TEST['NAME'] equals NAME (DJTEST)" in caplog.text


def test_setup_does_not_warn_for_a_separate_library(setup_with, caplog) -> None:
    with caplog.at_level("WARNING", logger="django_db2_for_i"):
        setup_with(FakeCatalog({}))._create_test_db(0, autoclobber=False)
    assert caplog.text == ""


def test_destroy_drops_run_tables_then_marker(setup_with) -> None:
    catalog = FakeCatalog(
        {MARKER_TABLE: "T", "TESTAPP_AUTHOR": "T", "KEEP": "T"},
        marker_rows=[("r" * 32, None, None), ("r" * 32, None, "KEEP")],
    )
    setup_with(catalog)._destroy_test_db(LIB, 0)
    assert catalog.statements == [
        'DROP TABLE "DJTEST"."TESTAPP_AUTHOR"',
        f'DROP TABLE "DJTEST"."{MARKER_TABLE}"',
    ]


def test_destroy_without_marker_drops_nothing(setup_with) -> None:
    catalog = FakeCatalog({"TESTAPP_AUTHOR": "T"})
    with pytest.raises(TestDatabaseRefused, match="no DJDB2I_TEST_MARKER table"):
        setup_with(catalog)._destroy_test_db(LIB, 0)
    assert catalog.statements == []


def test_destroy_failure_keeps_marker_for_the_next_run(setup_with) -> None:
    catalog = FakeCatalog(
        {MARKER_TABLE: "T", "A": "T", "B": "T"},
        marker_rows=[("r" * 32, None, None)],
        fail={"A": -7008},
    )
    with pytest.raises(TestDatabaseRefused, match="Could not drop 1 object"):
        setup_with(catalog)._destroy_test_db(LIB, 0)
    assert 'DROP TABLE "DJTEST"."B"' in catalog.statements
    assert f'DROP TABLE "DJTEST"."{MARKER_TABLE}"' not in catalog.statements


def test_destroy_tolerates_objects_already_dropped(setup_with) -> None:
    catalog = FakeCatalog(
        {MARKER_TABLE: "T", "GONE": "V", "A": "T"},
        marker_rows=[("r" * 32, None, None)],
        fail={"GONE": -204},
    )
    setup_with(catalog)._destroy_test_db(LIB, 0)
    assert catalog.statements[-1] == f'DROP TABLE "DJTEST"."{MARKER_TABLE}"'


def test_marker_lifecycle(setup_with) -> None:
    """Setup creates the marker, a later run rewrites it, teardown drops it last."""
    catalog = FakeCatalog({})
    creation = setup_with(catalog)
    creation._create_test_db(0, autoclobber=False)
    # Simulate migrate creating a table and the marker existing now.
    catalog.inventory |= {MARKER_TABLE: "T", "TESTAPP_AUTHOR": "T"}
    catalog.marker_rows = [("x" * 32, None, None)]
    creation._create_test_db(0, autoclobber=False, keepdb=True)  # reuse: nothing dropped
    assert not any(s.startswith("DROP") for s in catalog.statements)
    assert sum(s.startswith("CREATE TABLE") for s in catalog.statements) == 1
    creation._destroy_test_db(LIB, 0)
    assert catalog.statements[-2:] == [
        'DROP TABLE "DJTEST"."TESTAPP_AUTHOR"',
        f'DROP TABLE "DJTEST"."{MARKER_TABLE}"',
    ]


def test_inventory_leaves_out_system_catalog_views(setup_with) -> None:
    catalog = FakeCatalog({})
    setup_with(catalog)._create_test_db(0, autoclobber=False)
    (inventory_sql,) = [sql for sql, _ in catalog.executed if "QSYS2.SYSTABLES" in sql]
    assert "SYSTEM_TABLE = 'N'" in inventory_sql


def test_legacy_marker_is_recognised_and_recreated(setup_with) -> None:
    catalog = FakeCatalog(
        {MARKER_TABLE: "T", "TESTAPP_AUTHOR": "T"},
        marker_rows=[("o" * 32, None, None)],
        legacy=True,
    )
    setup_with(catalog)._create_test_db(0, autoclobber=True)
    assert catalog.statements[:3] == [
        'DROP TABLE "DJTEST"."TESTAPP_AUTHOR"',
        f'DROP TABLE "DJTEST"."{MARKER_TABLE}"',
        catalog.statements[2],
    ]
    assert catalog.statements[2].startswith(f'CREATE TABLE "DJTEST"."{MARKER_TABLE}"')


def test_module_set_is_written_to_the_marker(setup_with, monkeypatch) -> None:
    catalog = FakeCatalog({})
    creation = setup_with(catalog)
    monkeypatch.setitem(
        creation.connection.settings_dict["TEST"], "MODULE_SET", "transactions,basic"
    )
    creation._create_test_db(0, autoclobber=False)
    header = [params for sql, params in catalog.executed if "MODULE_SET) VALUES" in sql]
    assert header[0][2] == "basic,transactions"


def test_changed_module_set_with_keepdb_drops_and_logs(setup_with, monkeypatch, caplog) -> None:
    catalog = FakeCatalog(
        {MARKER_TABLE: "T", "TESTAPP_AUTHOR": "T"},
        marker_rows=[("o" * 32, None, None, "transactions")],
    )
    creation = setup_with(catalog)
    monkeypatch.setitem(creation.connection.settings_dict["TEST"], "MODULE_SET", "basic")
    with caplog.at_level("INFO", logger="django_db2_for_i"):
        creation._create_test_db(0, autoclobber=False, keepdb=True)
    assert 'DROP TABLE "DJTEST"."TESTAPP_AUTHOR"' in catalog.statements
    assert "another module set (transactions); dropping them for basic" in caplog.text
