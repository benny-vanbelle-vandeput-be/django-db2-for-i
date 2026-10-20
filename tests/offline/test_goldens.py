"""Golden files: generated SQL matches the stored goldens (no server needed).

Run ``pytest -m offline --update-goldens`` to rewrite them after an intended
change (never in CI); review the diff. See CONTRIBUTING.md.
"""

import dataclasses
import difflib
import os
import re

import pytest
from django.db import connection

from django_db2_for_i import capabilities
from django_db2_for_i.compat import DJANGO_SERIES
from tests.golden import (
    GOLDEN_ROOT,
    UNVERIFIED,
    VERIFIED_PATTERN,
    Golden,
    all_golden_paths,
    merge,
    new_stamp,
    parse,
    read,
    render_last_verification,
)
from tests.golden_cases import CASES, CASES_BY_NAME, GROUPS, build_case
from tests.testapp.models import (
    Account,
    Author,
    Book,
    Code,
    Contact,
    Defaults,
    Link,
    Measure,
    Node,
    Profile,
    Schedule,
    Switch,
    Tag,
)

PROFILES = sorted(capabilities.PROFILES)
PAIRS = [(profile, case) for profile in PROFILES for case in CASES]


def generate(profile, case) -> Golden:
    statements = tuple(build_case(case, connection, profile))
    return Golden(case.name, DJANGO_SERIES, profile, case.depends, statements)


