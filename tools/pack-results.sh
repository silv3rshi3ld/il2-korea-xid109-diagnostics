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
    'Privacy reminder: the archive can contain usernames, local paths, hostnames,' \
    'hardware identifiers, game paths, and logs. Review it before sharing publicly.'

timestamp=$(date -u +%Y-%m-%dT%H%M%SZ)
if command -v zstd >/dev/null 2>&1 && tar --help 2>/dev/null | grep -q -- '--zstd'; then
    archive="$repo_dir/il2-xid109-results-$timestamp.tar.zst"
    [[ ! -e $archive ]] || { printf 'error: archive already exists: %s\n' "$archive" >&2; exit 1; }
    tar --zstd -cf "$archive" -C "$repo_dir" \
        --exclude='results/.shader-store' \
        --exclude='*.tmp' \
        results build-manifest.json build/source-lock.json
else
    archive="$repo_dir/il2-xid109-results-$timestamp.tar.gz"
    [[ ! -e $archive ]] || { printf 'error: archive already exists: %s\n' "$archive" >&2; exit 1; }
    tar -czf "$archive" -C "$repo_dir" \
        --exclude='results/.shader-store' \
        --exclude='*.tmp' \
        results build-manifest.json build/source-lock.json
fi
sha256sum -- "$archive" >"$archive.sha256"
printf 'Created: %s\n' "$archive"
printf 'SHA256:  %s\n' "$archive.sha256"
