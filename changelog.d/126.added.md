Every pull request is classified from its changed files (needs full tier,
SQL-affecting, docs/tests only) by `scripts/classify_pr.py`; the CI job
`classify` comments the result and adds the labels `needs-full-tier` and
`run-ibmi` that decide which IBM i run a pull request needs
(CONTRIBUTING.md, "Pull requests and IBM i runs").
