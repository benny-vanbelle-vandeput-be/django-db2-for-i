"""Generate docs/TEST_STATUS.md, the test badges and README's status from the logs.

    nox -s test_status

Reads test-results/<django-version>/<module>.log as written by
scripts/run_django_tests.py and reports, per module and Django version, the
counts from Django's test runner summary, plus the expected failures and
skips per fixed reason, the feature flags the backend sets to True, and the
golden-file status.

It also writes:

- docs/badges/{modules,passed,failed,skipped,xfail}.json: shields.io endpoint
  files for the newest Django version that has runs. Their label names the
  combination, e.g. ``Django 6.1 · Python 3.14 on PUB400``: the system is
  ``versions.test_system`` from docs/status.toml, and the Python part is shown
  only when every counted log of that Django version records the same Python
  series (logs written before the runner recorded it have none).
- docs/badges/<django-version>/*.json: the same files per Django version, only
  while logs of more than one Django version exist (from phase 3 on). README.md
  and TEST_STATUS.md then show one badge row per version, newest first, and
  directories of versions without logs are removed. With a single version
  there are no per-version directories and the top-level URLs stay as they
  are. Without any logs no badge file is touched.
- README.md: the badges and the "Project status" section, between the
  ``<!-- badges:start -->`` / ``<!-- status:start -->`` marker comments and
  their ``:end`` counterparts, from docs/status.toml (releases, phases, open
  tracks) and the same module results. The rest of README.md is untouched.

The modules badge reads ``<run>/<total>``: ``run`` is the number of distinct
Django test modules of that version whose log has a test summary (a module run
as several labels counts once); ``total`` is the number of test modules in the
vendored checkout vendor/django-<version>/tests/ (rule: count_test_modules).
Without the checkout (CI, the wheel session) the total of the existing badge
file is kept when that file is for the same Django version; otherwise the
badge shows only ``<run> run``.
"""

from __future__ import annotations

import dataclasses
import json
import re
import shutil
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "test-results"
OUTPUT = ROOT / "docs" / "TEST_STATUS.md"
BADGES_DIR = ROOT / "docs" / "badges"
STATUS_DATA = ROOT / "docs" / "status.toml"
README = ROOT / "README.md"
VENDOR = ROOT / "vendor"

REPO = "benny-vanbelle-vandeput-be/django-db2-for-i"
RAW_MAIN = f"https://raw.githubusercontent.com/{REPO}/main"

# Directories under Django's tests/ that runtests.py never runs as test modules:
# SUBDIRS_TO_SKIP[""] in runtests.py, plus gis_tests, which it skips when the
# database has no GIS support (this backend has none, gis_enabled is False).
NOT_TEST_MODULES = frozenset({"import_error_package", "test_runner_apps", "gis_tests"})

_RAN = re.compile(r"^Ran (\d+) tests? in ([\d.]+)s", re.MULTILINE)
_RESULT = re.compile(r"^(OK|FAILED)(?: \((.*)\))?\s*$", re.MULTILINE)
_HEADER = re.compile(r"^# (\w+): (.*)$", re.MULTILINE)
_VERSION_DIR = re.compile(r"^\d+\.\d+$")
_MODULES_MESSAGE = re.compile(r"^\d+/(\d+)$")
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


def collect(results_dir: Path = RESULTS) -> list[ModuleResult]:
    found = []
    for log in sorted(results_dir.glob("*/*.log")):
        if log.parent.name == "probes":
            continue
        found.append(parse_log(log.read_text(errors="replace"), log.stem, log.parent.name))
    return sorted(found, key=lambda r: (r.module, r.django))


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

    goldens = [read(path) for path in all_golden_paths()]
    unverified = sum(golden.verified == UNVERIFIED for golden in goldens)
    return ["## Golden files", "", f"{len(goldens)} goldens, {unverified} unverified."]


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


def python_series(results: list[ModuleResult]) -> str | None:
    """``3.14`` when every counted run records Python 3.14.x; None when a run
    records no version, the runs disagree, or there are none (never guessed)."""
    versions = [r.python for r in counted(results)]
    if not versions or not all(versions):
        return None
    series = {".".join(version.split(".")[:2]) for version in versions}
    return series.pop() if len(series) == 1 else None


