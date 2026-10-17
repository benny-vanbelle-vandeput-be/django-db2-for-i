"""The report redaction plugin (tests/redaction.py) hides the password."""

import pytest

SECRET = "Fake-Pw-4711"

LEAKY_TESTS = """
import os

import pytest


def check(secrets):
    assert secrets == ()


def test_traceback_and_output():
    password = os.environ["DB2I_PASSWORD"]
    print("stdout", password)
    check((password,))


def test_skip_reason():
    pytest.skip("skipped with " + os.environ["DB2I_PASSWORD"])
"""


@pytest.fixture
def leaky(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> pytest.Pytester:
    monkeypatch.setenv("DB2I_PASSWORD", SECRET)
    pytester.makepyfile(test_leaky=LEAKY_TESTS)
    return pytester


@pytest.mark.parametrize("tb", ["long", "short", "native"])
def test_reports_are_redacted(leaky: pytest.Pytester, tb: str) -> None:
    result = leaky.runpytest(
        "-p", "no:django", "-p", "tests.redaction", f"--tb={tb}", "-rA", "--junitxml=out.xml"
    )
    result.assert_outcomes(failed=1, skipped=1)
    output = result.stdout.str() + result.stderr.str()
    assert SECRET not in output
    assert "***" in output
    assert SECRET not in (leaky.path / "out.xml").read_text()


def test_without_plugin_the_secret_would_show(leaky: pytest.Pytester) -> None:
    # Guards the test above: the leaky tests really do expose the secret.
    result = leaky.runpytest("-p", "no:django", "-p", "no:tests.redaction", "--tb=long", "-rA")
    assert SECRET in result.stdout.str()
