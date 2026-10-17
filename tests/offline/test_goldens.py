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
    parse,
    read,
)
from tests.golden_cases import CASES, CASES_BY_NAME, build_case
from tests.testapp.models import Author, Book, Node, Tag

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
        f"verified must be '{UNVERIFIED}' or 'IBM i <release> on PUB400, <date>'"
    )
    creates = {case.name for case in CASES if case.kind == "create"}
    assert set(golden.depends) <= creates, "a golden can only depend on create goldens"


def test_dependencies_point_to_create_cases() -> None:
    creates = {case.name for case in CASES if case.kind == "create"}
    for case in CASES:
        assert set(case.depends) <= creates, case.name


# --- No system-specific names ------------------------------------------------------

QUOTED = re.compile(r'"((?:[^"]|"")+)"')
QUOTED_PLACEHOLDER = "QUOTEDNAME"
UNQUOTED_QUALIFIED = re.compile(r"\b([A-Za-z_#@$][\w#@$]*)\s*\.\s*[A-Za-z_\"]")


def allowed_identifiers() -> set[str]:
    names = {"A"}  # alias used by exists()
    for model in (Author, Book, Node, Tag):
        names.add(model._meta.db_table.upper())
        names.update(field.column.upper() for field in model._meta.local_fields)
    return names


@pytest.mark.parametrize("path", all_golden_paths(), ids=lambda p: str(p.relative_to(GOLDEN_ROOT)))
def test_golden_contains_no_library_or_profile_names(path) -> None:
    """Only testapp tables, columns and TESTAPP_* index/constraint names appear."""
    golden = read(path)
    allowed = allowed_identifiers()
    for sql, _params in golden.statements:
        for name in QUOTED.findall(sql):
            assert name in allowed or name.startswith("TESTAPP_"), f"unexpected name {name!r}"
        # Quoted names were checked above; a placeholder keeps "T"."C" from
        # turning the preceding keyword into a qualifier.
        for qualifier in UNQUOTED_QUALIFIED.findall(QUOTED.sub(QUOTED_PLACEHOLDER, sql)):
            assert qualifier.upper() in {"SYSIBM", "QSYS2", QUOTED_PLACEHOLDER}, (
                f"unexpected qualifier {qualifier!r}"
            )
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