def combination_label(results: list[ModuleResult], version: str, system: str) -> str:
    """The test badge label, e.g. ``Django 6.1 · Python 3.14 on PUB400``."""
    python = python_series(version_results(results, version))
    return f"Django {version}" + (f" · Python {python}" if python else "") + f" on {system}"


def count_test_modules(tests_dir: Path) -> int | None:
    """The number of test modules in a Django checkout's ``tests/`` directory.

    Mirrors get_test_modules() in Django's runtests.py for a database without
    GIS: every directory directly under tests/ whose name has no dot and which
    contains an ``__init__.py``, except NOT_TEST_MODULES. None when the
    checkout is absent.
    """
    if not (tests_dir / "runtests.py").is_file():
        return None
    return sum(
        1
        for entry in tests_dir.iterdir()
        if "." not in entry.name
        and entry.name not in NOT_TEST_MODULES
        and entry.is_dir()
        and (entry / "__init__.py").exists()
    )


def modules_run(results: list[ModuleResult]) -> int:
    """Distinct test modules with a recorded run (a module run as labels counts once)."""
    return len({r.module.split(".")[0] for r in counted(results)})


def previous_total(path: Path, label: str) -> int | None:
    """The ``<total>`` of an existing modules badge with the same label, else None."""
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("label") != label:
        return None
    match = _MODULES_MESSAGE.match(str(data.get("message", "")))
    return int(match.group(1)) if match else None


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


def badge_data(total: Totals, label: str) -> dict[str, dict]:
    """The test-count badges per badge file name."""
    return {
        "passed": _endpoint(label, f"{total.passed} passed", "brightgreen"),
        "failed": _endpoint(
            label, f"{total.failed} failed", "red" if total.failed else "brightgreen"
        ),
        "skipped": _endpoint(label, f"{total.skipped} skipped", "lightgrey"),
        "xfail": _endpoint(label, f"{total.expected_failures} expected failures", "blue"),
    }


def modules_label(version: str) -> str:
    # The version in the label also tells previous_total() which version a file is for.
    return f"Django {version} modules"


def modules_badge(run: int, total: int | None, version: str) -> dict:
    message = f"{run}/{total}" if total is not None else f"{run} run"
    return _endpoint(modules_label(version), message, "informational")


def write_badges(
    results: list[ModuleResult],
    status: dict | None = None,
    directory: Path | None = None,
    vendor: Path | None = None,
) -> list[Path]:
    """Write the badge files (see the module docstring for the layout)."""
    directory = BADGES_DIR if directory is None else directory
    vendor = VENDOR if vendor is None else vendor
    system = (status or {}).get("versions", {}).get("test_system", "unknown system")
    versions = django_versions(results)
    if not versions:
        return []
    per_version = len(versions) > 1
    targets = [(versions[0], directory)]
    if per_version:
        targets += [(version, directory / version) for version in versions]
    written = []
    for version, target in targets:
        selected = version_results(results, version)
        total = count_test_modules(vendor / f"django-{version}" / "tests")
        if total is None:
            total = previous_total(target / "modules.json", modules_label(version))
        files = {
            "modules": modules_badge(modules_run(selected), total, version),
            **badge_data(totals(results, version), combination_label(results, version, system)),
        }
        target.mkdir(parents=True, exist_ok=True)
        for name, data in files.items():
            path = target / f"{name}.json"
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
            written.append(path)
    if directory.is_dir():
        for stale in directory.iterdir():
            is_version_dir = stale.is_dir() and _VERSION_DIR.match(stale.name)
            if is_version_dir and (not per_version or stale.name not in versions):
                shutil.rmtree(stale)
    return written


def _shield_text(text: str) -> str:
    """Escape a static shields.io badge segment (dashes, underscores, spaces, bars)."""
    text = text.replace("-", "--").replace("_", "__")
    return text.replace(" ", "%20").replace("|", "%7C")


