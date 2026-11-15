"""scripts/release_history.py: docs/RELEASE_HISTORY.md from the release tags."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.offline

ROOT = Path(__file__).resolve().parents[2]


def _module():
    spec = importlib.util.spec_from_file_location(
        "release_history", ROOT / "scripts" / "release_history.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look the module up
    spec.loader.exec_module(module)
    return module


history = _module()

OLD_STATUS = """# Test status

## Django test modules

| Module | Django | Tests | Passed | Fail | Err | Skip | XF | US | Result | Run |
|---|---|---|---|---|---|---|---|---|---|---|
| basic | 6.1 | 83 | 80 | 0 | 0 | 3 | 0 | 0 | OK | 2026-10-17 |
| transactions | 6.1 | 88 | 85 | 0 | 0 | 3 | 0 | 0 | OK | 2026-10-17 |

## Feature flags set to True by the backend

- `uses_savepoints`
- `has_native_boolean_field` (from the `has_boolean_type` capability)

## Golden files

55 goldens, 0 unverified.
"""

NEW_STATUS = """# Test status

## Django 6.1 ✅

| Test set | Passed | Skipped | Expected failures | Failed | Last run |
|---|---|---|---|---|---|
| Offline · own tests | 10 | 1 | 0 | 0 | 2026-10-21 |
| IBM i · own tests | 5 | 0 | 1 | 0 | 2026-10-21 |

## Django 5.2 ✅

| Test set | Passed | Skipped | Expected failures | Failed | Last run |
|---|---|---|---|---|---|
| Replay tests | 7 | 0 | 0 | 0 | 2026-10-21 |

## Django test modules

| Module | Django | Tests | Passed | Fail | Err | Skip | XF | US | Result | Run | Commit |
|---|---|---|---|---|---|---|---|---|---|---|---|
| basic | 6.1 | 83 | 80 | 1 | 1 | 1 | 0 | 0 | FAILED | 2026-10-21 | abc |
| basic | 5.2 | 80 | 78 | 0 | 0 | 2 | 0 | 0 | OK | 2026-10-21 | abc |

## Feature flags set to True by the backend

- `uses_savepoints`

## Golden files

463 goldens, 3 unverified.
"""

FEATURES = """# Feature flags

## Enabled (2)

| Flag | Description | Django 5.2 | Django 6.0 | Django 6.1 |
|---|---|---|---|---|
| `uses_savepoints` | Savepoints. | ✅ | ✅ | ✅ |
| `supports_json_field` | JSONField. | ✅ | ✅ | ✅ |

## Intentionally off (1)

| Flag | Description | Django 5.2 | Django 6.0 | Django 6.1 | Reason |
|---|---|---|---|---|---|
| `supports_comments` | Comments. | ❌ | ❌ | ❌ | No Unicode. |
"""


def test_flags_come_from_features_md_when_it_exists() -> None:
    assert history.parse_flags(FEATURES, NEW_STATUS) == {"uses_savepoints", "supports_json_field"}


def test_flags_come_from_test_status_before_features_md() -> None:
    assert history.parse_flags("", OLD_STATUS) == {"uses_savepoints", "has_native_boolean_field"}


def test_modules_are_summed_per_django_version() -> None:
    assert history.parse_modules(OLD_STATUS) == {
        "6.1": {"modules": 2, "tests": 171, "passed": 165, "failed": 0, "skipped": 6, "xfail": 0}
    }
    totals = history.parse_modules(NEW_STATUS)
    assert totals["6.1"]["failed"] == 2  # failures and errors
    assert totals["5.2"]["passed"] == 78


def test_test_sets_get_their_current_names() -> None:
    assert history.parse_sets(NEW_STATUS) == {
        "6.1": {"Offline tests": [10, 1, 0, 0], "IBM i tests": [5, 0, 1, 0]},
        "5.2": {"Replay tests": [7, 0, 0, 0]},
    }
    assert history.parse_sets(OLD_STATUS) == {}


def test_goldens() -> None:
    assert history.parse_goldens(OLD_STATUS) == 55
    assert history.parse_goldens("") is None


def _release(tag, status, features="", summary=""):
    read = {history.TEST_STATUS: status, history.FEATURES: features}.get
    return history.release(tag, "2026-10-21", lambda path: read(path, ""), {tag: summary})


def test_render_lists_each_release_and_what_it_switched() -> None:
    releases = history.with_changes(
        [
            _release("v0.1.0a1", OLD_STATUS, summary="Phase 1."),
            _release("v0.1.0a4", NEW_STATUS, FEATURES),
        ]
    )
    assert releases[1].added == ["supports_json_field"]
    assert releases[1].removed == ["has_native_boolean_field"]
    text = history.render(releases)
    assert "do not edit by hand" in text
    assert "Up to date with v0.1.0a4 (2026-10-21)" in text
    assert "| v0.1.0a1 | 2026-10-21 | 2 | 6.1 | 2 | 165 | 6 | 0 | 0 | 55 |" in text
    assert "| v0.1.0a4 | 2026-10-21 | 2 | 6.1, 5.2 | 1 | 80 | 1 | 0 | 2 | 463 |" in text
    assert "Phase 1." in text
    assert "Switched on (1): `supports_json_field`." in text
    assert "Switched off: `has_native_boolean_field`." in text
    assert "| v0.1.0a4 | 6.1 | 10 / 1 / 0 / 0 | 5 / 0 / 1 / 0 | \u2013 | \u2013 |" in text
    assert "x-axis [a1, a4]" in text


def test_the_page_matches_the_release_tags() -> None:
    """The committed page is what the script writes from the tags (none in a
    shallow clone: then there is nothing to compare)."""
    try:
        tags = history.git("tag", "--list", "v*").split()
    except Exception as exc:
        pytest.skip(f"the release tags cannot be read here: {exc}")
    if not tags:
        pytest.skip("no release tags in this clone (CI checks out without tags)")
    releases = history.collect()
    assert history.OUTPUT.read_text(encoding="utf-8") == history.render(releases)


def test_the_date_comes_from_the_changelog_section() -> None:
    changelog = "## [Unreleased]\n\n## [0.1.0b4] - 2026-11-14\n\n## [0.1.0b3] - 2026-11-11\n"
    assert history.changelog_date(changelog, "0.1.0b4") == "2026-11-14"
    assert history.changelog_date(changelog, "0.1.0b5") is None
    release = _release("v0.1.0b3", NEW_STATUS)
    assert release.date == "2026-10-21"  # no CHANGELOG at this "tag": the given date


def test_an_untagged_release_version_is_added(monkeypatch) -> None:
    files = {history.VERSION_FILE: '__version__ = "0.1.0b5"\n'}
    monkeypatch.setattr(history, "_working_tree", lambda path: files.get(path, ""))
    assert history.untagged_version(["v0.1.0b4"]) == "0.1.0b5"
    assert history.untagged_version(["v0.1.0b4", "v0.1.0b5"]) is None
    files[history.VERSION_FILE] = '__version__ = "0.0.1.dev0"\n'
    assert history.untagged_version([]) is None


def test_release_prepare_and_status_write_the_page() -> None:
    for script in ("release-prepare", "status"):
        text = (ROOT / "bin" / script).read_text(encoding="utf-8")
        assert "release_history" in text, script
