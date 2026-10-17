"""pytest plugin: remove secrets from test reports (defense in depth).

The backend never puts the password into messages or traceback frames
(tests/offline/test_driver.py). As a second line of defense, every test and
collection report is scrubbed here before any reporter (terminal, junitxml,
...) sees it: the values of SECRET_VARIABLES from the environment are
replaced with ``***`` in the failure representation and in captured output.
"""

from __future__ import annotations

import os

import pytest

SECRET_VARIABLES = ("DB2I_PASSWORD",)
MASK = "***"


def _secrets() -> list[str]:
    return [value for name in SECRET_VARIABLES if (value := os.environ.get(name))]


def _scrub(text: str, secrets: list[str]) -> str:
    for secret in secrets:
        text = text.replace(secret, MASK)
    return text


def redact_report(report: pytest.CollectReport | pytest.TestReport) -> None:
    secrets = _secrets()
    if not secrets:
        return
    longrepr = report.longrepr
    if isinstance(longrepr, tuple):  # skip/xfail: (path, lineno, reason)
        report.longrepr = tuple(_scrub(str(part), secrets) for part in longrepr)
    elif longrepr is not None:
        text = str(longrepr)
        if any(secret in text for secret in secrets):
            # Rendered text replaces the rich representation only when needed.
            report.longrepr = _scrub(text, secrets)
    report.sections = [(title, _scrub(content, secrets)) for title, content in report.sections]


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    report = yield
    redact_report(report)
    return report


@pytest.hookimpl(wrapper=True)
def pytest_make_collect_report(collector: pytest.Collector):
    report = yield
    redact_report(report)
    return report