TEST_BADGES = [
    ("modules", "Django modules"),
    ("passed", "passed"),
    ("failed", "failed"),
    ("skipped", "skipped"),
    ("xfail", "expected failures"),
]


def badge_lines(
    status: dict, test_link: str, root: str = "", versions: list[str] | None = None
) -> list[str]:
    """Markdown for all badges.

    ``test_link`` is where the test badges link to; ``root`` is the path from
    the rendered file to the repository root (for the LICENSE link).
    ``versions`` are the Django versions with runs, newest first: with more
    than one, each gets its own row of test badges from its own directory.
    """
    status_versions = status.get("versions", {})
    static = [
        (
            "Django",
            status_versions.get("django", "6.1"),
            "0C4B33",
            "https://www.djangoproject.com/",
        ),
        ("Python", status_versions.get("python", "3.12 | 3.13 | 3.14"), "3776AB", None),
        ("IBM i", status_versions.get("ibmi", "7.5"), "054ADA", None),
        ("license", "BSD-3-Clause", "blue", f"{root}LICENSE"),
    ]
    lines = []
    for label, message, color, link in static:
        url = f"https://img.shields.io/badge/{_shield_text(label)}-{_shield_text(message)}-{color}"
        image = f"![{label}]({url})"
        lines.append(f"[{image}]({link})" if link else image)
    lines += [
        f"[![offline CI](https://img.shields.io/github/actions/workflow/status/{REPO}/offline.yml"
        f"?branch=main&label=offline%20CI)](https://github.com/{REPO}/actions/workflows/offline.yml)",
        f"[![release](https://img.shields.io/github/v/release/{REPO}?include_prereleases"
        f"&label=release)](https://github.com/{REPO}/releases)",
    ]
    versions = list(versions or [])
    rows = [f"{version}/" for version in versions] if len(versions) > 1 else [""]
    for row in rows:
        lines.append("")  # each row of test badges is its own paragraph
        for name, alt in TEST_BADGES:
            lines.append(
                f"[![{alt}](https://img.shields.io/endpoint?url={RAW_MAIN}/docs/badges/"
                f"{row}{name}.json)]({test_link})"
            )
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


def status_lines(status: dict, results: list[ModuleResult]) -> list[str]:
    """The "Project status" section for README.md."""
    by_module = {r.module: r for r in newest_results(results)}
    lines = ["## Project status", "", "### Releases", ""]
    lines += [
        f"- **`{release['tag']}`** ({release['date']}): {release['summary']}"
        for release in status.get("releases", [])
    ] or ["- (none yet)"]
    lines += ["", "### Phases", "", "| Phase | Content | Status |", "|---|---|---|"]
    for phase in status.get("phases", []):
        lines.append(f"| {phase['phase']} | {phase['content']} | {phase['status']} |")
    section = status.get("modules_section", {})
    lines += [
        "",
        f"### {section.get('title', 'Modules')}",
        "",
        "Tests and results from the last recorded run, see [TEST_STATUS](docs/TEST_STATUS.md).",
        "",
    ]
    columns = section.get("django")
    if columns:
        lines += _modules_per_version(status, results, columns)
    else:
        lines += ["| Module | Tests | Result | Status |", "|---|---|---|---|"]
        for module in status.get("modules", []):
            r = by_module.get(module["module"])
            tests = "" if r is None or r.ran is None else str(r.ran)
            result = "not run yet" if r is None else _result_text(r)
            lines.append(f"| {module['module']} | {tests} | {result} | {_module_state(module)} |")
    lines += ["", "### Open tracks and notes", ""]
    lines += [f"- {track['text']}" for track in status.get("tracks", [])] or ["- (none)"]
    return lines


def _module_state(module: dict) -> str:
    return module["status"] + (f" ({module['note']})" if module.get("note") else "")


