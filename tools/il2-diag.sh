#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
umask 077

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
repo_dir=$(cd -- "$script_dir/.." && pwd -P)
# shellcheck source=tools/lib/common.sh
source "$script_dir/lib/common.sh"

matrix="$repo_dir/config/test-matrix.conf"
artifact_root="$repo_dir/build/output/vkd3d-proton-diag"
build_manifest="$repo_dir/build-manifest.json"

usage() {
    printf '%s\n' \
        'Usage: ./tools/il2-diag.sh COMMAND [ARGUMENT]' \
        '' \
        'Commands:' \
        '  doctor                 Read-only prerequisite and provenance checks' \
        '  install                Create the isolated compatibility tool' \
        '  uninstall              Disable the custom tool without deleting it' \
        '  select CASE            Select baseline, single-queue, no-descriptor-buffer, or sync' \
        '  status                 Show installation, selected case, and captured runs' \
        '  analyze                Write results/analysis-summary.{md,json}' \
        '  pack                   Analyze and create a shareable results archive' \
        '  cases                  List the controlled four-run matrix'
}

pass() { printf '[PASS] %s\n' "$*"; }
warn() { printf '[WARN] %s\n' "$*"; }
fail() { printf '[FAIL] %s\n' "$*"; }

baseline_provenance() {
    local baseline=$1
    local root_version="$baseline/version"
    local vkd3d_version="$baseline/files/lib/wine/vkd3d-proton/version"
    [[ -r $root_version && -r $vkd3d_version ]] || return 1
    grep -Fq -- "$IL2_DIAG_EXPECTED_PROTON_BUILD" "$root_version" &&
        grep -Fq -- "$IL2_DIAG_EXPECTED_VKD3D_COMMIT" "$vkd3d_version"
}

