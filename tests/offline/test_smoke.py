"""The smoke set (tests/ibmi/smoke.txt, phase 7, section 7): the list names real
tests, stays small, and keeps to what runs on any IBM i; no IBM i needed."""

import ast
import re
from pathlib import Path

import pytest

from tests.ibmi.conftest import SMOKE_LIST, smoke_ids

pytestmark = pytest.mark.offline

ROOT = Path(__file__).resolve().parents[2]
# Modules whose tests change the system, need a special library state, or a
# reply list entry: not for someone else's IBM i.
NOT_IN_THE_SMOKE_SET = {
    "tests/ibmi/test_cpa32b2.py",
    "tests/ibmi/test_inquiry.py",
    "tests/ibmi/test_creation.py",
    "tests/ibmi/test_unusable_connection.py",
    "tests/ibmi/test_goldens.py",
}


def functions(path: Path) -> dict[str, ast.FunctionDef]:
    tree = ast.parse(path.read_text())
    return {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}


def test_about_thirty_tests() -> None:
    assert 25 <= len(smoke_ids()) <= 45


def test_every_listed_test_exists_at_module_level() -> None:
    missing = []
    for node_id in sorted(smoke_ids()):
        module, name = node_id.split("::")
        path = ROOT / module
        if not path.is_file() or name not in functions(path):
            missing.append(node_id)
    assert missing == []


def test_the_smoke_set_keeps_to_one_connection_and_no_system_changes() -> None:
    wrong = []
    for node_id in sorted(smoke_ids()):
        module, name = node_id.split("::")
        if module in NOT_IN_THE_SMOKE_SET:
            wrong.append(node_id)
            continue
        function = functions(ROOT / module)[name]
        arguments = {a.arg for a in function.args.args}
        source = ast.get_source_segment((ROOT / module).read_text(), function) or ""
        if "second_job" in arguments or re.search(r"connections\[\s*['\"]other", source):
            wrong.append(node_id)
    assert wrong == []


def test_the_list_has_comments_and_one_id_per_line(tmp_path) -> None:
    path = tmp_path / "smoke.txt"
    path.write_text(
        "# a comment\n\ntests/ibmi/test_x.py::test_a\n  tests/ibmi/test_x.py::test_b \n"
    )
    assert smoke_ids(path) == {"tests/ibmi/test_x.py::test_a", "tests/ibmi/test_x.py::test_b"}
    assert SMOKE_LIST.name == "smoke.txt"


def test_the_smoke_session_writes_no_results_summary() -> None:
    """TEST_STATUS counts the full own tier only."""
    text = (ROOT / "noxfile.py").read_text()
    session = text[text.index("def smoke(") :]
    session = session[: session.index("\n@nox.session")]
    assert '"ibmi and smoke"' in session
    assert "--results-summary" not in session
