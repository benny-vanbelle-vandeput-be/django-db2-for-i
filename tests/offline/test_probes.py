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
NOT_PROBES = {"_common.py", "run.py"}
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
        assert re.search(r"\bconnect\(", text), path.name


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
