"""Generate docs/TEST_STATUS.md, the test badges and README's generated sections.

    nox -s test_status

Inputs:

- test-results/<django-version>/<module>.log (and labels/<label>.log), written
  by scripts/run_django_tests.py: the "Django suite on IBM i" runs, per
  module and Django version, from Django's test runner summary;
- test-results/<django-version>/sets/*.json, written by pytest
  ``--results-summary`` (tests/results_summary.py; the nox sessions pass it):
  ``offline-py<python>.json`` ("Offline tests", the newest Python's file
  counts), ``pub400.json`` ("IBM i tests") and ``corpus.json``
  ("Replay tests", counted per corpus entry);
- docs/status.toml: the IBM i, Python and Django versions with their state,
  the phases with their steps, releases and open tracks;
- docs/features/<django-version>.json (scripts/features.py): the number of
  enabled feature flags.

Outputs:

- README.md, between marker comments (the rest is hand-written):
  ``badges`` (release, license, CI, one badge per IBM i / Python / Django
  version with its state, and the legend), ``tests`` ("Test status": per
  supported or in-development Django version the four test sets with their
  totals as badges, then "About the tests") and ``status`` ("Project
  status": the current phase with its steps, the phase table, the latest
  release and the open tracks);
- docs/badges/<django-version>/{passed,skipped,xfail,failed}.json: shields.io
  endpoint files with the sums of that version's test-set table. Files of
  versions no longer shown, and the old top-level and ``modules`` badges, are
  removed;
- docs/TEST_STATUS.md: the same test-set tables, the definitions, the run
  header, every Django test module per version, the feature flags and
  reasons, and the golden-file status.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import re
import shutil
import sys
import tomllib
import urllib.parse
from collections.abc import Collection
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "test-results"
OUTPUT = ROOT / "docs" / "TEST_STATUS.md"
BADGES_DIR = ROOT / "docs" / "badges"
STATUS_DATA = ROOT / "docs" / "status.toml"
README = ROOT / "README.md"

REPO = "benny-vanbelle-vandeput-be/django-db2-for-i"
RAW_MAIN = f"https://raw.githubusercontent.com/{REPO}/main"

_RAN = re.compile(r"^Ran (\d+) tests? in ([\d.]+)s", re.MULTILINE)
_RESULT = re.compile(r"^(OK|FAILED)(?: \((.*)\))?\s*$", re.MULTILINE)
_HEADER = re.compile(r"^# (\w+): (.*)$", re.MULTILINE)
_VERSION_DIR = re.compile(r"^\d+\.\d+$")
COUNT_KEYS = {
    "failures": "failures",
    "errors": "errors",
    "skipped": "skipped",
    "expected failures": "expected_failures",
    "unexpected successes": "unexpected_successes",
}


@dataclasses.dataclass
class ModuleResult:
    module: str
    django: str
    started: str = ""
    keepdb: str = ""
    ran: int | None = None
    seconds: float | None = None
    outcome: str = "no summary"  # OK, FAILED, or "no summary" (stopped before the end)
    failures: int = 0
    errors: int = 0
    skipped: int = 0
    expected_failures: int = 0
    unexpected_successes: int = 0
    exit_code: str = ""
    django_build: str = ""  # the full "# django:" header, e.g. "6.1 (1e01021 2026-10-12)"
    backend: str = (
        ""  # the "# backend:" header: commit the run was made on, e.g. "a7ca5f8 2026-10-19"
    )
    partial: str = ""  # why a module summed from label logs is incomplete (empty: complete)
    python: str = ""  # the "# python:" header, e.g. "3.14.0" (empty: not recorded)

    @property
    def passed(self) -> int | None:
        if self.ran is None:
            return None
        return (
            self.ran
            - self.failures
            - self.errors
            - self.skipped
            - self.expected_failures
            - (self.unexpected_successes)
        )


def parse_log(text: str, module: str, django: str) -> ModuleResult:
    header = dict(_HEADER.findall(text))
    result = ModuleResult(
        module=header.get("module", module),
        django=header.get("django", django).split(" ")[0],
        django_build=header.get("django", django),
        started=header.get("started", ""),
        keepdb=header.get("keepdb", ""),
        exit_code=header.get("exit", ""),
        backend=header.get("backend", ""),
        python=header.get("python", ""),
    )
    ran = _RAN.findall(text)
    outcomes = _RESULT.findall(text)
    if ran:
        result.ran, result.seconds = int(ran[-1][0]), float(ran[-1][1])
    if ran and outcomes:
        result.outcome, details = outcomes[-1]
        for part in filter(None, (p.strip() for p in details.split(","))):
            key, _, value = part.partition("=")
            if key.strip() in COUNT_KEYS:
                setattr(result, COUNT_KEYS[key.strip()], int(value))
    return result


def collect(
    results_dir: Path = RESULTS, modules: Collection[str] | None = None
) -> list[ModuleResult]:
    """The module logs ``<version>/<module>.log``.

    With ``modules`` (the current run set: the supported modules run as a whole
    module), any other log is ignored and named on stderr: a day-to-day run of
    a module that is not supported yet, or a leftover of an older layout.
    """
    found, ignored = [], []
    for log in sorted(results_dir.glob("*/*.log")):
        if log.parent.name == "probes":
            continue
        if modules is not None and log.stem not in modules:
            ignored.append(f"{log.parent.name}/{log.name}")
            continue
        found.append(parse_log(log.read_text(errors="replace"), log.stem, log.parent.name))
    if ignored:
        print(f"ignored (not in the run set): {', '.join(ignored)}", file=sys.stderr)
    return sorted(found, key=lambda r: (r.module, r.django))


def run_set(status: dict) -> set[str]:
    """The supported modules run as one log each (modules with ``labels`` are summed)."""
    return {m["module"] for m in status.get("modules", []) if not m.get("labels")}


def collect_label_groups(status: dict, results_dir: Path = RESULTS) -> list[ModuleResult]:
    """Modules run as several labels (``labels`` in docs/status.toml), summed per
    Django version from ``<version>/labels/<label>.log``.

    Only logs of one run set are combined: all labels present and made on the
    same backend commit. Otherwise the row is marked partial (the counts are
    those of the logs found).
    """
    groups = []
    if not results_dir.is_dir():
        return groups
    for module in status.get("modules", []):
        labels = module.get("labels")
        if not labels:
            continue
        for version_dir in sorted(p for p in results_dir.iterdir() if p.is_dir()):
            if version_dir.name == "probes":
                continue
            found = {
                label: parse_log(path.read_text(errors="replace"), label, version_dir.name)
                for label in labels
                if (path := version_dir / "labels" / f"{label}.log").exists()
            }
            if found:
                groups.append(_sum_labels(module["module"], version_dir.name, labels, found))
    return groups


def _sum_labels(module: str, django: str, labels: list[str], found: dict) -> ModuleResult:
    runs = list(found.values())
    commits = sorted({r.backend or "unknown" for r in runs})
    pythons = {r.python for r in runs}
    total = ModuleResult(
        module=module,
        django=django,
        django_build=", ".join(sorted({r.django_build for r in runs if r.django_build})),
        started=min((r.started for r in runs if r.started), default=""),
        backend=", ".join(commits),
        ran=sum(r.ran or 0 for r in runs),
        # Set only when every label log records the same version.
        python=pythons.pop() if len(pythons) == 1 else "",
    )
    for key in COUNT_KEYS.values():
        setattr(total, key, sum(getattr(r, key) for r in runs))
    reasons = []
    missing = [label for label in labels if label not in found]
    if missing:
        reasons.append(f"missing {', '.join(missing)}")
    if len(commits) > 1:
        reasons.append(f"different commits {', '.join(commits)}")
    stopped = [label for label, r in found.items() if r.ran is None]
    if stopped:
        reasons.append(f"stopped before the summary: {', '.join(stopped)}")
    total.partial = "; ".join(reasons)
    if total.partial:
        total.outcome = "PARTIAL"
    else:
        total.outcome = "OK" if all(r.outcome == "OK" for r in runs) else "FAILED"
    return total


def feature_section() -> list[str]:
    from django_db2_for_i import features

    cls = features.DatabaseFeatures
    # Every flag the backend's class sets to True, also those Django defaults
    # to True: features.py lists them all explicitly (False until enabled).
    enabled = sorted(name for name, value in vars(cls).items() if value is True)
    lines = ["## Feature flags set to True by the backend", ""]
    lines += [f"- `{name}`" for name in enabled] or ["- (none)"]
    lines += [
        "- `has_native_boolean_field` (from the `has_boolean_type` capability)",
        "",
        "## Expected failures and skips per reason",
        "",
        "| Reason | Expected failures | Skips |",
        "|---|---|---|",
    ]
    reasons = sorted(set(cls.expected_failures) | set(cls.django_test_skips))
    for reason in reasons:
        failures = len(cls.expected_failures.get(reason, ()))
        skips = len(cls.django_test_skips.get(reason, ()))
        lines.append(f"| {reason} | {failures} | {skips} |")
    if not reasons:
        lines.append("| (none) | 0 | 0 |")
    return lines


def golden_section() -> list[str]:
    sys.path.insert(0, str(ROOT))
    from tests.golden import UNVERIFIED, all_golden_paths, read
    from tests.verification_gate import UNVERIFIABLE, summary

    goldens = [read(path) for path in all_golden_paths()]
    unverified = sum(golden.verified == UNVERIFIED for golden in goldens)
    allowed = summary() if UNVERIFIABLE.exists() else 0
    return [
        "## Golden files",
        "",
        f"{len(goldens)} goldens, {unverified} unverified; unverifiable on PUB400: {allowed}"
        " (`tests/offline/golden/unverifiable.toml`, with the reason and what makes each"
        " verifiable).",
    ]


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", version.split(" ")[0]))


def django_versions(results: list[ModuleResult]) -> list[str]:
    """The Django versions that have runs, newest first."""
    return sorted({r.django for r in results}, key=_version_key, reverse=True)


def version_results(results: list[ModuleResult], version: str) -> list[ModuleResult]:
    return [r for r in results if r.django == version]


def newest_results(results: list[ModuleResult]) -> list[ModuleResult]:
    """The results of the newest Django version that has runs."""
    versions = django_versions(results)
    return version_results(results, versions[0]) if versions else []


def counted(results: list[ModuleResult]) -> list[ModuleResult]:
    """The runs the badges count: those whose log has a test summary."""
    return [r for r in results if r.passed is not None]


@dataclasses.dataclass
class Totals:
    passed: int = 0
    failed: int = 0  # failures + errors + unexpected successes
    skipped: int = 0
    expected_failures: int = 0


def totals(results: list[ModuleResult], version: str | None = None) -> Totals:
    """Totals of one Django version's runs (default: the newest version)."""
    selected = newest_results(results) if version is None else version_results(results, version)
    total = Totals()
    for r in counted(selected):
        total.passed += r.passed
        total.failed += r.failures + r.errors + r.unexpected_successes
        total.skipped += r.skipped
        total.expected_failures += r.expected_failures
    return total


