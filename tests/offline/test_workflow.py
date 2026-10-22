"""docs/WORKFLOW.md and bin/help: every topic and every bin/ script is documented."""

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BIN = ROOT / "bin"
GUIDE = ROOT / "docs" / "WORKFLOW.md"
pytestmark = pytest.mark.skipif(
    not (BIN.is_dir() and GUIDE.exists()), reason="bin/ and docs/ are not part of this copy"
)

# The topics of phase 4 step 0 (docs/phases/phase-4.md) and the status topic.
TOPICS = [
    "setup", "branch", "change", "commit", "pr", "review", "ibmi", "status", "release",
    "troubleshooting",
]  # fmt: skip
SCRIPTS = (
    sorted(p.name for p in BIN.glob("*") if not p.name.startswith("_")) if BIN.is_dir() else []
)


def help_(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(BIN / "help"), *args], capture_output=True, text=True)


def test_every_topic_has_a_section() -> None:
    headings = re.findall(r"^## ([a-z]+): ", GUIDE.read_text(), re.MULTILINE)
    assert headings == TOPICS


def test_the_quick_start_has_the_five_commands_of_a_change() -> None:
    text = GUIDE.read_text()
    quick = text.split("## Quick start", 1)[1].split("\n## ", 1)[0]
    (block,) = re.findall(r"```sh\n(.*?)```", quick, re.DOTALL)
    commands = [line.split("#")[0].strip() for line in block.splitlines() if line.strip()]
    assert len(commands) == 5
    assert commands[0].startswith("git fetch origin && git switch -c")
    assert commands[1:3] == ["bin/check", "bin/verify"]
    assert "gh pr create" in commands[4]
    assert text.index("## Quick start") < text.index("## setup: ")


@pytest.mark.parametrize("script", SCRIPTS)
def test_every_script_is_documented(script) -> None:
    assert f"bin/{script}" in GUIDE.read_text(), "docs/WORKFLOW.md"
    for doc in ("README.md", "CONTRIBUTING.md"):
        assert f"| `bin/{script}` |" in (ROOT / doc).read_text(), f"the script table of {doc}"


def test_help_shows_the_quick_start_and_lists_the_topics() -> None:
    result = help_()
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("## Quick start\n")
    listed = re.findall(r"^  ([a-z]+) +\S", result.stdout, re.MULTILINE)
    assert listed == TOPICS


@pytest.mark.parametrize("topic", TOPICS)
def test_help_shows_each_topic(topic) -> None:
    result = help_(topic)
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith(f"## {topic}: ")
    assert "\n## " not in result.stdout  # one section only


def test_help_refuses_unknown_topics() -> None:
    for args in (("nope",), ("Status",), ("../x",), ("a", "b")):
        result = help_(*args)
        assert result.returncode == 2 and result.stdout == "", args


def test_the_env_link_rule_is_written_down() -> None:
    branch = help_("branch").stdout
    assert "only into worktrees the\n   main session uses for IBM i runs" in branch
    assert "**Never** link (or copy) it into a\n   subagent's worktree" in branch
    claude = (ROOT / "CLAUDE.md").read_text()
    assert "only into worktrees the\n  main session uses for IBM i runs" in claude


def test_bin_setup_is_for_humans_everywhere() -> None:
    for path in (GUIDE, ROOT / "CONTRIBUTING.md", ROOT / "CLAUDE.md", BIN / "setup"):
        text = " ".join(path.read_text().split())
        assert "never runs it interactively and never enters values" in text, path
