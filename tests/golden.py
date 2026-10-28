"""Golden files: format, parameter encoding and paths.

A golden file holds the SQL the backend generates for one case, for one
Django series and one capability profile::

    -- golden: queries/slice_offset_fetch
    -- django: 6.1
    -- profile: 7.5
    -- depends: ddl/create_author
    -- params: [[]]
    -- verified: unverified
    SELECT ... OFFSET 1 ROWS FETCH FIRST 2 ROWS ONLY;

``params`` holds one JSON list per statement; values JSON cannot express are
tagged (``{"$datetime": ...}``). ``verified`` is ``unverified`` or
``IBM i <release> on PUB400, <date>`` and means "accepted by Db2 for i" (see
CONTRIBUTING.md). Any change to the SQL or the params resets it.
"""

from __future__ import annotations

import base64
import dataclasses
import datetime as dt
import json
import re
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

GOLDEN_ROOT = Path(__file__).parent / "offline" / "golden"
UNVERIFIED = "unverified"
# "<level>, <date>": the level is the system and Django version the golden was
# verified with; older stamps have no TR / PTF Group / Django part.
VERIFIED_PATTERN = re.compile(
    r"^(?P<level>IBM i \d+\.\d+ on PUB400"
    r"(?: \(TR [^,()]+, Db2 PTF Group [^()]+\), Django [\w.]+)?)"
    r", (?P<date>\d{4}-\d{2}-\d{2})$"
)
# The latest verification run (date, level, counts): one file, so a run on the
# same level does not touch every golden.
LAST_VERIFICATION = GOLDEN_ROOT / "last-verification.txt"
HEADER_KEYS = ("golden", "django", "profile", "depends", "params", "verified")


@dataclasses.dataclass(frozen=True)
class Golden:
    name: str  # "<group>/<name>"
    django: str
    profile: str
    depends: tuple[str, ...]
    statements: tuple[tuple[str, tuple], ...]  # (sql, params)
    verified: str = UNVERIFIED

    @property
    def path(self) -> Path:
        return golden_path(self.django, self.profile, self.name)

    def content_equals(self, other: Golden) -> bool:
        """Same SQL and params (the verification status is not compared)."""
        return encode_statements(self.statements) == encode_statements(other.statements)

    def render(self) -> str:
        sql_list, params_list = encode_statements(self.statements)
        lines = [
            f"-- golden: {self.name}",
            f"-- django: {self.django}",
            f"-- profile: {self.profile}",
            f"-- depends: {', '.join(self.depends) if self.depends else '-'}",
            f"-- params: {json.dumps(params_list, ensure_ascii=False)}",
            f"-- verified: {self.verified}",
        ]
        lines.extend(f"{sql};" for sql in sql_list)
        return "\n".join(lines) + "\n"


def golden_path(django: str, profile: str, name: str) -> Path:
    return GOLDEN_ROOT / django / profile / f"{name}.sql"


def parse(text: str) -> Golden:
    header: dict[str, str] = {}
    body: list[str] = []
    for line in text.splitlines():
        if line.startswith("-- ") and not body and ":" in line:
            key, _, value = line[3:].partition(":")
            header[key.strip()] = value.strip()
        elif line.strip():
            body.append(line)
    missing = [key for key in HEADER_KEYS if key not in header]
    if missing:
        raise ValueError(f"golden header lacks {', '.join(missing)}")
    sql_list = [s.strip() for s in "\n".join(body).split(";\n")]
    sql_list = [s.removesuffix(";").strip() for s in sql_list if s.strip()]
    params_list = json.loads(header["params"])
    if len(params_list) != len(sql_list):
        raise ValueError("golden has a different number of statements and params lists")
    depends = (
        ()
        if header["depends"] == "-"
        else tuple(part.strip() for part in header["depends"].split(","))
    )
    return Golden(
        name=header["golden"],
        django=header["django"],
        profile=header["profile"],
        depends=depends,
        statements=tuple(
            (sql, tuple(decode_param(p) for p in params))
            for sql, params in zip(sql_list, params_list, strict=True)
        ),
        verified=header["verified"],
    )


def read(path: Path) -> Golden:
    return parse(path.read_text())


def encode_statements(statements) -> tuple[list[str], list[list[Any]]]:
    return (
        [sql for sql, _ in statements],
        [[encode_param(p) for p in params] for _, params in statements],
    )


def encode_param(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dt.datetime):
        if value.tzinfo is not None:
            raise ValueError("aware datetime in golden params; the backend sends naive values")
        return {"$datetime": value.isoformat()}
    if isinstance(value, dt.date):
        return {"$date": value.isoformat()}
    if isinstance(value, dt.time):
        return {"$time": value.isoformat()}
    if isinstance(value, Decimal):
        return {"$decimal": str(value)}
    if isinstance(value, uuid.UUID):
        return {"$uuid": str(value)}
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"$bytes": base64.b64encode(bytes(value)).decode()}
    raise TypeError(f"cannot store {type(value).__name__} in a golden file")


def decode_param(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    ((tag, text),) = value.items()
    return {
        "$datetime": dt.datetime.fromisoformat,
        "$date": dt.date.fromisoformat,
        "$time": dt.time.fromisoformat,
        "$decimal": Decimal,
        "$uuid": uuid.UUID,
        "$bytes": base64.b64decode,
    }[tag](text)


def all_golden_paths() -> list[Path]:
    return sorted(GOLDEN_ROOT.rglob("*.sql"))


def merge(stored: Golden | None, generated: Golden) -> Golden:
    """The golden to write for ``generated``, given the stored one.

    The verification status survives only if the SQL and the params are
    unchanged; any change resets it to unverified.
    """
    if stored is not None and stored.content_equals(generated):
        return dataclasses.replace(generated, verified=stored.verified)
    return dataclasses.replace(generated, verified=UNVERIFIED)


# --- Verification stamps ---------------------------------------------------------------


def verification_level(release: str, tr: str, ptf_group: str, django_version: str) -> str:
    return (
        f"IBM i {release} on PUB400 (TR {tr}, Db2 PTF Group {ptf_group}), Django {django_version}"
    )


def new_stamp(current: str, level: str, today: str) -> str | None:
    """The stamp to write after ``current`` passed on ``level``, or None to keep it.

    A golden is stamped when it is unverified (new, or its SQL / params changed)
    or was verified on another system level or Django version; otherwise its
    stamp, and its date, stay as they are.
    """
    match = VERIFIED_PATTERN.match(current)
    if match and match["level"] == level:
        return None
    return f"{level}, {today}"


def render_last_verification(level: str, today: str, results: dict[str, str]) -> str:
    counts = {
        outcome: sum(1 for r in results.values() if r == outcome)
        for outcome in ("passed", "failed", "skipped")
    }
    return (
        "# Latest golden verification run (tests/ibmi/test_goldens.py --record-verification)\n"
        f"date: {today}\n"
        f"level: {level}\n"
        f"passed: {counts['passed']}\n"
        f"failed: {counts['failed']}\n"
        f"skipped: {counts['skipped']}\n"
    )
