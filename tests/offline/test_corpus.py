"""The offline query corpus machinery (tests/corpus/, scripts/build_corpus.py); no IBM i."""

import gzip
import json
import pickle
import sys
import tomllib
import unittest
from pathlib import Path

import pytest

from tests.corpus import capture, store
from tests.golden import UNVERIFIED
from tests.testapp.models import Author

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
LEVEL = "IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.2"


def entry(sql="SELECT 1", params=(), compiler="SQLCompiler", tests=("m.t.T.test_a",)):
    return store.Entry(compiler, [[sql, list(params)]], "cXVlcnk=", list(tests), {"USE_TZ": False})


# --- store -------------------------------------------------------------------------------


def test_the_key_ignores_whitespace_but_not_params_or_settings() -> None:
    assert entry("SELECT  1\n FROM X").key == entry("SELECT 1 FROM X").key
    assert entry(params=[1]).key != entry(params=[2]).key
    other_settings = entry()
    other_settings.settings = {"USE_TZ": True}
    assert other_settings.key != entry().key


def test_dedup_keeps_the_first_pickle_and_merges_test_ids() -> None:
    first = entry(tests=["m.t.T.test_b"])
    second = entry(tests=["m.t.T.test_a"])
    second.query = "b3RoZXI="
    (kept,) = store.dedup([first, second])
    assert kept.query == first.query
    assert kept.tests == ["m.t.T.test_a", "m.t.T.test_b"]


def test_stamps_follow_the_golden_rule() -> None:
    stored = entry()
    stored.verified = f"{LEVEL}, 2026-10-01"
    same, new = entry(), entry("SELECT 2")
    store.stamp([same, new], [stored], LEVEL, "2026-10-20")
    assert same.verified == f"{LEVEL}, 2026-10-01"  # same level: stamp and date kept
    assert new.verified == f"{LEVEL}, 2026-10-20"
    other_level = entry()
    store.stamp([other_level], [stored], LEVEL.replace("6.1.2", "6.1.3"), "2026-10-20")
    assert other_level.verified.endswith("6.1.3, 2026-10-20")


def test_gzip_files_are_byte_identical_and_unchanged_files_are_not_rewritten(tmp_path) -> None:
    assert store.gzip_bytes("x\n") == store.gzip_bytes("x\n")
    assert store.gzip_bytes("x\n")[4:8] == b"\0\0\0\0"  # mtime 0
    entries = [entry("SELECT 2"), entry("SELECT 1")]
    assert store.write_module(tmp_path, "m", entries) is True
    data, index = store.module_paths(tmp_path, "m")
    before = data.read_bytes()
    assert store.write_module(tmp_path, "m", list(reversed(entries))) is False
    assert data.read_bytes() == before
    assert index.read_text() == "SELECT 1;\nSELECT 2;\n"
    assert [e.sql for e in store.read_module(tmp_path, "m")] == [
        [["SELECT 1", []]],
        [["SELECT 2", []]],
    ]
    assert gzip.decompress(before).decode().count("\n") == 2


def test_manifest_round_trip(tmp_path) -> None:
    manifest = {
        "django": "6.1",
        "django_commit": "1e01021" + "0" * 33,
        "profile": "7.5",
        "modules": {"ordering": {"recorded": 3, "unique": 2, "level": LEVEL}},
    }
    assert store.write_manifest(tmp_path, manifest) is True
    assert store.write_manifest(tmp_path, manifest) is False
    assert tomllib.loads((tmp_path / "manifest.toml").read_text()) == manifest
    assert store.read_manifest(tmp_path) == manifest


# --- capture -----------------------------------------------------------------------------


def test_the_recorder_compiles_a_fresh_copy_and_never_touches_the_compiler(tmp_path) -> None:
    recorder = capture.Recorder(tmp_path / "raw.jsonl")
    compiler = Author.objects.filter(name="a").query.get_compiler("default")
    recorder.record(compiler)  # no running test: nothing recorded
    assert recorder.counts["recorded"] == 0
    recorder.start("ordering.tests.T.test_a")
    recorder.record(compiler)
    (record,) = recorder.pending["ordering.tests.T.test_a"]
    assert record["sql"] == store.encode_statements([compiler.as_sql()])
    assert record["compiler"] == "SQLCompiler"
    from django.conf import settings

    assert record["settings"] == {"USE_TZ": settings.USE_TZ, "TIME_ZONE": settings.TIME_ZONE}
    query = pickle.loads(store.decode_query(record["query"]))
    assert str(query) == str(compiler.query)


def test_only_passing_tests_and_their_classes_setup_are_kept(tmp_path, monkeypatch) -> None:
    recorder = capture.Recorder(tmp_path / "raw.jsonl")
    monkeypatch.setattr(capture, "RECORDER", recorder)
    compiler = Author.objects.all().query.get_compiler("default")

    class Passing(unittest.TestCase):
        def test_ok(self):
            capture.RECORDER.record(compiler)

    class Failing(unittest.TestCase):
        def test_fails(self):
            capture.RECORDER.record(compiler)
            self.fail("expected")

    for case in (Passing, Failing):
        recorder.context = f"{capture.class_key(case)}.setUpTestData"
        recorder.record(compiler)
    recorder.context = None
    result_class = type("R", (capture.CaptureResultMixin, unittest.TestResult), {})
    result = result_class()
    suite = unittest.TestSuite([Passing("test_ok"), Failing("test_fails")])
    result.startTestRun()
    suite.run(result)
    result.stopTestRun()
    lines = (tmp_path / "raw.jsonl").read_text().splitlines()
    header = json.loads(lines[0])["header"]
    tests = sorted(json.loads(line)["tests"][0].rsplit(".", 1)[-1] for line in lines[1:])
    assert tests == ["setUpTestData", "test_ok"]  # Passing's only
    assert header["counts"]["kept"] == 2


