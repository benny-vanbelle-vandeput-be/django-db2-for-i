"""The three axes stay apart (CLAUDE.md, section 4): Django-version checks only in compat.py."""

import re
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[2] / "django_db2_for_i"

# django.VERSION, "from django import VERSION", django.get_version().
DJANGO_VERSION_CHECK = re.compile(
    r"\bdjango\s*\.\s*(VERSION|get_version)\b|\bfrom\s+django\s+import\s+[^\n]*\b(VERSION|get_version)\b"
)


OUTSIDE_COMPAT = sorted(set(PACKAGE.rglob("*.py")) - {PACKAGE / "compat.py"})


@pytest.mark.parametrize("path", OUTSIDE_COMPAT, ids=lambda path: str(path.relative_to(PACKAGE)))
def test_django_version_checks_only_in_compat(path) -> None:
    found = DJANGO_VERSION_CHECK.findall(path.read_text(encoding="utf-8"))
    assert not found, f"{path.name}: Django version check outside compat.py: {found}"


def test_the_pattern_finds_version_checks() -> None:
    for source in (
        "if django.VERSION >= (6, 1):",
        "from django import VERSION",
        "from django import get_version, setup",
        "django.get_version()",
    ):
        assert DJANGO_VERSION_CHECK.search(source), source
    assert DJANGO_VERSION_CHECK.search((PACKAGE / "compat.py").read_text(encoding="utf-8"))
    assert not DJANGO_VERSION_CHECK.search("_VERSION = re.compile(...)")
