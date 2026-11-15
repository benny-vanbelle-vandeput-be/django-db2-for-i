"""docs/RELEASE_HISTORY.md: the enabled flags and the test results per release.

    python scripts/release_history.py      (nox -s release_history)

The release tags (``v*``, oldest first) are read from git: each release's own
``docs/TEST_STATUS.md`` and ``docs/FEATURES.md`` at its tag. When
``__version__`` is a release without a tag yet (the release pull request of
``bin/release-prepare``, until the maintainer tags it), that release is added
from the working tree; its row stays the same once the tag exists. A
release's date is the one of its CHANGELOG section (else of its
``[[releases]]`` entry in ``docs/status.toml``, else of the tagged commit).
The flags come from the "Enabled" list of
FEATURES.md, or, before FEATURES.md existed (0.1.0a3 and earlier), from
TEST_STATUS's list "Feature flags set to True by the backend". The summary of
each release comes from the ``[[releases]]`` of ``docs/status.toml``, where
it has one.

Never connects to an IBM i; reads git, writes only docs/RELEASE_HISTORY.md.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime
import re
import subprocess
import sys
import tomllib
from collections.abc import Callable, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "RELEASE_HISTORY.md"
TEST_STATUS = "docs/TEST_STATUS.md"
FEATURES = "docs/FEATURES.md"
STATUS = "docs/status.toml"
CHANGELOG = "CHANGELOG.md"
VERSION_FILE = "django_db2_for_i/__init__.py"
_VERSION = re.compile(r'^__version__ = "([^"]+)"$', re.MULTILINE)
_RELEASE = re.compile(r"^\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?$")
VERSIONS = ("6.1", "6.0", "5.2")
# The test sets were renamed in 0.1.0b1 (#191); the old names map to the new.
SET_NAMES = {
    "Offline · own tests": "Offline tests",
    "IBM i · own tests": "IBM i tests",
    "IBM i · Django test suite": "Django suite on IBM i",
    "Offline · Django test suite (replay)": "Replay tests",
}
NONE = "\u2013"  # an en dash: no number for this release
SETS = ("Offline tests", "IBM i tests", "Django suite on IBM i", "Replay tests")
_DJANGO_SECTION = re.compile(r"^Django (\d+\.\d+)")

Reader = Callable[[str], str]


@dataclasses.dataclass
class Release:
    tag: str
    date: str
    flags: set[str]
    modules: dict[str, dict[str, int]]
    sets: dict[str, dict[str, list[int]]]
    goldens: int | None
    summary: str = ""
    added: list[str] = dataclasses.field(default_factory=list)
    removed: list[str] = dataclasses.field(default_factory=list)


def _sections(text: str) -> dict[str, list[str]]:
    """The lines of each ``## `` section."""
    sections: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in text.splitlines():
        if line.startswith("## "):
            current = sections.setdefault(line[3:].strip(), [])
        elif current is not None:
            current.append(line)
    return sections


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def parse_flags(features: str, test_status: str) -> set[str]:
    """The flags that are on: FEATURES.md's "Enabled" list, else TEST_STATUS's."""
    for name, lines in _sections(features).items():
        if name.startswith("Enabled"):
            return {m.group(1) for line in lines if (m := re.match(r"^\| `(\w+)`", line))}
    lines = _sections(test_status).get("Feature flags set to True by the backend", [])
    return {m.group(1) for line in lines if (m := re.match(r"^- `(\w+)`", line))}


def parse_modules(test_status: str) -> dict[str, dict[str, int]]:
    """Per Django version: the modules and the sums of their counts."""
    totals: dict[str, dict[str, int]] = {}
    for line in _sections(test_status).get("Django test modules", []):
        if not line.startswith("| ") or line.startswith("| Module"):
            continue
        cells = _cells(line)
        try:
            tests, passed, failures, errors, skipped, xfail = map(int, cells[2:8])
        except ValueError:
            continue
        total = totals.setdefault(
            cells[1],
            {"modules": 0, "tests": 0, "passed": 0, "failed": 0, "skipped": 0, "xfail": 0},
        )
        total["modules"] += 1
        total["tests"] += tests
        total["passed"] += passed
        total["failed"] += failures + errors
        total["skipped"] += skipped
        total["xfail"] += xfail
    return totals


