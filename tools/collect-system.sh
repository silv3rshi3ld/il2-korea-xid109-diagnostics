#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
umask 077

usage() {
    printf '%s\n' 'Usage: ./tools/collect-system.sh OUTPUT_DIRECTORY'
}

(($# == 1)) || { usage >&2; exit 2; }
output_dir=$1
mkdir -p -- "$output_dir"
output_file="$output_dir/system.txt"
probe_failures=0

{
    printf 'collected_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf '\n[uname]\n'
    uname -srmo || true
    printf '\n[os-release]\n'
    if [[ -r /etc/os-release ]]; then
        while IFS= read -r line; do
            case $line in
                NAME=*|ID=*|ID_LIKE=*|PRETTY_NAME=*|VERSION_ID=*|BUILD_ID=*) printf '%s\n' "$line" ;;
            esac
        done </etc/os-release
    fi
    printf '\n[nvidia-smi]\n'
    if command -v nvidia-smi >/dev/null 2>&1; then
        if timeout --kill-after=5s 20s nvidia-smi \
            --query-gpu=index,name,pci.bus_id,driver_version,vbios_version \
            --format=csv,noheader 2>&1; then
            :
        else
            status=$?
            printf 'probe_failed exit_status=%d\n' "$status"
            probe_failures=$((probe_failures + 1))
        fi
    else
        printf 'unavailable\n'
        probe_failures=$((probe_failures + 1))
    fi
    printf '\n[vulkan-summary]\n'
    if command -v vulkaninfo >/dev/null 2>&1; then
        if timeout --kill-after=5s 30s vulkaninfo --summary 2>&1; then
            :
        else
            status=$?
            printf 'probe_failed exit_status=%d\n' "$status"
            probe_failures=$((probe_failures + 1))
        fi
    else
        printf 'unavailable\n'
        probe_failures=$((probe_failures + 1))
    fi
    printf '\n[session]\n'
    printf 'XDG_SESSION_TYPE=%s\n' "${XDG_SESSION_TYPE:-unset}"
    printf 'DISPLAY=%s\n' "${DISPLAY:-unset}"
    printf 'WAYLAND_DISPLAY=%s\n' "${WAYLAND_DISPLAY:-unset}"
} >"$output_file"

if ((probe_failures)); then
    printf 'error: %d required per-run system probe(s) failed; see %s\n' \
        "$probe_failures" "$output_file" >&2
    exit 1
fi
