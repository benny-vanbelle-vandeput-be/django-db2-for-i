"""Build the offline query corpus from raw PUB400 captures.

    python scripts/build_corpus.py <django-version> [<raw capture> ...] [--profile 7.5]

Without capture files, all of test-results/<version>/corpus/*.jsonl are used
(written by ``scripts/runtests.sh <version> --capture <label>``). The records
are grouped by Django test module (the first part of the test id), so the
labels of one module (``queries.tests``, ``queries.test_q``, ...) are combined:
build a module only from captures that cover all of its labels, because the
module's corpus file is replaced by what the captures contain.

Per module: entries are deduplicated (compiler, normalized SQL, params,
settings), stamped (an entry already stored on the same level keeps its stamp
and date; docs/proposals/offline-query-corpus.md, "Verification stamps"), and
the files are written only if their content changed. The manifest records the
Django commit, the profile and per-module counts. Captures from different
Django commits, or a commit other than the corpus's for modules that are not
rebuilt, are refused.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.corpus import store  # noqa: E402


class BuildRefused(Exception):
    """The captures cannot be combined into the corpus; nothing was written."""


def read_capture(path: Path) -> tuple[dict, list[dict]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        raise BuildRefused(f"{path}: empty capture")
    first = json.loads(lines[0])
    if "header" not in first:
        raise BuildRefused(f"{path}: no header line")
    return first["header"], [json.loads(line) for line in lines[1:] if line.strip()]


def series(version: str) -> str:
    """``6.1.3`` / ``6.1.3a0`` / ``6.1`` -> ``6.1``."""
    return ".".join(version.split(".")[:2])


def build(version: str, paths: Sequence[Path], profile: str = "7.5") -> dict[str, dict]:
    """Write the corpus files for the captures; returns the counts per module."""
    if not paths:
        raise BuildRefused(f"no captures for Django {version}")
    captures = [(path, *read_capture(path)) for path in paths]
    commits = {header["django_commit"] for _, header, _ in captures}
    if len(commits) != 1 or "unknown" in commits:
        raise BuildRefused(f"captures from more than one (or an unknown) Django commit: {commits}")
    (commit,) = commits
    for path, header, _ in captures:
        if series(header["django"]) != version:
            raise BuildRefused(f"{path}: Django {header['django']}, not {version}")

    by_module: dict[str, list[store.Entry]] = defaultdict(list)
    skipped: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    level_of: dict[str, str] = {}
    date_of: dict[str, str] = {}
    for _path, header, records in captures:
        modules_here = {store.module_of(record["tests"][0]) for record in records}
        for module in modules_here or {header.get("label", "").split(".")[0]}:
            for key in ("unpicklable", "not_compiled", "unencodable"):
                skipped[module][key] += header["counts"].get(key, 0)
        for record in records:
            module = store.module_of(record["tests"][0])
            by_module[module].append(
                store.Entry(
                    compiler=record["compiler"],
                    sql=record["sql"],
                    query=record["query"],
                    tests=list(record["tests"]),
                    settings=dict(record.get("settings", {})),
                )
            )
            level_of[module] = header["level"]
            date_of[module] = header["date"]

    directory = store.corpus_dir(version, profile)
    manifest = store.read_manifest(directory)
    others = set(manifest.get("modules", {})) - set(by_module)
    if manifest.get("django_commit") not in (None, commit) and others:
        raise BuildRefused(
            f"the corpus has modules from Django {manifest['django_commit']} "
            f"({', '.join(sorted(others))}); recapture them too, or drop them"
        )

    counts = {}
    for module, records in sorted(by_module.items()):
        entries = store.dedup(records)
        entries = store.stamp(
            entries, store.read_module(directory, module), level_of[module], date_of[module]
        )
        changed = store.write_module(directory, module, entries)
        counts[module] = {
            "recorded": len(records),
            "unique": len(entries),
            **dict(skipped[module]),
            "level": level_of[module],
            "captured": date_of[module],
        }
        print(
            f"{module}: {len(records)} recorded, {len(entries)} unique"
            f"{'' if changed else ' (unchanged)'}"
        )
    manifest = {
        "django": version,
        "django_commit": commit,
        "profile": profile,
        "modules": {**manifest.get("modules", {}), **counts},
    }
    store.write_manifest(directory, manifest)
    return counts


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("version", help="Django feature release, e.g. 6.1")
    parser.add_argument("captures", nargs="*", type=Path)
    parser.add_argument("--profile", default="7.5")
    args = parser.parse_args(argv)
    captured = ROOT / "test-results" / args.version / "corpus"
    paths = args.captures or sorted(captured.glob("*.jsonl"))
    try:
        build(args.version, paths, args.profile)
    except BuildRefused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