def _endpoint(label: str, message: str, color: str) -> dict:
    """shields.io endpoint JSON (schemaVersion 1)."""
    return {"schemaVersion": 1, "label": label, "message": message, "color": color}


def _sum(rows: list[Totals]) -> Totals:
    total = Totals()
    for row in rows:
        total.passed += row.passed
        total.failed += row.failed
        total.skipped += row.skipped
        total.expected_failures += row.expected_failures
    return total


# --- Versions and their states (docs/status.toml) -----------------------------------

# state -> (symbol, shields.io colour, legend text). Colour as well as symbol:
# emoji in SVG badges depend on the viewer's fonts.
STATES = {
    "supported": ("✅", "brightgreen", "supported"),
    "development": ("🚧", "yellow", "in development"),
    "planned": ("🗓️", "blue", "planned"),
    "eol": ("⚠️", "orange", "end of life, no longer maintained"),
    "unsupported": ("❌", "red", "not supported"),
}
SHOWN_STATES = ("supported", "development", "eol")  # with a test status section


def version_state(entry: dict, today: dt.date | None = None) -> str:
    """The entry's state; ``eol`` once its ``eol`` month (YYYY-MM) has passed."""
    state = entry.get("state", "supported")
    eol = entry.get("eol")
    if eol and state in ("supported", "development"):
        year, month = (int(part) for part in str(eol).split("-")[:2])
        first_after = dt.date(year + month // 12, month % 12 + 1, 1)
        if (today or dt.date.today()) >= first_after:
            return "eol"
    return state


def shown_django_versions(status: dict, today: dt.date | None = None) -> list[str]:
    """Django versions with a test status section, newest first."""
    shown = [
        entry["version"]
        for entry in status.get("django", [])
        if version_state(entry, today) in SHOWN_STATES
    ]
    return sorted(shown, key=_version_key, reverse=True)


def _shield_text(text: str) -> str:
    """Escape a static shields.io badge segment: dashes and underscores doubled,
    everything else percent-encoded (spaces, bars, the state symbols)."""
    return urllib.parse.quote(text.replace("-", "--").replace("_", "__"), safe="")


def _static_badge(label: str, message: str, color: str, link: str | None = None) -> str:
    url = f"https://img.shields.io/badge/{_shield_text(label)}-{_shield_text(message)}-{color}"
    image = f"![{label} {message}]({url})"
    return f"[{image}]({link})" if link else image


VERSION_LINKS = {
    "IBM i": "docs/user/IBM-i-Requirements.md",
    "Python": None,
    "Django": "docs/DJANGO_VERSIONS.md",
}


def general_badge_lines(status: dict, root: str = "", today: dt.date | None = None) -> list[str]:
    """Release, license, CI; one badge per IBM i / Python / Django version; legend."""
    lines = [
        f"[![release](https://img.shields.io/github/v/release/{REPO}?include_prereleases"
        f"&label=release)](https://github.com/{REPO}/releases)",
        f"[![license](https://img.shields.io/badge/license-BSD--3--Clause-blue)]({root}LICENSE)",
        f"[![CI](https://img.shields.io/github/actions/workflow/status/{REPO}/offline.yml"
        f"?branch=main&label=CI)](https://github.com/{REPO}/actions/workflows/offline.yml)",
        "",
    ]
    for key, label in (("ibmi", "IBM i"), ("python", "Python"), ("django", "Django")):
        link = VERSION_LINKS[label]
        for entry in sorted(status.get(key, []), key=lambda e: _version_key(e["version"])):
            symbol, color, _ = STATES[version_state(entry, today)]
            message = f"{entry['version']} {symbol}"
            lines.append(_static_badge(label, message, color, f"{root}{link}" if link else None))
        lines.append("")
    legend = " · ".join(f"{symbol} {text}" for symbol, _, text in STATES.values())
    lines.append(f"<sub>{legend}</sub>")
    return lines


# --- The four test sets per Django version ------------------------------------------

SET_OFFLINE = "Offline tests"
SET_IBMI = "IBM i tests"
SET_DJANGO = "Django suite on IBM i"
SET_REPLAY = "Replay tests"
TEST_SETS = [SET_OFFLINE, SET_IBMI, SET_DJANGO, SET_REPLAY]
# The names used before (code, sessions and directories keep them for now).
OLD_NAMES = {
    SET_OFFLINE: "offline tier (`nox -s offline`, `tests/offline/`)",
    SET_IBMI: "IBM i tests (`nox -s ibmi`, `tests/ibmi/`)",
    SET_DJANGO: "Django's own test modules on IBM i (`scripts/django_suite.sh`, the status run)",
    SET_REPLAY: "offline query corpus (`nox -s replay`, `tests/corpus/`)",
}


@dataclasses.dataclass
class SetResult:
    totals: Totals
    last_run: str


def _read_summary(path: Path) -> SetResult | None:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    counts = Totals(
        passed=int(data.get("passed", 0)),
        failed=int(data.get("failed", 0)),
        skipped=int(data.get("skipped", 0)),
        expected_failures=int(data.get("expected_failures", 0)),
    )
    return SetResult(counts, str(data.get("finished", "")))


_PYTEST_SUMMARY = re.compile(
    r"^=+ (.*\d+ (?:passed|failed|skipped|xfailed|error).*) in [\d.]+s", re.M
)
_PYTEST_COUNT = re.compile(r"(\d+) (passed|failed|skipped|xfailed|xpassed|errors?|deselected)")


def _read_tier_log(path: Path) -> SetResult | None:
    """The pytest summary line of a status run's tier log (tiers/pub400.log),
    for runs from before ``--results-summary``; the file's time as the run."""
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return None
    lines = _PYTEST_SUMMARY.findall(text)
    if not lines:
        return None
    counts = {kind: int(n) for n, kind in _PYTEST_COUNT.findall(lines[-1])}
    total = Totals(
        passed=counts.get("passed", 0),
        failed=counts.get("failed", 0)
        + counts.get("error", 0)
        + counts.get("errors", 0)
        + counts.get("xpassed", 0),
        skipped=counts.get("skipped", 0),
        expected_failures=counts.get("xfailed", 0),
    )
    finished = dt.datetime.fromtimestamp(path.stat().st_mtime, dt.UTC)
    return SetResult(total, finished.strftime("%Y-%m-%d %H:%M:%S UTC"))


def set_results(
    results: list[ModuleResult], version: str, results_dir: Path | None = None
) -> dict[str, SetResult | None]:
    """The four test sets of one Django version; None for a set without a recorded run."""
    sets = (RESULTS if results_dir is None else results_dir) / version / "sets"
    offline = sorted(
        sets.glob("offline-py*.json"),
        key=lambda path: _version_key(path.stem.removeprefix("offline-py")),
    )
    runs = counted(version_results(results, version))
    django = None
    if runs:
        django = SetResult(totals(results, version), max((r.started for r in runs), default=""))
    tier = _read_summary(sets / "pub400.json") or _read_tier_log(
        sets.parent / "tiers" / "pub400.log"
    )
    return {
        SET_OFFLINE: _read_summary(offline[-1]) if offline else None,
        SET_IBMI: tier,
        SET_DJANGO: django,
        SET_REPLAY: _read_summary(sets / "corpus.json"),
    }


def version_totals(sets: dict[str, SetResult | None]) -> Totals:
    """The sums of a version's test-set table (its badges)."""
    return _sum([result.totals for result in sets.values() if result is not None])


def badge_data(total: Totals, label: str) -> dict[str, dict]:
    """The test-count badges per badge file name."""
    return {
        "passed": _endpoint(label, f"{total.passed} passed", "brightgreen"),
        "skipped": _endpoint(label, f"{total.skipped} skipped", "lightgrey"),
        "xfail": _endpoint(label, f"{total.expected_failures} expected failures", "blue"),
        "failed": _endpoint(
            label, f"{total.failed} failed", "red" if total.failed else "brightgreen"
        ),
    }


BADGE_FILES = ("passed", "skipped", "xfail", "failed")
BADGE_ALT = {
    "passed": "passed",
    "skipped": "skipped",
    "xfail": "expected failures",
    "failed": "failed",
}


def write_badges(
    status: dict,
    results: list[ModuleResult],
    directory: Path | None = None,
    results_dir: Path | None = None,
    today: dt.date | None = None,
) -> list[Path]:
    """docs/badges/<version>/*.json for every shown Django version; stale files removed."""
    directory = BADGES_DIR if directory is None else directory
    versions = shown_django_versions(status, today)
    written = []
    for version in versions:
        total = version_totals(set_results(results, version, results_dir))
        target = directory / version
        target.mkdir(parents=True, exist_ok=True)
        for name, data in badge_data(total, f"Django {version}").items():
            path = target / f"{name}.json"
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
            written.append(path)
    if directory.is_dir():
        for stale in directory.iterdir():
            if stale.is_file() and stale.suffix == ".json":  # the old top-level badges
                stale.unlink()
            elif stale.is_dir() and _VERSION_DIR.match(stale.name):
                if stale.name not in versions:
                    shutil.rmtree(stale)
                elif (stale / "modules.json").exists():
                    (stale / "modules.json").unlink()
    return written


CORPUS_ROOT = ROOT / "tests" / "offline" / "replay"
NONE = "\u2013"  # an en dash: no recorded run


def set_table(sets: dict[str, SetResult | None], version: str = "") -> list[str]:
    lines = [
        "| Test set | Passed | Skipped | Expected failures | Failed | Last run |",
        "|---|---|---|---|---|---|",
    ]
    for name in TEST_SETS:
        result = sets.get(name)
        if result is None:
            none = "not run yet"
            if name == SET_REPLAY and version and not (CORPUS_ROOT / version).is_dir():
                none = "no corpus yet"
            lines.append(f"| {name} | {NONE} | {NONE} | {NONE} | {NONE} | {none} |")
            continue
        t = result.totals
        lines.append(
            f"| {name} | {t.passed} | {t.skipped} | {t.expected_failures} | {t.failed} | "
            f"{result.last_run or 'not recorded'} |"
        )
    return lines


def version_sections(
    status: dict,
    results: list[ModuleResult],
    link: str,
    results_dir: Path | None = None,
    today: dt.date | None = None,
    level: str = "###",
) -> list[str]:
    """One section per shown Django version: total badges and the test-set table."""
    states = {entry["version"]: version_state(entry, today) for entry in status.get("django", [])}
    lines = []
    for version in shown_django_versions(status, today):
        symbol = STATES[states[version]][0]
        lines += [f"{level} Django {version} {symbol}", ""]
        lines += [
            f"[![{BADGE_ALT[name]}](https://img.shields.io/endpoint?url={RAW_MAIN}/docs/badges/"
            f"{version}/{name}.json)]({link})"
            for name in BADGE_FILES
        ]
        lines += ["", *set_table(set_results(results, version, results_dir), version), ""]
    return lines


def modules_used(results: list[ModuleResult]) -> list[str]:
    """The Django test modules with a recorded run, any version (from the logs)."""
    return sorted({r.module.split(".")[0] for r in counted(results)})


def enabled_flags(features_dir: Path | None = None) -> tuple[str, int] | None:
    """(newest Django series, number of enabled flags) from docs/features/*.json."""
    directory = ROOT / "docs" / "features" if features_dir is None else features_dir
    files = sorted(directory.glob("*.json"), key=lambda path: _version_key(path.stem))
    if not files:
        return None
    data = json.loads(files[-1].read_text())
    return data["django"], sum(1 for value in data["flags"].values() if value)


def about_lines(results: list[ModuleResult], system: str, ibmi: str) -> list[str]:
    modules = modules_used(results)
    module_text = ", ".join(f"`{m}`" for m in modules) if modules else "none yet"
    return [
        "### About the tests",
        "",
        f"- **{SET_OFFLINE}:** unit tests and SQL checks written for this project (golden",
        "  files of the generated SQL and DDL, operations, the driver layer). They run in",
        "  GitHub CI on every commit, for every Python × Django combination, without an IBM i.",
        f"- **{SET_IBMI}:** tests written for this project, run against a real Db2 for i",
        f"  ({system}, IBM i {ibmi}): queries with model instances, schema changes, transactions,",
        "  and every golden file executed on the server. They run for every backend change.",
        f"- **{SET_DJANGO}:** Django's official test suite, limited to the modules that use",
        f"  the database and that this backend supports so far: {module_text}. They run on",
        f"  {system} before every release (the status run) and for the modules a change",
        "  touches.",
        f"- **{SET_REPLAY}:** the SQL of every passing test of that Django test suite is",
        "  recorded on IBM i; GitHub CI generates it again on every commit, without an IBM i,",
        "  and compares (counted per recorded statement). See",
        "  [docs/REPLAY_TESTS.md](docs/REPLAY_TESTS.md).",
        "",
        "**failed** = failures + errors + unexpected successes; it should be 0 on `main`.",
        "**Skipped** tests need a feature that is off (see the feature flags) or another",
        "database; **expected failures** are known Db2 for i limitations, each with a reason",
        "([Known limitations](docs/user/Known-Limitations.md)).",
    ]


def test_status_lines(
    status: dict,
    results: list[ModuleResult],
    results_dir: Path | None = None,
    features_dir: Path | None = None,
    today: dt.date | None = None,
) -> list[str]:
    """README's "Test status" section."""
    versions = status.get("versions", {})
    system = versions.get("test_system", "unknown system")
    ibmi = ", ".join(e["version"] for e in status.get("ibmi", [])) or versions.get("ibmi", "?")
    lines = ["## Test status", ""]
    lines += version_sections(status, results, "docs/TEST_STATUS.md", results_dir, today)
    lines += about_lines(results, system, ibmi)
    flags = enabled_flags(features_dir)
    flag_text = f" ({flags[1]} enabled on Django {flags[0]})" if flags else ""
    lines += [
        "",
        f"Feature flags: [docs/FEATURES.md](docs/FEATURES.md){flag_text} · "
        "All details: [docs/TEST_STATUS.md](docs/TEST_STATUS.md)",
    ]
    return lines


# --- Project status -----------------------------------------------------------------


def _phase_link(phase: dict) -> str:
    number = str(phase["phase"])
    if (ROOT / "docs" / "phases" / f"phase-{number}.md").exists():
        return f"[{number}](docs/phases/phase-{number}.md)"
    return number


def _prs(numbers: list[int]) -> str:
    return ", ".join(f"[#{n}](https://github.com/{REPO}/pull/{n})" for n in numbers)


def project_status_lines(status: dict) -> list[str]:
    """README's "Project status": the current phase's steps, the phases, release, tracks."""
    phases = [p for p in status.get("phases", []) if str(p["phase"]).isdigit()]
    current = next((p for p in phases if p["status"] == "in progress"), None)
    lines = ["## Project status", ""]
    if current is not None:
        lines += [f"**Phase {current['phase']}: {current['content']}** ({current['status']})", ""]
        steps = current.get("steps", [])
        if steps:
            lines += ["| Step | State | Pull requests |", "|---|---|---|"]
            for step in steps:
                lines.append(f"| {step['step']} | {step['status']} | {_prs(step.get('prs', []))} |")
            lines.append("")
    lines += ["| Phase | Content | Status |", "|---|---|---|"]
    for phase in phases:
        lines.append(f"| {_phase_link(phase)} | {phase['content']} | {phase['status']} |")
    releases = status.get("releases", [])
    if releases:
        latest = releases[0]
        lines += [
            "",
            f"Latest release: **`{latest['tag']}`** ({latest['date']}): {latest['summary']} "
            "([CHANGELOG](CHANGELOG.md))",
        ]
    tracks = status.get("tracks", [])
    if tracks:
        lines += ["", "Open tracks:", ""]
        lines += [f"- {track['text']}" for track in tracks]
    return lines


def load_status(path: Path | None = None) -> dict:
    with (STATUS_DATA if path is None else path).open("rb") as handle:
        return tomllib.load(handle)


def _result_text(r: ModuleResult) -> str:
    if r.ran is None:
        return "stopped before the summary"
    if r.partial:
        return f"PARTIAL ({r.partial})"
    details = [
        f"{count} {label}"
        for count, label in [
            (r.failures, "failures"),
            (r.errors, "errors"),
            (r.skipped, "skipped"),
            (r.expected_failures, "expected failures"),
            (r.unexpected_successes, "unexpected successes"),
        ]
        if count
    ]
    return r.outcome + (f" ({', '.join(details)})" if details else "")


class MarkerError(ValueError):
    """README.md lacks a marker pair (or has it twice, or in the wrong order)."""


def replace_between(text: str, name: str, content: list[str]) -> str:
    """Replace what lies between ``<!-- name:start -->`` and ``<!-- name:end -->``."""
    start, end = f"<!-- {name}:start -->", f"<!-- {name}:end -->"
    if text.count(start) != 1 or text.count(end) != 1:
        raise MarkerError(f"README.md needs exactly one {start} and one {end} marker")
    before, rest = text.split(start)
    if end not in rest:
        raise MarkerError(f"{end} comes before {start} in README.md")
    _, after = rest.split(end)
    body = "\n".join(content)
    return f"{before}{start}\n{body}\n{end}{after}"


def render_readme(
    text: str,
    status: dict,
    results: list[ModuleResult],
    results_dir: Path | None = None,
    features_dir: Path | None = None,
    today: dt.date | None = None,
) -> str:
    text = replace_between(text, "badges", general_badge_lines(status, today=today))
    text = replace_between(
        text, "tests", test_status_lines(status, results, results_dir, features_dir, today)
    )
    return replace_between(text, "status", project_status_lines(status))


def run_header(results: list[ModuleResult], status: dict | None) -> list[str]:
    """Run dates, Django builds and the IBM i release for the top of TEST_STATUS.md."""
    versions = (status or {}).get("versions", {})
    releases = [entry["version"] for entry in (status or {}).get("ibmi", [])]
    ibmi = ", ".join(releases) or versions.get("ibmi", "unknown")
    system = versions.get("test_system", "unknown system")
    builds = sorted({r.django_build or r.django for r in results}, key=_version_key)
    commits = sorted({r.backend for r in results if r.backend})
    pythons = sorted({r.python for r in results if r.python}, key=_version_key)
    python = ", ".join(pythons) or "not recorded"
    if pythons and any(not r.python for r in results):
        python += " (not recorded in every log)"
    started = sorted(r.started for r in results if r.started)
    if not started:
        runs = "none recorded"
    elif started[0] == started[-1]:
        runs = started[-1]
    else:
        runs = f"{started[0]} to {started[-1]}"
    return [
        f"- **Runs:** {runs}",
        f"- **Django:** {', '.join(builds) or 'none'}",
        f"- **Python:** {python}",
        f"- **Backend commits:** {', '.join(commits) or 'not recorded'} (per module in the table)",
        f"- **IBM i:** {ibmi} on {system}",
    ]


DEFINITIONS = [
    '- **Test sets:** four per Django version, see README\'s "About the tests".',
    "  The names replace earlier ones:",
    "",
    "  | Test set | Called before |",
    "  |---|---|",
    *[f"  | {new} | {old} |" for new, old in OLD_NAMES.items()],
    "",
    "- **The badges** of a Django version are the sums of its table. The counts come",
    "  from the last recorded run of each set (the logs and summaries in",
    "  `test-results/`), not from every commit. The replay is counted per recorded",
    "  statement, the other sets per test.",
    "- **passed:** the test ran and succeeded (replay: the SQL is identical).",
    "- **failed** = failures + errors + unexpected successes: the test ran and did not",
    "  succeed (or an expected failure passed), with no known reason yet. This should be 0",
    "  on `main`.",
    "- **skipped:** the test did not run, because it needs a feature the backend reports",
    "  as unsupported (a feature flag that is off, for example something planned for a",
    "  later phase) or because it is written for another database (replay: the recorded",
    "  query cannot be loaded or compiled offline). Skips shrink as features are",
    "  implemented.",
    "- **expected failures:** the test runs but is known to fail because of a real Db2",
    "  for i limitation, each with a documented reason (see",
    "  [Known limitations](user/Known-Limitations.md)). If one starts passing, it is",
    "  reported as an unexpected success and counted as failed.",
]


def render(
    results: list[ModuleResult],
    status: dict | None = None,
    results_dir: Path | None = None,
    today: dt.date | None = None,
) -> str:
    status = status or {}
    lines = [
        "# Test status",
        "",
        "Generated by `scripts/update_test_status.py` (`nox -s test_status`) from the logs and",
        "summaries in `test-results/`. Do not edit by hand.",
        "",
        *version_sections(status, results, "#django-test-modules", results_dir, today, "##"),
        *DEFINITIONS,
        "",
        *run_header(results, status),
        "",
        "## Django test modules",
        "",
        f"The {SET_DJANGO} per module and Django version.",
        "",
    ]
    if results:
        lines += [
            "| Module | Django | Tests | Passed | Failures | Errors | Skipped | Expected failures"
            " | Unexpected successes | Result | Run | Backend commit |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for r in results:
            lines.append(
                f"| {r.module} | {r.django} | {'' if r.ran is None else r.ran} | "
                f"{'' if r.passed is None else r.passed} | {r.failures} | {r.errors} | "
                f"{r.skipped} | {r.expected_failures} | {r.unexpected_successes} | "
                f"{r.outcome if not r.partial else f'PARTIAL ({r.partial})'} | {r.started} | "
                f"{r.backend or 'not recorded'} |"
            )
    else:
        lines.append("No Django test modules have been run yet.")
    lines += ["", *feature_section(), "", *golden_section(), ""]
    return "\n".join(lines)


def main() -> int:
    status = load_status()
    results = sorted(
        collect(modules=run_set(status)) + collect_label_groups(status),
        key=lambda r: (r.module, r.django),
    )
    try:
        readme = render_readme(README.read_text(), status, results)
    except MarkerError as error:
        print(f"error: {error}; nothing written", file=sys.stderr)
        return 1
    OUTPUT.write_text(render(results, status))
    written = [OUTPUT, *write_badges(status, results)]
    README.write_text(readme)
    written.append(README)
    for path in written:
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
