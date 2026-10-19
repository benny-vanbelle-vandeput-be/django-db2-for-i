"""A statement that leaves the connection unusable, and recovering from it (writes).

On IBM i, a parameterized statement on a service (a QSYS2 table function or
view that calls system APIs) that fails with SQL0443 leaves its server
statement in use; once the cursor is closed, every later statement fails
with SQL0519 until a new connection is opened (probe fetch_errors,
docs/IBMI_NOTES.md). On PUB400 a normal user is not authorized to the PTF
group service, which reproduces it. The driver marks the connection unusable;
it never reconnects by itself.

The tests.testapp tables are created for this module and dropped again
(``testapp_tables`` in conftest.py).
"""

import pytest
from django.db import DatabaseError, OperationalError, transaction

from tests.testapp.models import Author

pytestmark = pytest.mark.usefixtures("testapp_tables")

TRIGGER = (
    "SELECT MAX(PTF_GROUP_LEVEL) FROM QSYS2.GROUP_PTF_INFO WHERE PTF_GROUP_DESCRIPTION LIKE %s"
)


def trigger(live) -> None:
    """Run the trigger; skip where the PTF service is readable (no SQL0443)."""
    try:
        with live.cursor() as cursor:
            cursor.execute(TRIGGER, ["%DB2%"])
            cursor.fetchall()
    except DatabaseError as exc:
        assert "SQL0443" in str(exc), exc  # the real cause, not SQL0519
        raise
    pytest.skip("the PTF group service is readable here; SQL0443 cannot be triggered")


def test_trigger_marks_the_connection_unusable(live, empty) -> None:
    with pytest.raises(DatabaseError, match="SQL0443"):
        trigger(live)
    assert live.is_usable() is False
    # The safety net: the next statement on this connection explains itself.
    with pytest.raises(OperationalError, match="needs to be closed"), live.cursor() as cursor:
        cursor.execute("SELECT 1 FROM SYSIBM.SYSDUMMY1")
    # Django replaces it (here: close; the next statement opens a new one).
    live.close()
    assert Author.objects.count() == 0
    assert live.is_usable() is True


def test_trigger_inside_atomic_rolls_back(live, empty) -> None:
    """Inside atomic() the error propagates (no reconnect); the work is rolled back."""
    with pytest.raises(DatabaseError, match="SQL0443"), transaction.atomic():
        Author.objects.create(name="inside")
        trigger(live)
    assert live.is_usable() is False
    assert live.in_atomic_block is False
    live.close()
    assert Author.objects.filter(name="inside").exists() is False
    Author.objects.create(name="after")
    assert list(Author.objects.values_list("name", flat=True)) == ["after"]
