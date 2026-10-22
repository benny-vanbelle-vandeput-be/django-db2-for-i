"""Keeping probe results: scripts/publish_probe_result.py and bin/worktree-remove (no server)."""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BIN = ROOT / "bin"
needs_bin = pytest.mark.skipif(not BIN.is_dir(), reason="bin/ is not part of this copy")

spec = importlib.util.spec_from_file_location(
    "scripts_publish_probe_result", ROOT / "scripts" / "publish_probe_result.py"
)
publish = importlib.util.module_from_spec(spec)
sys.modules["scripts_publish_probe_result"] = publish
spec.loader.exec_module(publish)

# Test values only.
ENV = {
    "DB2I_HOST": "ibmi.example.test",
    "DB2I_USER": "TSTUSR",
    "DB2I_DEFAULT_LIBRARY": "TSTUSR1",
    "DB2I_OTHER_LIBRARY": "TSTUSR2",
}


# --- scripts/publish_probe_result.py -----------------------------------------------------


def test_host_user_and_libraries_become_placeholders() -> None:
    text = (
        '{"host": "ibmi.example.test", "rows": ["TSTUSR1.DJW13P", "tstusr2", '
        '"Q_TSTUSR1_T_ID_00001", "owner TSTUSR"]}'
    )
    assert publish.clean(text, ENV) == (
        '{"host": "<HOST>", "rows": ["<DEFAULT_LIBRARY>.DJW13P", "<OTHER_LIBRARY>", '
        '"Q_<DEFAULT_LIBRARY>_T_ID_00001", "owner <USER>"]}'
    )


def test_a_password_or_connection_string_is_refused() -> None:
    for text in ('{"x": "PWD=***"}', '{"message": "Password length = ***"}'):
        with pytest.raises(publish.Refused):
            publish.clean(text, ENV)


def test_the_result_name_gives_the_target(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(publish, "RESULTS", tmp_path / "results")
    source = tmp_path / "alter_table-20261022T203029Z.json"
    source.write_text('{"probe": "alter_table", "host": "ibmi.example.test"}\n')
    written = publish.publish(source, ENV)
    assert written == tmp_path / "results" / "alter_table.json"
    assert written.read_text() == '{"probe": "alter_table", "host": "<HOST>"}\n'
    with pytest.raises(publish.Refused, match="not a probe result name"):
        publish.target(tmp_path / "notes.json")
    with pytest.raises(publish.Refused, match="DB2I_HOST is not set"):
        publish.publish(source, {})


def test_the_published_results_hold_no_placeholder_leaks() -> None:
    """Every committed result uses placeholders: no raw host of the test system."""
    for path in (ROOT / "probes" / "results").glob("*.json"):
        text = path.read_text()
        assert "pub400.com" not in text.lower(), path
        assert "PWD=" not in text.upper(), path


# --- bin/worktree-remove ------------------------------------------------------------------


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(
        [
            "git", "-c", "user.name=t", "-c", "user.email=t@example.test",
            "-c", "commit.gpgsign=false", *args,
        ],
        cwd=cwd, capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip


@pytest.fixture
def worktree(tmp_path):
    """A repository with origin/main, the bin/ scripts, and a worktree of a merged branch."""
    main = tmp_path / "main"
    (main / "bin").mkdir(parents=True)
    for name in ("_common.sh", "worktree-remove"):
        (main / "bin" / name).write_text((BIN / name).read_text())
    (main / ".gitignore").write_text("test-results/\n.env\n")
    (main / ".env").write_text("not read\n")
    git("init", "-q", "-b", "main", cwd=main)
    git("add", ".", cwd=main)
    git("commit", "-q", "-m", "init", cwd=main)
    git("update-ref", "refs/remotes/origin/main", "HEAD", cwd=main)
    tree = tmp_path / "main-topic"
    git("worktree", "add", "-q", "-b", "topic", str(tree), cwd=main)
    (tree / "test-results" / "probes").mkdir(parents=True)
    (tree / "test-results" / "probes" / "catalog-20261022T203029Z.json").write_text("{}\n")
    (tree / ".env").symlink_to("../main/.env")
    return main, tree


def remove(main: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(main / "bin" / "worktree-remove"), *args], capture_output=True, text=True
    )


@needs_bin
def test_a_merged_worktree_is_archived_unlinked_and_removed(worktree) -> None:
    main, tree = worktree
    dry = remove(main, "--dry-run", str(tree))
    assert dry.returncode == 0, dry.stderr
    assert tree.exists() and "+ git -C" in dry.stdout
    result = remove(main, str(tree))
    assert result.returncode == 0, result.stderr
    assert not tree.exists()
    archived = main / "test-results" / "archive" / "main-topic" / "probes"
    assert (archived / "catalog-20261022T203029Z.json").read_text() == "{}\n"
    assert (main / ".env").read_text() == "not read\n"  # only the link went


@needs_bin
def test_it_refuses_unmerged_dirty_or_the_main_checkout(worktree) -> None:
    main, tree = worktree
    (tree / "file.txt").write_text("x\n")
    git("add", "file.txt", cwd=tree)
    dirty = remove(main, str(tree))
    assert dirty.returncode == 2 and "has changes to tracked files" in dirty.stderr
    git("commit", "-q", "-m", "work", cwd=tree)
    unmerged = remove(main, str(tree))
    assert unmerged.returncode == 2 and "is not merged into origin/main" in unmerged.stderr
    itself = remove(main, str(main))
    assert itself.returncode == 2 and "the main checkout" in itself.stderr
    assert tree.exists() and os.path.islink(tree / ".env")


@needs_bin
def test_a_real_env_file_is_refused_not_deleted(worktree) -> None:
    main, tree = worktree
    (tree / ".env").unlink()
    (tree / ".env").write_text("a real file\n")
    result = remove(main, str(tree))
    assert result.returncode == 2 and ".env is a real file, not a link" in result.stderr
    assert (tree / ".env").read_text() == "a real file\n"
