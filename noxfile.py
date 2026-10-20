"""nox sessions.

Run inside the container:  docker compose run --rm tests nox -s <session>
"""

import nox

nox.options.default_venv_backend = "uv"
nox.options.error_on_missing_interpreters = True
nox.options.sessions = ["lint", "offline"]

PYPROJECT = nox.project.load_toml("pyproject.toml")

# Python versions supported by each Django version, taken from Django's
# release notes (see docs/DJANGO_VERSIONS.md), oldest first.
DJANGO_PYTHONS = {
    "5.2": ["3.12", "3.13", "3.14"],
    "6.0": ["3.12", "3.13", "3.14"],
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


def results_summary(django: str, test_set: str) -> str:
    """Where a run writes its counts for README's test status (update_test_status.py)."""
    return f"test-results/{django}/sets/{test_set}.json"


def django_argument(session: nox.Session) -> tuple[str, list[str]]:
    """A supported Django version given as the first argument (default: the
    newest), and the other arguments."""
    if session.posargs and session.posargs[0] in DJANGO_PYTHONS:
        return session.posargs[0], session.posargs[1:]
    if session.posargs and session.posargs[0][:1].isdigit():
        session.error(f"Django {session.posargs[0]} is not supported: {', '.join(DJANGO_PYTHONS)}")
    return NEWEST_DJANGO, list(session.posargs)


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
    session.run(
        "pytest",
        "-m",
        "offline",
        f"--results-summary={results_summary(django, f'offline-py{session.python}')}",
        *session.posargs,
    )


def django_checkout(session: nox.Session, django: str, commit: str) -> str:
    """A Django checkout at exactly ``commit``: vendor/django-<django> when it is
    there, otherwise a shallow fetch of that one commit into .nox/_django/<commit>."""
    import pathlib

    def head(path: pathlib.Path) -> str:
        if not (path / ".git").exists():
            return ""
        return session.run(
            "git", "-c", "safe.directory=*", "-C", str(path), "rev-parse", "HEAD",
            external=True, silent=True,
        ).strip()  # fmt: skip

    vendor = pathlib.Path(f"vendor/django-{django}")
    if head(vendor) == commit:
        return str(vendor.resolve())
    cache = pathlib.Path(".nox/_django") / commit
    if head(cache) != commit:
        cache.mkdir(parents=True, exist_ok=True)
        git = ["git", "-c", "safe.directory=*", "-C", str(cache)]
        if not (cache / ".git").exists():
            session.run(*git, "init", "-q", external=True)
            session.run(
                *git, "remote", "add", "origin", "https://github.com/django/django.git",
                external=True,
            )  # fmt: skip
        session.run(*git, "fetch", "-q", "--depth", "1", "origin", commit, external=True)
        session.run(*git, "checkout", "-q", "FETCH_HEAD", external=True)
    return str(cache.resolve())


@nox.session
@nox.parametrize(
    "python,django",
    OFFLINE_MATRIX,
    ids=[f"{python}-django{django}" for python, django in OFFLINE_MATRIX],
)
def corpus(session: nox.Session, django: str) -> None:
    """Replay the offline query corpus of this Django version (no IBM i).

    Django, library and test suite, comes from exactly the commit the corpus was
    captured with (docs/proposals/offline-query-corpus.md), never from PyPI.
    """
    import pathlib
    import tomllib

    manifests = sorted(pathlib.Path("tests/offline/corpus", django).glob("*/manifest.toml"))
    if not manifests:
        session.log(f"no offline query corpus for Django {django}: nothing to replay")
        return
    manifest = tomllib.loads(manifests[0].read_text())
    checkout = django_checkout(session, django, manifest["django_commit"])
    session.install(*nox.project.dependency_groups(PYPROJECT, "test"))
    session.install("--no-deps", "-e", ".")
    others = [
        dependency
        for dependency in PYPROJECT["project"]["dependencies"]
        if not dependency.lower().startswith("django")
    ]
    # Editable, as the django_tests session installs it for the capture, so the
    # version string (with the git date) matches the pickles' exactly.
    session.install(*others)
    session.install("-e", checkout)
    session.run(
        "pytest",
        "tests/corpus",
        "-m",
        "corpus",
        "--ds=tests.django_settings.settings_corpus",
        f"--results-summary={results_summary(django, 'corpus')}",
        *session.posargs,
        env={
            "DB2I_DJANGO_TESTS": f"{checkout}/tests",
            "DB2I_CORPUS_MODULES": ",".join(manifest.get("modules", {})),
            "DB2I_CORPUS_DJANGO": django,
        },
    )


@nox.session(python=NEWEST_PYTHON)
def wheel(session: nox.Session) -> None:
    """Build sdist + wheel into dist/ and run the offline tier against the installed wheel.

    The tests run from a copy of tests/, scripts/, probes/, changelog.d/, pyproject.toml
    and CHANGELOG.md without the django_db2_for_i source tree, so the import
    comes from the wheel (checked before pytest runs).
    """
    import glob
    import shutil
    import tempfile

    shutil.rmtree("dist", ignore_errors=True)
    session.run("uv", "build", "--out-dir", "dist", external=True)
    (built,) = glob.glob("dist/*.whl")
    session.install(*nox.project.dependency_groups(PYPROJECT, "test"))
    session.install(built, f"Django~={NEWEST_DJANGO}.0")
    with tempfile.TemporaryDirectory(prefix="wheel-test-") as tmp:
        # probes/: scripts/release_run.py reuses its reachability check.
        for name in ("tests", "scripts", "probes", "changelog.d"):
            shutil.copytree(name, f"{tmp}/{name}", ignore=shutil.ignore_patterns("__pycache__"))
        for name in ("pyproject.toml", "CHANGELOG.md"):
            shutil.copy(name, tmp)
        session.chdir(tmp)
        session.run(
            "python",
            "-c",
            "import django_db2_for_i as m; assert 'site-packages' in m.__file__, m.__file__; "
            "print('testing', m.__file__, m.__version__)",
        )
        session.run("pytest", "-m", "offline", "-p", "no:cacheprovider", *session.posargs)


@nox.session(python=NEWEST_PYTHON)
def pub400(session: nox.Session) -> None:
    """Tier 2: curated smoke set against PUB400 (newest Python, newest Django).

    Another supported Django version as the first argument: nox -s pub400 -- 6.0
    Reuses the test library by default (pytest-django --reuse-db, Django's
    keepdb: safe with the test marker table, and saves DDL on PUB400).
    Fully clean run: nox -s pub400 -- --create-db
    """
    django, args = django_argument(session)
    install(session, django, "test")
    reuse = [] if "--create-db" in args else ["--reuse-db"]
    session.run(
        "pytest",
        "-m",
        "pub400",
        "--ds=tests.django_settings.settings_pub400",
        # Short tracebacks: no function arguments (defense in depth, together
        # with the report redaction in tests/redaction.py).
        "--tb=short",
        f"--results-summary={results_summary(django, 'pub400')}",
        *reuse,
        *args,
    )


@nox.session(python=NEWEST_PYTHON)
def django_tests(session: nox.Session) -> None:
    """Tier 3 on a shared system: Django's runtests.py for named modules (scripts/runtests.sh).

    nox -s django_tests -- <django-version> [--clean] [--debug-sql] <module> [<module> ...]
    """
    if not session.posargs:
        session.error(
            "usage: nox -s django_tests -- <django-version> [--clean] [--debug-sql] <module> ..."
        )
    version = session.posargs[0]
    checkout = f"vendor/django-{version}"
    # Django from the vendor checkout (stable/<version>.x); the backend without
    # dependency resolution, since the checkout's version is a pre-release.
    session.install("-e", checkout)
    session.install("--no-deps", "-e", ".")
    others = [
        dependency
        for dependency in PYPROJECT["project"]["dependencies"]
        if not dependency.lower().startswith("django")
    ]
    session.install(*others)
    session.run("python", "scripts/run_django_tests.py", *session.posargs)


@nox.session(python=NEWEST_PYTHON)
def release_run(session: nox.Session) -> None:
    """Before a release, per Django version: all supported Django modules, then the
    pub400 tier (scripts/release_run.py; sequential, one connection at a time).

    nox -s release_run -- <django-version>
    """
    if len(session.posargs) != 1:
        session.error("usage: nox -s release_run -- <django-version>")
    # Django from the vendor checkout, as in django_tests, for the modules and the tier.
    session.install(*nox.project.dependency_groups(PYPROJECT, "test"))
    session.install("-e", f"vendor/django-{session.posargs[0]}")
    session.install("--no-deps", "-e", ".")
    session.install(
        *[
            dependency
            for dependency in PYPROJECT["project"]["dependencies"]
            if not dependency.lower().startswith("django")
        ]
    )
    session.run("python", "scripts/release_run.py", *session.posargs)


@nox.session(python=NEWEST_PYTHON)
def features(session: nox.Session) -> None:
    """docs/FEATURES.md: dump the feature flags on every supported Django (offline), then render."""
    session.install(*nox.project.dependency_groups(PYPROJECT, "test"))
    for django in DJANGO_PYTHONS:
        session.install("-e", ".", f"Django~={django}.0")
        session.run("python", "scripts/features.py", "dump")
    session.run("python", "scripts/features.py", "render")


@nox.session(python=NEWEST_PYTHON)
def test_status(session: nox.Session) -> None:
    """Regenerate docs/TEST_STATUS.md from the logs in test-results/."""
    install(session, NEWEST_DJANGO)
    session.run("python", "scripts/update_test_status.py", *session.posargs)


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
def probe_drop(session: nox.Session) -> None:
    """CHANGES THE IBM i: write probe w05 (tables + view). Dry run unless -- --execute."""
    session.install("-e", ".")
    session.run("python", "probes/w05_drop.py", *session.posargs)


@nox.session(python=NEWEST_PYTHON)
def probe_defaults(session: nox.Session) -> None:
    """Write probe 06 (QTEMP only, nothing persists): accepted column DEFAULT forms."""
    session.install("-e", ".")
    session.run("python", "probes/w06_defaults.py", *session.posargs)


@nox.session(python=NEWEST_PYTHON)
def probe_savepoints(session: nox.Session) -> None:
    """CHANGES THE IBM i: write probe w07 (one table). Dry run unless -- --execute."""
    session.install("-e", ".")
    session.run("python", "probes/w07_savepoints.py", *session.posargs)


@nox.session(python=NEWEST_PYTHON)
def probe_inquiry(session: nox.Session) -> None:
    """Write probe 08 (QTEMP and own job only): DROP COLUMN inquiry message."""
    session.install("-e", ".")
    session.run("python", "probes/w08_inquiry.py", *session.posargs)


@nox.session(python=NEWEST_PYTHON)
def probe_job_reuse(session: nox.Session) -> None:
    """Write probe 09 (own job only, two sequential connections): INQMSGRPY after disconnect."""
    session.install("-e", ".")
    session.run("python", "probes/w09_job_reuse.py", *session.posargs)


@nox.session(python=NEWEST_PYTHON)
def setup_journal(session: nox.Session) -> None:
    """CHANGES THE IBM i: create QSQJRN in a test library. Dry run unless -- --execute."""
    session.install("-e", ".")
    session.run("python", "probes/setup_journal.py", *session.posargs)


@nox.session(python=NEWEST_PYTHON)
def probe_encoding(session: nox.Session) -> None:
    """Write probe 10 (QTEMP only, one connection per variant): string encoding."""
    session.install("-e", ".")
    session.run("python", "probes/w10_encoding.py", *session.posargs)


@nox.session(python=NEWEST_PYTHON)
def probe_job_ccsid(session: nox.Session) -> None:
    """Write probe 11 (QTEMP and own job, restored): job CCSID 37 and finding B."""
    session.install("-e", ".")
    session.run("python", "probes/w11_job_ccsid.py", *session.posargs)


@nox.session(python=NEWEST_PYTHON)
def probe_locale(session: nox.Session) -> None:
    """Write probe 12 (QTEMP only, one connection per locale): non-UTF-8 locale."""
    install(session, NEWEST_DJANGO)
    session.run("python", "probes/w12_locale.py", *session.posargs, env={"PYTHONPATH": "."})
