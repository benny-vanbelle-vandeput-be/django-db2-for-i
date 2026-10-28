Each git worktree gets its own nox virtualenvs (a Docker volume per checkout), so `bin/check` and other nox runs in two worktrees no longer break each other; `bin/worktree-remove` removes the volume.
