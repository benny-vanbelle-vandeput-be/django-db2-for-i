"""Server axis: what this Db2 for i server can do (ServerCapabilities).

The only module allowed to compare IBM i releases, TR or PTF levels.
Knows nothing about drivers; it gets the server version string and, for
targeted probes, a callable that runs one SQL statement.

Capabilities come from one of two sources:

- **Detection** (default): the OS release from the server version string
  (e.g. ``07.05.0015``) selects a profile; targeted probes then check
  capabilities that depend on a Technology Refresh or Db2 PTF Group level
  (PTF levels cannot be read by normal users, see docs/IBMI_NOTES.md).
  Results are cached per server.
- **A configured profile** (``OPTIONS["capabilities"]``), which needs no
  connection at all; the offline test tier uses this.

In both cases individual capabilities can be overridden::

    "OPTIONS": {"capabilities": "7.5"}
    "OPTIONS": {"capabilities": {"profile": "7.5", "has_json_functions": False}}
    "OPTIONS": {"capabilities": {"has_json_functions": False}}  # detect, then override
"""

from __future__ import annotations

import dataclasses
import logging
import re
from collections.abc import Callable, Mapping
from typing import Any

MINIMUM_RELEASE = (7, 5)

logger = logging.getLogger("django_db2_for_i")


class CapabilityError(ValueError):
    """Invalid capability configuration or unsupported server."""


@dataclasses.dataclass(frozen=True)
class ServerCapabilities:
    release: tuple[int, int]
    # BOOLEAN data type (otherwise SMALLINT + CHECK would be needed).
    has_boolean_type: bool
    # LIMIT n OFFSET m.
    has_limit_offset: bool
    # OFFSET m ROWS FETCH FIRST n ROWS ONLY.
    has_offset_fetch: bool
    # JSON_OBJECT, JSON_VALUE, JSON_TABLE.
    has_json_functions: bool
    # QSYS2.OVERRIDE_QAQQINI with the QAQQINI option SUPPRESS_INQUIRY_MESSAGES:
    # a job can skip inquiry message CPA32B2 for its own ALTER TABLE (7.5 and
    # 7.6 base; 7.4 needs SF99704 levels 4 and 7).
    can_suppress_inquiry_messages: bool
    # Longest SQL name for tables, columns, indexes and constraints.
    max_name_length: int
    # Longest system (object) name, e.g. for schemas/libraries.
    max_system_name_length: int
    # Where the values came from, for diagnostics (e.g. "profile 7.5").
    source: str = dataclasses.field(default="", compare=False)

    @property
    def release_name(self) -> str:
        return f"{self.release[0]}.{self.release[1]}"


CAPABILITY_FIELDS = {
    field.name: field.type
    for field in dataclasses.fields(ServerCapabilities)
    if field.name not in ("release", "source")
}

# Profiles per OS release. Values must be backed by evidence:
# 7.5: probe `features` on PUB400 (IBM i 7.5, TR level not readable),
#      2026-10-17; name lengths from SQLGetInfo and IBM i system names;
#      can_suppress_inquiry_messages from probe `qaqqini_inquiry`, 2026-10-25.
PROFILES: Mapping[str, Mapping[str, Any]] = {
    "7.5": {
        "release": (7, 5),
        "has_boolean_type": True,
        "has_limit_offset": True,
        "has_offset_fetch": True,
        "has_json_functions": True,
        "can_suppress_inquiry_messages": True,
        "max_name_length": 128,
        "max_system_name_length": 10,
    },
}


@dataclasses.dataclass(frozen=True)
class FeatureProbe:
    """A capability that depends on TR / PTF level: True if ``sql`` succeeds."""

    capability: str
    sql: str


# Capabilities whose availability within a supported release depends on the
# TR or Db2 PTF Group level. None so far: everything in the 7.5 profile is
# available on 7.5 itself.
TARGETED_PROBES: tuple[FeatureProbe, ...] = ()

_VERSION = re.compile(r"^\s*(\d{1,2})\.(\d{1,2})\.(\d+)\s*$")


def parse_release(server_version: str) -> tuple[int, int]:
    """``07.05.0015`` (SQL_DBMS_VER, VV.RR.MMMM) -> ``(7, 5)``."""
    match = _VERSION.match(server_version)
    if not match:
        raise CapabilityError(f"unrecognized server version {server_version!r}")
    return int(match.group(1)), int(match.group(2))


