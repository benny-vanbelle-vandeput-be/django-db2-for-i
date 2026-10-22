"""scripts/verify.py, the offline side of bin/verify (no server needed)."""

import importlib.util
import json
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.conftest import _select_goldens
from tests.corpus import store
from tests.golden import UNVERIFIED, Golden

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
LEVEL = "IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.2"
STAMP = f"{LEVEL}, 2026-10-20"

spec = importlib.util.spec_from_file_location("scripts_verify", SCRIPTS / "verify.py")
verify = importlib.util.module_from_spec(spec)
sys.modules["scripts_verify"] = verify
spec.loader.exec_module(verify)


@pytest.fixture
def results_dir(tmp_path, monkeypatch):
    directory = tmp_path / "verify"
    directory.mkdir()
    monkeypatch.setattr(verify, "verify_dir", lambda django: directory)
    return directory


# --- triage ------------------------------------------------------------------------------


def junit(path: Path, *cases: tuple[str, str, str | None]) -> None:
    """A JUnit report with (classname, name, failure message or None) cases."""
    body = ""
    for classname, name, message in cases:
        failure = f'<failure message="{message}">x</failure>' if message else ""
        body += f'<testcase classname="{classname}" name="{name}">{failure}</testcase>'
    path.write_text(f'<testsuites><testsuite name="pytest">{body}</testsuite></testsuites>')


def test_changed_sql_is_told_apart_from_other_failures() -> None:
    sql = [
        ("tests.offline.test_goldens::test_golden[7.5:queries/x]", "golden x differs"),
        ("tests.offline.test_goldens::test_every_case_has_a_golden", "cases without a golden: y"),
        (
            "tests.corpus.test_replay::test_corpus_module_replays[ordering]",
            "2 of 9 corpus entries of ordering write different SQL now",
        ),
    ]
    other = [
        ("tests.offline.test_goldens::test_every_golden_has_a_case", "goldens without a case"),
        ("tests.corpus.test_replay::test_corpus_module_replays[ordering]", "ImportError"),
        ("tests.offline.test_operations::test_x", "assert 1 == 2"),
    ]
    assert all(verify.is_sql_change(verify.Failure(*f)) for f in sql)
    assert not any(verify.is_sql_change(verify.Failure(*f)) for f in other)


def test_triage_exit_codes(results_dir, capsys) -> None:
    golden = ("tests.offline.test_goldens", "test_golden[7.5:queries/x]", "golden x differs")
    passing = ("tests.offline.test_operations", "test_y", None)
    junit(results_dir / "offline.xml", passing)
    junit(results_dir / "corpus.xml", ("tests.corpus.test_replay", "test_ok", None))
    assert verify.triage("6.1") == 0
    junit(results_dir / "offline.xml", passing, golden)
    assert verify.triage("6.1") == verify.EXIT_SQL_CHANGED
    junit(results_dir / "offline.xml", golden, ("tests.offline.test_x", "test_z", "boom"))
    assert verify.triage("6.1") == verify.EXIT_FAILED
    assert "test_z: boom" in capsys.readouterr().out
    (results_dir / "offline.xml").unlink()
    assert verify.triage("6.1") == verify.EXIT_FAILED  # no report: the run did not finish


# --- select: goldens and corpus ----------------------------------------------------------


def write_golden(root: Path, name: str, verified: str, depends=()) -> None:
    golden = Golden(name, "6.1", "7.5", tuple(depends), (("SELECT 1", ()),), verified)
    path = root / "6.1" / "7.5" / f"{name}.sql"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(golden.render())


