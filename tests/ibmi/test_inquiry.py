"""OPTIONS['inquiry_message_reply'] against the IBM i (QTEMP and own job only).

Changes only the job attribute INQMSGRPY of this run's connection (always
restored) and a table in QTEMP. Never more than one connection at a time:
the option test closes the default connection before it opens its own.
"""

import pytest
from django.db import OperationalError, connection

from django_db2_for_i import inquiry
from django_db2_for_i.base import DatabaseWrapper

TABLE = "QTEMP.DJINQ"
REASON_NO_REPLY_LIST_ENTRY = "no CPA32B2 entry in the system reply list"


@pytest.fixture
def live(django_db_blocker):
    with django_db_blocker.unblock():
        yield connection
        connection.restore_inquiry_message_reply()


def current_reply(wrapper) -> str:
    with wrapper.connection.cursor() as cursor:
        return inquiry.read_reply(cursor)


def reply_list_answers_cpa32b2(wrapper) -> bool:
    """An unconditional system reply list entry CPA32B2 -> I."""
    with wrapper.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM QSYS2.REPLY_LIST_INFO WHERE MESSAGE_ID = 'CPA32B2' "
            "AND MESSAGE_REPLY = 'I' AND COMPARISON_DATA IS NULL"
        )
        return cursor.fetchone()[0] > 0


def test_helpers_switch_and_restore(live) -> None:
    live.ensure_connection()
    original = current_reply(live)
    live.set_inquiry_message_reply("*SYSRPYL")
    assert current_reply(live) == "*SYSRPYL"
    assert live.restore_inquiry_message_reply() is True
    assert current_reply(live) == original


def test_option_switches_at_connect_and_restores(live, django_db_blocker) -> None:
    live.close()  # one connection at a time
    settings_dict = {
        **live.settings_dict,
        "OPTIONS": {**live.settings_dict["OPTIONS"], "inquiry_message_reply": "*SYSRPYL"},
    }
    wrapper = DatabaseWrapper(settings_dict, alias="inquiry_test")
    try:
        wrapper.ensure_connection()
        original = wrapper._inquiry_reply_original
        assert original in inquiry.VALID_REPLIES
        assert current_reply(wrapper) == "*SYSRPYL"
        # What close() runs before it disconnects (PUB400 ends the job at
        # disconnect, so the restored value cannot be read afterwards).
        assert wrapper.restore_inquiry_message_reply() is True
        assert current_reply(wrapper) == original
    finally:
        wrapper.close()


@pytest.fixture
def qtemp_table(live):
    with live.cursor() as cursor:
        cursor.execute(f"CREATE OR REPLACE TABLE {TABLE} (A INTEGER, B INTEGER)")
    yield
    with live.cursor() as cursor:
        cursor.execute(f"DROP TABLE {TABLE}")


def test_cancelled_drop_column_is_explained(live, qtemp_table) -> None:
    if reply_list_answers_cpa32b2(live):
        pytest.skip("the system reply list answers CPA32B2; nothing is cancelled")
    live.set_inquiry_message_reply("*SYSRPYL")
    with live.schema_editor(atomic=False) as editor, pytest.raises(OperationalError) as info:
        editor.execute(f"ALTER TABLE {TABLE} DROP COLUMN B")
    assert "CPA32B2" in str(info.value)
    assert "already uses OPTIONS['inquiry_message_reply'] = '*SYSRPYL'" in str(info.value)


def test_drop_column_with_the_option(live, qtemp_table, request) -> None:
    """Works once an administrator added the reply list entry (dedicated system)."""
    if not reply_list_answers_cpa32b2(live):
        request.applymarker(pytest.mark.xfail(reason=REASON_NO_REPLY_LIST_ENTRY, strict=True))
    with live.cursor() as cursor:
        cursor.execute(f"INSERT INTO {TABLE} VALUES (1, 2) WITH NC")
    live.set_inquiry_message_reply("*SYSRPYL")
    with live.schema_editor(atomic=False) as editor:
        editor.execute(f"ALTER TABLE {TABLE} DROP COLUMN B")
