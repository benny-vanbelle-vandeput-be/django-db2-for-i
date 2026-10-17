"""Server capabilities: profiles, detection, overrides (no server needed)."""

import re

import pytest

from django_db2_for_i import capabilities
from django_db2_for_i.capabilities import (
    CapabilityConfig,
    CapabilityError,
    FeatureProbe,
    ServerCapabilities,
)


@pytest.fixture(autouse=True)
def _fresh_cache():
    capabilities.clear_cache()
    yield
    capabilities.clear_cache()


def no_probes(sql: str) -> bool:
    raise AssertionError(f"unexpected probe: {sql}")


# --- Profiles --------------------------------------------------------------------


def test_profile_7_5() -> None:
    caps = capabilities.from_profile("7.5")
    assert caps == ServerCapabilities(
        release=(7, 5),
        has_boolean_type=True,
        has_limit_offset=True,
        has_offset_fetch=True,
        has_json_functions=True,
        max_name_length=128,
        max_system_name_length=10,
    )
    assert caps.release_name == "7.5"
    assert caps.source == "profile 7.5"


def test_every_profile_defines_every_capability() -> None:
    expected = set(capabilities.CAPABILITY_FIELDS) | {"release"}
    for name, values in capabilities.PROFILES.items():
        assert set(values) == expected, name


def test_unknown_profile() -> None:
    with pytest.raises(CapabilityError, match=re.escape("unknown capability profile '7.4'")):
        capabilities.from_profile("7.4")


def test_profile_overrides() -> None:
    caps = capabilities.from_profile("7.5", {"has_json_functions": False})
    assert caps.has_json_functions is False
    assert caps.has_boolean_type is True
    assert caps.source == "profile 7.5, overrides: has_json_functions"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"has_jsn_functions": False}, "unknown capability 'has_jsn_functions'"),
        ({"has_boolean_type": 1}, "must be bool"),
        ({"max_name_length": "128"}, "must be int"),
        ({"max_name_length": True}, "must be int"),
        ({"release": (7, 6)}, "unknown capability 'release'"),
    ],
)
def test_invalid_overrides(overrides: dict, message: str) -> None:
    with pytest.raises(CapabilityError, match=message):
        capabilities.from_profile("7.5", overrides)


# --- Releases -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("version", "release"),
    [("07.05.0015", (7, 5)), ("07.06.0000", (7, 6)), (" 7.5.0 ", (7, 5))],
)
def test_parse_release(version: str, release: tuple[int, int]) -> None:
    assert capabilities.parse_release(version) == release


@pytest.mark.parametrize("version", ["", "V7R5M0", "07.05", "DB2/400 SQL"])
def test_parse_release_rejects_garbage(version: str) -> None:
    with pytest.raises(CapabilityError, match="unrecognized server version"):
        capabilities.parse_release(version)


def test_profile_for_release() -> None:
    assert capabilities.profile_for_release((7, 5)) == "7.5"
    # A newer release uses the newest known profile.
    assert capabilities.profile_for_release((7, 6)) == "7.5"


@pytest.mark.parametrize("release", [(7, 4), (7, 3), (6, 1)])
def test_profile_for_release_below_minimum(release: tuple[int, int]) -> None:
    with pytest.raises(CapabilityError, match=re.escape("not supported (minimum 7.5)")):
        capabilities.profile_for_release(release)


# --- Detection ------------------------------------------------------------------


def test_detect_7_5() -> None:
    caps = capabilities.detect("07.05.0015", no_probes)
    assert caps == capabilities.from_profile("7.5")
    assert caps.source == "detected 07.05.0015 (profile 7.5)"


def test_detect_newer_release_warns(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("WARNING", logger="django_db2_for_i"):
        caps = capabilities.detect("07.06.0000", no_probes)
    assert caps.release == (7, 6)
    assert caps.has_boolean_type is True
    assert "IBM i 7.6 has no capability profile yet; using profile 7.5" in caplog.text


def test_detect_known_release_does_not_warn(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("WARNING", logger="django_db2_for_i"):
        capabilities.detect("07.05.0015", no_probes)
    assert caplog.text == ""


def test_detect_unsupported_release() -> None:
    with pytest.raises(CapabilityError, match=re.escape("IBM i 7.4 is not supported")):
        capabilities.detect("07.04.0000", no_probes)


def test_detect_runs_targeted_probes(monkeypatch: pytest.MonkeyPatch) -> None:
    probes = (
        FeatureProbe("has_json_functions", "VALUES JSON_OBJECT('a' VALUE 1)"),
        FeatureProbe("has_limit_offset", "VALUES 1 LIMIT 1"),
    )
    monkeypatch.setattr(capabilities, "TARGETED_PROBES", probes)
    seen = []

    def run_probe(sql: str) -> bool:
        seen.append(sql)
        return "JSON" not in sql

    caps = capabilities.detect("07.05.0015", run_probe)
    assert seen == [probe.sql for probe in probes]
    assert caps.has_json_functions is False
    assert caps.has_limit_offset is True


def test_detect_caches_per_server(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        capabilities, "TARGETED_PROBES", (FeatureProbe("has_json_functions", "VALUES 1"),)
    )
    calls = []

    def run_probe(sql: str) -> bool:
        calls.append(sql)
        return True

    first = capabilities.detect("07.05.0015", run_probe, cache_key="ibmi.example.com")
    second = capabilities.detect("07.05.0015", run_probe, cache_key="ibmi.example.com")
    assert first is second
    assert len(calls) == 1
    capabilities.detect("07.05.0015", run_probe, cache_key="other.example.com")
    assert len(calls) == 2


def test_detect_overrides_after_cache() -> None:
    capabilities.detect("07.05.0015", no_probes, cache_key="h")
    caps = capabilities.detect("07.05.0015", no_probes, {"has_boolean_type": False}, "h")
    assert caps.has_boolean_type is False
    assert caps.source == "detected 07.05.0015 (profile 7.5), overrides: has_boolean_type"
    # The cached detection itself is unchanged.
    assert capabilities.detect("07.05.0015", no_probes, cache_key="h").has_boolean_type


# --- OPTIONS -----------------------------------------------------------------------


def test_config_absent_means_detection() -> None:
    config = CapabilityConfig.from_option(None)
    assert config.needs_detection
    with pytest.raises(CapabilityError, match="detection is required"):
        config.build()


def test_config_profile_name() -> None:
    config = CapabilityConfig.from_option("7.5")
    assert not config.needs_detection
    assert config.build() == capabilities.from_profile("7.5")


def test_config_profile_with_overrides() -> None:
    config = CapabilityConfig.from_option({"profile": "7.5", "has_offset_fetch": False})
    assert config.build().has_offset_fetch is False


def test_config_overrides_only() -> None:
    config = CapabilityConfig.from_option({"has_json_functions": False})
    assert config.needs_detection
    assert config.overrides == {"has_json_functions": False}


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("7.4", "unknown capability profile"),
        ({"profile": "7.4"}, "unknown capability profile"),
        ({"profile": 7.5}, "'profile' must be a string"),
        ({"has_jsn": True}, "unknown capability 'has_jsn'"),
        (["7.5"], "must be a profile name or a mapping"),
    ],
)
def test_config_invalid(value, message: str) -> None:
    with pytest.raises(CapabilityError, match=message):
        CapabilityConfig.from_option(value).build()