cmd_doctor() {
    local failures=0
    local command_name steam_root baseline tool_dir extension_output baseline_kib available_kib
    printf 'IL-2 Korea Xid109 diagnostic doctor (read-only)\n\n'

    for command_name in bash python3 git sha256sum cp mv flock journalctl stat awk grep; do
        if command -v "$command_name" >/dev/null 2>&1; then
            pass "$command_name is available"
        else
            fail "$command_name is required"
            failures=$((failures + 1))
        fi
    done

    if steam_root=$(il2_diag_find_steam_root); then
        pass "Steam root: $steam_root"
    else
        fail 'Steam root not found (set IL2_DIAG_STEAM_ROOT only if Steam uses a nonstandard location)'
        return 1
    fi
    baseline=$(il2_diag_baseline_dir)
    tool_dir=$(il2_diag_tool_dir)
    if [[ -x $baseline/proton ]]; then
        pass "Proton Experimental installation found: $baseline"
    else
        fail "Proton Experimental installation not found: $baseline"
        failures=$((failures + 1))
    fi
    if [[ -d $baseline ]] && baseline_provenance "$baseline"; then
        pass "baseline is the exact failing Proton and VKD3D revision"
    elif [[ -d $baseline ]]; then
        fail "baseline provenance does not match $IL2_DIAG_EXPECTED_PROTON_BUILD"
        failures=$((failures + 1))
    fi

    if [[ -f $build_manifest ]] && python3 "$script_dir/verify-build.py" \
        --manifest "$build_manifest" --artifact-root "$artifact_root" >/dev/null 2>&1; then
        pass 'diagnostic DLL hashes and release+trace manifest verify'
    else
        fail 'diagnostic build is missing or invalid; run ./build/build-vkd3d-diag.sh first'
        failures=$((failures + 1))
    fi

    if journalctl -k -n 1 --no-pager >/dev/null 2>&1; then
        pass 'current user can read the kernel journal'
    else
        fail 'current user cannot read the kernel journal; fix journal permissions before testing'
        failures=$((failures + 1))
    fi

    if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
        pass 'NVIDIA driver is responding'
        nvidia-smi --query-gpu=index,name,pci.bus_id,driver_version --format=csv,noheader 2>/dev/null \
            | sed 's/^/       /' || true
    else
        fail 'nvidia-smi is unavailable or the NVIDIA driver is not responding'
        failures=$((failures + 1))
    fi

    if command -v vulkaninfo >/dev/null 2>&1; then
        extension_output=$(vulkaninfo 2>/dev/null || true)
        if grep -Fq 'VK_NV_device_diagnostic_checkpoints' <<<"$extension_output"; then
            pass 'VK_NV_device_diagnostic_checkpoints is exposed'
        else
            fail 'VK_NV_device_diagnostic_checkpoints is not exposed; NVIDIA breadcrumbs cannot work'
            failures=$((failures + 1))
        fi
        if grep -Fq 'VK_EXT_descriptor_buffer' <<<"$extension_output"; then
            pass 'VK_EXT_descriptor_buffer is exposed for the controlled disable test'
        else
            warn 'VK_EXT_descriptor_buffer is not exposed; no-descriptor-buffer would not be a discriminator'
        fi
        if grep -Fq 'VK_EXT_device_fault' <<<"$extension_output"; then
            warn 'VK_EXT_device_fault is exposed but intentionally not enabled in the default matrix'
        fi
    else
        fail 'vulkaninfo is required (Arch package: vulkan-tools)'
        failures=$((failures + 1))
    fi

    if [[ -d $baseline ]]; then
        baseline_kib=$(du -sk -- "$baseline" | awk '{print $1}')
        available_kib=$(df -Pk -- "$steam_root" | awk 'NR == 2 {print $4}')
        if [[ $baseline_kib =~ ^[0-9]+$ && $available_kib =~ ^[0-9]+$ ]] &&
            ((available_kib > baseline_kib + 1048576)); then
            pass 'space is available for an isolated Proton copy plus 1 GiB result headroom'
        else
            fail 'insufficient free space for the isolated Proton copy plus result headroom'
            failures=$((failures + 1))
        fi
    fi

    if [[ -e $tool_dir ]]; then
        if [[ -r $tool_dir/.il2-xid109-diagnostic/identity ]] &&
            [[ $(<"$tool_dir/.il2-xid109-diagnostic/identity") == "$IL2_DIAG_IDENTITY" ]]; then
            warn 'diagnostic compatibility tool is already installed'
        else
            fail "target path exists but is not this harness: $tool_dir"
            failures=$((failures + 1))
        fi
    fi

    printf '\n'
    if ((failures)); then
        fail "$failures blocking prerequisite(s)"
        return 1
    fi
    pass 'doctor completed with no blockers'
}

