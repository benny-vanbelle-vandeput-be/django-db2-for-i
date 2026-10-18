"""Assemble the changelog fragments in changelog.d/ into a CHANGELOG.md section.

Usage:
    python scripts/assemble_changelog.py check
    python scripts/assemble_changelog.py draft
    python scripts/assemble_changelog.py release <version> [--date YYYY-MM-DD]

Every pull request adds its own fragment instead of editing CHANGELOG.md, so
parallel pull requests do not conflict. A fragment is
``changelog.d/<name>.<type>.md``: ``<name>`` is the pull request number (the
entry gets a ``(#<number>)`` reference) or a short kebab-case topic, and
``<type>`` one of the TYPES below. The file holds one entry in Markdown,
or several as a list of ``- `` items.

``check`` validates the fragment names and contents (the offline tier runs it
too). ``draft`` prints the section the fragments would make. ``release``
writes it into CHANGELOG.md as ``## [<version>] - <date>`` below
``## [Unreleased]``, updates the compare links at the end, and deletes the
fragments; the release pull request commits both (CONTRIBUTING.md).
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = ROOT / "CHANGELOG.md"
FRAGMENTS = ROOT / "changelog.d"
REPOSITORY = "https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i"

# Fragment type -> CHANGELOG heading, in the order the headings appear.
TYPES = {
    "added": "Added",
    "enabled": "Enabled features",
    "changed": "Changed",
    "fixed": "Fixed",
    "limitation": "Known limitations",
}
FRAGMENT_NAME = re.compile(
    rf"^(?P<name>[1-9][0-9]*|[a-z][a-z0-9]*(?:-[a-z0-9]+)*)\.(?P<type>{'|'.join(TYPES)})\.md$"
)
IGNORED = {"README.md", ".gitkeep"}
UNRELEASED = "## [Unreleased]"


class FragmentError(ValueError):
    pass


def fragment_paths(directory: Path = FRAGMENTS) -> list[Path]:
    return sorted(p for p in directory.iterdir() if p.is_file() and p.name not in IGNORED)


def check(paths: list[Path]) -> list[str]:
    """Problems with the fragment files (empty list: all valid)."""
    problems = []
    for path in paths:
        if not FRAGMENT_NAME.match(path.name):
            problems.append(
                f"{path.name}: not <pull request number or topic>.<type>.md, "
                f"type one of {', '.join(TYPES)}"
            )
        elif not path.read_text(encoding="utf-8").strip():
            problems.append(f"{path.name}: empty")
    return problems


def _sort_key(path: Path) -> tuple[int, int, str]:
    name = FRAGMENT_NAME.match(path.name)["name"]
    return (0, int(name), "") if name.isdigit() else (1, 0, name)


def entry(path: Path) -> str:
    """The fragment as ``- `` list items, each with its pull request reference."""
    name = FRAGMENT_NAME.match(path.name)["name"]
    text = path.read_text(encoding="utf-8").strip()
    if not text.startswith("- "):
        first, *rest = text.splitlines()
        text = "\n".join([f"- {first}", *(f"  {line}" if line else line for line in rest)])
    if not name.isdigit():
        return text
    items = re.split(r"\n(?=- )", text)
    return "\n".join(f"{item} (#{name})" for item in items)


def render(paths: list[Path]) -> str:
    """The section body: one ``### <heading>`` per type that has fragments."""
    problems = check(paths)
    if problems:
        raise FragmentError("\n".join(problems))
    blocks = []
    for type_, heading in TYPES.items():
        of_type = [p for p in paths if FRAGMENT_NAME.match(p.name)["type"] == type_]
        if of_type:
            entries = "\n".join(entry(p) for p in sorted(of_type, key=_sort_key))
            blocks.append(f"### {heading}\n{entries}")
    if not blocks:
        raise FragmentError("no changelog fragments in changelog.d/")
    return "\n\n".join(blocks)


def release(changelog: str, version: str, date: str, body: str) -> str:
    """CHANGELOG.md text with the new version section and compare links."""
    if re.search(rf"^## \[{re.escape(version)}\]", changelog, re.MULTILINE):
        raise FragmentError(f"CHANGELOG.md already has a section for {version}")
    start = changelog.index(UNRELEASED)
    following = re.compile(r"^## \[(?P<previous>[^\]]+)\]", re.MULTILINE)
    previous = following.search(changelog, start + len(UNRELEASED))
    if previous is None:
        raise FragmentError("CHANGELOG.md has no released version below [Unreleased]")
    unreleased_body = changelog[start + len(UNRELEASED) : previous.start()].strip()
    section = f"## [{version}] - {date}\n\n{body}\n\n"
    text = (
        changelog[:start]
        + f"{UNRELEASED}\n\n"
        + (f"{unreleased_body}\n\n" if unreleased_body else "")
        + section
        + changelog[previous.start() :]
    )
    old_link = re.compile(r"^\[Unreleased\]: .*$", re.MULTILINE)
    links = (
        f"[Unreleased]: {REPOSITORY}/compare/v{version}...HEAD\n"
        f"[{version}]: {REPOSITORY}/compare/v{previous['previous']}...v{version}"
    )
    text, count = old_link.subn(links, text)
    if count != 1:
        raise FragmentError("CHANGELOG.md needs exactly one [Unreleased]: link")
    return text


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check")
    sub.add_parser("draft")
    rel = sub.add_parser("release")
    rel.add_argument("version")
    rel.add_argument("--date", default=dt.date.today().isoformat())
    args = parser.parse_args(argv)
    paths = fragment_paths()
    try:
        if args.command == "check":
            problems = check(paths)
            for problem in problems:
                print(f"error: {problem}", file=sys.stderr)
            return 1 if problems else 0
        body = render(paths)
        if args.command == "draft":
            print(body)
            return 0
        text = release(CHANGELOG.read_text(encoding="utf-8"), args.version, args.date, body)
        CHANGELOG.write_text(text, encoding="utf-8")
        for path in paths:
            path.unlink()
        print(f"CHANGELOG.md: added [{args.version}], removed {len(paths)} fragment(s)")
        return 0
    except FragmentError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
