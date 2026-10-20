"""docs/FEATURES.md (scripts/features.py): descriptions, up to date, per Django version."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load_script():
    spec = importlib.util.spec_from_file_location(
        "scripts_features", ROOT / "scripts" / "features.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["scripts_features"] = module
    spec.loader.exec_module(module)
    return module


features = load_script()

# The wheel session tests a copy without docs/.
pytestmark = pytest.mark.skipif(
    not features.VALUES_DIR.is_dir(), reason="docs/features/ is not part of this copy"
)


def test_every_enabled_off_or_planned_flag_has_a_description() -> None:
    assert features.missing_descriptions(features.load_values(), features.load_descriptions()) == []


def test_the_page_is_up_to_date() -> None:
    expected = features.render(features.load_values(), features.load_descriptions())
    assert features.OUTPUT.read_text() == expected, "run: nox -s features"


def test_the_committed_values_of_this_django_version_are_current(tmp_path) -> None:
    """Each offline CI job checks its own Django version's column."""
    written = features.dump(tmp_path)
    committed = features.VALUES_DIR / written.name
    assert committed.exists(), f"no {committed.name}: run nox -s features"
    assert json.loads(written.read_text()) == json.loads(committed.read_text()), (
        "the backend's flags changed: run nox -s features"
    )


def test_cells_and_groups() -> None:
    values = {"5.2": {"a": False}, "6.1": {"a": True, "b": False, "c": False, "d": False}}
    info = {"b": {"off": "reason"}, "c": {"planned": "phase 4"}}
    assert features.group_of("a", values, {}) == "enabled"
    assert features.group_of("b", values, info["b"]) == "off"
    assert features.group_of("c", values, info["c"]) == "planned"
    assert features.group_of("d", values, {}) == "unevaluated"
    assert features.cell("b", values["5.2"], info["b"]) == features.MISSING
    assert features.cell("a", values["6.1"], {}) == features.ON
    assert features.cell("c", values["6.1"], info["c"]) == features.PLANNED
    assert features.cell("d", values["6.1"], {}) == features.OFF
    assert features.missing_descriptions(values, {"flags": info}) == ["a", "b", "c"]


def test_development_versions_are_supported_versions() -> None:
    descriptions = features.load_descriptions()
    assert set(descriptions.get("development", [])) <= set(features.load_values())