cmd_install() {
    local steam_root baseline tool_dir staging state_dir baseline_version baseline_vkd3d_version
    local source_core target_core harness_commit lock_file
    cmd_doctor

    steam_root=$(il2_diag_find_steam_root)
    baseline=$(il2_diag_baseline_dir)
    tool_dir=$(il2_diag_tool_dir)
    [[ ! -e $tool_dir ]] || {
        printf 'error: diagnostic tool already exists; use status or uninstall first\n' >&2
        exit 1
    }
    source_core="$artifact_root/x64/d3d12core.dll"
    [[ -f $source_core ]] || { printf 'error: missing %s\n' "$source_core" >&2; exit 1; }

    mkdir -p -- "$steam_root/compatibilitytools.d"
    lock_file="$steam_root/compatibilitytools.d/.il2-xid109-install.lock"
    exec 8>"$lock_file"
    flock -n 8 || { printf 'error: another install/uninstall operation is active\n' >&2; exit 1; }
    staging="$steam_root/compatibilitytools.d/.IL2-Xid109-installing-$$"
    [[ ! -e $staging ]] || { printf 'error: staging path already exists: %s\n' "$staging" >&2; exit 1; }

    baseline_version=$(<"$baseline/version")
    baseline_vkd3d_version=$(<"$baseline/files/lib/wine/vkd3d-proton/version")
    printf 'Creating isolated copy of %s. This can take several minutes.\n' "$baseline"
    printf 'Official Steam-managed files will not be modified.\n'
    mkdir -- "$staging"
    if ! cp -a --reflink=auto -- "$baseline/." "$staging/"; then
        printf 'error: copy failed; partial staging data was preserved at %s\n' "$staging" >&2
        exit 1
    fi
    if [[ $(<"$baseline/version") != "$baseline_version" ]] ||
        [[ $(<"$baseline/files/lib/wine/vkd3d-proton/version") != "$baseline_vkd3d_version" ]] ||
        ! baseline_provenance "$staging"; then
        printf 'error: Proton changed or failed provenance validation during copying\n' >&2
        printf 'The staging copy was preserved for inspection at %s\n' "$staging" >&2
        exit 1
    fi

    state_dir="$staging/.il2-xid109-diagnostic"
    mkdir -- "$state_dir"
    target_core="$staging/files/lib/wine/vkd3d-proton/x86_64-windows/d3d12core.dll"
    [[ -f $target_core ]] || { printf 'error: copied Proton has no x64 d3d12core.dll\n' >&2; exit 1; }
    harness_commit=$(git -C "$repo_dir" rev-parse HEAD 2>/dev/null || printf uncommitted)

    cp -a -- "$build_manifest" "$state_dir/build-manifest.json"
    python3 "$script_dir/install-manifest.py" \
        --output "$state_dir/install-manifest.json" \
        --baseline "$baseline" \
        --baseline-version "$baseline_version" \
        --baseline-vkd3d-version "$baseline_vkd3d_version" \
        --original-core "$target_core" \
        --diagnostic-core "$source_core" \
        --build-manifest "$build_manifest" \
        --harness-commit "$harness_commit"

    cp -a -- "$source_core" "$target_core"
    mv -- "$staging/proton" "$staging/proton.real"
    cp -a -- "$script_dir/proton-wrapper.sh" "$staging/proton"
    cp -a -- "$script_dir/il2-diag-launch.sh" "$state_dir/il2-diag-launch.sh"
    cp -a -- "$script_dir/lib/common.sh" "$state_dir/common.sh"
    cp -a -- "$matrix" "$state_dir/test-matrix.conf"
    cp -a -- "$repo_dir/config/compatibilitytool.vdf" "$staging/compatibilitytool.vdf"
    chmod 0755 -- "$staging/proton" "$staging/proton.real" "$state_dir/il2-diag-launch.sh"
    printf '%s\n' "$repo_dir" >"$state_dir/repo-path"
    printf '%s\n' baseline >"$state_dir/selected-case"
    printf '%s\n' "$IL2_DIAG_IDENTITY" >"$state_dir/identity"

    mv -- "$staging" "$tool_dir"
    printf '\nInstalled: %s\n' "$tool_dir"
    printf '%s\n' 'Restart Steam, select “IL2 Xid109 Diagnostic” once for IL-2 Korea,' \
        'then use ./tools/il2-diag.sh select CASE before each launch.'
}

cmd_uninstall() {
    local steam_root tool_dir disabled_root destination timestamp
    steam_root=$(il2_diag_find_steam_root) || { printf 'error: Steam root not found\n' >&2; exit 1; }
    tool_dir=$(il2_diag_tool_dir)
    [[ -r $tool_dir/.il2-xid109-diagnostic/identity ]] || {
        printf 'error: the diagnostic compatibility tool is not installed\n' >&2
        exit 1
    }
    [[ $(<"$tool_dir/.il2-xid109-diagnostic/identity") == "$IL2_DIAG_IDENTITY" ]] || {
        printf 'error: refusing to move an unrecognized compatibility tool\n' >&2
        exit 1
    }
    exec 8>"$steam_root/compatibilitytools.d/.il2-xid109-install.lock"
    flock -n 8 || { printf 'error: another install/uninstall operation is active\n' >&2; exit 1; }
    disabled_root="$steam_root/compatibilitytools.d-disabled"
    timestamp=$(date -u +%Y-%m-%dT%H%M%SZ)
    destination="$disabled_root/$IL2_DIAG_TOOL_NAME-$timestamp"
    mkdir -p -- "$disabled_root"
    [[ ! -e $destination ]] || { printf 'error: destination exists: %s\n' "$destination" >&2; exit 1; }
    mv -- "$tool_dir" "$destination"
    printf 'Disabled the custom compatibility tool without deleting it.\n'
    printf 'Recoverable copy: %s\n' "$destination"
    printf 'Captured results remain in: %s/results\n' "$repo_dir"
}

