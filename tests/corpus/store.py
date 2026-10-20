"""The offline query corpus: entries, files and manifest (docs/proposals/offline-query-corpus.md).

One corpus per Django version and capability profile::

    tests/offline/corpus/<django>/<profile>/
        manifest.toml             # Django commit, capture level and date, counts per module
        queries/<module>.jsonl.gz # one JSON object per unique statement (gzip)
        queries/<module>.sql      # the unique SQL, one statement per line, for review

An entry is one statement a passing Django test sent to Db2 for i:
``tests`` (the test ids), ``compiler`` (class name), ``sql`` ([sql, params]
pairs, params tagged as in the golden files), ``query`` (base64 pickle,
protocol 5), ``settings`` (the USE_TZ / TIME_ZONE the test ran with, applied
again on replay) and ``verified`` (a golden-style stamp).

Files are deterministic: entries sorted by key, JSON with sorted keys and fixed
separators, gzip without a timestamp or file name, and a module file is only
written when its content changes, so an unchanged module stays byte-identical
and git history does not grow on every capture.
"""

from __future__ import annotations

import base64
import gzip
import io
import json
import re
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tests.golden import UNVERIFIED, encode_param, new_stamp

CORPUS_ROOT = Path(__file__).resolve().parents[1] / "offline" / "corpus"
PICKLE_PROTOCOL = 5
_WHITESPACE = re.compile(r"\s+")


def corpus_dir(django: str, profile: str = "7.5") -> Path:
    return CORPUS_ROOT / django / profile


def normalize_sql(sql: str) -> str:
    return _WHITESPACE.sub(" ", sql).strip()


def encode_statements(statements: Iterable[tuple[str, Iterable[Any]]]) -> list[list[Any]]:
    """[[sql, tagged params], ...]; raises TypeError for a param that has no tag."""
    return [[sql, [encode_param(p) for p in params]] for sql, params in statements]


@dataclass
class Entry:
    compiler: str
    sql: list[list[Any]]
    query: str
    tests: list[str] = field(default_factory=list)
    settings: dict[str, Any] = field(default_factory=dict)
    verified: str = UNVERIFIED

    @property
    def key(self) -> str:
        """Compiler class, whitespace-normalized SQL and tagged params (the dedup key)."""
        statements = [[normalize_sql(sql), params] for sql, params in self.sql]
        return json.dumps(
            [self.compiler, statements, self.settings], sort_keys=True, separators=(",", ":")
        )

    def to_json(self) -> str:
        data = {
            "compiler": self.compiler,
            "query": self.query,
            "settings": self.settings,
            "sql": self.sql,
            "tests": sorted(set(self.tests)),
            "verified": self.verified,
        }
        return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def from_json(cls, line: str) -> Entry:
        data = json.loads(line)
        return cls(
            compiler=data["compiler"],
            sql=data["sql"],
            query=data["query"],
            tests=list(data.get("tests", [])),
            settings=dict(data.get("settings", {})),
            verified=data.get("verified", UNVERIFIED),
        )


def module_of(test_id: str) -> str:
    """``ordering.tests.OrderingTests.test_x`` -> ``ordering``."""
    return test_id.split(".", 1)[0]


def dedup(entries: Iterable[Entry]) -> list[Entry]:
    """One entry per key, sorted by key: the first pickle is kept, test ids are merged."""
    by_key: dict[str, Entry] = {}
    for entry in entries:
        kept = by_key.get(entry.key)
        if kept is None:
            by_key[entry.key] = Entry(
                entry.compiler, entry.sql, entry.query, list(entry.tests), dict(entry.settings)
            )
        else:
            kept.tests = sorted(set(kept.tests) | set(entry.tests))
    return [by_key[key] for key in sorted(by_key)]