@pytest.mark.parametrize(
    ("profile", "case"), PAIRS, ids=[f"{profile}:{case.name}" for profile, case in PAIRS]
)
def test_golden(profile, case, request) -> None:
    generated = generate(profile, case)
    path = generated.path
    stored = read(path) if path.exists() else None
    if stored is not None and stored.content_equals(generated) and stored.depends == case.depends:
        return
    if request.config.getoption("--update-goldens"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(merge(stored, generated).render())
        return
    if stored is None:
        pytest.fail(
            f"no golden for {case.name} ({path.relative_to(GOLDEN_ROOT)}); "
            "run with --update-goldens"
        )
    diff = "\n".join(
        difflib.unified_diff(
            stored.render().splitlines(),
            generated.render().splitlines(),
            "stored",
            "generated",
            lineterm="",
        )
    )
    pytest.fail(f"golden {case.name} differs; run with --update-goldens if intended:\n{diff}")


# --- Completeness and headers ---------------------------------------------------------


def test_every_golden_has_a_case() -> None:
    orphans = []
    for path in all_golden_paths():
        _django, profile, *rest = path.relative_to(GOLDEN_ROOT).with_suffix("").parts
        if "/".join(rest) not in CASES_BY_NAME or profile not in PROFILES:
            orphans.append(str(path.relative_to(GOLDEN_ROOT)))
    assert not orphans, f"goldens without a case (remove them): {orphans}"


def test_every_case_has_a_golden() -> None:
    missing = [
        f"{DJANGO_SERIES}/{profile}/{case.name}"
        for profile, case in PAIRS
        if not (GOLDEN_ROOT / DJANGO_SERIES / profile / f"{case.name}.sql").exists()
    ]
    assert not missing, f"cases without a golden (run --update-goldens): {missing}"


@pytest.mark.parametrize("path", all_golden_paths(), ids=lambda p: str(p.relative_to(GOLDEN_ROOT)))
def test_golden_header(path) -> None:
    golden = read(path)
    django, profile, *rest = path.relative_to(GOLDEN_ROOT).with_suffix("").parts
    assert golden.name == "/".join(rest)
    assert (golden.django, golden.profile) == (django, profile)
    assert golden.verified == UNVERIFIED or VERIFIED_PATTERN.match(golden.verified), (
        f"verified must be '{UNVERIFIED}' or '<level>, <date>' (tests/golden.py)"
    )
    creates = {case.name for case in CASES if case.kind == "create"}
    assert set(golden.depends) <= creates, "a golden can only depend on create goldens"


def test_cases_are_in_the_module_of_their_group() -> None:
    """tests/golden_cases/<group>.py holds exactly the cases named <group>/...
    (DROP TABLE goldens are ddl/ too)."""
    for group, cases in GROUPS.items():
        assert {case.name.split("/", 1)[0] for case in cases} == {group}
    assert len(CASES_BY_NAME) == len(CASES), "duplicate case names"


def test_dependencies_point_to_create_cases() -> None:
    creates = {case.name for case in CASES if case.kind == "create"}
    for case in CASES:
        assert set(case.depends) <= creates, case.name


# --- No system-specific names ------------------------------------------------------

QUOTED = re.compile(r'"((?:[^"]|"")+)"')
QUOTED_PLACEHOLDER = "QUOTEDNAME"
UNQUOTED_QUALIFIED = re.compile(r"\b([A-Za-z_#@$][\w#@$]*)\s*\.\s*[A-Za-z_\"]")
# Aliases Django generates: tables in subqueries and joins (U0, T2, ...), and the
# columns of a compound query (COL1, ...).
DJANGO_ALIAS = re.compile(r"^(?:[TU]\d+|COL\d+)$")


def allowed_identifiers() -> set[str]:
    # Aliases (exists(), the annotations, values()), the column the AddField golden
    # adds and the savepoint names of dml/savepoints.
    names = {
        "A",
        "X",
        "NICKNAME",
        "S140234567890123_X1",
        "S140234567890123_X2",
        "LAST",
        "M",
        "HAS",
        "N",
        "B",
        "NEG",
        # values("pk") / values("author") in a subquery.
        "PK",
        "AUTHOR",
        # The backend's LATERAL grouping table and its columns (compiler.py).
        "DJDB2I_GROUPING",
        "G1",
        # The derived table of a rewritten IN (subquery) (compiler.py).
        "DJDB2I_IN",
    }
    models = (
        Account,
        Author,
        Book,
        Code,
        Contact,
        Defaults,
        Link,
        Measure,
        Node,
        Profile,
        Schedule,
        Switch,
        Tag,
    )
    for model in models:
        names.add(model._meta.db_table.upper())
        names.update(field.column.upper() for field in model._meta.local_fields if field.column)
    return names


@pytest.mark.parametrize("path", all_golden_paths(), ids=lambda p: str(p.relative_to(GOLDEN_ROOT)))
def test_golden_contains_no_library_or_profile_names(path) -> None:
    """Only testapp tables, columns and TESTAPP_* index/constraint names appear."""
    golden = read(path)
    allowed = allowed_identifiers()
    for sql, _params in golden.statements:
        for name in QUOTED.findall(sql):
            assert name in allowed or name.startswith("TESTAPP_") or DJANGO_ALIAS.match(name), (
                f"unexpected name {name!r}"
            )
        # Quoted names were checked above; a placeholder keeps "T"."C" from
        # turning the preceding keyword into a qualifier.
        for qualifier in UNQUOTED_QUALIFIED.findall(QUOTED.sub(QUOTED_PLACEHOLDER, sql)):
            # Django before 6.1 leaves its aliases unquoted (U0."ID").
            known = qualifier.upper() in {"SYSIBM", "QSYS2", QUOTED_PLACEHOLDER}
            assert known or DJANGO_ALIAS.match(qualifier), f"unexpected qualifier {qualifier!r}"
    text = path.read_text().upper()
    for variable in ("DB2I_USER", "DB2I_DEFAULT_LIBRARY", "DB2I_OTHER_LIBRARY"):
        value = os.environ.get(variable, "").strip().upper()
        if value:
            assert value not in text, f"{variable} appears in {path.name}"


def test_name_check_catches_a_library_name() -> None:
    golden = parse(
        "-- golden: queries/x\n-- django: 6.1\n-- profile: 7.5\n-- depends: -\n"
        '-- params: [[]]\n-- verified: unverified\nSELECT 1 FROM "MYLIB"."TESTAPP_AUTHOR";\n'
    )
    ((sql, _),) = golden.statements
    assert "MYLIB" in QUOTED.findall(sql) and "MYLIB" not in allowed_identifiers()


# --- Format and verification status ----------------------------------------------------

STORED = Golden(
    "queries/x",
    "6.1",
    "7.5",
    (),
    (("SELECT ? FROM SYSIBM.SYSDUMMY1", (1,)),),
    "IBM i 7.5 on PUB400, 2026-10-17",
)


def test_round_trip_with_tagged_params() -> None:
    import datetime as dt
    from decimal import Decimal

    golden = dataclasses.replace(
        STORED,
        statements=(
            (
                "SELECT ?, ?, ?",
                (dt.datetime(2026, 10, 17, 13, 30), dt.time(1, 2, 3), Decimal("1.50")),
            ),
        ),
    )
    assert parse(golden.render()) == golden


def test_unchanged_golden_keeps_its_verification() -> None:
    assert (
        merge(STORED, dataclasses.replace(STORED, verified=UNVERIFIED)).verified == STORED.verified
    )


@pytest.mark.parametrize(
    "change",
    [
        {"statements": (("SELECT ? FROM SYSIBM.SYSDUMMY1 X", (1,)),)},  # SQL changed
        {"statements": (("SELECT ? FROM SYSIBM.SYSDUMMY1", (2,)),)},  # params changed
    ],
    ids=["sql", "params"],
)
def test_changed_golden_is_unverified_again(change) -> None:
    generated = dataclasses.replace(STORED, verified=UNVERIFIED, **change)
    assert merge(STORED, generated).verified == UNVERIFIED


def test_update_goldens_is_refused_in_ci(pytester, monkeypatch) -> None:
    monkeypatch.setenv("CI", "true")
    pytester.makeconftest("from tests.conftest import pytest_addoption, pytest_configure\n")
    pytester.makepyfile("def test_nothing():\n    pass\n")
    result = pytester.runpytest_inprocess("-p", "no:django", "--update-goldens")
    assert "--update-goldens must not be used in CI" in result.stderr.str()


# --- Verification stamps -----------------------------------------------------------

LEVEL = "IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.2"


def test_unverified_goldens_get_a_stamp() -> None:
    assert new_stamp(UNVERIFIED, LEVEL, "2026-10-20") == f"{LEVEL}, 2026-10-20"


def test_a_stamp_on_the_same_level_is_kept() -> None:
    """A run on the same level does not touch the golden (its date stays)."""
    assert new_stamp(f"{LEVEL}, 2026-10-18", LEVEL, "2026-10-20") is None


@pytest.mark.parametrize(
    "old",
    [
        "IBM i 7.5 on PUB400, 2026-10-18",  # older stamps without TR / PTF / Django
        "IBM i 7.5 on PUB400 (TR 6, Db2 PTF Group 7), Django 6.1.2, 2026-10-18",
        "IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.1, 2026-10-18",
    ],
    ids=["old format", "other system level", "other Django version"],
)
def test_a_stamp_from_another_level_is_replaced(old) -> None:
    assert VERIFIED_PATTERN.match(old)
    assert new_stamp(old, LEVEL, "2026-10-20") == f"{LEVEL}, 2026-10-20"


def test_last_verification_report() -> None:
    results = {"a": "passed", "b": "passed", "c": "failed", "d": "skipped"}
    text = render_last_verification(LEVEL, "2026-10-20", results)
    assert text.splitlines()[1:] == [
        "date: 2026-10-20",
        f"level: {LEVEL}",
        "passed: 2",
        "failed: 1",
        "skipped: 1",
    ]
