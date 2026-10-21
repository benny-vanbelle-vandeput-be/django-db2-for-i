"""The verification gate: no golden or corpus entry without a verification stamp.

    python -m tests.verification_gate      (nox -s gate; CI, as part of the offline check)

Every golden (``tests/offline/golden/``) and every corpus entry
(``tests/offline/corpus/``) must carry a verification stamp, except the goldens
in ``tests/offline/golden/unverifiable.toml``, which cannot be verified on the
test system (each with its reason and the condition under which it becomes
verifiable). An entry there that is no longer needed (the golden is verified
or gone) fails the gate too, so the list cannot go stale.

It is a separate nox session, not part of ``nox -s offline``: a pull request
that adds or changes SQL is pushed before its IBM i run, so the local offline
tier (run before every push) must pass while the gate keeps the pull request
red until the stamps are committed (phase 4 decision 15).
"""

from __future__ import annotations

import dataclasses
import gzip
import json
import sys
import tomllib
from pathlib import Path

from tests.golden import GOLDEN_ROOT, UNVERIFIED, read

CORPUS_ROOT = GOLDEN_ROOT.parent / "corpus"
UNVERIFIABLE = GOLDEN_ROOT / "unverifiable.toml"
FIX = "run bin/verify or request run-ibmi"
REQUIRED = ("name", "django", "reason", "verifiable_when")
ROOT = GOLDEN_ROOT.parents[2]


@dataclasses.dataclass(frozen=True)
class Unverifiable:
    name: str
    django: tuple[str, ...]
    reason: str
    verifiable_when: str


def load_unverifiable(path: Path = UNVERIFIABLE) -> list[Unverifiable]:
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    entries = []
    for raw in data.get("golden", []):
        missing = [key for key in REQUIRED if not raw.get(key)]
        if missing:
            name = raw.get("name", "?")
            raise ValueError(f"{path.name}: entry {name!r} lacks {', '.join(missing)}")
        entries.append(
            Unverifiable(raw["name"], tuple(raw["django"]), raw["reason"], raw["verifiable_when"])
        )
    return entries


def reasons(django: str, path: Path = UNVERIFIABLE) -> dict[str, str]:
    """Golden name -> reason, for one Django series (the IBM i test's expected failures)."""
    return {e.name: e.reason for e in load_unverifiable(path) if django in e.django}


def _shown(path: Path) -> str:
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def check(
    golden_root: Path = GOLDEN_ROOT,
    corpus_root: Path = CORPUS_ROOT,
    unverifiable: Path = UNVERIFIABLE,
) -> list[str]:
    """The problems found; empty when the gate passes."""
    allowed = {(django, e.name): e for e in load_unverifiable(unverifiable) for django in e.django}
    problems, used = [], set()
    for path in sorted(golden_root.rglob("*.sql")):
        golden = read(path)
        key = (golden.django, golden.name)
        if golden.verified != UNVERIFIED:
            continue
        if key in allowed:
            used.add(key)
            continue
        where = _shown(path)
        problems.append(
            f"golden {golden.django}/{golden.profile} {golden.name} ({where}) has no "
            f"verification stamp: {FIX}"
        )
    for django, name in sorted(allowed):
        if (django, name) not in used:
            problems.append(
                f"{unverifiable.name}: {name} (Django {django}) is no longer needed, the golden "
                f"is verified or gone: remove it from the entry"
            )
    for path in sorted(corpus_root.rglob("*.jsonl.gz")):
        lines = gzip.decompress(path.read_bytes()).decode().splitlines()
        unstamped = sum(
            1
            for line in lines
            if line.strip() and json.loads(line).get("verified", UNVERIFIED) == UNVERIFIED
        )
        if unstamped:
            where = _shown(path)
            problems.append(
                f"corpus {where}: {unstamped} entries without a verification stamp: {FIX}"
            )
    return problems


def summary(unverifiable: Path = UNVERIFIABLE) -> int:
    """The number of allow-listed goldens (one per Django series), for TEST_STATUS."""
    return sum(len(entry.django) for entry in load_unverifiable(unverifiable))


def main() -> int:
    problems = check()
    for problem in problems:
        print(f"error: {problem}")
    if problems:
        print(f"verification gate: {len(problems)} problem(s)")
        return 1
    print(f"verification gate: passed (unverifiable on PUB400: {summary()})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
