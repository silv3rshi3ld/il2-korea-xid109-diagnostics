#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
umask 077

if (($# < 1)); then
    printf 'error: internal launcher requires the real Proton path\n' >&2
    exit 2
fi
real_proton=$1
shift

app_id=${SteamAppId:-${STEAM_COMPAT_APP_ID:-${SteamGameId:-}}}
if [[ $app_id != 247970 ]]; then
    exec "$real_proton" "$@"
fi
proton_action=${1:-}
case $proton_action in
    run|waitforexitandrun) ;;
    *) exec "$real_proton" "$@" ;;
esac

state_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
repo_path_file="$state_dir/repo-path"
case_file="$state_dir/selected-case"
matrix="$state_dir/test-matrix.conf"
common="$state_dir/common.sh"

if [[ ! -r $repo_path_file || ! -r $case_file || ! -r $matrix || ! -r $common ]]; then
    printf 'error: diagnostic compatibility-tool state is incomplete; reinstall it\n' >&2
    exit 1
fi
# shellcheck source=tools/lib/common.sh
source "$common"

repo_dir=$(<"$repo_path_file")
selected_case=$(<"$case_file")
[[ -d $repo_dir && -x $repo_dir/tools/run-artifacts.py ]] || {
    printf 'error: diagnostic repository is unavailable at %s; reinstall after moving it\n' "$repo_dir" >&2
    exit 1
}

record_launch_error() {
    local message=$1 error_file error_tmp
    mkdir -p -- "$repo_dir/.state"
    error_file="$repo_dir/.state/last-launch-error.txt"
    error_tmp="$error_file.tmp.$$"
    {
        printf 'time_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        printf 'message=%s\n' "$message"
    } >"$error_tmp"
    mv -- "$error_tmp" "$error_file"
}

if [[ ${XDG_SESSION_TYPE:-unknown} != x11 ]]; then
    record_launch_error "session was ${XDG_SESSION_TYPE:-unknown}, not X11; the game was not started"
    printf '%s\n' \
        'error: the controlled diagnostic launch requires an X11 session.' \
        'Do not change login-session settings without asking the investigation coordinator.' >&2
    exit 1
fi

case_record=$(il2_diag_matrix_lookup "$matrix" "$selected_case") || {
    printf 'error: invalid selected diagnostic case: %s\n' "$selected_case" >&2
    exit 1
}
IFS='|' read -r case_name vkd3d_config disabled_extensions case_description <<<"$case_record"

kernel_probe=$(journalctl -k -n 1 -o cat --no-pager 2>/dev/null || true)
if [[ -z $kernel_probe ]]; then
    record_launch_error 'kernel journal access was unavailable; the game was not started'
    printf '%s\n' \
        'error: kernel journal access is unavailable, so an NVIDIA Xid could not be captured.' \
        'Run ./il2-diagnostic.sh check and send its output to the investigation coordinator.' >&2
    exit 1
fi

available_kib=$(df -Pk -- "$repo_dir" | awk 'NR == 2 {print $4}')
if [[ ! $available_kib =~ ^[0-9]+$ ]] || ((available_kib < IL2_DIAG_PER_RUN_HEADROOM_KIB)); then
    record_launch_error 'less than 2 GiB of result space was available; the game was not started'
    printf 'error: at least 2 GiB of free result space is required before each run\n' >&2
    exit 1
fi

exec 9>"$state_dir/run.lock"
if ! flock -n 9; then
    record_launch_error 'another diagnostic run was already active; the game was not started'
    printf 'error: another IL-2 diagnostic run is already active\n' >&2
    exit 1
fi

authorization="$state_dir/run-authorization"
if [[ ! -f $authorization || -L $authorization ]] ||
    ! grep -Fxq -- "case=$case_name" "$authorization"; then
    record_launch_error 'no one-use launch authorization was available; run ./il2-diagnostic.sh next'
    printf '%s\n' \
        'error: this diagnostic launch was not authorized by the Next step.' \
        'Return to the extracted folder and run ./il2-diagnostic.sh next before clicking Play.' >&2
    exit 1
fi

results_root="$repo_dir/results"
mkdir -p -- "$results_root"
timestamp=$(date -u +%Y-%m-%dT%H%M%SZ)
run_dir=''
for suffix in '' '-2' '-3' '-4' '-5' '-6' '-7' '-8' '-9'; do
    candidate="$results_root/$timestamp-$case_name$suffix"
    if mkdir -- "$candidate" 2>/dev/null; then
        run_dir=$candidate
        break
    fi
