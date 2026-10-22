# Shared part of the bin/ scripts, sourced by each of them (phase 4 step 0).
#
# - --help / -h prints the script's header comment; --dry-run prints every
#   command instead of running it (run).
# - container runs a command in the tests container (docker compose). In a
#   git worktree it also mounts the repository's shared git directory at its
#   host path, so git works inside the container. The checkout's mount
#   (/workspace) is git's safe.directory for that one run (passed as
#   environment, never written to a config file, never '*'): the files belong
#   to the host user, so git would otherwise refuse with "dubious ownership".
# - nox_combinations lists the Python x Django combinations of the noxfile
#   (DJANGO_PYTHONS), so the scripts keep no second list.
# - pub400 runs a PUB400 nox session through scripts/pub400.sh, which holds
#   the PUB400 lock (one PUB400 job at a time on this machine); --wait
#   (DB2I_LOCK_WAIT=1) queues behind a running job instead of stopping.
# - newest_django is the newest Django version of the noxfile.
#
# No secrets: the scripts never read, source or print .env; docker compose
# loads it into the container itself. Written for bash 3.2 (macOS).

set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# The checkout's mount point in the container (compose.yaml).
WORKSPACE=/workspace
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
            --wait) export DB2I_LOCK_WAIT=1 ;;
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
    run docker compose --project-directory "$ROOT" run --rm ${mounts[@]+"${mounts[@]}"} \
        -e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory -e GIT_CONFIG_VALUE_0="$WORKSPACE" \
        tests "$@"
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

newest_django() {
    nox_combinations | awk '{ print $2 }' | sort -t. -k1,1n -k2,2n | tail -n 1
}

pub400() {
    run "$ROOT/scripts/pub400.sh" "$@"
}

# ibmi_runs <django> <runs file> <results file> <record: 0|1>
# Runs each line of a runs file (scripts/verify.py select), each through the
# PUB400 lock, and writes "<kind> TAB <arguments> TAB <exit status>" per run to
# the results file. With record=1 the goldens that pass are stamped and the
# Django runs capture their statements for the corpus (bin/verify); with 0
# nothing is written (bin/ibmi-test --affected). A failed run does not stop
# the others. Returns 1 when a run failed.
ibmi_runs() {
    local django=$1 runs=$2 results=$3 record=$4 kind args status failed=0
    local tab=$'\t'
    if [ "$DRY_RUN" = 1 ]; then
        echo "+ (the IBM i runs listed in ${runs#"$ROOT"/}, each through scripts/pub400.sh)"
        return 0
    fi
    : >"$results"
    # fd 3: docker compose reads standard input.
    while IFS="$tab" read -r kind args <&3; do
        args=${args//$tab/ }
        local extra=()
        case $kind in
            goldens)
                [ "$record" = 1 ] && extra=(--record-verification)
                set -- pub400 pub400 "$django" tests/pub400/test_goldens.py --goldens-from "$args" \
                    ${extra[@]+"${extra[@]}"}
                ;;
            own)
                if [ "$args" = full ]; then
                    set -- pub400 pub400 "$django" --create-db
                else
                    # shellcheck disable=SC2086 # node ids, one word each
                    set -- pub400 pub400 "$django" --create-db $args
                fi
                ;;
            django)
                [ "$record" = 1 ] && extra=(--capture)
                # shellcheck disable=SC2086 # Django test labels, one word each
                set -- run "$ROOT/scripts/runtests.sh" "$django" --clean ${extra[@]+"${extra[@]}"} $args
                ;;
            *)
                echo "$(basename "$0"): unknown run in ${runs#"$ROOT"/}: $kind" >&2
                return 2
                ;;
        esac
        status=0
        "$@" || status=$?
        printf '%s\t%s\t%s\n' "$kind" "$args" "$status" >>"$results"
        [ "$status" = 0 ] || failed=1
    done 3<"$runs"
    return "$failed"
}
