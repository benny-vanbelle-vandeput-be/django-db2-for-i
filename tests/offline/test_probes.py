"""The probe naming rule and the approval gate of lib_ probes (CLAUDE.md,
"Initial test system: PUB400"); no IBM i needed."""

import ast
import importlib.util
import re
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PROBES = ROOT / "probes"
NOT_PROBES = {"_common.py", "_twojobs.py", "run.py"}
URL = "https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/143#issuecomment-42"


def load(path: Path, name: str, monkeypatch: pytest.MonkeyPatch | None = None):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    if monkeypatch is not None:
        # In sys.modules before it runs, as importlib's recipe does: dataclasses
        # look the module up there while building a class. Without it this file
        # failed when it ran on its own (#154).
        monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def common(monkeypatch):
    monkeypatch.syspath_prepend(str(PROBES))
    monkeypatch.delenv("DB2I_PROBE_APPROVED", raising=False)
    monkeypatch.delenv("DB2I_PROBE_APPROVED_BY", raising=False)
    return load(PROBES / "_common.py", "_common", monkeypatch)


def probe_files() -> list[Path]:
    return sorted(p for p in PROBES.glob("*.py") if p.name not in NOT_PROBES)


def test_every_probe_says_where_it_acts() -> None:
    names = [p.name for p in probe_files()]
    assert names, "no probes found"
    wrong = [n for n in names if not re.fullmatch(r"(qtemp|lib)_[a-z0-9_]+\.py", n)]
    assert wrong == [], "probes must be named qtemp_<topic>.py or lib_<topic>.py"


def test_run_py_runs_only_qtemp_probes() -> None:
    tree = ast.parse((PROBES / "run.py").read_text())
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    probes = {name for name in imported if name.startswith(("qtemp_", "lib_"))}
    assert probes and all(name.startswith("qtemp_") for name in probes)


def test_no_nox_session_starts_a_lib_probe_but_the_gated_one() -> None:
    text = (ROOT / "noxfile.py").read_text()
    assert not re.search(r"probes/lib_", text), "lib_ probes start only through probe_lib"
    session = text[text.index("def probe_lib(") :]
    session = session[: session.index("\n@nox.session")]
    assert '"--approved"' in session and '"--approved-by"' in session


def test_lib_probes_connect_only_through_the_gate() -> None:
    for path in PROBES.glob("lib_*.py"):
        text = path.read_text()
        assert "pyodbc.connect" not in text, f"{path.name} must connect through _common.connect"
        assert re.search(r"\b(connect|open_job)\(", text), path.name
    # The two-job helper (#162, #237, #238) opens its jobs through the same gate.
    helper = (PROBES / "_twojobs.py").read_text()
    assert "pyodbc.connect" not in helper and re.search(r"\bconnect\(", helper)


@pytest.mark.parametrize(
    ("message", "code"),
    [
        (
            "[SQL0913] Row or object DJDB2I_X in L type *FILE in use. (-913) (SQLExecDirectW)",
            "SQL0913",
        ),
        ("Duplicate key value specified. (-803) (SQLExecDirectW)", "SQL0803"),
        ("no code here", "?"),
    ],
)
def test_twojobs_reads_the_sqlcode(common, message, code) -> None:
    two = load(PROBES / "_twojobs.py", "_twojobs")
    assert two.sqlcode(message) == code


def test_twojobs_probes_never_open_more_than_two_jobs_at_once() -> None:
    """CLAUDE.md: a lock test may use at most three connections (#234); these use two."""
    for name in ("lib_lock_table", "lib_select_for_update", "lib_merge_concurrency"):
        text = (PROBES / f"{name}.py").read_text()
        assert text.count("two.open_job(") <= 4, name
        # A probe that reopens a job closes it first (jobs.clear() or reopen_a()).
        assert (
            "jobs.clear()" in text or "def reopen_a" in text or text.count("two.open_job(") == 2
        ), name


def test_lock_table_followup_deallocates_only_job_as_locks_on_its_table(
    common, monkeypatch
) -> None:
    """#162 follow-up: DLCOBJ with each lock's own state (and member), job A's rows only."""
    monkeypatch.setitem(sys.modules, "pyodbc", types.SimpleNamespace(Error=Exception))
    monkeypatch.setitem(sys.modules, "tests.table_registry", types.SimpleNamespace())
    probe = load(PROBES / "lib_lock_table.py", "lib_lock_table", monkeypatch)
    sent = []
    monkeypatch.setattr(probe.two, "timed", lambda conn, label, sql, *a, **k: sent.append(sql))
    follow = probe.Followup(None, [object(), object()], "LIB")
    follow.short, follow.a_job = "DJDB200001", "1/U/A"
    rows = [
        {"JOB_NAME": "1/U/A", "LOCK_STATE": "*EXCL", "MEMBER_NAME": None},
        {"JOB_NAME": "1/U/A", "LOCK_STATE": "*SHRRD", "MEMBER_NAME": "DJDB200001"},
        {"JOB_NAME": "2/U/B", "LOCK_STATE": "*SHRRD", "MEMBER_NAME": None},
    ]
    follow.dlcobj(rows)
    assert sent == [
        "CALL QSYS2.QCMDEXC('DLCOBJ OBJ((LIB/DJDB200001 *FILE *EXCL))')",
        "CALL QSYS2.QCMDEXC('DLCOBJ OBJ((LIB/DJDB200001 *FILE *SHRRD DJDB200001))')",
    ]


