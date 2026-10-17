"""nox sessions.

Run inside the container:  docker compose run --rm tests nox -s <session>
"""

import nox

nox.options.default_venv_backend = "uv"
nox.options.error_on_missing_interpreters = True
nox.options.sessions = ["lint", "offline"]

PYPROJECT = nox.project.load_toml("pyproject.toml")

# Python versions supported by each Django version, taken from Django's
# release notes (see docs/DJANGO_VERSIONS.md). Phases 0-2 target 6.1 only.
DJANGO_PYTHONS = {
    "6.1": ["3.12", "3.13", "3.14"],
}
NEWEST_DJANGO = "6.1"
NEWEST_PYTHON = DJANGO_PYTHONS[NEWEST_DJANGO][-1]

OFFLINE_MATRIX = [
    (python, django) for django, pythons in DJANGO_PYTHONS.items() for python in pythons
]


def install(session: nox.Session, django: str, *groups: str) -> None:
    """Install the backend, a specific Django version and dependency groups."""
    if groups:
        session.install(*nox.project.dependency_groups(PYPROJECT, *groups))
    session.install("-e", ".", f"Django~={django}.0")


@nox.session(python=NEWEST_PYTHON)
def lint(session: nox.Session) -> None:
    """Static checks: ruff lint and format check."""
    session.install(*nox.project.dependency_groups(PYPROJECT, "lint"))
    session.run("ruff", "check", ".")
    session.run("ruff", "format", "--check", ".")


@nox.session
@nox.parametrize(
    "python,django",
    OFFLINE_MATRIX,
    ids=[f"{python}-django{django}" for python, django in OFFLINE_MATRIX],
)
def offline(session: nox.Session, django: str) -> None:
    """Tier 1: no IBM i needed. Every Python x every Django version."""
    install(session, django, "test")
    session.run("pytest", "-m", "offline", *session.posargs)


@nox.session(python=NEWEST_PYTHON)
def pub400(session: nox.Session) -> None:
    """Tier 2: curated smoke set against PUB400 (newest Python, newest Django)."""
    install(session, NEWEST_DJANGO, "test")
    session.run(
        "pytest",
        "-m",
        "pub400",
        "--ds=tests.django_settings.settings_pub400",
        # Short tracebacks: no function arguments (defense in depth, together
        # with the report redaction in tests/redaction.py).
        "--tb=short",
        *session.posargs,
    )


@nox.session(python=NEWEST_PYTHON)
def probe(session: nox.Session) -> None:
    """Read-only IBM i probes: nox -s probe -- [reachability|connect|sysinfo|libraries|all]."""
    session.install("-e", ".")
    session.run("python", "probes/run.py", *session.posargs)


@nox.session(python=NEWEST_PYTHON)
def probe_write(session: nox.Session) -> None:
    """CHANGES THE IBM i: write probe w01 (temporary table). Dry run unless -- --execute."""
    session.install("-e", ".")
    session.run("python", "probes/w01_commitment.py", *session.posargs)


@nox.session(python=NEWEST_PYTHON)
def probe_autocommit(session: nox.Session) -> None:
    """CHANGES THE IBM i: write probe w02 (temporary table). Dry run unless -- --execute."""
    session.install("-e", ".")
    session.run("python", "probes/w02_autocommit.py", *session.posargs)


@nox.session(python=NEWEST_PYTHON)
def probe_operations(session: nox.Session) -> None:
    """CHANGES THE IBM i: write probe w03 (temporary tables). Dry run unless -- --execute."""
    session.install("-e", ".")
    session.run("python", "probes/w03_operations.py", *session.posargs)


@nox.session(python=NEWEST_PYTHON)
def probe_sequence(session: nox.Session) -> None:
    """CHANGES THE IBM i: write probe w04 (sequence + tables). Dry run unless -- --execute."""
    session.install("-e", ".")
    session.run("python", "probes/w04_sequence.py", *session.posargs)


@nox.session(python=NEWEST_PYTHON)
def setup_journal(session: nox.Session) -> None:
    """CHANGES THE IBM i: create QSQJRN in a test library. Dry run unless -- --execute."""
    session.install("-e", ".")
    session.run("python", "probes/setup_journal.py", *session.posargs)
