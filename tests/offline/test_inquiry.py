"""OPTIONS['inquiry_message_reply'] and cancelled ALTER TABLE (no server needed)."""

import logging

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.db import DatabaseError, OperationalError, connections
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

from django_db2_for_i import inquiry
from django_db2_for_i.base import DatabaseWrapper
from django_db2_for_i.drivers import base as driver_base

JOB = "974600/QUSER/QZDASSINIT"


class FakeCursor:
    """Answers the job name and JOB_INFO queries; records everything."""

    def __init__(self, server):
        self.server = server
        self.rows: list[tuple] = []

    def execute(self, sql, params=None):
        self.server.statements.append(sql)
        if self.server.fail_on and self.server.fail_on in sql:
            raise driver_base.DatabaseError("SQL0443 - failure", sqlstate="HY000", sqlcode=-443)
        if sql == inquiry.JOB_NAME_SQL:
            self.rows = [(self.server.job_name,)]
        elif "QSYS2.JOB_INFO" in sql:
            self.rows = [(self.server.reply,)] if self.server.reply is not None else []
        elif "CHGJOB INQMSGRPY(" in sql:
            self.server.reply = sql.split("INQMSGRPY(")[1].split(")")[0]
            self.rows = []
        elif sql == inquiry.JOB_LOG_SQL:
            self.rows = [(message,) for message in self.server.job_log]
        else:
            self.rows = []

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class FakeServerConnection:
    def __init__(self, reply="*RQD", job_name=JOB):
        self.reply = reply
        self.job_name = job_name
        self.statements: list[str] = []
        self.job_log: list[str] = []
        self.fail_on: str | None = None
        self.closed = False

    def cursor(self):
        return FakeCursor(self)

    def close(self):
        self.closed = True


def make_wrapper(**options) -> DatabaseWrapper:
    settings_dict = dict(connections["default"].settings_dict)
    settings_dict["OPTIONS"] = {**settings_dict["OPTIONS"], **options}
    return DatabaseWrapper(settings_dict, alias="offline_test")


def connected(wrapper: DatabaseWrapper, server: FakeServerConnection) -> DatabaseWrapper:
    wrapper.connection = server
    return wrapper


# --- Validation -------------------------------------------------------------------------


@pytest.mark.parametrize(("value", "reply"), [("*sysrpyl", "*SYSRPYL"), (" *DFT ", "*DFT")])
def test_valid_replies_are_normalized(value, reply) -> None:
    assert make_wrapper(inquiry_message_reply=value).inquiry_message_reply == reply


@pytest.mark.parametrize("value", ["*NOMAX", "I", "", 1, "*SYSRPYL) DLTLIB(X"])
def test_invalid_replies_are_refused(value) -> None:
    wrapper = make_wrapper(inquiry_message_reply=value)
    with pytest.raises(ImproperlyConfigured, match="inquiry_message_reply"):
        _ = wrapper.inquiry_message_reply
    with pytest.raises(ImproperlyConfigured, match="inquiry_message_reply"):
        wrapper.get_connection_params()


def test_change_sql_only_accepts_valid_replies() -> None:
    assert inquiry.change_sql("*sysrpyl") == ("CALL QSYS2.QCMDEXC('CHGJOB INQMSGRPY(*SYSRPYL)')")
    with pytest.raises(ValueError):
        inquiry.change_sql("*SYSRPYL) DLTLIB(X")


# --- Connection level: set at connect, restore the original at close ---------------------


def test_without_the_option_the_job_is_never_touched() -> None:
    server = FakeServerConnection()
    wrapper = connected(make_wrapper(), server)
    wrapper.init_connection_state()
    wrapper.close()
    assert not any("INQMSGRPY" in sql or "JOB_INFO" in sql for sql in server.statements)


def test_option_sets_the_reply_at_connect_and_restores_the_original_at_close() -> None:
    server = FakeServerConnection(reply="*DFT")
    wrapper = connected(make_wrapper(inquiry_message_reply="*SYSRPYL"), server)
    wrapper.init_connection_state()
    assert server.reply == "*SYSRPYL"
    assert wrapper._inquiry_reply_original == "*DFT"
    wrapper.close()
    assert server.reply == "*DFT"  # the value read, not a fixed *RQD
    assert server.statements[-1] == "CALL QSYS2.QCMDEXC('CHGJOB INQMSGRPY(*DFT)')"
    assert server.closed


def test_job_info_is_read_for_the_jobs_own_user() -> None:
    server = FakeServerConnection()
    connected(make_wrapper(inquiry_message_reply="*SYSRPYL"), server).init_connection_state()
    job_info = next(sql for sql in server.statements if "JOB_INFO" in sql)
    assert "JOB_USER_FILTER => 'QUSER'" in job_info
    assert "WHERE JOB_NAME = QSYS2.JOB_NAME" in job_info


@pytest.mark.parametrize(
    ("reply", "job_name", "fail_on"),
    [
        (None, JOB, None),  # job not found
        ("*NOMAX", JOB, None),  # unexpected value
        ("*RQD", "not a job name", None),
        ("*RQD", JOB, "QSYS2.JOB_INFO"),  # query fails
    ],
)
def test_unreadable_original_refuses_to_change_anything(reply, job_name, fail_on) -> None:
    server = FakeServerConnection(reply=reply, job_name=job_name)
    server.fail_on = fail_on
    wrapper = connected(make_wrapper(inquiry_message_reply="*SYSRPYL"), server)
    with pytest.raises(DatabaseError, match=r"could not be read.*not changed to \*SYSRPYL"):
        wrapper.init_connection_state()
    assert not any("CHGJOB" in sql for sql in server.statements)
    assert wrapper._inquiry_reply_original is None