def stamp(entries: list[Entry], stored: list[Entry], level: str, today: str) -> list[Entry]:
    """Verification stamps for freshly captured ``entries`` (all from passing tests).

    An entry already stored with the same key keeps its stamp when it was verified
    on the same level (as goldens: re-stamped only when new or on another level).
    """
    previous = {entry.key: entry.verified for entry in stored}
    for entry in entries:
        current = previous.get(entry.key, UNVERIFIED)
        entry.verified = new_stamp(current, level, today) or current
    return entries


# --- Files -------------------------------------------------------------------------------


def gzip_bytes(text: str) -> bytes:
    """gzip with a fixed header (no timestamp, no file name): same text, same bytes."""
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buffer, mtime=0) as stream:
        stream.write(text.encode("utf-8"))
    return buffer.getvalue()


def render_module(entries: list[Entry]) -> tuple[bytes, str]:
    """(gzip JSONL, plain SQL index) for one module's entries, sorted by key."""
    entries = sorted(entries, key=lambda entry: entry.key)
    jsonl = "".join(entry.to_json() + "\n" for entry in entries)
    index_lines = []
    for entry in entries:
        for sql, _params in entry.sql:
            index_lines.append(normalize_sql(sql) + ";")
    return gzip_bytes(jsonl), "".join(line + "\n" for line in index_lines)


def module_paths(directory: Path, module: str) -> tuple[Path, Path]:
    queries = directory / "queries"
    return queries / f"{module}.jsonl.gz", queries / f"{module}.sql"


def read_module(directory: Path, module: str) -> list[Entry]:
    data_path, _ = module_paths(directory, module)
    if not data_path.exists():
        return []
    text = gzip.decompress(data_path.read_bytes()).decode("utf-8")
    return [Entry.from_json(line) for line in text.splitlines() if line.strip()]


def write_module(directory: Path, module: str, entries: list[Entry]) -> bool:
    """Write the module's files if their content changed; True when something was written."""
    data, index = render_module(entries)
    data_path, index_path = module_paths(directory, module)
    current_data = data_path.read_bytes() if data_path.exists() else None
    current_index = index_path.read_text(encoding="utf-8") if index_path.exists() else None
    if current_data == data and current_index == index:
        return False
    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_bytes(data)
    index_path.write_text(index, encoding="utf-8")
    return True


def modules(directory: Path) -> list[str]:
    queries = directory / "queries"
    if not queries.is_dir():
        return []
    return sorted(path.name.removesuffix(".jsonl.gz") for path in queries.glob("*.jsonl.gz"))


# --- Manifest ----------------------------------------------------------------------------


def read_manifest(directory: Path) -> dict[str, Any]:
    path = directory / "manifest.toml"
    if not path.exists():
        return {}
    return tomllib.loads(path.read_text(encoding="utf-8"))


def render_manifest(manifest: dict[str, Any]) -> str:
    """A small TOML writer for the manifest's fixed shape (strings, ints, one table per module)."""

    def value(item: Any) -> str:
        if isinstance(item, bool):
            return "true" if item else "false"
        if isinstance(item, int):
            return str(item)
        return json.dumps(str(item), ensure_ascii=False)

    lines = [
        "# Offline query corpus manifest (tests/corpus/store.py); written by",
        "# scripts/build_corpus.py from PUB400 captures. Do not edit by hand.",
    ]
    for key in ("django", "django_commit", "profile"):
        if key in manifest:
            lines.append(f"{key} = {value(manifest[key])}")
    for module in sorted(manifest.get("modules", {})):
        lines.append("")
        lines.append(f"[modules.{module}]")
        for key, item in sorted(manifest["modules"][module].items()):
            lines.append(f"{key} = {value(item)}")
    return "\n".join(lines) + "\n"


def write_manifest(directory: Path, manifest: dict[str, Any]) -> bool:
    path = directory / "manifest.toml"
    text = render_manifest(manifest)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    directory.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def encode_query(pickled: bytes) -> str:
    return base64.b64encode(pickled).decode("ascii")


def decode_query(text: str) -> bytes:
    return base64.b64decode(text)
