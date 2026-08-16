#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
umask 077

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
repo_dir=$(cd -- "$script_dir/.." && pwd -P)
results_dir="$repo_dir/results"
# shellcheck source=tools/lib/common.sh
source "$script_dir/lib/common.sh"

mkdir -p -- "$repo_dir/.state"
tool_dir=$(il2_diag_tool_dir 2>/dev/null || true)
tool_state="$tool_dir/.il2-xid109-diagnostic"
if [[ -n $tool_dir && -r $tool_state/identity ]] &&
    [[ $(<"$tool_state/identity") == "$IL2_DIAG_IDENTITY" ]]; then
    exec 9>"$tool_state/run.lock"
else
    exec 9>"$repo_dir/.state/package.lock"
fi
flock -n 9 || {
    printf '%s\n' 'error: a diagnostic run or another packaging operation is active' >&2
    exit 1
}

validate_results_tree() {
    local unsafe_entry entry name marker
    [[ -d $results_dir && ! -L $results_dir ]] || {
        printf '%s\n' 'error: results path is missing or unsafe' >&2
        return 1
    }
    unsafe_entry=$(find "$results_dir" \( -type l -o \( ! -type d ! -type f \) \) \
        -print -quit 2>/dev/null || true)
    if [[ -n $unsafe_entry ]]; then
        printf 'error: results contain an unsafe symlink or special file: %s\n' \
            "$unsafe_entry" >&2
        return 1
    fi
    while IFS= read -r -d '' entry; do
        name=$(basename -- "$entry")
        case $name in
            .gitkeep|.shader-store|nvidia-reports|culprit-candidate|archive-inventory.txt|analysis-summary.json|analysis-summary.md) ;;
            culprit-candidate.previous-*) ;;
            .culprit-candidate-building-*)
                printf 'error: unfinished analyzer staging directory remains: %s\n' \
                    "$entry" >&2
                return 1
                ;;
            *)
                if [[ -d $entry && $name =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{6}Z-(baseline|single-queue|no-descriptor-buffer|sync)(-[0-9]+)?$ ]]; then
                    continue
                fi
                printf 'error: unrecognized top-level result entry will not be archived: %s\n' \
                    "$entry" >&2
                return 1
                ;;
        esac
    done < <(find "$results_dir" -mindepth 1 -maxdepth 1 -print0)
    if [[ -e $results_dir/culprit-candidate ]]; then
        marker="$results_dir/culprit-candidate/.generated-by-il2-xid109-analyzer"
        if [[ ! -d $results_dir/culprit-candidate || ! -f $marker ]] ||
            [[ $(<"$marker") != 'generated; safe for analyzer-owned files only' ]]; then
            printf '%s\n' \
                'error: refusing to archive an unrecognized culprit-candidate directory' >&2
            return 1
        fi
    fi
}

validate_results_tree

if find "$results_dir" -mindepth 2 -maxdepth 2 -type f \
    -name .capture-in-progress -print -quit 2>/dev/null | grep -q .; then
    printf '%s\n' 'error: recover the interrupted capture before creating an archive' >&2
    exit 1
fi

workflow_action=$(python3 "$script_dir/workflow-status.py" --next)
case $workflow_action in
    COMPLETE|STOP_BASELINE_NO_XID) ;;
    *)
        printf 'error: evidence is not ready to package (workflow action: %s)\n' \
            "$workflow_action" >&2
        exit 1
        ;;
esac

python3 "$repo_dir/analyzer/analyze.py"
validate_results_tree

run_count=$(find "$results_dir" -mindepth 1 -maxdepth 1 -type d -name '20*-*' -printf '.' | wc -c)
if ((run_count == 0)); then
    printf 'error: there are no captured runs to pack\n' >&2
    exit 1
fi

printf '%s\n' \
    'PRIVACY WARNING: this archive can contain username-bearing paths, hardware' \
    'identifiers, kernel/game logs, and game shader bytecode.' \
    'It is for private transfer to the investigation coordinator only.' \
    'Nothing is uploaded automatically. NVIDIA bug reports are excluded.'
