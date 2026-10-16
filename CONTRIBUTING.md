# Contributing

Thank you for your interest in django-db2-for-i.

## License of contributions

This project is licensed under the [BSD 3-Clause License](LICENSE), the same
license as Django. By submitting a contribution (pull request, patch, or any
other form), you agree that it is licensed under the same BSD 3-Clause License.

- Code or tests adapted from Django keep their original copyright notice.
- Do not submit code copied from projects with an incompatible license.
- The IBM i Access ODBC Driver is not part of this project and must never be
  committed or redistributed.

## Ground rules

- No credentials in commits, logs, or issue reports. Connection settings come
  from environment variables or a local `.env` file (gitignored).
- One logical change per commit, with a
  [Conventional Commits](https://www.conventionalcommits.org/) message
  (`feat:`, `fix:`, `docs:`, `test:`, `build:`, `ci:`, `chore:`).
- Claims about IBM i behaviour must be backed by a probe script in `probes/`
  and a note in `docs/IBMI_NOTES.md`.
- Every test skip or expected failure carries a one-line reason.
- Never run the full Django test suite against PUB400 or any other shared system.

## Development environment

All development and test runs happen in a container. See [README.md](README.md)
for setup instructions.