def parse_sets(test_status: str) -> dict[str, dict[str, list[int]]]:
    """Per Django version: passed, skipped, expected failures, failed of each test set."""
    result: dict[str, dict[str, list[int]]] = {}
    for name, lines in _sections(test_status).items():
        if not (match := _DJANGO_SECTION.match(name)):
            continue
        for line in lines:
            if not line.startswith("| ") or line.startswith("| Test set"):
                continue
            cells = _cells(line)
            try:
                counts = list(map(int, cells[1:5]))
            except ValueError:
                continue
            result.setdefault(match.group(1), {})[SET_NAMES.get(cells[0], cells[0])] = counts
    return result


def parse_goldens(test_status: str) -> int | None:
    for line in _sections(test_status).get("Golden files", []):
        if match := re.match(r"(\d+) goldens", line):
            return int(match.group(1))
    return None


def changelog_date(changelog: str, version: str) -> str | None:
    pattern = rf"^## \[{re.escape(version)}\] - (\d{{4}}-\d{{2}}-\d{{2}})"
    match = re.search(pattern, changelog, re.MULTILINE)
    return match.group(1) if match else None


def release(tag: str, date: str, read: Reader, summaries: dict[str, str]) -> Release:
    test_status = read(TEST_STATUS)
    return Release(
        tag=tag,
        date=changelog_date(read(CHANGELOG), tag.removeprefix("v")) or date,
        flags=parse_flags(read(FEATURES), test_status),
        modules=parse_modules(test_status),
        sets=parse_sets(test_status),
        goldens=parse_goldens(test_status),
        summary=summaries.get(tag, ""),
    )


def with_changes(releases: list[Release]) -> list[Release]:
    """Fill in which flags each release switched on and off."""
    previous: set[str] = set()
    for item in releases:
        item.added = sorted(item.flags - previous)
        item.removed = sorted(previous - item.flags)
        previous = item.flags
    return releases


def _version_key(version: str) -> tuple:
    return tuple(int(part) for part in version.split("."))


def _chart(title: str, label: str, names: list[str], values: list[int]) -> list[str]:
    top = max(values, default=0)
    return [
        "```mermaid",
        "xychart-beta",
        f'    title "{title}"',
        "    x-axis [" + ", ".join(names) + "]",
        f'    y-axis "{label}" 0 --> {int(top * 1.1) + 1}',
        "    line [" + ", ".join(map(str, values)) + "]",
        "```",
    ]


