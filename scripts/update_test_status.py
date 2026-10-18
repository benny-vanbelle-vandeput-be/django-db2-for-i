"""Generate docs/TEST_STATUS.md, the test badges and README's status from the logs.

    nox -s test_status

Reads test-results/<django-version>/<module>.log as written by
scripts/run_django_tests.py and reports, per module and Django version, the
counts from Django's test runner summary, plus the expected failures and
skips per fixed reason, the feature flags the backend sets to True, and the
golden-file status.

It also writes:

- docs/badges/{passed,failed,skipped,xfail}.json: shields.io endpoint files
  with the totals of the newest Django version's runs;
- README.md: the badges and the "Project status" section, between the
  ``<!-- badges:start -->`` / ``<!-- status:start -->`` marker comments and
  their ``:end`` counterparts, from docs/status.toml (releases, phases, open
  tracks) and the same module results. The rest of README.md is untouched.
"""

from __future__ import annotations

import dataclasses
import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "test-results"
OUTPUT = ROOT / "docs" / "TEST_STATUS.md"
BADGES_DIR = ROOT / "docs" / "badges"
STATUS_DATA = ROOT / "docs" / "status.toml"
README = ROOT / "README.md"

REPO = "benny-vanbelle-vandeput-be/django-db2-for-i"
RAW_MAIN = f"https://raw.githubusercontent.com/{REPO}/main"
TEST_LABEL = "Django tests (PUB400)"

_RAN = re.compile(r"^Ran (\d+) tests? in ([\d.]+)s", re.MULTILINE)
_RESULT = re.compile(r"^(OK|FAILED)(?: \((.*)\))?\s*$", re.MULTILINE)
_HEADER = re.compile(r"^# (\w+): (.*)$", re.MULTILINE)
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


def newest_results(results: list[ModuleResult]) -> list[ModuleResult]:
    """The results of the newest Django version that has runs (the badges count these)."""
    if not results:
        return []
    newest = max((r.django for r in results), key=_version_key)
    return [r for r in results if r.django == newest]


@dataclasses.dataclass
class Totals:
    passed: int = 0
    failed: int = 0  # failures + errors + unexpected successes
    skipped: int = 0
    expected_failures: int = 0


def totals(results: list[ModuleResult]) -> Totals:
    total = Totals()
    for r in newest_results(results):
        if r.passed is None:
            continue
        total.passed += r.passed
        total.failed += r.failures + r.errors + r.unexpected_successes
        total.skipped += r.skipped
        total.expected_failures += r.expected_failures
    return total


def badge_data(total: Totals) -> dict[str, dict]:
    """shields.io endpoint JSON (schemaVersion 1) per badge file name."""

    def badge(message: str, color: str) -> dict:
        return {"schemaVersion": 1, "label": TEST_LABEL, "message": message, "color": color}

    return {
        "passed": badge(f"{total.passed} passed", "brightgreen"),
        "failed": badge(f"{total.failed} failed", "red" if total.failed else "brightgreen"),
        "skipped": badge(f"{total.skipped} skipped", "lightgrey"),
        "xfail": badge(f"{total.expected_failures} expected failures", "blue"),
    }


def write_badges(total: Totals, directory: Path | None = None) -> list[Path]:
    directory = BADGES_DIR if directory is None else directory
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for name, data in badge_data(total).items():
        path = directory / f"{name}.json"
        path.write_text(json.dumps(data, indent=2) + "\n")
        written.append(path)
    return written


def _shield_text(text: str) -> str:
    """Escape a static shields.io badge segment (dashes, underscores, spaces, bars)."""
    text = text.replace("-", "--").replace("_", "__")
    return text.replace(" ", "%20").replace("|", "%7C")


TEST_BADGES = [
    ("passed", "passed"),
    ("failed", "failed"),
    ("skipped", "skipped"),
    ("xfail", "expected failures"),
]


def badge_lines(status: dict, test_link: str, root: str = "") -> list[str]:
    """Markdown for all badges.

    ``test_link`` is where the test badges link to; ``root`` is the path from
    the rendered file to the repository root (for the LICENSE link).
    """
    versions = status.get("versions", {})
    static = [
        ("Django", versions.get("django", "6.1"), "0C4B33", "https://www.djangoproject.com/"),
        ("Python", versions.get("python", "3.12 | 3.13 | 3.14"), "3776AB", None),
        ("IBM i", versions.get("ibmi", "7.5"), "054ADA", None),
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
    for name, alt in TEST_BADGES:
        lines.append(
            f"[![{alt}](https://img.shields.io/endpoint?url={RAW_MAIN}/docs/badges/{name}.json)]"
            f"({test_link})"
        )
    return lines


def load_status(path: Path | None = None) -> dict:
    with (STATUS_DATA if path is None else path).open("rb") as handle:
        return tomllib.load(handle)


def _result_text(r: ModuleResult) -> str:
    if r.ran is None:
        return "stopped before the summary"
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
    lines += [
        "",
        "### Phase 2 modules",
        "",
        "Tests and results from the last recorded run, see [TEST_STATUS](docs/TEST_STATUS.md).",
        "",
        "| Module | Tests | Result | Status |",
        "|---|---|---|---|",
    ]
    for module in status.get("modules", []):
        r = by_module.get(module["module"])
        tests = "" if r is None or r.ran is None else str(r.ran)
        result = "not run yet" if r is None else _result_text(r)
        state = module["status"] + (f" ({module['note']})" if module.get("note") else "")
        lines.append(f"| {module['module']} | {tests} | {result} | {state} |")
    lines += ["", "### Open tracks and notes", ""]
    lines += [f"- {track['text']}" for track in status.get("tracks", [])] or ["- (none)"]
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
    text = replace_between(text, "badges", badge_lines(status, "docs/TEST_STATUS.md"))
    return replace_between(text, "status", status_lines(status, results))


def run_header(results: list[ModuleResult], status: dict | None) -> list[str]:
    """Run dates, Django builds and the IBM i release for the top of TEST_STATUS.md."""
    versions = (status or {}).get("versions", {})
    ibmi = versions.get("ibmi", "unknown")
    system = versions.get("test_system", "unknown system")
    builds = sorted({r.django_build or r.django for r in results}, key=_version_key)
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
        f"- **IBM i:** {ibmi} on {system}",
    ]


# What the test badges mean; README.md has the same definitions (hand-written).
BADGE_DEFINITIONS = [
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
        *badge_lines(status or {}, "#django-test-modules", root="../"),
        "",
        "Generated by `scripts/update_test_status.py` (`nox -s test_status`) from the logs in",
        "`test-results/`. Do not edit by hand. The test badges count the newest Django",
        "version's runs.",
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
            " | Unexpected successes | Result | Run |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for r in results:
            lines.append(
                f"| {r.module} | {r.django} | {'' if r.ran is None else r.ran} | "
                f"{'' if r.passed is None else r.passed} | {r.failures} | {r.errors} | "
                f"{r.skipped} | {r.expected_failures} | {r.unexpected_successes} | "
                f"{r.outcome} | {r.started} |"
            )
    else:
        lines.append("No Django test modules have been run yet.")
    lines += ["", *feature_section(), "", *golden_section(), ""]
    return "\n".join(lines)


def main() -> int:
    results = collect()
    status = load_status()
    try:
        readme = render_readme(README.read_text(), status, results)
    except MarkerError as error:
        print(f"error: {error}; nothing written", file=sys.stderr)
        return 1
    OUTPUT.write_text(render(results, status))
    written = [OUTPUT, *write_badges(totals(results))]
    README.write_text(readme)
    written.append(README)
    for path in written:
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
