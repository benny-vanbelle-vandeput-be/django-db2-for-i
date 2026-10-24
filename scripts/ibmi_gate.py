"""The IBM i gate: the commit status ``ibmi-gate`` of a pull request's head.

    python scripts/ibmi_gate.py --base origin/main --head <sha> --comments <file>

Red ("failure") while the pull request's classification (scripts/classify_pr.py)
needs an IBM i run and no posted run result covers the current content; green
("success") for docs/tests only, or when a result covers the head. Labels can
be missing or removed by mistake; this status cannot (CLAUDE.md, "Git
workflow").

A run result is a PR comment whose first line is the marker

    <!-- ibmi-run sha=<40 hex> tier=targeted|full -->

by the machine account or the maintainer (anyone else's comment is ignored).
It covers the head when ``sha`` is the head, or when the push from ``sha`` to
the head needs no new run by the exceptions of ``classify_pr.py --before``
(verification stamps only, docs/tests only, an identical rebase onto
docs/tests-only commits). ``tier=targeted`` does not cover a pull request that
needs the full tier. The maintainer may waive the gate for a commit:

    <!-- ibmi-run sha=<40 hex> waived -->

``.github/workflows/ibmi-gate.yml`` runs this file from main
(pull_request_target, issue_comment), never from the pull request: the pull
request is only data (its commits, read with git). The comments file is the
JSON list of the PR's comments from the GitHub API. Prints JSON:
``{"state": "success" | "failure", "description": ...}``.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import subprocess
import sys
from collections.abc import Callable, Iterable

import classify_pr as cp

CONTEXT = "ibmi-gate"
MACHINE_ACCOUNT = "claude-v-belle-net"
MAINTAINER = "benny-vanbelle-vandeput-be"
TARGETED, FULL = "targeted", "full"
_MARKER = re.compile(
    r"\A<!-- ibmi-run sha=(?P<sha>[0-9a-f]{40}) "
    r"(?:tier=(?P<tier>targeted|full)|(?P<waived>waived)) -->"
)


@dataclasses.dataclass(frozen=True)
class Result:
    """A posted IBM i run result (or a maintainer's waiver) for one commit."""

    sha: str
    tier: str | None  # None for a waiver
    author: str

    @property
    def waived(self) -> bool:
        return self.tier is None


@dataclasses.dataclass(frozen=True)
class Verdict:
    state: str  # "success" or "failure"
    description: str


def marker(sha: str, tier: str) -> str:
    """The first line of a run result comment."""
    return f"<!-- ibmi-run sha={sha} tier={tier} -->"


def results(comments: Iterable[dict]) -> list[Result]:
    """The run results among the PR's comments, oldest first: only markers on
    the first line, by the machine account or the maintainer; a waiver only by
    the maintainer."""
    found = []
    for comment in comments:
        author = (comment.get("user") or {}).get("login", "")
        match = _MARKER.match(comment.get("body") or "")
        if not match or author not in (MACHINE_ACCOUNT, MAINTAINER):
            continue
        if match["waived"] and author != MAINTAINER:
            continue
        found.append(Result(match["sha"], match["tier"], author))
    return found


def decide(
    classification: cp.Classification,
    head: str,
    posted: list[Result],
    push_check: Callable[[str, str], cp.PushCheck],
) -> Verdict:
    labels = classification.labels
    if not labels:
        return Verdict("success", "docs/tests only: no IBM i run needed")
    needed = FULL if cp.FULL_TIER_LABEL in labels else TARGETED
    for result in reversed(posted):  # the newest first
        if not result.waived and needed == FULL and result.tier != FULL:
            continue
        if result.sha == head:
            reason = "covers this commit"
        else:
            check = push_check(result.sha, head)
            if check.new_run_needed:
                continue
            reason = check.reason
        what = "waived by the maintainer" if result.waived else f"{result.tier} run on"
        return Verdict("success", f"{what} {result.sha[:7]}: {reason}")
    return Verdict(
        "failure", f"needs a {needed} IBM i run ({', '.join(labels)}); no posted result covers it"
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--head", required=True, help="the pull request's head commit")
    parser.add_argument("--comments", required=True, help="the PR's comments (GitHub API JSON)")
    args = parser.parse_args(argv)
    with open(args.comments, encoding="utf-8") as handle:
        comments = json.load(handle)
    try:
        merge_base = cp.git("merge-base", args.base, args.head).strip()
        classification = cp.classify_refs(merge_base, args.head)
        verdict = decide(
            classification,
            args.head,
            results(comments),
            lambda before, head: cp.check_push(before, head, args.base),
        )
    except subprocess.CalledProcessError as exc:
        verdict = Verdict("failure", f"git {' '.join(exc.cmd[1:3])} failed; rerun the gate")
    # A status description holds at most 140 characters.
    print(json.dumps({"state": verdict.state, "description": verdict.description[:140]}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
