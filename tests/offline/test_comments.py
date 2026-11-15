"""Comments (supports_comments): printable ASCII only, refused before any SQL and
by the system check E006 (schema.comment_text, decision 2026-11-15)."""

from __future__ import annotations

import pytest
from django.db import NotSupportedError, connections, models
from django.test.utils import isolate_apps

from django_db2_for_i import validation
from django_db2_for_i.schema import comment_text
from tests.testapp.models import Schedule

pytestmark = pytest.mark.offline


@pytest.mark.parametrize("text", ["", "Plain text, O'Brien's (max 10%) ~!", None])
def test_printable_ascii_passes(text) -> None:
    assert comment_text(text, "table 't'") == (text or "")


@pytest.mark.parametrize("text", ["Grüße", "Price in €", "Smile \U0001f600", "tab\there", "\x7f"])
def test_anything_else_is_refused(text) -> None:
    with pytest.raises(NotSupportedError, match=r"table 't'.*outside printable ASCII"):
        comment_text(text, "table 't'")


def test_the_schema_editor_refuses_before_any_sql() -> None:
    connection = connections["default"]
    old = Schedule._meta.get_field("start")
    new = old.clone()
    new.set_attributes_from_name("start")
    new.model = Schedule
    new.db_comment = "Start in €"
    with connection.schema_editor(collect_sql=True, atomic=False) as editor:
        with pytest.raises(NotSupportedError, match=r"column testapp_schedule\.start"):
            editor.alter_field(Schedule, old, new, strict=True)
        with pytest.raises(NotSupportedError, match="table 'testapp_schedule'"):
            editor.alter_db_table_comment(Schedule, None, "Plan für heute")
        assert editor.collected_sql == []
        editor.alter_db_table_comment(Schedule, None, "It's planned")
    assert editor.collected_sql == ["""COMMENT ON TABLE "TESTAPP_SCHEDULE" IS 'It''s planned';"""]


@isolate_apps("tests.testapp")
def test_the_system_check_reports_column_and_table_comments() -> None:
    class Noted(models.Model):
        plain = models.IntegerField(db_comment="Plain")
        fancy = models.IntegerField(db_comment="Größe")

        class Meta:
            app_label = "testapp"
            db_table_comment = "Notizen für alle"

    connection = connections["default"]
    assert connection.validation.check_field(Noted._meta.get_field("plain")) == []
    (field_issue,) = connection.validation.check_field(Noted._meta.get_field("fancy"))
    assert field_issue.id == validation.E006
    assert "testapp_noted.fancy" in field_issue.msg
    (table_issue,) = validation.check_table_comments([Noted])
    assert table_issue.id == validation.E006
    assert table_issue.obj is Noted