def test_hook_errors_never_escape(tmp_path) -> None:
    recorder = capture.Recorder(tmp_path / "raw.jsonl")
    recorder.start("m.t.T.test_a")
    recorder.record(object())  # no .query: counted, not raised
    assert recorder.counts["unpicklable"] + recorder.counts["not_compiled"] == 1


# --- build -------------------------------------------------------------------------------


def load_build():
    import importlib.util

    spec = importlib.util.spec_from_file_location("build_corpus", SCRIPTS / "build_corpus.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_corpus"] = module
    spec.loader.exec_module(module)
    return module


def raw_capture(path: Path, label: str, records, commit="a" * 40, django="6.1.2") -> Path:
    header = {
        "django": django,
        "django_commit": commit,
        "label": label,
        "level": LEVEL,
        "date": "2026-10-20",
        "counts": {"recorded": len(records), "unpicklable": 1, "not_compiled": 0, "unencodable": 0},
    }
    lines = [json.dumps({"header": header})] + [json.dumps(r) for r in records]
    path.write_text("\n".join(lines) + "\n")
    return path


def record(test, sql="SELECT 1"):
    return {"tests": [test], "compiler": "SQLCompiler", "sql": [[sql, []]], "query": "cQ==",
            "settings": {"USE_TZ": False}}  # fmt: skip


def test_build_combines_the_labels_of_a_module(tmp_path, monkeypatch) -> None:
    build = load_build()
    monkeypatch.setattr(store, "CORPUS_ROOT", tmp_path / "corpus")
    tests_records = [record("queries.tests.T.test_a"), record("queries.tests.T.test_b")]
    first = raw_capture(tmp_path / "queries.tests.jsonl", "queries.tests", tests_records)
    q_records = [record("queries.test_q.Q.test_c", "SELECT 2")]
    second = raw_capture(tmp_path / "queries.test_q.jsonl", "queries.test_q", q_records)
    counts = build.build("6.1", [first, second])
    assert counts["queries"]["recorded"] == 3
    assert counts["queries"]["unique"] == 2
    assert counts["queries"]["unpicklable"] == 2
    directory = store.corpus_dir("6.1")
    one, _two = store.read_module(directory, "queries")
    assert one.tests == ["queries.tests.T.test_a", "queries.tests.T.test_b"]
    assert one.verified == f"{LEVEL}, 2026-10-20"
    manifest = store.read_manifest(directory)
    assert manifest["django_commit"] == "a" * 40
    # A second build from the same captures changes nothing.
    data, _ = store.module_paths(directory, "queries")
    before = data.read_bytes()
    build.build("6.1", [first, second])
    assert data.read_bytes() == before


def test_build_refuses_mixed_commits_and_other_versions(tmp_path, monkeypatch) -> None:
    build = load_build()
    monkeypatch.setattr(store, "CORPUS_ROOT", tmp_path / "corpus")
    a = raw_capture(tmp_path / "a.jsonl", "ordering", [record("ordering.t.T.t")])
    b = raw_capture(tmp_path / "b.jsonl", "basic", [record("basic.t.T.t")], commit="b" * 40)
    with pytest.raises(build.BuildRefused, match="more than one"):
        build.build("6.1", [a, b])
    with pytest.raises(build.BuildRefused, match=r"not 6\.0"):
        build.build("6.0", [a])
    build.build("6.1", [a])
    with pytest.raises(build.BuildRefused, match="recapture them too"):
        build.build("6.1", [b])


# --- replay ------------------------------------------------------------------------------


def test_an_entry_recorded_from_the_backend_replays_identically() -> None:
    from tests.corpus.test_replay import replay

    recorder = capture.Recorder(Path("/nonexistent"))
    recorder.start("m.t.T.test_a")
    for queryset in (
        Author.objects.filter(name__in=["a", "b"]).order_by("-name")[1:3],
        Author.objects.values("name").distinct(),
    ):
        recorder.record(queryset.query.get_compiler("default"))
    for raw in recorder.pending["m.t.T.test_a"]:
        recorded = store.Entry(raw["compiler"], raw["sql"], raw["query"], raw["tests"],
                               raw["settings"])  # fmt: skip
        assert replay(recorded) == recorded.sql
    changed = store.Entry(raw["compiler"], [["SELECT 1", []]], raw["query"], raw["tests"],
                          raw["settings"])  # fmt: skip
    assert replay(changed) != changed.sql
    assert changed.verified == UNVERIFIED


def test_the_runner_passes_the_capture_settings(monkeypatch, tmp_path) -> None:
    import importlib.util

    path = SCRIPTS / "run_django_tests.py"
    spec = importlib.util.spec_from_file_location("run_django_tests", path)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    seen = {}

    class FakeProcess:
        import io

        stdout = io.StringIO("Ran 0 tests in 0.000s\n\nOK\n")

        def __init__(self, command, env, **kwargs):
            seen.update(env)

        def wait(self):
            return 0

    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "git_commit", lambda path: "abc1234 2026-10-20")
    monkeypatch.setattr(runner, "git_full_commit", lambda path: "f" * 40)
    monkeypatch.setattr(runner.subprocess, "Popen", FakeProcess)
    assert runner.run_label("6.1", "ordering", False, 2, lambda t: t, capture=True) == 0
    assert seen["DB2I_CORPUS_CAPTURE"] == str(tmp_path / "test-results/6.1/corpus/ordering.jsonl")
    assert seen["DB2I_DJANGO_COMMIT"] == "f" * 40
    assert seen["DB2I_CORPUS_LABEL"] == "ordering"
    log = (tmp_path / "test-results/6.1/ordering.log").read_text()
    assert "# capture: yes" in log