cmd_select() {
    local wanted=${1:-} tool_dir state_dir temporary
    [[ -n $wanted ]] || { printf 'error: select requires a case\n' >&2; il2_diag_list_cases "$matrix" >&2; exit 2; }
    il2_diag_matrix_lookup "$matrix" "$wanted" >/dev/null || {
        printf 'error: unknown case: %s\n' "$wanted" >&2
        il2_diag_list_cases "$matrix" >&2
        exit 2
    }
    tool_dir=$(il2_diag_tool_dir) || { printf 'error: Steam root not found\n' >&2; exit 1; }
    state_dir="$tool_dir/.il2-xid109-diagnostic"
    [[ -r $state_dir/identity && $(<"$state_dir/identity") == "$IL2_DIAG_IDENTITY" ]] || {
        printf 'error: install the diagnostic compatibility tool first\n' >&2
        exit 1
    }
    temporary="$state_dir/selected-case.tmp.$$"
    printf '%s\n' "$wanted" >"$temporary"
    mv -- "$temporary" "$state_dir/selected-case"
    printf 'Selected case: %s\n' "$wanted"
    printf '%s\n' 'Launch IL-2 Korea normally through Steam and reproduce once.'
}

cmd_status() {
    local tool_dir state_dir selected='not installed' count
    tool_dir=$(il2_diag_tool_dir 2>/dev/null || true)
    state_dir="$tool_dir/.il2-xid109-diagnostic"
    if [[ -n $tool_dir && -r $state_dir/identity ]] &&
        [[ $(<"$state_dir/identity") == "$IL2_DIAG_IDENTITY" ]]; then
        selected=$(<"$state_dir/selected-case")
        printf 'Installation: %s\n' "$tool_dir"
    else
        printf 'Installation: not installed\n'
    fi
    printf 'Selected case: %s\n' "$selected"
    count=$(find "$repo_dir/results" -mindepth 1 -maxdepth 1 -type d \
        -name '20*-*' -printf '.' 2>/dev/null | wc -c)
    printf 'Captured runs: %s\n' "$count"
    find "$repo_dir/results" -mindepth 1 -maxdepth 1 -type d -name '20*-*' \
        -printf '  %f\n' 2>/dev/null | sort || true
}

command_name=${1:-}
case $command_name in
    doctor) shift; (($# == 0)) || { usage >&2; exit 2; }; cmd_doctor ;;
    install) shift; (($# == 0)) || { usage >&2; exit 2; }; cmd_install ;;
    uninstall) shift; (($# == 0)) || { usage >&2; exit 2; }; cmd_uninstall ;;
    select) shift; cmd_select "${1:-}" ;;
    status) shift; (($# == 0)) || { usage >&2; exit 2; }; cmd_status ;;
    analyze) shift; (($# == 0)) || { usage >&2; exit 2; }; exec python3 "$repo_dir/analyzer/analyze.py" ;;
    pack) shift; (($# == 0)) || { usage >&2; exit 2; }; exec "$script_dir/pack-results.sh" ;;
    cases) shift; (($# == 0)) || { usage >&2; exit 2; }; il2_diag_list_cases "$matrix" ;;
    help|--help|-h|'') usage ;;
    *) printf 'error: unknown command: %s\n' "$command_name" >&2; usage >&2; exit 2 ;;
esac
