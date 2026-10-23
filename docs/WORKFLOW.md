# Workflow

How to work on django-db2-for-i, step by step, with the exact commands. This
file is the single source: `bin/help` shows the quick start and lists the
topics, `bin/help <topic>` shows one of them. Every script in `bin/` runs on
the host, has `--help` and `--dry-run`, and never prints secrets. The rules
behind the steps are in [CONTRIBUTING.md](../CONTRIBUTING.md) and, for Claude,
in [CLAUDE.md](../CLAUDE.md).

## Quick start

A typical change, from a new branch to a pull request:

```sh
git fetch origin && git switch -c feat/<topic> origin/main   # 1. a branch from main
bin/check                                                     # 2. lint, offline tests, replay, gate
bin/verify                                                    # 3. changed SQL / IBM i tests: verify on IBM i
git add <paths> && git commit                                 # 4. signed, by explicit path
git push -u origin feat/<topic> && gh pr create               # 5. the pull request
```

Step 3 is needed when step 2 reports unverified SQL or the classification
asks for an IBM i run (topic `change`). Then add a changelog fragment
(topic `commit`).

## setup: first-time installation

1. Install Docker (e.g. Docker Desktop) with the `docker compose` plugin.
   The host needs nothing else: bash 3.2 and the system `python3` are enough.
2. Run `bin/setup` **in your own terminal**:
   - it builds the images (`tests` with the IBM i Access ODBC Driver,
     `offline` without it);
   - when there is no `.env`, it copies `.env.example` and asks for the IBM i
     user, password (hidden), the two libraries and the host, and writes them
     into `.env` (mode 600, nothing printed). An existing `.env` is never
     read or changed;
   - it puts `vendor/django-<version>` at the commit each corpus manifest pins;
   - it ends with `bin/doctor --offline`.
3. Run `bin/doctor`: every check again, then one connection to PUB400.