done
[[ -n $run_dir ]] || { printf 'error: could not allocate a unique run directory\n' >&2; exit 1; }
if ! mv -- "$authorization" "$run_dir/run-authorization.txt"; then
    rmdir -- "$run_dir"
    record_launch_error 'the one-use launch authorization could not be consumed'
    printf '%s\n' 'error: could not consume the one-use diagnostic launch authorization' >&2
    exit 1
fi
rm -f -- "$repo_dir/.state/last-launch-error.txt"
mkdir -p -- "$run_dir/shaders"
printf 'capture started; this file becomes .capture-complete during normal finalization\n' \
    >"$run_dir/.capture-in-progress"

start_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
start_epoch=$(date +%s)
harness_commit=$(il2_diag_harness_revision "$repo_dir")
printf '%s\n' "$start_utc" >"$run_dir/start-utc.txt"
printf '%s\n' "$start_epoch" >"$run_dir/start-epoch.txt"
if [[ -r /proc/sys/kernel/random/boot_id ]]; then
    cp -- /proc/sys/kernel/random/boot_id "$run_dir/boot-id-start.txt"
else
    printf '%s\n' unavailable >"$run_dir/boot-id-start.txt"
fi

journal_cursor=''
if command -v journalctl >/dev/null 2>&1; then
    while IFS= read -r line; do
        case $line in
            '-- cursor: '*) journal_cursor=${line#-- cursor: } ;;
        esac
    done < <(journalctl -k -n 0 --show-cursor --no-pager 2>/dev/null || true)
fi
printf '%s\n' "${journal_cursor:-unavailable}" >"$run_dir/journal-cursor-start.txt"

python3 "$repo_dir/tools/run-artifacts.py" init \
    --output "$run_dir/metadata.json" \
    --case "$case_name" \
    --description "$case_description" \
    --vkd3d-config "$vkd3d_config" \
    --disabled-extensions "$disabled_extensions" \
    --start "$start_utc" \
    --build-manifest "$state_dir/build-manifest.json" \
    --harness-commit "$harness_commit"
cp -a -- "$state_dir/install-manifest.json" "$run_dir/install-manifest.json"

{
    printf 'real_proton='
    printf '%q' "$real_proton"
    printf '\narguments='
    printf ' %q' "$@"
    printf '\n'
} >"$run_dir/command.txt"

export PROTON_LOG=1
export PROTON_LOG_DIR="$run_dir"
export VKD3D_CONFIG="$vkd3d_config"
export VKD3D_DEBUG=info
export VKD3D_SHADER_DEBUG=err
export VKD3D_LOG_FILE="$run_dir/vkd3d.log"
export VKD3D_SHADER_DUMP_PATH="$run_dir/shaders"
if [[ -n $disabled_extensions ]]; then
    export VKD3D_DISABLE_EXTENSIONS="$disabled_extensions"
else
    unset VKD3D_DISABLE_EXTENSIONS
fi
# The controlled matrix always uses Vulkan's normal device selection.
unset VKD3D_VULKAN_DEVICE VKD3D_FILTER_DEVICE_NAME

{
    printf 'SteamAppId=%s\n' "${SteamAppId:-unset}"
    printf 'STEAM_COMPAT_APP_ID=%s\n' "${STEAM_COMPAT_APP_ID:-unset}"
    printf 'SteamGameId=%s\n' "${SteamGameId:-unset}"
    printf 'STEAM_COMPAT_DATA_PATH=%s\n' "${STEAM_COMPAT_DATA_PATH:-unset}"
    printf 'PROTON_LOG=%s\n' "$PROTON_LOG"
    printf 'PROTON_LOG_DIR=%s\n' "$PROTON_LOG_DIR"
    printf 'VKD3D_CONFIG=%s\n' "$VKD3D_CONFIG"
    printf 'VKD3D_DEBUG=%s\n' "$VKD3D_DEBUG"
    printf 'VKD3D_SHADER_DEBUG=%s\n' "$VKD3D_SHADER_DEBUG"
    printf 'VKD3D_LOG_FILE=%s\n' "$VKD3D_LOG_FILE"
    printf 'VKD3D_SHADER_DUMP_PATH=%s\n' "$VKD3D_SHADER_DUMP_PATH"
    printf 'VKD3D_DISABLE_EXTENSIONS=%s\n' "${VKD3D_DISABLE_EXTENSIONS:-unset}"
    printf 'VKD3D_VULKAN_DEVICE=unset-by-harness\n'
    printf 'VKD3D_FILTER_DEVICE_NAME=unset-by-harness\n'
} >"$run_dir/environment.txt"

warnings_file="$run_dir/capture-warnings.txt"
: >"$warnings_file"
if ! "$repo_dir/tools/collect-system.sh" "$run_dir"; then
    printf '%s\n' 'system collection failed' >>"$warnings_file"
fi

journal_pid=''
capture_ready=1
proton_status=125
proton_pid=''
requested_signal_status=''
stop_journal_follower() {
    if [[ -n $journal_pid ]] && kill -0 "$journal_pid" 2>/dev/null; then
        kill "$journal_pid" 2>/dev/null || true
        wait "$journal_pid" 2>/dev/null || true
    fi
    journal_pid=''
}
# Called indirectly by signal traps.
# shellcheck disable=SC2329
forward_signal() {
    local signal_name=$1
    local signal_status=$2
    requested_signal_status=$signal_status
    if [[ -n $proton_pid ]] && kill -0 "$proton_pid" 2>/dev/null; then
        kill -s "$signal_name" "$proton_pid" 2>/dev/null || true
    else
        exit "$signal_status"
    fi
}
# Called indirectly by the EXIT trap.
# shellcheck disable=SC2329
finalize_on_exit() {
    local saved_status=$?
    trap - EXIT HUP INT TERM
    stop_journal_follower
    if ((capture_ready)) && [[ -f $run_dir/.capture-in-progress ]]; then
        "$repo_dir/tools/finalize-run.sh" --run-dir "$run_dir" \
            --exit-code "$proton_status" --interrupted || true
    fi
    exit "$saved_status"
}
trap finalize_on_exit EXIT
trap 'forward_signal HUP 129' HUP
trap 'forward_signal INT 130' INT
trap 'forward_signal TERM 143' TERM

boot_id=$(tr -d '-' <"$run_dir/boot-id-start.txt")
if [[ -n $journal_cursor ]]; then
    python3 "$repo_dir/tools/parent-death-exec.py" stdbuf -oL -eL \
        journalctl -k --boot="$boot_id" --after-cursor="$journal_cursor" \
        -o short-iso-precise --no-hostname --no-pager --follow \
        >"$run_dir/kernel-live.log" 2>"$run_dir/journal-follow-errors.log" 9>&- &
else
    python3 "$repo_dir/tools/parent-death-exec.py" stdbuf -oL -eL \
        journalctl -k --boot="$boot_id" --since "$start_utc" \
        -o short-iso-precise --no-hostname --no-pager --follow \
        >"$run_dir/kernel-live.log" 2>"$run_dir/journal-follow-errors.log" 9>&- &
fi
journal_pid=$!
printf '%s\n' "$journal_pid" >"$run_dir/journal-follower.pid"
sleep 0.2
if ! kill -0 "$journal_pid" 2>/dev/null; then
    wait "$journal_pid" 2>/dev/null || true
    printf '%s\n' 'live kernel journal collector exited before the game started' >>"$warnings_file"
    printf '%s\n' \
        'error: live kernel journal capture could not stay active; the game was not started.' \
        'Run ./il2-diagnostic.sh check and send the output to the coordinator.' >&2
    exit 1
fi

printf 'IL-2 Xid109 diagnostics: starting %s run in %s\n' "$case_name" "$run_dir" >&2
# This timestamp excludes harness preflight. It is the Proton process-runtime start,
# not the tester's hangar-ready observation time.
proton_runtime_start_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
proton_runtime_start_epoch=$(date +%s)
printf '%s\n' "$proton_runtime_start_utc" >"$run_dir/proton-runtime-start-utc.txt"
printf '%s\n' "$proton_runtime_start_epoch" >"$run_dir/proton-runtime-start-epoch.txt"
set +e
python3 "$repo_dir/tools/parent-death-exec.py" "$real_proton" "$@" 9>&- &
proton_pid=$!
printf '%s\n' "$proton_pid" >"$run_dir/proton-child.pid"
while true; do
    wait "$proton_pid"
    wait_status=$?
    if kill -0 "$proton_pid" 2>/dev/null; then
        continue
    fi
    proton_status=$wait_status
    break
done
if [[ -n $requested_signal_status ]]; then
    proton_status=$requested_signal_status
fi
set -e
stop_journal_follower
finalize_args=(--run-dir "$run_dir" --exit-code "$proton_status")
[[ -n $requested_signal_status ]] && finalize_args+=(--interrupted)
"$repo_dir/tools/finalize-run.sh" "${finalize_args[@]}"
capture_ready=0
trap - EXIT HUP INT TERM

printf 'IL-2 Xid109 diagnostics: finalized %s\n' "$run_dir" >&2
exit "$proton_status"
