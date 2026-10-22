- `bin/setup`: first-time setup: images, `.env` from `.env.example` (values
  typed in a terminal; an existing `.env` is never touched), the `vendor/`
  Django checkouts at their pinned commits, then `bin/doctor --offline`.
- `bin/release-run`: the release run per Django version, resumable: results
  are recorded as they come, and a later start on the same commits skips what
  passed (`--restart`, `--limit N`); the corpus is rebuilt when a version
  passed completely.
- `bin/release-prepare <version>`: checks the release preconditions and opens
  the release pull request; it never tags and never creates releases, and
  prints the maintainer's manual steps.
