"""Check the approval of a lib_ probe before bin/probe runs it.

    python3 scripts/probe_approval.py <link>

A lib_ probe changes the IBM i outside QTEMP and needs the maintainer's
explicit approval for that specific probe (CLAUDE.md, "Initial test system:
PUB400"). The link is a comment on an issue or pull request of this
repository; its author must be the repository's owner, never the machine
account. Prints the approver's login and exits 0, or explains and exits 1.
Reads GitHub through ``gh api``; runs with the host's Python (3.9 or newer).
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "probes"))
from _common import APPROVAL_URL, REPOSITORY

MACHINE_ACCOUNT = "claude-v-belle-net"


class ApprovalError(Exception):
    pass


def gh_api(path: str) -> dict[str, Any]:
    result = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    if result.returncode != 0:
        raise ApprovalError(f"cannot read {path} from GitHub: {result.stderr.strip()[:200]}")
    return json.loads(result.stdout)


def check(url: str, fetch: Callable[[str], dict[str, Any]] = gh_api) -> str:
    """The approver's login, or ApprovalError."""
    match = APPROVAL_URL.match(url)
    if not match:
        raise ApprovalError(
            f"not a link to a comment in {REPOSITORY}: {url!r} "
            f"(https://github.com/{REPOSITORY}/pull/<n>#issuecomment-<id>)"
        )
    comment = fetch(f"repos/{REPOSITORY}/issues/comments/{match.group(1)}")
    if comment.get("html_url") != url:
        raise ApprovalError(f"the comment is not at {url} (it is at {comment.get('html_url')})")
    author = (comment.get("user") or {}).get("login", "")
    owner = fetch(f"repos/{REPOSITORY}")["owner"]["login"]
    if author == MACHINE_ACCOUNT or author != owner:
        raise ApprovalError(f"the comment is by {author!r}, not by the maintainer ({owner})")
    return author


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 1
    try:
        print(check(argv[0]))
    except ApprovalError as exc:
        print(f"probe approval: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