def test_helpers_set_and_restore_manually(monkeypatch) -> None:
    server = FakeServerConnection(reply="*RQD")
    wrapper = connected(make_wrapper(), server)
    monkeypatch.setattr(wrapper, "ensure_connection", lambda: None)  # already "connected"
    wrapper.set_inquiry_message_reply("*sysrpyl")
    wrapper.set_inquiry_message_reply("*DFT")  # the original is read only once
    assert server.reply == "*DFT"
    assert wrapper._inquiry_reply_original == "*RQD"
    assert wrapper.restore_inquiry_message_reply() is True
    assert server.reply == "*RQD"
    assert wrapper.restore_inquiry_message_reply() is False  # nothing left to restore
    with pytest.raises(ValueError):
        wrapper.set_inquiry_message_reply("*NOMAX")


def test_close_still_closes_when_the_restore_fails(caplog) -> None:
    server = FakeServerConnection(reply="*RQD")
    wrapper = connected(make_wrapper(inquiry_message_reply="*SYSRPYL"), server)
    wrapper.init_connection_state()
    server.fail_on = "CHGJOB INQMSGRPY(*RQD)"
    with caplog.at_level(logging.WARNING, logger="django_db2_for_i"):
        wrapper.close()
    assert server.closed
    assert "could not restore the job's inquiry message reply *RQD" in caplog.text
    assert wrapper._inquiry_reply_original is None


def test_a_new_connection_forgets_the_old_jobs_original(monkeypatch) -> None:
    wrapper = make_wrapper(inquiry_message_reply="*SYSRPYL")
    wrapper._inquiry_reply_original = "*DFT"
    monkeypatch.setattr(wrapper.driver, "connect", lambda *args, **kwargs: FakeServerConnection())
    wrapper.get_new_connection(wrapper.get_connection_params())
    assert wrapper._inquiry_reply_original is None


# --- Cancelled ALTER TABLE -----------------------------------------------------------------


def cancelled(sqlstate: str = "HY008") -> OperationalError:
    error = OperationalError("[HY008] Operation cancelled. (30071)")
    error.__cause__ = driver_base.OperationalError("cancelled", sqlstate=sqlstate)
    return error


@pytest.fixture
def failing_execute(monkeypatch):
    def install(error):
        def execute(self, sql, params=()):
            raise error

        monkeypatch.setattr(BaseDatabaseSchemaEditor, "execute", execute)

    return install


def editor_for(server: FakeServerConnection, **options):
    wrapper = connected(make_wrapper(**options), server)
    wrapper.cursor = server.cursor
    return wrapper.schema_editor(atomic=False)


def test_cancelled_alter_table_is_explained(failing_execute) -> None:
    server = FakeServerConnection()
    server.job_log = ["SQL0952", "CPF7304", "CPD32CE", "CPD32CC"]
    failing_execute(cancelled())
    editor = editor_for(server)
    with pytest.raises(OperationalError) as info:
        editor.execute('ALTER TABLE "T" DROP COLUMN "B"')
    message = str(info.value)
    assert "CPA32B2" in message
    assert "ADDRPYLE SEQNBR(<free number>) MSGID(CPA32B2) RPY('I')" in message
    assert "OPTIONS['inquiry_message_reply'] = '*SYSRPYL'" in message
    assert "is not set to '*SYSRPYL'" in message
    assert "making a column NOT NULL" in message
    assert message.endswith(
        'See "ALTER TABLE that may lose data" in docs/user/IBM-i-Requirements.md.'
    )
    assert isinstance(info.value.__cause__, OperationalError)


def test_cancelled_alter_table_with_the_option_points_at_the_reply_list(failing_execute) -> None:
    server = FakeServerConnection()
    server.job_log = ["CPD32CE"]
    failing_execute(cancelled())
    editor = editor_for(server, inquiry_message_reply="*SYSRPYL")
    editor.connection._inquiry_reply_active = "*SYSRPYL"
    with pytest.raises(OperationalError, match=r"already uses .* no entry that answers CPA32B2"):
        editor.execute('ALTER TABLE "T" ALTER COLUMN "B" SET DATA TYPE SMALLINT')


@pytest.mark.parametrize(
    ("sql", "sqlstate", "job_log"),
    [
        ('ALTER TABLE "T" DROP COLUMN "B"', "HY008", ["SQL0952"]),  # other cancellation
        ('ALTER TABLE "T" DROP COLUMN "B"', "HY000", ["CPD32CE"]),  # other error
        ('DELETE FROM "T"', "HY008", ["CPD32CE"]),  # not an ALTER TABLE
    ],
)
def test_other_errors_are_not_rewritten(failing_execute, sql, sqlstate, job_log) -> None:
    server = FakeServerConnection()
    server.job_log = job_log
    error = cancelled(sqlstate)
    failing_execute(error)
    with pytest.raises(OperationalError) as info:
        editor_for(server).execute(sql)
    assert info.value is error
