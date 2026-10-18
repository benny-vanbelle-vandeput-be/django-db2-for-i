"""Release scripts: CHANGELOG sections, version consistency, tag verification.

The tag verification tests build a throwaway git repository and throwaway
OpenPGP keys (no passphrase) in temporary directories; they need git and gpg.
"""

import importlib.util
import os
import shutil
import subprocess
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
verify_tag = load("verify_release_tag")
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


# --- Tag verification ------------------------------------------------------------------------

needs_gpg = pytest.mark.skipif(
    not (shutil.which("gpg") and shutil.which("git")), reason="needs git and gpg installed"
)


def run(*args: str, cwd: Path | None = None, env: dict | None = None, **kwargs) -> str:
    result = subprocess.run(
        list(args), cwd=cwd, env=env, capture_output=True, text=True, check=True, **kwargs
    )
    return result.stdout


class Keys:
    def __init__(self, home: Path):
        self.home = home
        home.mkdir(mode=0o700)
        self.env = {**os.environ, "GNUPGHOME": str(home)}

    def create(self, uid: str) -> str:
        run("gpg", "--batch", "--passphrase", "", "--quick-gen-key", uid, "ed25519", "sign",
            "never", env=self.env)  # fmt: skip
        listing = run("gpg", "--batch", "--with-colons", "--fingerprint", "--list-keys", uid,
                      env=self.env)  # fmt: skip
        return next(line.split(":")[9] for line in listing.splitlines() if line.startswith("fpr"))

    def public(self, fingerprint: str) -> str:
        return run("gpg", "--batch", "--armor", "--export", fingerprint, env=self.env)

    def secret(self, fingerprint: str) -> str:
        return run("gpg", "--batch", "--pinentry-mode", "loopback", "--passphrase", "",
                   "--armor", "--export-secret-keys", fingerprint, env=self.env)  # fmt: skip


@pytest.fixture(scope="module")
def release_repo(tmp_path_factory):
    """A repository with main, a side branch and tags; keys `release` and `other`."""
    base = tmp_path_factory.mktemp("release")
    keys = Keys(base / "gnupg")
    release, other = (
        keys.create("Release <release@example.invalid>"),
        keys.create("Other <other@example.invalid>"),
    )
    repo = base / "repo"
    git_env = {
        **keys.env,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.invalid",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.invalid",
    }

    def git(*args: str) -> str:
        return run("git", "-c", "gpg.program=gpg", *args, cwd=repo, env=git_env)

    def commit(version: str, text: str) -> None:
        (repo / "django_db2_for_i").mkdir(exist_ok=True)
        (repo / "django_db2_for_i" / "__init__.py").write_text(f'__version__ = "{version}"\n')
        (repo / "CHANGELOG.md").write_text(text)
        git("add", "-A")
        git("commit", "-q", "-m", f"version {version}")

    def signed(tag: str, key: str) -> None:
        git("-c", f"user.signingkey={key}", "tag", "-s", "-m", tag, tag)

    repo.mkdir()
    git("init", "-q", "-b", "main")
    commit("0.1.0a2", CHANGELOG)
    signed("v0.1.0a2", release)
    signed("v0.1.0a3", release)  # does not match __version__
    signed("v0.1.0a2-other", other)
    git("tag", "-a", "-m", "unsigned", "v0.1.0a2-unsigned")
    git("tag", "v0.1.0a2-light")
    git("switch", "-q", "-c", "side")
    commit("0.1.0a2", CHANGELOG + "\nside\n")
    signed("v0.1.0a2-side", release)
    git("switch", "-q", "main")
    commit("0.1.0a4", CHANGELOG)  # no section for 0.1.0a4
    signed("v0.1.0a4", release)
    yield repo, keys, release, other
    subprocess.run(["gpgconf", "--kill", "all"], env=keys.env, check=False)


@pytest.fixture
def in_repo(release_repo, monkeypatch):
    repo, keys, release, other = release_repo
    monkeypatch.chdir(repo)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.delenv("GNUPGHOME", raising=False)
    return keys, release, other


@needs_gpg
def test_a_good_tag_passes(in_repo, capsys) -> None:
    keys, release, _ = in_repo
    assert verify_tag.verify("v0.1.0a2", keys.public(release), "main") == "0.1.0a2"
    out = capsys.readouterr().out
    assert "signed by the release key" in out
    assert "BEGIN PGP" not in out  # the key is never printed


@needs_gpg
@pytest.mark.parametrize(
    ("tag", "message"),
    [
        ("v0.1.0a2-light", "is not annotated"),
        ("v0.1.0a2-unsigned", "is not signed with OpenPGP"),
        ("v0.1.0a2-other", "no valid signature by the release key"),
        ("v0.1.0a2-side", "not on main"),
        ("v0.1.0a3", "does not match __version__ '0.1.0a2'"),
        ("v0.1.0a4", "no section for version 0.1.0a4"),
        ("v9.9.9", "not found"),
    ],
)
def test_bad_tags_are_refused(in_repo, tag, message) -> None:
    keys, release, _ = in_repo
    with pytest.raises(verify_tag.TagError, match=message):
        verify_tag.verify(tag, keys.public(release), "main")


@needs_gpg
def test_the_key_variable_must_hold_exactly_one_public_key(in_repo) -> None:
    keys, release, other = in_repo
    with pytest.raises(verify_tag.TagError, match="empty or not set"):
        verify_tag.verify("v0.1.0a2", "  ", "main")
    with pytest.raises(verify_tag.TagError, match="could not be imported"):
        verify_tag.verify("v0.1.0a2", "not a key", "main")
    both = keys.public(release) + keys.public(other)
    with pytest.raises(verify_tag.TagError, match="exactly one public key, found 2"):
        verify_tag.verify("v0.1.0a2", both, "main")
    with pytest.raises(verify_tag.TagError, match="contains a secret key"):
        verify_tag.verify("v0.1.0a2", keys.secret(release), "main")


@needs_gpg
def test_main_reports_refusal(in_repo, monkeypatch, capsys) -> None:
    keys, release, _ = in_repo
    monkeypatch.setenv(verify_tag.KEY_VARIABLE, keys.public(release))
    assert verify_tag.main(["v0.1.0a2", "--main-ref", "main"]) == 0
    assert verify_tag.main(["v0.1.0a2-light", "--main-ref", "main"]) == 1
    assert "REFUSED: tag v0.1.0a2-light is not annotated" in capsys.readouterr().err


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