def test_unverified_goldens_bring_their_create_goldens(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(verify, "GOLDEN_ROOT", tmp_path)
    write_golden(tmp_path, "ddl/create_author", STAMP)
    write_golden(tmp_path, "ddl/create_book", STAMP, ["ddl/create_author"])
    write_golden(tmp_path, "queries/new", UNVERIFIED, ["ddl/create_book"])
    write_golden(tmp_path, "queries/old", STAMP, ["ddl/create_author"])
    write_golden(tmp_path, "queries/rejected", UNVERIFIED)
    assert verify.unverified_goldens("6.1", ["queries/rejected"]) == [
        "ddl/create_author",
        "ddl/create_book",
        "queries/new",
    ]


def entry(sql: str, tests: list[str], verified: str = UNVERIFIED) -> store.Entry:
    return store.Entry("SQLCompiler", [[sql, []]], "cXVlcnk=", tests, {"USE_TZ": False}, verified)


def test_one_test_per_unverified_corpus_entry(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(verify.store, "corpus_dir", lambda django: tmp_path)
    store.write_module(
        tmp_path,
        "ordering",
        [
            entry("SELECT 1", ["ordering.tests.A.test_a", "ordering.tests.A.test_b"]),
            entry("SELECT 2", ["ordering.tests.A.test_b", "ordering.tests.A.test_c"]),
            entry("SELECT 3", ["ordering.tests.A.test_d"], STAMP),
        ],
    )
    # test_b covers both unverified entries; the verified one needs no run.
    assert verify.corpus_test_ids("6.1") == ["ordering.tests.A.test_b"]


# --- select: own IBM i tests -------------------------------------------------------------

BEFORE = textwrap.dedent(
    """
    import pytest

    def helper():
        return 1

    def test_same():
        assert helper()

    def test_changed():
        assert 1

    def test_removed():
        pass

    class TestThings:
        def test_method(self):
            pass

        def test_other(self):
            pass
    """
)


def test_new_and_changed_tests_are_selected_by_node_id() -> None:
    after = (
        BEFORE.replace("def test_changed():\n    assert 1", "def test_changed():\n    assert 2")
        .replace("def test_removed():\n    pass\n", "")
        .replace(
            "def test_other(self):", "def test_other(self):\n        assert True\n        pass"
        )
        + "\ndef test_new():\n    pass\n"
    )
    path = "tests/pub400/test_x.py"
    assert verify.changed_tests(path, BEFORE, after) == [
        f"{path}::test_changed",
        f"{path}::TestThings::test_other",
        f"{path}::test_new",
    ]
    assert verify.changed_tests(path, BEFORE, BEFORE) == []
    assert verify.changed_tests(path, BEFORE, "") == []  # removed module
    new_module = verify.changed_tests(path, "", BEFORE)
    assert f"{path}::TestThings::test_method" in new_module and len(new_module) == 5


def test_module_and_class_level_changes_select_the_module_or_class() -> None:
    path = "tests/pub400/test_x.py"
    helper_changed = BEFORE.replace("return 1", "return 2")
    assert verify.changed_tests(path, BEFORE, helper_changed) == [path]
    class_changed = BEFORE.replace("class TestThings:\n", "class TestThings:\n    value = 1\n\n")
    assert verify.changed_tests(path, BEFORE, class_changed) == [f"{path}::TestThings"]
    marked = BEFORE.replace("class TestThings:", "@pytest.mark.slow\nclass TestThings:")
    assert verify.changed_tests(path, BEFORE, marked) == [f"{path}::TestThings"]


@pytest.mark.parametrize(
    "path",
    [
        "tests/pub400/conftest.py",
        "tests/pub400/marked_library.py",
        "tests/pub400/testapp_tables.py",
        "tests/conftest.py",
        "tests/testapp/models.py",
        "tests/django_settings/settings_pub400.py",
        "django_db2_for_i/base.py",
        "django_db2_for_i/drivers/pyodbc.py",
        "docker/Dockerfile",
    ],
)
def test_shared_code_runs_the_full_own_tier(path) -> None:
    selection = verify.own_selection(
        ["tests/pub400/test_x.py", path], lambda p: BEFORE, lambda p: BEFORE + "\n"
    )
    assert selection.full and selection.full.startswith(path)


def test_backend_and_docs_changes_select_no_own_tests() -> None:
    selection = verify.own_selection(
        ["django_db2_for_i/operations.py", "docs/DECISIONS.md", "tests/offline/test_x.py"],
        lambda p: "",
        lambda p: "x = 1\n",
    )
    assert selection == verify.OwnSelection()


# --- select: Django test labels ----------------------------------------------------------


def test_ids_that_leave_the_skip_lists_are_selected(tmp_path) -> None:
    before = {
        "django_db2_for_i/features.py": textwrap.dedent(
            """
            expected_failures = {
                REASON: {
                    "lookup.tests.LookupTests.test_a",
                    "lookup.tests.LookupTests.test_b",
                    "queries.tests.Gone.test_c",
                },
            }
            name = "django_db2_for_i.features"
            """
        ),
        "django_db2_for_i/compat.py": 'SKIPS = {"basic.tests.A.test_d"}\n',
    }
    after = {
        "django_db2_for_i/features.py": (
            'expected_failures = {REASON: {"lookup.tests.LookupTests.test_b"}}\n'
        ),
        "django_db2_for_i/compat.py": "SKIPS = set()\n",
    }
    removed = verify.unlisted_test_ids(before.get, after.get, None)
    assert removed == [
        "basic.tests.A.test_d",
        "lookup.tests.LookupTests.test_a",
        "queries.tests.Gone.test_c",
    ]
    moved = {**after, "django_db2_for_i/compat.py": 'SKIPS = {"basic.tests.A.test_d"}\n'}
    assert "basic.tests.A.test_d" not in verify.unlisted_test_ids(before.get, moved.get, None)
    tests = tmp_path / "tests"
    (tests / "lookup").mkdir(parents=True)
    (tests / "lookup" / "tests.py").write_text("")
    (tests / "basic" / "tests").mkdir(parents=True)
    (tests / "basic" / "tests" / "__init__.py").write_text("")
    # Only tests that exist in this version's checkout.
    assert verify.unlisted_test_ids(before.get, after.get, tests) == [
        "basic.tests.A.test_d",
        "lookup.tests.LookupTests.test_a",
    ]


def test_many_ids_collapse_into_class_module_and_app_labels() -> None:
    few = ["m.tests.A.test_1", "m.tests.A.test_2", "m.tests.A.test_3"]
    assert verify.collapse(few) == few
    many = [f"m.tests.A.test_{i}" for i in range(5)]
    assert verify.collapse([*many, "m.tests.B.test_x"]) == ["m.tests.A", "m.tests.B.test_x"]
    classes = [f"m.tests.C{c}.test_{i}" for c in range(4) for i in range(5)]
    assert verify.collapse(classes) == ["m.tests"]
    modules = [f"m.test_{n}.C.test_{i}" for n in range(4) for i in range(5)]
    assert verify.collapse([*modules, "other.tests.D.test_y"]) == ["m", "other.tests.D.test_y"]
    # An id inside a label that runs anyway is dropped.
    assert verify.collapse([*many, "m.tests.A"]) == ["m.tests.A"]


def test_django_labels_run_three_at_a_time() -> None:
    assert verify.django_runs(["a", "b", "c", "d"]) == [["a", "b", "c"], ["d"]]
    assert verify.django_runs([]) == []


# --- select ------------------------------------------------------------------------------


@pytest.fixture
def selecting(tmp_path, results_dir, monkeypatch):
    """select() on a fake repository: goldens, corpus and git are stubbed."""
    monkeypatch.setattr(verify, "ROOT", tmp_path)
    monkeypatch.setattr(verify, "merge_base", lambda base: "abc123")
    monkeypatch.setattr(verify, "unverifiable_names", lambda django: [])
    state = SimpleNamespace(paths=[], goldens=[], corpus=[], unlisted=[])
    monkeypatch.setattr(verify, "changed_paths", lambda commit: state.paths)
    monkeypatch.setattr(verify, "text_at", lambda commit, path: "")
    monkeypatch.setattr(verify, "current_text", lambda path: "def test_a():\n    pass\n")
    monkeypatch.setattr(verify, "unverified_goldens", lambda django, skip: state.goldens)
    monkeypatch.setattr(verify, "is_unverified", lambda django, name: name.startswith("queries/"))
    monkeypatch.setattr(verify, "corpus_test_ids", lambda django: state.corpus)
    monkeypatch.setattr(verify, "unlisted_test_ids", lambda *args: state.unlisted)
    results_dir.relative_to(tmp_path)  # the runs file names paths relative to ROOT
    return state


def runs(directory: Path) -> list[list[str]]:
    return [line.split("\t") for line in (directory / "runs.txt").read_text().splitlines()]


def test_select_writes_one_run_per_line(selecting, results_dir) -> None:
    selecting.goldens = ["ddl/create_author", "queries/new"]
    selecting.paths = ["tests/pub400/test_x.py"]
    selecting.corpus = ["a.tests.A.test_1", "b.tests.B.test_2"]
    selecting.unlisted = ["c.tests.C.test_3", "d.tests.D.test_4"]
    assert verify.select("6.1", "origin/main") == 0
    assert runs(results_dir) == [
        ["goldens", "verify/goldens.txt"],
        ["own", "tests/pub400/test_x.py::test_a"],
        ["django", "a.tests.A.test_1", "b.tests.B.test_2", "c.tests.C.test_3"],
        ["django", "d.tests.D.test_4"],
    ]
    assert (results_dir / "goldens.txt").read_text() == "ddl/create_author\nqueries/new\n"
    selection = json.loads((results_dir / "selection.json").read_text())
    assert selection["merge_base"] == "abc123" and selection["own_full"] is None
    assert selection["unverified_goldens"] == ["queries/new"]


def test_select_runs_the_full_own_tier_for_shared_code(selecting, results_dir, capsys) -> None:
    selecting.paths = ["tests/pub400/test_x.py", "tests/pub400/conftest.py"]
    assert verify.select("6.1", "origin/main") == 0
    assert runs(results_dir) == [["own", "full"]]
    assert (
        "the full tier (tests/pub400/conftest.py: shared own-test code)" in capsys.readouterr().out
    )


def test_select_with_nothing_to_run(selecting, results_dir, capsys) -> None:
    assert verify.select("6.1", "origin/main") == 0
    assert (results_dir / "runs.txt").read_text() == ""
    assert "nothing to run on IBM i" in capsys.readouterr().out


def test_select_refuses_too_many_labels_or_runs(selecting, capsys) -> None:
    selecting.corpus = [f"app{i}.tests.A.test_x" for i in range(61)]
    assert verify.select("6.1", "origin/main") == verify.EXIT_TOO_MANY
    assert "refused: 61 Django test labels in 21 runs" in capsys.readouterr().out
    selecting.corpus = selecting.corpus[:7]
    assert verify.select("6.1", "origin/main", max_runs=2) == verify.EXIT_TOO_MANY
    assert verify.select("6.1", "origin/main", max_labels=6) == verify.EXIT_TOO_MANY
    assert verify.select("6.1", "origin/main") == 0
    # Collapsing keeps a large but narrow selection under the caps.
    selecting.corpus = [f"app.tests.A.test_{i}" for i in range(200)]
    assert verify.select("6.1", "origin/main") == 0


# --- finish ------------------------------------------------------------------------------


def capture(path: Path, entries: list[store.Entry], level: str = LEVEL) -> None:
    header = {"header": {"level": level, "date": "2026-10-22", "django_commit": "x" * 40}}
    records = [
        {
            "compiler": e.compiler,
            "sql": e.sql,
            "query": e.query,
            "tests": e.tests,
            "settings": e.settings,
        }
        for e in entries
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(line) for line in [header, *records]) + "\n")


def test_only_exactly_captured_statements_are_stamped(tmp_path, monkeypatch) -> None:
    corpus = tmp_path / "corpus"
    monkeypatch.setattr(verify.store, "corpus_dir", lambda django: corpus)
    store.write_module(
        corpus,
        "ordering",
        [
            entry("SELECT 1", ["ordering.tests.A.test_a"]),
            entry("SELECT 2", ["ordering.tests.A.test_b"]),
            entry("SELECT 3", ["ordering.tests.A.test_c"], STAMP),
        ],
    )
    other_settings = entry("SELECT 2", ["ordering.tests.A.test_b"])
    other_settings.settings = {"USE_TZ": True}
    capture(tmp_path / "c.jsonl", [entry("SELECT  1", ["x.y.Z.test_q"]), other_settings])
    assert verify.stamp_corpus("6.1", [tmp_path / "c.jsonl"]) == (1, 1)
    stamps = {e.sql[0][0]: e.verified for e in store.read_module(corpus, "ordering")}
    assert stamps == {"SELECT 1": f"{LEVEL}, 2026-10-22", "SELECT 2": UNVERIFIED, "SELECT 3": STAMP}


@pytest.fixture
def finishing(tmp_path, results_dir, monkeypatch):
    monkeypatch.setattr(verify, "ROOT", tmp_path)
    monkeypatch.setattr(verify, "GOLDEN_ROOT", tmp_path / "golden")
    monkeypatch.setattr(verify.store, "corpus_dir", lambda django: tmp_path / "corpus")
    write_golden(tmp_path / "golden", "queries/new", STAMP)
    (results_dir / "selection.json").write_text(json.dumps({"goldens": ["queries/new"]}))
    (results_dir / "runs.txt").write_text("goldens\tverify/goldens.txt\ndjango\ta.tests.A.test_1\n")
    return results_dir


def test_finish_reports_success(finishing, capsys) -> None:
    (finishing / "results.txt").write_text(
        "goldens\tverify/goldens.txt\t0\ndjango\ta.tests.A.test_1\t0\n"
    )
    assert verify.finish("6.1", updated=True) == 0
    report = (finishing / "report.txt").read_text()
    assert "IBM i runs: 2 of 2, 0 failed" in report
    assert "goldens: 1 of 1 verified" in report
    assert "WARNING" not in report
    assert "The new stamps are in the working tree" in report


def test_finish_says_when_no_stamp_was_written(finishing) -> None:
    # Only already verified goldens ran (none was unverified when selected).
    selection = {"goldens": ["queries/new"], "unverified_goldens": []}
    (finishing / "selection.json").write_text(json.dumps(selection))
    (finishing / "results.txt").write_text(
        "goldens\tverify/goldens.txt\t0\ndjango\ta.tests.A.test_1\t0\n"
    )
    assert verify.finish("6.1", updated=False) == 0
    report = (finishing / "report.txt").read_text()
    assert "No stamps were written; nothing was committed." in report
    assert "The new stamps" not in report


def test_finish_warns_when_new_sql_is_not_verified(finishing, tmp_path) -> None:
    write_golden(tmp_path / "golden", "queries/new", UNVERIFIED)
    (finishing / "results.txt").write_text("goldens\tverify/goldens.txt\t1\n")
    assert verify.finish("6.1", updated=True) == verify.EXIT_UNVERIFIED
    report = (finishing / "report.txt").read_text()
    assert report.splitlines()[2].startswith("WARNING: new SQL was written")
    assert "NOT verified on IBM i. Review it before committing" in report
    assert "FAILED: goldens verify/goldens.txt" in report
    assert "not run: 1" in report
    assert "unverified: queries/new" in report
    # Without the update step there is no new SQL to warn about.
    assert verify.finish("6.1", updated=False) == verify.EXIT_UNVERIFIED
    assert "WARNING" not in (finishing / "report.txt").read_text()


def test_finish_for_affected_only_reports_the_runs(finishing) -> None:
    (finishing / "results.txt").write_text(
        "goldens\tverify/goldens.txt\t0\ndjango\ta.tests.A.test_1\t0\n"
    )
    assert verify.finish("6.1", updated=False, stamp=False) == 0
    assert "corpus entries" not in (finishing / "report.txt").read_text()


# --- --goldens-from (tests/conftest.py) --------------------------------------------------


def test_goldens_from_deselects_only_other_goldens(tmp_path) -> None:
    names = tmp_path / "goldens.txt"
    names.write_text("ddl/create_author\nqueries/new\n")
    deselected = []
    config = SimpleNamespace(
        getoption=lambda name: str(names),
        hook=SimpleNamespace(pytest_deselected=lambda items: deselected.extend(items)),
    )

    def item(name, param=None):
        return SimpleNamespace(
            originalname=name, callspec=SimpleNamespace(id=param), name=f"{name}[{param}]"
        )

    items = [
        item("test_golden_is_accepted", "ddl/create_author"),
        item("test_golden_is_accepted", "queries/old"),
        item("test_golden_is_accepted", "queries/new"),
        item("test_other"),
    ]
    _select_goldens(config, items)
    assert [i.name for i in items] == [
        "test_golden_is_accepted[ddl/create_author]",
        "test_golden_is_accepted[queries/new]",
        "test_other[None]",
    ]
    assert [i.callspec.id for i in deselected] == ["queries/old"]
    config.getoption = lambda name: None
    _select_goldens(config, items)
    assert len(items) == 3
