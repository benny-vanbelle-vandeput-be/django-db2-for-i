"""A partial run writes no results summary (#251): its counts would replace the
whole run's in the status pages."""

from types import SimpleNamespace

import pytest

from tests.conftest import narrowed

pytestmark = pytest.mark.offline


def config(args_source=pytest.Config.ArgsSource.TESTPATHS, keyword="", **options):
    defaults = {"deselect": None, "lf": False, "failedfirst": False}
    defaults.update(options)
    return SimpleNamespace(
        args_source=args_source,
        option=SimpleNamespace(keyword=keyword),
        getoption=lambda name, default=None: defaults.get(name, default),
    )


def test_a_whole_run_is_not_narrowed() -> None:
    assert narrowed(config()) is None
    assert narrowed(config(pytest.Config.ArgsSource.INVOCATION_DIR)) is None


@pytest.mark.parametrize(
    ("made", "reason"),
    [
        (config(pytest.Config.ArgsSource.ARGS), "tests named on the command line"),
        (config(keyword="goldens"), "-k"),
        (config(deselect=["tests/ibmi/test_x.py::test_y"]), "--deselect"),
        (config(lf=True), "--last-failed / --failed-first"),
    ],
)
def test_a_partial_run_says_why(made, reason) -> None:
    assert narrowed(made) == reason
