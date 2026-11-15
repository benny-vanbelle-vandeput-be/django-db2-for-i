`docs/RELEASE_HISTORY.md` shows, per release, the feature flags that were on,
which ones each release switched on, and the test results of the status run.
`scripts/release_history.py` (`nox -s release_history`) generates it from the
release tags. `bin/release-prepare` and `bin/status` regenerate it, so every
release pull request adds its own row.
