"""Release scripts: CHANGELOG sections, version consistency, changelog fragments."""

import importlib.util
import sys
from pathlib import Path

import pytest

import django_db2_for_i

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"


def load(name: str):
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(f"scripts_{name}", SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"scripts_{name}"] = module
    spec.loader.exec_module(module)
    return module


changelog = load("changelog_section")
assemble = load("assemble_changelog")

CHANGELOG = """# Changelog

## [Unreleased]

## [0.1.0a2] - 2026-10-18

### Fixed
- Something.

## [0.1.0a1] - 2026-10-17

### Added
- First.

[Unreleased]: https://example.invalid/compare/v0.1.0a2...HEAD
[0.1.0a2]: https://example.invalid/compare/v0.1.0a1...v0.1.0a2
"""


# --- CHANGELOG sections and the version ---------------------------------------------------


def test_section_stops_at_the_next_version() -> None:
    assert changelog.section(CHANGELOG, "0.1.0a2") == "### Fixed\n- Something."


def test_last_section_stops_at_the_link_definitions() -> None:
    assert changelog.section(CHANGELOG, "0.1.0a1") == "### Added\n- First."


@pytest.mark.parametrize("version", ["0.1.0a3", "0.1.0", "Unreleased"])
def test_missing_or_empty_sections_are_refused(version) -> None:
    with pytest.raises(LookupError):
        changelog.section(CHANGELOG, version)


def test_the_package_version_has_a_changelog_section() -> None:
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert changelog.section(text, django_db2_for_i.__version__)


# --- Changelog fragments -------------------------------------------------------------


def fragments(tmp_path, **files) -> list[Path]:
    for name, text in files.items():
        (tmp_path / name).write_text(text)
    return assemble.fragment_paths(tmp_path)


def test_the_fragments_in_the_repository_are_valid() -> None:
    assert assemble.check(assemble.fragment_paths()) == []


@pytest.mark.parametrize(
    "name",
    [
        "38.feature.md",
        "38.fixed.txt",
        "PR38.fixed.md",
        "38.fixed.2.md",
        "_x.added.md",
        "0.added.md",
    ],
)
def test_check_refuses_bad_names(tmp_path, name) -> None:
    (problem,) = assemble.check(fragments(tmp_path, **{name: "Something."}))
    assert problem.startswith(f"{name}: not <pull request number or topic>.<type>.md")


def test_check_refuses_empty_fragments_and_ignores_the_readme(tmp_path) -> None:
    paths = fragments(tmp_path, **{"README.md": "about", "38.fixed.md": "\n"})
    assert assemble.check(paths) == ["38.fixed.md: empty"]


def test_render_groups_by_type_in_heading_order(tmp_path) -> None:
    paths = fragments(
        tmp_path,
        **{
            "40.fixed.md": "Second fix.\n",
            "9.fixed.md": "First fix,\nwrapped.\n",
            "release-tooling.added.md": "Tooling.\n",
            "38.limitation.md": "- One.\n- Two.\n",
            "39.enabled.md": "`supports_any_value`.\n",
        },
    )
    assert assemble.render(paths) == (
        "### Added\n- Tooling.\n\n"
        "### Enabled features\n- `supports_any_value`. (#39)\n\n"
        "### Fixed\n- First fix,\n  wrapped. (#9)\n- Second fix. (#40)\n\n"
        "### Known limitations\n- One. (#38)\n- Two. (#38)"
    )


def test_render_needs_fragments(tmp_path) -> None:
    with pytest.raises(assemble.FragmentError, match="no changelog fragments"):
        assemble.render(fragments(tmp_path))


def test_release_adds_the_section_and_compare_links() -> None:
    text = assemble.release(CHANGELOG, "0.1.0a3", "2026-11-01", "### Added\n- New.")
    assert changelog.section(text, "0.1.0a3") == "### Added\n- New."
    assert changelog.section(text, "0.1.0a2") == "### Fixed\n- Something."
    assert text.index("## [Unreleased]") < text.index("## [0.1.0a3]") < text.index("## [0.1.0a2]")
    assert (
        "[Unreleased]: https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/compare/v0.1.0a3...HEAD"
        in text
    )
    assert (
        "[0.1.0a3]: https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/compare/v0.1.0a2...v0.1.0a3"
        in text
    )
    assert "[0.1.0a2]: https://example.invalid/compare/v0.1.0a1...v0.1.0a2" in text


def test_release_refuses_an_existing_version() -> None:
    with pytest.raises(assemble.FragmentError, match="already has a section"):
        assemble.release(CHANGELOG, "0.1.0a2", "2026-11-01", "### Added\n- New.")
