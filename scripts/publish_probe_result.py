"""Copy a probe result into the repository, without host, user or library names.

    python scripts/publish_probe_result.py test-results/probes/<probe>-<utc>.json

Runs in the tests container (bin/probe --publish), where the connection
settings come from .env as environment variables. Raw probe output that a
decision rests on is kept in probes/results/<probe>.json (CLAUDE.md): the
local results in test-results/ are gitignored and vanish with a worktree.

The values of DB2I_HOST, DB2I_USER, DB2I_DEFAULT_LIBRARY and
DB2I_OTHER_LIBRARY are replaced by <HOST>, <USER>, <DEFAULT_LIBRARY> and
<OTHER_LIBRARY> (longest first, case-insensitively: a library name often
starts with the user name); the password was already scrubbed when the
result was written. The script refuses to write anything if one of the
values is still found afterwards, and never prints them.
"""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "probes" / "results"
PLACEHOLDERS = {
    "DB2I_HOST": "<HOST>",
    "DB2I_DEFAULT_LIBRARY": "<DEFAULT_LIBRARY>",
    "DB2I_OTHER_LIBRARY": "<OTHER_LIBRARY>",
    "DB2I_USER": "<USER>",
}
# "<probe>-<YYYYmmddTHHMMSSZ>.json" -> "<probe>"
_NAME = re.compile(r"^(?P<probe>.+)-\d{8}T\d{6}Z\.json$")


class Refused(Exception):
    """Nothing was written."""


def secrets(environ: Mapping[str, str]) -> list[tuple[str, str]]:
    """(value, placeholder) pairs, longest value first; empty values are skipped."""
    pairs = [
        (environ.get(name, "").strip(), placeholder) for name, placeholder in PLACEHOLDERS.items()
    ]
    return sorted([pair for pair in pairs if pair[0]], key=lambda pair: -len(pair[0]))


def clean(text: str, environ: Mapping[str, str]) -> str:
    pairs = secrets(environ)
    for value, placeholder in pairs:
        text = re.sub(re.escape(value), placeholder, text, flags=re.IGNORECASE)
    if any(value.lower() in text.lower() for value, _ in pairs):
        raise Refused("a host, user or library name is still in the result")
    if "PWD=" in text.upper() or "password" in text.lower():
        raise Refused("the result mentions a password or connection string")
    return text


def target(path: Path) -> Path:
    match = _NAME.match(path.name)
    if not match:
        raise Refused(f"not a probe result name (<probe>-<utc>.json): {path.name}")
    return RESULTS / f"{match['probe']}.json"


def publish(path: Path, environ: Mapping[str, str]) -> Path:
    if not environ.get("DB2I_HOST"):
        raise Refused("DB2I_HOST is not set: run it in the tests container (bin/probe --publish)")
    destination = target(path)
    text = clean(path.read_text(encoding="utf-8"), environ)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")
    return destination


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    try:
        destination = publish(Path(argv[0]), os.environ)
    except (Refused, OSError) as exc:
        print(f"refused, nothing written: {exc}", file=sys.stderr)
        return 1
    print(f"written: {destination.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