def render(releases: list[Release]) -> str:
    latest = releases[-1] if releases else None
    lines = [
        "# Release history",
        "",
        "<!-- Generated by scripts/release_history.py (bin/release-prepare); "
        "do not edit by hand. -->",
        "",
        "How the enabled feature flags and the test results grew from release to",
        "release.",
        "",
    ]
    if latest:
        lines += [
            f"> **Up to date with {latest.tag} ({latest.date}).** `bin/release-prepare`",
            "> adds every new release to this page in the release pull request.",
            "",
        ]
    lines += [
        "**Where the numbers come from**",
        "",
        "- **Test results:** each release's own `docs/TEST_STATUS.md`, at its tag:",
        "  the counts of the status run before that release.",
        "- **Feature flags:**",
        '  - from 0.1.0a4 on, the "Enabled" list of `docs/FEATURES.md` at the tag;',
        '  - before that, the list "Feature flags set to True by the backend" in',
        "    `TEST_STATUS.md`. For 0.1.0a4, where both lists exist, they hold the",
        "    same flags.",
        "- **The latest release:** [TEST_STATUS](TEST_STATUS.md) and",
        "  [FEATURES](FEATURES.md) show its numbers in full.",
        "",
    ]
    lines += [
        "## At a glance",
        "",
        "| Release | Date | Flags on | Django versions | Django test modules | "
        "Django tests passed (6.1) | Skipped (6.1) | Expected failures (6.1) | Failed | "
        "Golden files |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for item in releases:
        versions = sorted(item.modules, key=_version_key, reverse=True)
        newest = item.modules.get("6.1", {})
        failed = sum(total["failed"] for total in item.modules.values())
        lines.append(
            f"| {item.tag} | {item.date} | {len(item.flags)} | {', '.join(versions)} | "
            f"{newest.get('modules', NONE)} | {newest.get('passed', NONE)} | "
            f"{newest.get('skipped', NONE)} | {newest.get('xfail', NONE)} | {failed} | "
            f"{item.goldens if item.goldens is not None else NONE} |"
        )
    names = [re.sub(r"^v\d+\.\d+\.\d+", "", item.tag) or item.tag for item in releases]
    lines += [""]
    lines += _chart("Feature flags on", "flags", names, [len(item.flags) for item in releases])
    lines += [""]
    lines += _chart(
        "Django tests passed on IBM i (Django 6.1)",
        "tests",
        names,
        [item.modules.get("6.1", {}).get("passed", 0) for item in releases],
    )
    lines += ["", "## Feature flags per release", ""]
    lines += ["Which flags each release switched on, and off.", ""]
    for item in releases:
        lines += [f"### {item.tag} ({item.date}): {len(item.flags)} on", ""]
        if item.summary:
            lines += [item.summary, ""]
        switched = ", ".join(f"`{flag}`" for flag in item.added) or "none"
        lines += [f"Switched on ({len(item.added)}): {switched}.", ""]
        if item.removed:
            lines += [f"Switched off: {', '.join(f'`{flag}`' for flag in item.removed)}.", ""]
    lines += [
        "## Django suite on IBM i per release",
        "",
        "Django's own test modules on IBM i, summed over the modules supported at that",
        "release.",
        "",
        "| Release | Django | Modules | Tests | Passed | Failed | Skipped | Expected failures |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for item in releases:
        for version in VERSIONS:
            if total := item.modules.get(version):
                lines.append(
                    f"| {item.tag} | {version} | {total['modules']} | {total['tests']} | "
                    f"{total['passed']} | {total['failed']} | {total['skipped']} | "
                    f"{total['xfail']} |"
                )
    lines += [
        "",
        "## Test sets per release",
        "",
        "Passed / skipped / expected failures / failed of each test set, from the first",
        "release whose TEST_STATUS has this table (0.1.0a4). The sets were renamed in",
        "0.1.0b1 (#191); the old names are mapped to the new ones.",
        "",
        "| Release | Django | " + " | ".join(SETS) + " |",
        "|---|---|" + "---|" * len(SETS),
    ]
    for item in releases:
        for version in VERSIONS:
            if counts := item.sets.get(version):
                cells = (
                    " / ".join(map(str, counts[name])) if name in counts else NONE for name in SETS
                )
                lines.append(f"| {item.tag} | {version} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], check=True, capture_output=True, text=True
    ).stdout


def _at_tag(tag: str) -> Reader:
    def read(path: str) -> str:
        done = subprocess.run(
            ["git", "-C", str(ROOT), "show", f"{tag}:{path}"], capture_output=True, text=True
        )
        return done.stdout if done.returncode == 0 else ""

    return read


def _working_tree(path: str) -> str:
    file = ROOT / path
    return file.read_text(encoding="utf-8") if file.exists() else ""


def status_releases() -> dict[str, dict[str, str]]:
    data = tomllib.loads((ROOT / STATUS).read_text(encoding="utf-8"))
    return {entry["tag"]: entry for entry in data.get("releases", [])}


def untagged_version(tags: Sequence[str]) -> str | None:
    """``__version__`` when it is a release that has no tag yet."""
    match = _VERSION.search(_working_tree(VERSION_FILE))
    version = match.group(1) if match else ""
    return version if _RELEASE.match(version) and f"v{version}" not in tags else None


def collect() -> list[Release]:
    entries = status_releases()
    texts = {tag: entry.get("summary", "") for tag, entry in entries.items()}
    tags = git("tag", "--list", "v*", "--sort=creatordate").split()
    releases = []
    for tag in tags:
        date = entries.get(tag, {}).get("date") or git("log", "-1", "--format=%cs", tag).strip()
        releases.append(release(tag, date, _at_tag(tag), texts))
    if version := untagged_version(tags):
        today = datetime.datetime.now(datetime.UTC).date().isoformat()
        releases.append(release(f"v{version}", today, _working_tree, texts))
    return with_changes(releases)


def main(argv: Sequence[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args(argv)
    OUTPUT.write_text(render(collect()), encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
