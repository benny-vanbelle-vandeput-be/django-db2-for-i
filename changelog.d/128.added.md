`bin/check` (what CI does, locally) and `bin/status` (status pages, the
PUB400 lock holder, the pull requests waiting for an IBM i run), with
`--help` and `--dry-run`. Every PUB400 run holds a lock outside the checkout
(`scripts/pub400.sh`, `scripts/pub400_lock.py`): a second job stops with
"PUB400 busy: <holder>", or waits with `--wait`.