def _modules_per_version(
    status: dict, results: list[ModuleResult], columns: list[str]
) -> list[str]:
    """One column per Django version (``[modules_section] django``): the module's
    tests and result on that version, or "planned" without a recorded run."""
    by_key = {(r.module, r.django): r for r in results}
    lines = [
        "| Module | " + " | ".join(f"Django {v}" for v in columns) + " | Status |",
        "|---|" + "---|" * len(columns) + "---|",
    ]
    for module in status.get("modules", []):
        cells = []
        for version in columns:
            r = by_key.get((module["module"], version))
            if r is None:
                cells.append("planned")
            elif r.ran is None:
                cells.append(_result_text(r))
            else:
                cells.append(f"{r.ran} tests, {_result_text(r)}")
        row = " | ".join([module["module"], *cells, _module_state(module)])
        lines.append(f"| {row} |")
    return lines


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


def render_readme(text: str, status: dict, results: list[ModuleResult]) -> str:
    badges = badge_lines(status, "docs/TEST_STATUS.md", versions=django_versions(results))
    text = replace_between(text, "badges", badges)
    return replace_between(text, "status", status_lines(status, results))


def run_header(results: list[ModuleResult], status: dict | None) -> list[str]:
    """Run dates, Django builds and the IBM i release for the top of TEST_STATUS.md."""
    versions = (status or {}).get("versions", {})
    ibmi = versions.get("ibmi", "unknown")
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


# What the test badges mean; README.md has the same definitions (hand-written).
BADGE_DEFINITIONS = [
    "- **What the test badges count:** Django's own test modules (Django's `runtests.py`,",
    "  the modules in the table below), run against Db2 for i on the shared PUB400",
    "  system, for one Python × Django combination per row of badges. The label names",
    "  it, for example `Django 6.1 · Python 3.14 on PUB400`; the Python part is left out",
    "  while not every counted log records the same Python version. The counts come",
    "  from the last recorded run of each module, not from every commit.",
    "- **Not in these badges:** the full version matrix (every supported Python × Django",
    "  combination) runs only on a dedicated IBM i, not on the shared system. The",
    "  backend's own pub400 tier (`tests/pub400/`) is separate and not counted.",
    "- **offline CI:** the backend's offline tier on every commit, for every Python ×",
    "  Django combination, with no IBM i.",
    "- **Django modules** `<run>/<total>`: how many of the Django version's test modules",
    "  have a recorded run (a module run as several labels counts once), out of all",
    "  test modules in that version's test suite (as `runtests.py` finds them, without",
    "  the GIS tests).",
    "- **passed:** the test ran and succeeded.",
    "- **failed** = failures + errors + unexpected successes: the test ran and did not",
    "  succeed (or an expected failure passed), with no known reason yet. This should be 0",
    "  on `main`.",
    "- **skipped:** the test did not run, because it needs a feature the backend reports",
    "  as unsupported (a feature flag that is off, for example something planned for a",
    "  later phase) or because it is written for another database. Skips shrink as",
    "  features are implemented.",
    "- **expected failures:** the test runs but is known to fail because of a real Db2",
    "  for i limitation, each with a documented reason (see",
    "  [Known limitations](user/Known-Limitations.md)). If one starts passing, it is",
    "  reported as an unexpected success and counted as failed.",
]


def render(results: list[ModuleResult], status: dict | None = None) -> str:
    lines = [
        "# Test status",
        "",
        *badge_lines(
            status or {}, "#django-test-modules", root="../", versions=django_versions(results)
        ),
        "",
        "Generated by `scripts/update_test_status.py` (`nox -s test_status`) from the logs in",
        "`test-results/`. Do not edit by hand. Each row of test badges is one Django",
        "version's runs (one row while only one version has runs).",
        "",
        *BADGE_DEFINITIONS,
        "",
        *run_header(results, status),
        "",
        "## Django test modules",
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
    results = sorted(collect() + collect_label_groups(status), key=lambda r: (r.module, r.django))
    try:
        readme = render_readme(README.read_text(), status, results)
    except MarkerError as error:
        print(f"error: {error}; nothing written", file=sys.stderr)
        return 1
    OUTPUT.write_text(render(results, status))
    badges = write_badges(results, status)
    if not badges:
        print("no Django test logs: badge files left unchanged")
    written = [OUTPUT, *badges]
    README.write_text(readme)
    written.append(README)
    for path in written:
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
