#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
umask 077

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
repo_dir=$(cd -- "$script_dir/.." && pwd -P)

usage() {
    printf '%s\n' \
        'Usage: finalize-run.sh --run-dir PATH [--exit-code N] [--interrupted] [--recovered]'
}

run_dir=''
exit_code=''
interrupted=0
recovered=0
while (($#)); do
    case $1 in
        --run-dir) (($# >= 2)) || { usage >&2; exit 2; }; run_dir=$2; shift 2 ;;
        --exit-code) (($# >= 2)) || { usage >&2; exit 2; }; exit_code=$2; shift 2 ;;
        --interrupted) interrupted=1; shift ;;
        --recovered) recovered=1; interrupted=1; shift ;;
        --help|-h) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
done

[[ -n $run_dir && -d $run_dir ]] || { printf 'error: run directory is missing\n' >&2; exit 1; }
run_dir=$(cd -- "$run_dir" && pwd -P)
case $run_dir/ in
    "$repo_dir/results/"*) ;;
    *) printf 'error: refusing to finalize a directory outside this repository results path\n' >&2; exit 1 ;;
esac
[[ -f $run_dir/.capture-in-progress ]] || {
    if [[ -f $run_dir/.capture-complete ]]; then
        printf 'Capture is already complete: %s\n' "$run_dir"
        exit 0
    fi
    printf 'error: run has no in-progress marker: %s\n' "$run_dir" >&2
    exit 1
}

warnings_file="$run_dir/capture-warnings.txt"
touch -- "$warnings_file"
add_warning() {
    printf '%s\n' "$1" >>"$warnings_file"
}

if [[ -r $run_dir/start-epoch.txt ]] && [[ $(<"$run_dir/start-epoch.txt") =~ ^[0-9]+$ ]]; then
    start_epoch=$(<"$run_dir/start-epoch.txt")
else
    start_epoch=$(stat -c %Y -- "$run_dir/.capture-in-progress" 2>/dev/null || date +%s)
    add_warning 'start epoch was missing; used the capture-marker timestamp'
fi
if [[ -r $run_dir/start-utc.txt ]] && [[ -n $(<"$run_dir/start-utc.txt") ]]; then
    start_utc=$(<"$run_dir/start-utc.txt")
else
    start_utc=$(date -u -d "@$start_epoch" +%Y-%m-%dT%H:%M:%SZ)
    add_warning 'start UTC timestamp was missing; reconstructed it from the capture marker'
fi
end_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
end_epoch=$(date +%s)
if [[ ! $start_epoch =~ ^[0-9]+$ ]] || ((end_epoch < start_epoch)); then
    start_epoch=$end_epoch
    add_warning 'invalid start timestamp; duration could not be reconstructed'
fi
duration=$((end_epoch - start_epoch))

steam_log="$run_dir/steam-247970.log"
if [[ -f $steam_log ]]; then
    mv -- "$steam_log" "$run_dir/proton.log"
fi
home_proton_log="$HOME/steam-247970.log"
if [[ -f $home_proton_log ]]; then
    home_log_mtime=$(stat -c %Y -- "$home_proton_log" 2>/dev/null || printf 0)
    if [[ $home_log_mtime =~ ^[0-9]+$ ]] && ((home_log_mtime >= start_epoch)); then
        cp -a -- "$home_proton_log" "$run_dir/proton-home.log"
        if [[ ! -f $run_dir/proton.log ]]; then
            cp -a -- "$home_proton_log" "$run_dir/proton.log"
        fi
    fi
fi
if [[ ! -f $run_dir/proton.log ]]; then
    add_warning 'Proton log was not created'
    : >"$run_dir/proton.log"
fi
if [[ ! -f $run_dir/vkd3d.log ]]; then
    add_warning 'VKD3D log was not created'
    : >"$run_dir/vkd3d.log"
fi

journal_cursor=''
if [[ -r $run_dir/journal-cursor-start.txt ]]; then
    journal_cursor=$(<"$run_dir/journal-cursor-start.txt")
    [[ $journal_cursor != unavailable ]] || journal_cursor=''
