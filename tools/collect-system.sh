#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

usage() {
    printf '%s\n' 'Usage: ./tools/collect-system.sh OUTPUT_DIRECTORY'
}

(($# == 1)) || { usage >&2; exit 2; }
output_dir=$1
mkdir -p -- "$output_dir"
output_file="$output_dir/system.txt"

{
    printf 'collected_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'hostname=%s\n' "$(hostname 2>/dev/null || printf unavailable)"
    printf '\n[uname]\n'
    uname -a || true
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
        nvidia-smi --query-gpu=index,name,pci.bus_id,driver_version,vbios_version \
            --format=csv,noheader || true
    else
        printf 'unavailable\n'
    fi
    printf '\n[vulkan-summary]\n'
    if command -v vulkaninfo >/dev/null 2>&1; then
        vulkaninfo --summary 2>&1 || true
    else
        printf 'unavailable\n'
    fi
    printf '\n[session]\n'
    printf 'XDG_SESSION_TYPE=%s\n' "${XDG_SESSION_TYPE:-unset}"
    printf 'DISPLAY=%s\n' "${DISPLAY:-unset}"
    printf 'WAYLAND_DISPLAY=%s\n' "${WAYLAND_DISPLAY:-unset}"
} >"$output_file"