printf '%s\n' 'Type CREATE PRIVATE ARCHIVE exactly to continue, or press Enter to cancel.'
printf '> '
IFS= read -r confirmation
[[ $confirmation == 'CREATE PRIVATE ARCHIVE' ]] || {
    printf '%s\n' 'Cancelled. No archive was created.'
    exit 1
}

validate_results_tree
find "$results_dir" -type f ! -path "$results_dir/.shader-store/*" \
    ! -path "$results_dir/nvidia-reports/*" ! -name archive-inventory.txt \
    ! -path "$results_dir/culprit-candidate.previous-*/*" \
    ! -name '*.tmp' ! -name '*.tmp.[0-9]*' \
    ! -path "$results_dir/.culprit-candidate-building-*/*" \
    -printf '%P\t%s bytes\n' \
    | sort >"$results_dir/archive-inventory.txt"

timestamp=$(date -u +%Y-%m-%dT%H%M%SZ)
if command -v zstd >/dev/null 2>&1 && tar --help 2>/dev/null | grep -q -- '--zstd'; then
    archive="$repo_dir/PRIVATE-il2-xid109-results-$timestamp.tar.zst"
    compression=(--zstd)
else
    archive="$repo_dir/PRIVATE-il2-xid109-results-$timestamp.tar.gz"
    compression=(-z)
fi
[[ ! -e $archive && ! -e $archive.sha256 ]] || {
    printf 'error: archive or checksum already exists: %s\n' "$archive" >&2
    exit 1
}

included_bytes=$(find "$results_dir" -type f \
    ! -path "$results_dir/.shader-store/*" \
    ! -path "$results_dir/nvidia-reports/*" \
    ! -path "$results_dir/culprit-candidate.previous-*/*" \
    ! -path "$results_dir/.culprit-candidate-building-*/*" \
    ! -name '*.tmp' ! -name '*.tmp.[0-9]*' -printf '%s\n' \
    | awk '{total += $1} END {printf "%.0f", total}')
included_bytes=$((included_bytes + $(stat -c %s -- \
    "$repo_dir/build-manifest.json" "$repo_dir/build/source-lock.json" \
    | awk '{total += $1} END {print total}')))
available_kib=$(df -Pk -- "$repo_dir" | awk 'NR == 2 {print $4}')
required_kib=$(((included_bytes + 1023) / 1024 + 65536))
if [[ ! $available_kib =~ ^[0-9]+$ ]] || ((available_kib <= required_kib)); then
    printf '%s\n' \
        'error: insufficient free space to build the archive safely' \
        '       Free additional space and try Finish again; no archive was created.' >&2
    exit 1
fi

archive_name=$(basename -- "$archive")
archive_tmp="$repo_dir/.$archive_name.tmp.$$"
checksum_tmp="$repo_dir/.$archive_name.sha256.tmp.$$"
cleanup_temporary() {
    rm -f -- "$archive_tmp" "$checksum_tmp"
}
trap cleanup_temporary EXIT

validate_results_tree
tar "${compression[@]}" -cf "$archive_tmp" -C "$repo_dir" \
        --exclude='results/.shader-store' \
        --exclude='results/nvidia-reports' \
        --exclude='results/culprit-candidate.previous-*' \
        --exclude='results/.culprit-candidate-building-*' \
        --exclude='*.tmp' \
        --exclude='*.tmp.[0-9]*' \
        results build-manifest.json build/source-lock.json
archive_digest=$(sha256sum -- "$archive_tmp" | awk '{print $1}')
printf '%s  %s\n' "$archive_digest" "$archive_name" >"$checksum_tmp"
mv -- "$archive_tmp" "$archive"
mv -- "$checksum_tmp" "$archive.sha256"
trap - EXIT
printf 'Created: %s\n' "$archive"
du -h -- "$archive" | awk '{print "Size:     " $1}'
printf 'SHA256:  %s\n' "$archive.sha256"
