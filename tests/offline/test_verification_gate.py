"""tests/verification_gate.py: the CI gate on verification stamps (no server needed).

These tests check the gate's logic on sample files. The gate itself runs on the
real goldens and corpus in its own session (nox -s gate), not in the offline
tier: a pull request with new SQL is pushed before its IBM i run.
"""

import gzip
import json

import pytest

from tests import verification_gate as gate
from tests.golden import UNVERIFIED

STAMP = "IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.2, 2026-10-19"
ALLOW = """\
[[golden]]
name = "ddl/remove_field"
django = ["6.1"]
reason = "CPA32B2"
verifiable_when = "a reply list entry"
"""


def write_golden(root, name, stamp, django="6.1"):
    path = root / django / "7.5" / f"{name}.sql"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"-- golden: {name}\n-- django: {django}\n-- profile: 7.5\n-- depends: \n"
        f"-- params: [[]]\n-- verified: {stamp}\nSELECT 1;\n"
    )


def write_corpus(root, *stamps):
    path = root / "6.1" / "7.5" / "queries" / "basic.jsonl.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps({"sql": "SELECT 1", "n": i, "verified": s}) for i, s in enumerate(stamps)]
    path.write_bytes(gzip.compress("\n".join(lines).encode(), mtime=0))


@pytest.fixture
def roots(tmp_path):
    golden, corpus = tmp_path / "golden", tmp_path / "corpus"
    golden.mkdir()
    corpus.mkdir()
    allow = tmp_path / "unverifiable.toml"
    allow.write_text(ALLOW)
    return golden, corpus, allow


def test_passes_with_stamps_and_needed_allow_list_entries(roots) -> None:
    golden, corpus, allow = roots
    write_golden(golden, "queries/a", STAMP)
    write_golden(golden, "ddl/remove_field", UNVERIFIED)
    write_corpus(corpus, STAMP, STAMP)
    assert gate.check(golden, corpus, allow) == []


def test_an_unstamped_golden_fails_with_its_name_and_the_fix(roots) -> None:
    golden, corpus, allow = roots
    write_golden(golden, "ddl/remove_field", UNVERIFIED)
    write_golden(golden, "queries/new", UNVERIFIED)
    [problem] = gate.check(golden, corpus, allow)
    assert "golden 6.1/7.5 queries/new" in problem
    assert problem.endswith("run bin/verify or request run-ibmi")


def test_the_allow_list_is_per_django_series(roots) -> None:
    golden, corpus, allow = roots
    write_golden(golden, "ddl/remove_field", UNVERIFIED)
    write_golden(golden, "ddl/remove_field", UNVERIFIED, django="6.0")
    [problem] = gate.check(golden, corpus, allow)
    assert "golden 6.0/7.5 ddl/remove_field" in problem


def test_an_entry_no_longer_needed_fails(roots) -> None:
    golden, corpus, allow = roots
    write_golden(golden, "ddl/remove_field", STAMP)
    [problem] = gate.check(golden, corpus, allow)
    assert "ddl/remove_field (Django 6.1) is no longer needed" in problem


def test_unstamped_corpus_entries_fail(roots) -> None:
    golden, corpus, allow = roots
    write_golden(golden, "ddl/remove_field", UNVERIFIED)
    write_corpus(corpus, STAMP, UNVERIFIED, UNVERIFIED)
    [problem] = gate.check(golden, corpus, allow)
    assert "basic.jsonl.gz: 2 entries without a verification stamp" in problem


def test_entries_need_a_reason_and_a_condition(tmp_path) -> None:
    allow = tmp_path / "unverifiable.toml"
    allow.write_text(ALLOW.replace('verifiable_when = "a reply list entry"\n', ""))
    with pytest.raises(ValueError, match="lacks verifiable_when"):
        gate.load_unverifiable(allow)


def test_the_real_allow_list() -> None:
    # Empty since the CPA32B2 goldens run with CPA32B2 suppressed, as migrations
    # run them; the file stays, read by the gate and the IBM i golden check.
    assert gate.load_unverifiable() == []
    assert gate.reasons("6.1") == {}
    assert gate.summary() == 0