`bin/setup` is for humans: Claude never runs it interactively and never
enters values (only without a terminal, when it just copies the template, or
when `.env` exists). The image with the IBM driver is built locally and never
pushed to a public registry (IBM's license).

## branch: starting work

1. One branch per logical change, named `<type>/<topic>` (`feat/`, `fix/`,
   `docs/`, `test/`, `ci/`, `chore/`, `build/`), from an up-to-date `main`:
   `git fetch origin && git switch -c fix/<topic> origin/main`.
2. For parallel work, use a worktree next to the checkout:
   `git worktree add ../django-db2-for-i-<topic> -b fix/<topic> origin/main`.
   The `bin/` scripts work there too (the container gets the shared git
   directory).
3. `.env` is gitignored, so a new worktree has none, and IBM i runs there
   stop with "no .env in this checkout". Link it **only into worktrees the
   main session uses for IBM i runs**:
   `ln -s ../django-db2-for-i/.env .env`. **Never** link (or copy) it into a
   subagent's worktree (`.claude/worktrees/`): subagents work offline only,
   and a missing `.env` is an extra safeguard there.
4. Remove a worktree when its branch is merged:
   `bin/worktree-remove ../django-db2-for-i-<topic>`. It copies the
   worktree's `test-results/` (probe results, logs, reports) to the main
   checkout's `test-results/archive/<worktree>/`, removes the `.env` link and
   refuses a worktree with changes, an unmerged branch or a real `.env` file.
5. Probe output a decision rests on goes into the repository:
   `bin/probe --publish test-results/probes/<probe>-<utc>.json` writes
   `probes/results/<probe>.json` with host, user and library names replaced.

## change: the daily loop

1. Edit, then `bin/check` (what CI does: lint, the offline tests and the
   corpus replay for every Python × Django combination, the verification
   gate, the classification). Faster for one combination:
   `bin/check --python 3.14 --django 6.1`.
2. Read the classification at the end of `bin/check`:
   - **docs/tests only**, no label: no IBM i run;
   - **run-ibmi**: changed SQL or tests that run on IBM i: a targeted run;
   - **needs-full-tier**: the driver layer, `base.py`, `creation.py`, the
     capabilities, the container image, the pinned Django commit or the
     supported Django versions: the full own IBM i tier.
3. `bin/verify` does the targeted run: it writes changed SQL to the goldens
   and the corpus, runs exactly what needs IBM i (unverified goldens, new or
   changed own IBM i tests, one Django test per unverified corpus entry, tests
   that left the skip lists; the full own tier when shared test code changed)
   and writes the stamps of what passed. Read
   `test-results/verify/<django>/report.txt`, review `git diff`, commit the
   stamps yourself. `bin/ibmi-test --affected` runs the same selection without
   writing anything; `bin/ibmi-test --full-tier` the full own tier.
4. `bin/check` exits 3 when only the gate failed (SQL without a stamp): the
   branch may be pushed, and stays red in CI until the stamps are committed.

## commit: signed commits and changelog fragments

1. Stage by explicit path, never `git add -A` or `git add .`:
   `git add bin/verify tests/offline/test_bin.py`.
2. Conventional commit messages: `feat(scope): ...`, `fix: ...`,
   `docs: ...`, `test: ...`, `build(bin): ...`, `chore: ...`. One logical
   change per commit.
3. Every commit is signed (the repository's git config); `main` accepts only
   signed commits. Check with `git log --show-signature -1`.
4. A user-visible change gets a changelog fragment,
   `changelog.d/<topic>.<type>.md` (`added`, `enabled`, `changed`, `fixed`,
   `limitation`; see `changelog.d/README.md`). Once the pull request exists,
   rename it to `changelog.d/<PR>.<type>.md` and push.

## pr: pull requests and labels

1. Before every push: `bin/check` passes (exit 0, or 3 for the gate only).
2. `git push -u origin <branch>`, then `gh pr create`. The description says
   what changed, how it was checked, and which IBM i runs follow.
3. CI (`classify`) comments the classification and adds `run-ibmi` or
   `needs-full-tier`. Run what it asks for (topic `change`) on the pull
   request's **latest** commit, post the result (the SHA, the counts), then
   remove the label (REST:
   `gh api -X DELETE "repos/{owner}/{repo}/issues/<PR>/labels/run-ibmi"`).
4. A later push puts the labels back, except a push that only adds the
   stamps of that run (and files generated from them), or a conflict-free
   rebase onto docs/tests-only `main` commits with identical changes.
5. When the branch is behind `main`, rebase and
   `git push --force-with-lease` (pull request branches only; never `main`).
   Never use GitHub's "Update branch" button.
6. Never merge your own pull request; the maintainer reviews and merges.

## review: what the maintainer checks before merging

1. CI is green on the latest commit (`offline` is required on `main`).
2. No `run-ibmi` or `needs-full-tier` label is left, and the pull request
   shows the IBM i run on its latest commit (SHA and counts).
3. Goldens and corpus entries carry stamps (the gate); stamp-only commits
   match the run they come from.
4. The backend diff: only what the description says; capabilities and
   Django-version checks only in their own modules (`capabilities.py`,
   `compat.py`), driver code only in `drivers/`.
5. Docs and a changelog fragment come with user-visible changes.
6. Merge with a merge commit (no squash, no rebase merge).

## ibmi: working with PUB400

1. PUB400 is a shared community system: never the full Django test suite,
   one connection at a time, `--parallel=1`, no retry storms.
2. **One PUB400 job at a time on this machine.** Every run goes through
   `scripts/pub400.sh` and its lock; a second job stops with
   "PUB400 busy: <holder>", or queues with `--wait`.
3. The scripts:
   - `bin/doctor`: the environment check and one connection;
   - `bin/probe <name>` (`--list`): read-only probes; probes may change only
     `QTEMP`; anything else needs the maintainer's approval first;
   - `bin/ibmi-test own <tests>`, `bin/ibmi-test django <label>...`,
     `bin/ibmi-test --full-tier`, `bin/ibmi-test --affected`;
   - `bin/verify`: targeted runs with stamps (topic `change`);
   - `bin/ibmi-cleanup`: lists the leftover test tables of a crashed run;
     `--yes` drops them (only listed tables, only in a marked test library).
4. Django test runs always use `--clean`; a kept test database blocks the
   next own-test run.

## status: where things stand

1. **README badges**: CI on `main`, the latest release, and per IBM i release,
   Python and Django version ✅ supported, 🚧 in development, 🗓️ planned,
   ⚠️ end of life, ❌ not supported. The README's "Test status" and "Project
   status" sections and the badges are generated; never edit them by hand.
2. **[TEST_STATUS.md](TEST_STATUS.md)**: per Django version the counts of the
   four test sets (passed, skipped, expected failures, failed, last run), then
   per Django test module. Generated from the logs in `test-results/`.
3. **`bin/status`** regenerates TEST_STATUS, the badges, README's generated
   sections and FEATURES.md from `test-results/` (in the container, never
   connecting to an IBM i), then shows who holds the PUB400 lock and the open
   pull requests that still carry `run-ibmi` or `needs-full-tier`.
   `bin/status --no-write` only shows the lock and those pull requests.
4. Only the labelled pull requests, without regenerating:
   ```sh
   gh api "repos/{owner}/{repo}/pulls?state=open&per_page=100" \
     --jq '.[] | select(any(.labels[]; .name == "run-ibmi" or .name == "needs-full-tier")) | "#\(.number) \(.title)"'
   ```

## release: preparing a release

1. **Release run**, every supported Django version: `bin/release-run` (all
   versions, one after another) or `bin/release-run --django <version>`.
   It is resumable: a later start on the same commits skips what passed, so
   it may be spread over several nights (`--restart` starts over,
   `--limit N` stops after N runs). When a version passed completely, its
   corpus is rebuilt in the working tree. IBM i only, nothing on GitHub.
2. **Release pull request**: `bin/release-prepare <version>` in the main
   checkout on an up-to-date `main` (never in a subagent worktree; no `.env`
   needed). It checks every precondition first (CI on `main`, the gate,
   complete and passed release runs with the backend unchanged since, a
   newer version, changelog fragments), then opens the pull request.
3. **The maintainer merges it**, then signs and pushes the tag on the merge
   commit from their own release clone:
   ```sh
   git switch main && git pull --ff-only
   git log -1 --show-signature
   git tag -s v<version> -m "v<version>"
   git tag -v v<version>
   git push origin v<version>
   ```
4. **The maintainer creates the GitHub release** by hand (the release
   workflow is parked, see #94).

Claude never creates, pushes or deletes tags, and never creates or edits
releases; `bin/release-prepare` only prints steps 3 and 4.

## troubleshooting: common problems

- **PUB400 unreachable**: runs fail fast (a TCP check of the database port
  comes first). Check with `bin/doctor`; try again later, never in a loop.
- **The Mac slept during a run** (`08S01` "Communication link failure",
  CWBCO1034): `scripts/pub400.sh` wraps runs in `caffeinate`; keep the lid
  open, or start again (`bin/release-run` resumes).
- **CPA32B2 / HY008** (an `ALTER TABLE` that drops data is cancelled):
  see [Troubleshooting](user/Troubleshooting.md); the fix is a reply list
  entry an administrator adds, never a change made by a test run.
- **"PUB400 busy: <holder>"**: another job holds the lock; wait with
  `--wait`. The OS releases the lock when its process dies, so a lock is
  never stale: `python3 scripts/pub400_lock.py --status` shows the holder.
- **An unverified golden or corpus entry** (`bin/check` exit 3, the gate):
  run `bin/verify`, or add the `run-ibmi` label to the pull request.
- **"no .env in this checkout"** in a worktree: link it (topic `branch`),
  only in a worktree the main session uses for IBM i runs.
- **Leftover test tables after a crash** (the next run refuses the
  library): `bin/ibmi-cleanup` lists them, `bin/ibmi-cleanup --yes` drops them.
- **"detected dubious ownership"** from git in the container: the `bin/`
  scripts pass the checkout's mount (`/workspace`) as git's `safe.directory`
  for each run; run git in the container through them, never with
  `safe.directory '*'`.