def test_qtemp_probes_with_an_entry_point_run_through_one_session() -> None:
    """No nox session per probe (#191, item 10): probe_qtemp runs any of them,
    and only qtemp_ probes."""
    text = (ROOT / "noxfile.py").read_text()
    sessions = re.findall(r"^def (probe\w*)\(", text, re.MULTILINE)
    assert sessions == ["probe_lib", "probe", "probe_qtemp"]
    session = text[text.index("def probe_qtemp(") :]
    assert 'r"qtemp_[a-z0-9_]+"' in session


def test_a_lib_probe_gets_no_connection_without_approval(common, monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["probes/lib_drop.py"])
    monkeypatch.setitem(sys.modules, "pyodbc", None)  # never reached
    with pytest.raises(common.ProbeError, match="bin/probe --approved"):
        common.connect(object())


@pytest.mark.parametrize(
    ("url", "approver"),
    [("", ""), ("https://example.com/x", "maintainer"), (URL, ""), (URL + "x", "maintainer")],
)
def test_an_approval_needs_a_comment_link_and_an_approver(common, monkeypatch, url, approver):
    monkeypatch.setenv("DB2I_PROBE_APPROVED", url)
    monkeypatch.setenv("DB2I_PROBE_APPROVED_BY", approver)
    with pytest.raises(common.ProbeError):
        common.require_approval("probes/lib_drop.py")


def test_qtemp_probes_need_no_approval(common) -> None:
    assert common.require_approval("probes/qtemp_catalog.py") is None
    assert common.require_approval("probes/run.py") is None


