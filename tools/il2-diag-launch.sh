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

app_id=${SteamAppId:-${STEAM_COMPAT_APP_ID:-}}
if [[ $app_id != 247970 ]]; then
    exec "$real_proton" "$@"
fi

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

case_record=$(il2_diag_matrix_lookup "$matrix" "$selected_case") || {
    printf 'error: invalid selected diagnostic case: %s\n' "$selected_case" >&2
    exit 1
}
IFS='|' read -r case_name vkd3d_config disabled_extensions case_description <<<"$case_record"

exec 9>"$state_dir/run.lock"
if ! flock -n 9; then
    printf 'error: another IL-2 diagnostic run is already active\n' >&2
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
mkdir -p -- "$run_dir/shaders"
printf 'capture started; this file becomes .capture-complete during normal finalization\n' \
    >"$run_dir/.capture-in-progress"

start_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
start_epoch=$(date +%s)
harness_commit='uncommitted'
if [[ -d $repo_dir/.git ]]; then
    harness_commit=$(git -C "$repo_dir" rev-parse HEAD 2>/dev/null || printf uncommitted)
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

warnings=()
if ! "$repo_dir/tools/collect-system.sh" "$run_dir"; then
    warnings+=("system collection failed")
fi

printf 'IL-2 Xid109 diagnostics: starting %s run in %s\n' "$case_name" "$run_dir" >&2
set +e
"$real_proton" "$@"
proton_status=$?
set -e

end_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
end_epoch=$(date +%s)
duration=$((end_epoch - start_epoch))

steam_log="$run_dir/steam-$app_id.log"
if [[ -f $steam_log ]]; then
    mv -- "$steam_log" "$run_dir/proton.log"
fi
home_proton_log="$HOME/steam-$app_id.log"
if [[ -f $home_proton_log ]]; then
    home_log_mtime=$(stat -c %Y -- "$home_proton_log" 2>/dev/null || printf 0)
    if ((home_log_mtime >= start_epoch)); then
        cp -a -- "$home_proton_log" "$run_dir/proton-home.log"
        if [[ ! -f $run_dir/proton.log ]]; then
            cp -a -- "$home_proton_log" "$run_dir/proton.log"
        fi
    fi
fi
if [[ ! -f $run_dir/proton.log ]]; then
    warnings+=("Proton log was not created")
    : >"$run_dir/proton.log"
fi
if [[ ! -f $run_dir/vkd3d.log ]]; then
    warnings+=("VKD3D log was not created")
    : >"$run_dir/vkd3d.log"
fi

kernel_log="$run_dir/kernel-full.log"
if [[ -n $journal_cursor ]]; then
    if ! journalctl -k --after-cursor="$journal_cursor" -o short-iso-precise --no-pager \
        >"$kernel_log" 2>&1; then
        warnings+=("kernel journal capture after cursor failed")
    fi
elif command -v journalctl >/dev/null 2>&1; then
    if ! journalctl -k --since "$start_utc" --until "$end_utc" \
        -o short-iso-precise --no-pager >"$kernel_log" 2>&1; then
        warnings+=("kernel journal time-window capture failed")
    fi
else
    printf 'journalctl unavailable\n' >"$kernel_log"
    warnings+=("journalctl unavailable")
fi

if ! python3 "$repo_dir/tools/filter-kernel-context.py" \
    --input "$kernel_log" --output "$run_dir/kernel-window.log"; then
    warnings+=("kernel context filtering failed")
fi
if ! python3 "$repo_dir/tools/run-artifacts.py" xids \
    --input "$kernel_log" --output "$run_dir/xid-events.json"; then
    warnings+=("Xid parsing failed")
fi
if ! python3 "$repo_dir/tools/run-artifacts.py" breadcrumbs \
    --input "$run_dir/vkd3d.log" --output "$run_dir/breadcrumb-report.txt"; then
    warnings+=("breadcrumb extraction failed")
fi
if ! python3 "$repo_dir/tools/run-artifacts.py" shaders \
    --directory "$run_dir/shaders" --run-dir "$run_dir" \
    --results-root "$results_root" --output "$run_dir/shader-manifest.json"; then
    warnings+=("shader manifest generation failed")
fi

finish_args=(finish --metadata "$run_dir/metadata.json" --end "$end_utc" \
    --duration "$duration" --exit-code "$proton_status")
for warning in "${warnings[@]}"; do
    finish_args+=(--warning "$warning")
done
python3 "$repo_dir/tools/run-artifacts.py" "${finish_args[@]}"
python3 "$repo_dir/tools/run-artifacts.py" summary \
    --run-dir "$run_dir" --output "$run_dir/run-summary.txt" || true
mv -- "$run_dir/.capture-in-progress" "$run_dir/.capture-complete"

printf 'IL-2 Xid109 diagnostics: finalized %s\n' "$run_dir" >&2
exit "$proton_status"
