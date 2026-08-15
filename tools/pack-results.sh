#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
umask 077

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
repo_dir=$(cd -- "$script_dir/.." && pwd -P)
results_dir="$repo_dir/results"

python3 "$repo_dir/analyzer/analyze.py"

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

find "$results_dir" -type f ! -path "$results_dir/.shader-store/*" \
    ! -path "$results_dir/nvidia-reports/*" ! -name archive-inventory.txt \
    -printf '%P\t%s bytes\n' \
    | sort >"$results_dir/archive-inventory.txt"

timestamp=$(date -u +%Y-%m-%dT%H%M%SZ)
if command -v zstd >/dev/null 2>&1 && tar --help 2>/dev/null | grep -q -- '--zstd'; then
    archive="$repo_dir/PRIVATE-il2-xid109-results-$timestamp.tar.zst"
    [[ ! -e $archive ]] || { printf 'error: archive already exists: %s\n' "$archive" >&2; exit 1; }
    tar --zstd -cf "$archive" -C "$repo_dir" \
        --exclude='results/.shader-store' \
        --exclude='results/nvidia-reports' \
        --exclude='*.tmp' \
        results build-manifest.json build/source-lock.json
else
    archive="$repo_dir/PRIVATE-il2-xid109-results-$timestamp.tar.gz"
    [[ ! -e $archive ]] || { printf 'error: archive already exists: %s\n' "$archive" >&2; exit 1; }
    tar -czf "$archive" -C "$repo_dir" \
        --exclude='results/.shader-store' \
        --exclude='results/nvidia-reports' \
        --exclude='*.tmp' \
        results build-manifest.json build/source-lock.json
fi
sha256sum -- "$archive" >"$archive.sha256"
printf 'Created: %s\n' "$archive"
du -h -- "$archive" | awk '{print "Size:     " $1}'
printf 'SHA256:  %s\n' "$archive.sha256"