def test_the_approval_is_stored_with_the_result(common, monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DB2I_PROBE_APPROVED", URL)
    monkeypatch.setenv("DB2I_PROBE_APPROVED_BY", "maintainer")
    monkeypatch.setattr(sys, "argv", ["probes/lib_drop.py"])
    monkeypatch.setattr(common, "RESULTS_DIR", tmp_path)
    settings = types.SimpleNamespace(host="h", ssl=True, scrub=lambda text: text)
    path = common.write_result("lib_drop", {"steps": []}, settings)
    text = path.read_text()
    assert f'"approved": "{URL}"' in text and '"approved_by": "maintainer"' in text


# --- scripts/probe_approval.py -----------------------------------------------------


@pytest.fixture
def approval(common):
    return load(ROOT / "scripts" / "probe_approval.py", "probe_approval")


def fake_github(author: str, html_url: str = URL):
    def fetch(path: str) -> dict:
        if path.endswith("/issues/comments/42"):
            return {"html_url": html_url, "user": {"login": author}}
        if path == "repos/benny-vanbelle-vandeput-be/django-db2-for-i":
            return {"owner": {"login": "benny-vanbelle-vandeput-be"}}
        raise AssertionError(path)

    return fetch


def test_the_maintainers_comment_approves(approval) -> None:
    assert approval.check(URL, fake_github("benny-vanbelle-vandeput-be")) == (
        "benny-vanbelle-vandeput-be"
    )


@pytest.mark.parametrize(
    ("url", "fetch", "message"),
    [
        (URL, fake_github("claude-v-belle-net"), "not by the maintainer"),
        (URL, fake_github("someone"), "not by the maintainer"),
        (URL, fake_github("benny-vanbelle-vandeput-be", URL.replace("143", "1")), "not at"),
        ("https://github.com/other/repo/pull/1#issuecomment-42", None, "not a link"),
        (URL.split("#")[0], None, "not a link"),
    ],
)
def test_anything_else_does_not(approval, url, fetch, message) -> None:
    with pytest.raises(approval.ApprovalError, match=message):
        approval.check(url, fetch or fake_github("benny-vanbelle-vandeput-be"))


# --- probes/qtemp_connections.py (#234) --------------------------------------------


class FakeConnection:
    """Answers SELECT 1 and the job name; records whether it was closed."""

    def __init__(self, number: int, closed: list[int]):
        self.number, self.closed = number, closed

    def cursor(self):
        conn = self

        class Cursor:
            def execute(self, sql, params=()):
                column = "JOB_NAME" if "JOB_NAME" in sql else "ONE"
                self.description = [(column,)]
                self.rows = [(f"{conn.number:06d}/USER/QZDASOINIT" if column == "JOB_NAME" else 1,)]

            def fetchall(self):
                return self.rows

            def close(self):
                pass

        return Cursor()

    def close(self):
        self.closed.append(self.number)


@pytest.fixture
def connections_probe(common, monkeypatch):
    monkeypatch.setitem(sys.modules, "pyodbc", types.SimpleNamespace(Error=Exception))
    return load(PROBES / "qtemp_connections.py", "qtemp_connections", monkeypatch)


def opener(common, refuse_at: int | None, attempts: list[int], closed: list[int]):
    def open_connection(settings):
        attempts.append(len(attempts) + 1)
        if attempts[-1] == refuse_at:
            raise common.ProbeError("connection", "refused, password secret", 3)
        return FakeConnection(attempts[-1], closed)

    return open_connection


SETTINGS = types.SimpleNamespace(scrub=lambda text: text.replace("secret", "***"))


def test_connections_opens_up_to_four_holds_them_and_closes_in_reverse(
    common, connections_probe
) -> None:
    attempts, closed, sleeps = [], [], []
    result = connections_probe.run(
        SETTINGS, 4, opener(common, None, attempts, closed), sleeps.append
    )
    assert attempts == [1, 2, 3, 4]
    assert result["connections_open_together"] == 4 and result["separate_jobs"]
    assert [len(step["pings"]) for step in result["steps"]] == [1, 2, 3, 4]
    assert [h["after_seconds"] for h in result["hold"]] == [10, 20, 30]
    assert sleeps == [10, 10, 10] and result["all_pings_ok"]
    assert closed == [4, 3, 2, 1] and "refused" not in result


def test_connections_stops_at_the_first_refusal_without_retry(common, connections_probe) -> None:
    attempts, closed = [], []
    result = connections_probe.run(
        SETTINGS, 4, opener(common, 3, attempts, closed), lambda seconds: None
    )
    assert attempts == [1, 2, 3], "no retry and no 4th connection after a refusal"
    assert result["connections_open_together"] == 2
    assert result["refused"]["connection"] == 3
    assert "secret" not in result["refused"]["message"]
    assert closed == [2, 1]


def test_connections_without_a_first_connection_fails_as_usual(common, connections_probe) -> None:
    attempts, closed = [], []
    with pytest.raises(common.ProbeError):
        connections_probe.run(SETTINGS, 4, opener(common, 1, attempts, closed), lambda s: None)
    assert attempts == [1] and closed == []


@pytest.mark.parametrize("maximum", [0, 5])
def test_connections_never_tries_more_than_four(common, connections_probe, maximum) -> None:
    attempts = []
    with pytest.raises(common.ProbeError, match="--max"):
        connections_probe.run(SETTINGS, maximum, opener(common, None, attempts, []), print)
    assert attempts == []


def test_twojobs_refuses_a_job_while_odbc_pooling_is_on(common, monkeypatch) -> None:
    """#162: with pooling a closed connection stays connected, so the count of
    connections could pass the limit (CLAUDE.md, at most three)."""
    fake = types.SimpleNamespace(Error=Exception, pooling=True)
    monkeypatch.setitem(sys.modules, "pyodbc", fake)
    two = load(PROBES / "_twojobs.py", "_twojobs", monkeypatch)
    assert fake.pooling is False, "pooling is switched off at import"
    fake.pooling = True
    opened = []
    monkeypatch.setattr(two, "connect", lambda *a, **k: opened.append(a))
    with pytest.raises(common.ProbeError, match="pooling"):
        two.open_job(object(), "LIB")
    assert opened == []


def test_lock_table_ddl_deallocates_by_each_tables_system_name(common, monkeypatch) -> None:
    """--ddl (#162): OBJECT_LOCK_INFO names the SQL name; DLCOBJ needs the system name."""
    monkeypatch.setitem(
        sys.modules, "pyodbc", types.SimpleNamespace(Error=Exception, pooling=False)
    )
    probe = load(PROBES / "lib_lock_table.py", "lib_lock_table", monkeypatch)
    sent = []
    monkeypatch.setattr(probe.two, "timed", lambda conn, label, sql, *a, **k: sent.append(sql))
    cases = probe.DdlCases(None, [object(), object()], "LIB")
    cases.a_job = "1/U/A"
    cases.shorts = {"DJDB2I_LOCKPROBE": "DJDB200001", "DJDB2I_LOCKPROBE2": "DJDB200002"}
    rows = [
        {"JOB_NAME": "1/U/A", "OBJECT_NAME": "DJDB2I_LOCKPROBE2", "LOCK_STATE": "*EXCL"},
        {"JOB_NAME": "1/U/A", "OBJECT_NAME": "OTHER", "LOCK_STATE": "*EXCL"},
        {"JOB_NAME": "2/U/B", "OBJECT_NAME": "DJDB2I_LOCKPROBE", "LOCK_STATE": "*SHRRD"},
    ]
    cases.dlcobj(rows)
    assert sent == ["CALL QSYS2.QCMDEXC('DLCOBJ OBJ((LIB/DJDB200002 *FILE *EXCL))')"]