def profile_for_release(release: tuple[int, int]) -> str:
    """The profile for a release: exact, else the newest older one."""
    if release < MINIMUM_RELEASE:
        minimum = ".".join(map(str, MINIMUM_RELEASE))
        raise CapabilityError(
            f"IBM i {release[0]}.{release[1]} is not supported (minimum {minimum})"
        )
    known = sorted((values["release"], name) for name, values in PROFILES.items())
    return [name for profile_release, name in known if profile_release <= release][-1]


def from_profile(name: str, overrides: Mapping[str, Any] | None = None) -> ServerCapabilities:
    if name not in PROFILES:
        raise CapabilityError(
            f"unknown capability profile {name!r}; known: {', '.join(sorted(PROFILES))}"
        )
    return _build(dict(PROFILES[name]), overrides, f"profile {name}")


def _build(
    values: dict[str, Any], overrides: Mapping[str, Any] | None, source: str
) -> ServerCapabilities:
    overrides = dict(overrides or {})
    for key, value in overrides.items():
        expected = CAPABILITY_FIELDS.get(key)
        if expected is None:
            raise CapabilityError(f"unknown capability {key!r}")
        python_type = bool if expected == "bool" else int
        # bool is a subclass of int: reject True/False for integer capabilities.
        if type(value) is not python_type:
            raise CapabilityError(f"capability {key!r} must be {expected}, not {value!r}")
    if overrides:
        source = f"{source}, overrides: {', '.join(sorted(overrides))}"
    return ServerCapabilities(**(values | overrides), source=source)


# --- Configuration ----------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class CapabilityConfig:
    """Parsed ``OPTIONS["capabilities"]``."""

    profile: str | None = None
    overrides: Mapping[str, Any] = dataclasses.field(default_factory=dict)

    @property
    def needs_detection(self) -> bool:
        return self.profile is None

    @classmethod
    def from_option(cls, value: Any) -> CapabilityConfig:
        if value is None:
            return cls()
        if isinstance(value, str):
            from_profile(value)  # Validate early.
            return cls(profile=value)
        if isinstance(value, Mapping):
            values = dict(value)
            profile = values.pop("profile", None)
            if profile is not None and not isinstance(profile, str):
                raise CapabilityError("capabilities 'profile' must be a string")
            # Validate early, also when detection happens later.
            if profile is not None:
                from_profile(profile, values)
            else:
                _build(dict(PROFILES[_newest_profile()]), values, "")
            return cls(profile=profile, overrides=values)
        raise CapabilityError("OPTIONS['capabilities'] must be a profile name or a mapping")

    def build(self) -> ServerCapabilities:
        """Capabilities without a connection; only for a configured profile."""
        if self.profile is None:
            raise CapabilityError("no capability profile configured; detection is required")
        return from_profile(self.profile, self.overrides)


def _newest_profile() -> str:
    return max(PROFILES, key=lambda name: PROFILES[name]["release"])


# --- Detection --------------------------------------------------------------------

_cache: dict[tuple[str, str], ServerCapabilities] = {}


def detect(
    server_version: str,
    run_probe: Callable[[str], bool],
    overrides: Mapping[str, Any] | None = None,
    cache_key: str | None = None,
) -> ServerCapabilities:
    """Capabilities of a server from its version string and targeted probes.

    ``run_probe(sql)`` returns True if the statement succeeds. Results are
    cached per ``(cache_key, server_version)`` when ``cache_key`` is given;
    overrides are applied after the cache.
    """
    key = (cache_key, server_version) if cache_key is not None else None
    detected = _cache.get(key) if key else None
    if detected is None:
        release = parse_release(server_version)
        name = profile_for_release(release)
        if release > PROFILES[name]["release"]:
            logger.warning(
                "IBM i %d.%d has no capability profile yet; using profile %s. "
                "Capabilities added in %d.%d are not used.",
                *release,
                name,
                *release,
            )
        values = dict(PROFILES[name])
        values["release"] = release
        for probe in TARGETED_PROBES:
            values[probe.capability] = bool(run_probe(probe.sql))
        detected = ServerCapabilities(
            **values, source=f"detected {server_version.strip()} (profile {name})"
        )
        if key:
            _cache[key] = detected
    if not overrides:
        return detected
    values = {f.name: getattr(detected, f.name) for f in dataclasses.fields(detected)}
    source = values.pop("source")
    return _build(values, overrides, source)


def clear_cache() -> None:
    _cache.clear()
