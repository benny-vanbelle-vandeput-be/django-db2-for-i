"""Foreign key violations against the IBM i: SQL0530 / SQL0531 / SQL0532 raise
IntegrityError (writes).

The tests.testapp tables are created for this module with their foreign key
constraints (``testapp_tables`` in conftest.py enables foreign keys while it
creates them) and dropped again. Db2 for i reports these violations with
SQLSTATE HY000; the driver layer classifies them by SQLCODE.

Link.code is a ForeignKey to Code, whose primary key is a CharField (no
identity column), so its parent key can be updated. The violations are
written with QuerySet.update() and a plain DELETE: Model.delete() would run
Django's on_delete=CASCADE first and never reach the constraint.
"""

import pytest
from django.db import IntegrityError

from tests.testapp.models import Code, Link

pytestmark = pytest.mark.usefixtures("testapp_tables")


def sqlcode(excinfo) -> int | None:
    return getattr(excinfo.value.__cause__, "sqlcode", None)


def test_insert_child_without_parent(live, empty) -> None:
    """SQL0530: INSERT of a child row whose key has no parent row."""
    with pytest.raises(IntegrityError, match="SQL0530") as excinfo:
        Link.objects.create(code_id="MISSING")
    assert sqlcode(excinfo) == -530
    assert not Link.objects.exists()


def test_update_child_to_missing_parent(live, empty) -> None:
    """SQL0530: UPDATE of a child row to a key without a parent row."""
    Code.objects.create(code="C-1")
    link = Link.objects.create(code_id="C-1")
    with pytest.raises(IntegrityError, match="SQL0530") as excinfo:
        Link.objects.filter(pk=link.pk).update(code_id="MISSING")
    assert sqlcode(excinfo) == -530
    assert Link.objects.get(pk=link.pk).code_id == "C-1"


def test_update_referenced_parent_key(live, empty) -> None:
    """SQL0531: UPDATE of a parent key that a child row refers to."""
    Code.objects.create(code="C-1")
    Link.objects.create(code_id="C-1")
    with pytest.raises(IntegrityError, match="SQL0531") as excinfo:
        Code.objects.filter(pk="C-1").update(code="C-2")
    assert sqlcode(excinfo) == -531
    assert list(Code.objects.values_list("code", flat=True)) == ["C-1"]


def test_delete_referenced_parent(live, empty) -> None:
    """SQL0532: DELETE of a parent row that a child row refers to."""
    Code.objects.create(code="C-1")
    Link.objects.create(code_id="C-1")
    table = live.ops.quote_name(Code._meta.db_table)
    column = live.ops.quote_name(Code._meta.pk.column)
    with pytest.raises(IntegrityError, match="SQL0532") as excinfo, live.cursor() as cursor:
        cursor.execute(f"DELETE FROM {table} WHERE {column} = %s", ["C-1"])
    assert sqlcode(excinfo) == -532
    assert Code.objects.filter(pk="C-1").exists()
