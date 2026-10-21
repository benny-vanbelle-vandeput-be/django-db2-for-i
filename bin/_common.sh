# Shared part of the bin/ scripts, sourced by each of them (phase 4 step 0).
#
# - --help / -h prints the script's header comment; --dry-run prints every
#   command instead of running it (run).
# - container runs a command in the tests container (docker compose). In a
#   git worktree it also mounts the repository's shared git directory at its
#   host path, so git works inside the container.
# - nox_combinations lists the Python x Django combinations of the noxfile
#   (DJANGO_PYTHONS), so the scripts keep no second list.
# - pub400 runs a PUB400 nox session through scripts/pub400.sh, which holds
#   the PUB400 lock (one PUB400 job at a time on this machine).
#
# No secrets: the scripts never read, source or print .env; docker compose
# loads it into the container itself. Written for bash 3.2 (macOS).

set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
DRY_RUN=0
ARGS=()

usage() {
    # The header comment of the calling script, up to the first blank line.
    awk 'NR == 1 { next } /^#/ { sub(/^# ?/, ""); print; next } { exit }' "$0"
}

# Handles --help and --dry-run; the other arguments are left in ARGS.
common_args() {
    ARGS=()
    local arg
    for arg in "$@"; do
        case $arg in
            -h | --help)
                usage
                exit 0
                ;;
            --dry-run) DRY_RUN=1 ;;
            *) ARGS+=("$arg") ;;
        esac
    done
}

die() {
    echo "$(basename "$0"): $*" >&2
    exit 2
}

run() {
    if [ "$DRY_RUN" = 1 ]; then
        printf '+'
        printf ' %q' "$@"
        printf '\n'
    else
        "$@"
    fi
}

container() {
    local common mounts=()
    common=$(git -C "$ROOT" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)
    if [ -n "$common" ] && [ "$common" != "$ROOT/.git" ]; then
        mounts=(-v "$common:$common")
    fi
    run docker compose --project-directory "$ROOT" run --rm ${mounts[@]+"${mounts[@]}"} tests "$@"
}

nox_combinations() {
    python3 - "$ROOT/noxfile.py" <<'PY'
import ast
import sys

tree = ast.parse(open(sys.argv[1]).read())
for node in tree.body:
    if isinstance(node, ast.Assign) and any(
        isinstance(t, ast.Name) and t.id == "DJANGO_PYTHONS" for t in node.targets
    ):
        for django, pythons in ast.literal_eval(node.value).items():
            for python in pythons:
                print(python, django)
PY
}

pub400() {
    run "$ROOT/scripts/pub400.sh" "$@"
}