fi
journal_snapshot="$run_dir/kernel-snapshot.log"
journal_errors="$run_dir/journal-errors.log"
: >"$journal_errors"
journal_ok=0
boot_args=()
if [[ -r $run_dir/boot-id-start.txt ]]; then
    boot_id=$(tr -d '-' <"$run_dir/boot-id-start.txt")
    if [[ $boot_id =~ ^[0-9a-fA-F]{32}$ ]]; then
        boot_args=(--boot="$boot_id")
    else
        add_warning 'saved boot ID is invalid; previous-boot journal recovery is unavailable'
    fi
else
    add_warning 'saved boot ID is missing; previous-boot journal recovery is unavailable'
fi
if command -v journalctl >/dev/null 2>&1; then
    if [[ -n $journal_cursor ]] && journalctl -k "${boot_args[@]}" \
        --after-cursor="$journal_cursor" -o short-iso-precise --no-hostname --no-pager \
        >"$journal_snapshot" 2>>"$journal_errors"; then
        journal_ok=1
    elif journalctl -k "${boot_args[@]}" --since "$start_utc" --until "$end_utc" \
        -o short-iso-precise --no-hostname --no-pager \
        >"$journal_snapshot" 2>>"$journal_errors"; then
        journal_ok=1
        add_warning 'journal cursor recovery failed; used the UTC time window instead'
    fi
fi
if ((journal_ok == 0)); then
    : >"$journal_snapshot"
    add_warning 'kernel journal snapshot failed; retained any live journal capture'
fi
if [[ -s $run_dir/journal-follow-errors.log ]]; then
    add_warning 'live kernel journal collector reported an error; see journal-follow-errors.log'
fi

if ! python3 "$script_dir/merge-kernel-logs.py" --output "$run_dir/kernel-full.log" \
    "$journal_snapshot" "$run_dir/kernel-live.log"; then
    add_warning 'kernel journal merge failed'
    : >"$run_dir/kernel-full.log"
fi
if [[ ! -s $run_dir/kernel-full.log ]]; then
    add_warning 'kernel capture is empty'
fi
if ! python3 "$script_dir/filter-kernel-context.py" \
    --input "$run_dir/kernel-full.log" --output "$run_dir/kernel-window.log"; then
    add_warning 'kernel context filtering failed'
fi
if ! python3 "$script_dir/run-artifacts.py" xids \
    --input "$run_dir/kernel-full.log" --output "$run_dir/xid-events.json"; then
    add_warning 'Xid parsing failed'
fi
if ! python3 "$script_dir/run-artifacts.py" breadcrumbs \
    --input "$run_dir/vkd3d.log" --output "$run_dir/breadcrumb-report.txt"; then
    add_warning 'breadcrumb extraction failed'
fi
if ! python3 "$script_dir/run-artifacts.py" shaders \
    --directory "$run_dir/shaders" --run-dir "$run_dir" \
    --results-root "$repo_dir/results" --output "$run_dir/shader-manifest.json"; then
    add_warning 'shader manifest generation failed'
fi

finish_args=(finish --metadata "$run_dir/metadata.json" --end "$end_utc" --duration "$duration")
[[ -n $exit_code ]] && finish_args+=(--exit-code "$exit_code")
((interrupted)) && finish_args+=(--interrupted)
((recovered)) && finish_args+=(--recovered)
while IFS= read -r warning; do
    [[ -n $warning ]] && finish_args+=(--warning "$warning")
done <"$warnings_file"
python3 "$script_dir/run-artifacts.py" "${finish_args[@]}"
python3 "$script_dir/run-artifacts.py" summary \
    --run-dir "$run_dir" --output "$run_dir/run-summary.txt" || true
mv -- "$run_dir/.capture-in-progress" "$run_dir/.capture-complete"

printf 'Finalized capture: %s\n' "$run_dir"
if ((recovered)); then
    printf '%s\n' 'This recovered capture is marked interrupted and cannot count as a stable no-Xid run.'
fi
