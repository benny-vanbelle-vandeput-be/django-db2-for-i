"""Print the CHANGELOG.md section of one version (the GitHub release notes).

Usage: python scripts/changelog_section.py 0.1.0a2 [CHANGELOG.md]

Exits with an error if the version has no ``## [<version>]`` section or the
section is empty.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parent.parent / "CHANGELOG.md"


def section(text: str, version: str) -> str:
    """The body of ``## [<version>] ...`` up to the next ``## `` heading."""
    heading = re.compile(rf"^## \[{re.escape(version)}\](?:\s.*)?$", re.MULTILINE)
    match = heading.search(text)
    if not match:
        raise LookupError(f"CHANGELOG.md has no section for version {version}")
    following = re.compile(r"^## |^\[[^\]]+\]: ", re.MULTILINE).search(text, match.end())
    body = text[match.end() : following.start() if following else len(text)].strip()
    if not body:
        raise LookupError(f"the CHANGELOG.md section for version {version} is empty")
    return body


def main(argv: list[str]) -> int:
    if not 1 <= len(argv) <= 2:
        print(__doc__, file=sys.stderr)
        return 2
    path = Path(argv[1]) if len(argv) == 2 else CHANGELOG
    try:
        print(section(path.read_text(encoding="utf-8"), argv[0]))
    except LookupError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
