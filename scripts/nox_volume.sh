#!/bin/sh
# The name of a checkout's nox-envs volume (compose.yaml, DB2I_NOX_ENVS):
#
#   scripts/nox_volume.sh <checkout>
#
# The main checkout keeps django-db2-for-i_nox-envs; every git worktree gets
# its own, django-db2-for-i_nox-envs-<directory name>, so two worktrees never
# rebuild each other's nox virtualenvs (#190, topic 4). bin/ (container) and
# scripts/pub400.sh pass the name to docker compose; bin/worktree-remove
# removes a worktree's volume with it. A plain `docker compose run` without
# DB2I_NOX_ENVS uses the main checkout's volume.
set -eu

dir=$(cd "${1:?usage: $0 <checkout>}" && pwd)
common=$(git -C "$dir" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)
if [ -z "$common" ] || [ "$common" = "$dir/.git" ]; then
    echo django-db2-for-i_nox-envs
else
    # Docker volume names: letters, digits, _ . -
    printf 'django-db2-for-i_nox-envs-%s\n' "$(basename "$dir" | tr -c 'A-Za-z0-9_.\n-' '-')"
fi
