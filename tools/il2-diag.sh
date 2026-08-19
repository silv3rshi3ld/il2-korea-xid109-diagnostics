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
        '  terms                  Display the safety/privacy participation notice' \
        '  accept-terms           Record informed local acceptance before installation' \
        '  doctor                 Read-only prerequisite and provenance checks' \
        '  install                Create the isolated compatibility tool' \
        '  uninstall              Disable the custom tool without deleting it' \
        '  trash-copy             Move recognized disabled custom copies to desktop Trash' \
        '  select CASE            Select one case from the controlled six-run matrix' \
        '  ready                  Start the observation timer after the hangar is fully rendered' \
        '  recover                Finalize captures interrupted by a freeze or reboot' \
        '  status                 Show installation, selected case, and captured runs' \
        '  analyze                Write results/analysis-summary.{md,json}' \
        '  pack                   Analyze and create a shareable results archive' \
        '  cases                  List the controlled six-run matrix'
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
    local command_name steam_root game_manifest baseline tool_dir extension_output baseline_kib available_kib
    local kernel_probe architecture os_id os_like steam_device results_device results_kib required_kib
    local stale_staging journal_help
    printf 'IL-2 Korea Xid109 diagnostic doctor (read-only)\n\n'

    for command_name in bash python3 sha256sum cp mv flock journalctl stat awk grep sed du df \
        find wc sort tar gzip stdbuf id timeout tr head pgrep sleep date uname chmod mkdir kill; do
        if command -v "$command_name" >/dev/null 2>&1; then
            pass "$command_name is available"
        else
            fail "$command_name is required"
            failures=$((failures + 1))
        fi
    done

    architecture=$(uname -m)
    if [[ $architecture == x86_64 ]]; then
        pass 'x86_64 architecture is supported'
    else
        fail "unsupported architecture: $architecture (this tester bundle is x86_64 only)"
        failures=$((failures + 1))
    fi
    os_id=$(sed -n 's/^ID=//p' /etc/os-release 2>/dev/null | tr -d '"' | head -n 1)
    os_like=$(sed -n 's/^ID_LIKE=//p' /etc/os-release 2>/dev/null | tr -d '"' | head -n 1)
    if [[ $os_id == arch || $os_id == cachyos || $os_like == *arch* ]]; then
        pass "Arch-family operating system detected: ${os_id:-unknown}"
    else
        warn "this workflow was prepared for Arch/CachyOS; detected ${os_id:-unknown}"
    fi
    if [[ ${XDG_SESSION_TYPE:-unknown} == x11 ]]; then
        pass 'X11 session matches the known failing configuration'
    else
        fail "session is ${XDG_SESSION_TYPE:-unknown}; the controlled test requires X11"
        printf '%s\n' '       Stop here and ask the coordinator before changing login-session settings.'
        failures=$((failures + 1))
    fi
    if python3 "$script_dir/parent-death-exec.py" --self-test >/dev/null 2>&1; then
        pass 'Linux parent-death signaling is available for managed-process cleanup'
    else
        fail 'Linux parent-death signaling is unavailable; managed capture cleanup cannot run'
        failures=$((failures + 1))
    fi

    if steam_root=$(il2_diag_find_steam_root); then
        pass "Steam root: $steam_root"
    else
        if [[ -d $HOME/.var/app/com.valvesoftware.Steam ]]; then
            fail 'Flatpak Steam was detected, but this release supports native Arch Steam only'
        else
            fail 'native Steam root was not found'
        fi
        printf '%s\n' '       Stop here and send this output to the investigation coordinator.'
        return 1
    fi
    tool_dir=$(il2_diag_tool_dir)
    if game_manifest=$(il2_diag_find_app_manifest "$steam_root" 247970); then
        pass "IL-2 Korea AppID 247970 installation found: $game_manifest"
    else
        fail 'IL-2 Korea AppID 247970 is not installed in a native Steam library'
        printf '%s\n' '       Install the invited test build in Steam, then run setup again.'
        failures=$((failures + 1))
    fi
    if baseline=$(il2_diag_baseline_dir) && [[ -x $baseline/proton ]]; then
        pass "Proton Experimental installation found: $baseline"
    else
        fail 'Proton Experimental was not found in the native Steam libraries'
        printf '%s\n' '       Install/select Proton Experimental in Steam, or contact the coordinator.'
        failures=$((failures + 1))
        baseline=''
    fi
    if [[ -n $baseline && -d $baseline ]] && baseline_provenance "$baseline"; then
        pass "baseline is the exact failing Proton and VKD3D revision"
    elif [[ -n $baseline && -d $baseline ]]; then
        fail "baseline provenance does not match $IL2_DIAG_EXPECTED_PROTON_BUILD"
        printf '       Found version: '
        head -n 1 -- "$baseline/version" 2>/dev/null || printf 'unreadable\n'
        printf '%s\n' \
            '       Do not substitute a newer build: stop and contact the coordinator for the exact baseline.'
        failures=$((failures + 1))
    fi

    if [[ -f $build_manifest ]] && python3 "$script_dir/verify-build.py" \
        --manifest "$build_manifest" --artifact-root "$artifact_root" >/dev/null 2>&1; then
        pass 'diagnostic DLL hashes and release+trace+descriptor-QA manifest verify'
    else
        fail 'prepared diagnostic DLLs or their manifest are missing/invalid'
        printf '%s\n' \
            '       This is not a tester-build task. Ask for the prepared tester archive.'
        failures=$((failures + 1))
    fi
    if [[ -f $repo_dir/bundle-checksums.sha256 ]]; then
        if python3 "$script_dir/verify-tester-bundle.py" --root "$repo_dir" >/dev/null 2>&1; then
            pass 'prepared tester bundle checksums verify'
        else
            fail 'prepared tester bundle checksum verification failed'
            printf '%s\n' '       Do not continue; obtain a fresh archive from the coordinator.'
            failures=$((failures + 1))
        fi
    else
        warn 'this is a maintainer checkout, not a checksummed prepared tester archive'
    fi

    journal_help=$(journalctl --help 2>/dev/null || true)
    if grep -Fq -- '--no-hostname' <<<"$journal_help" &&
        grep -Fq -- '--boot' <<<"$journal_help" &&
        grep -Fq -- '--after-cursor' <<<"$journal_help"; then
        pass 'journalctl supports boot-scoped cursor capture without hostname fields'
    else
        fail 'journalctl lacks an option required for safe live/reboot capture'
        failures=$((failures + 1))
    fi
    kernel_probe=$(journalctl -k -n 1 -o cat --no-pager 2>/dev/null || true)
    if [[ -n $kernel_probe ]]; then
        pass 'current user can read the kernel journal'
    else
        fail 'current user cannot read a kernel journal record'
        printf '%s\n' \
            '       On Arch, wheel/systemd-journal members normally have read access.' \
            '       Do not use sudo inside a game run; ask the coordinator to help configure access.'
        failures=$((failures + 1))
    fi

    if command -v nvidia-smi >/dev/null 2>&1 &&
        timeout --kill-after=5s 20s nvidia-smi >/dev/null 2>&1; then
        pass 'NVIDIA driver is responding'
        timeout --kill-after=5s 20s nvidia-smi --query-gpu=index,name,pci.bus_id,driver_version \
            --format=csv,noheader 2>/dev/null \
            | sed 's/^/       /' || true
    else
        fail 'nvidia-smi is unavailable or the NVIDIA driver is not responding'
        failures=$((failures + 1))
    fi

    if ! command -v vulkaninfo >/dev/null 2>&1; then
        fail 'vulkaninfo is required (Arch package: vulkan-tools)'
        failures=$((failures + 1))
    elif ! extension_output=$(timeout --kill-after=5s 30s vulkaninfo 2>/dev/null); then
        fail 'vulkaninfo did not complete successfully; Vulkan capabilities could not be verified'
        failures=$((failures + 1))
    else
        if grep -Fq 'VK_NV_device_diagnostic_checkpoints' <<<"$extension_output"; then
            pass 'VK_NV_device_diagnostic_checkpoints is exposed'
        else
            fail 'VK_NV_device_diagnostic_checkpoints is not exposed; NVIDIA breadcrumbs cannot work'
            failures=$((failures + 1))
        fi
        if grep -Fq 'VK_EXT_descriptor_buffer' <<<"$extension_output"; then
            pass 'VK_EXT_descriptor_buffer is exposed for the controlled disable test'
        else
            fail 'VK_EXT_descriptor_buffer is not exposed; the disable case would not be a discriminator'
            failures=$((failures + 1))
        fi
        if grep -Fq 'VK_EXT_descriptor_heap' <<<"$extension_output"; then
            pass 'VK_EXT_descriptor_heap is exposed for the known-stable descriptor-heap case'
        else
            fail 'VK_EXT_descriptor_heap is not exposed; the descriptor-heap comparison cannot run'
            failures=$((failures + 1))
        fi
        if grep -Fq 'VK_EXT_device_fault' <<<"$extension_output"; then
            warn 'VK_EXT_device_fault is exposed but intentionally not enabled in the default matrix'
        fi
    fi

    if [[ -n $baseline && -d $baseline ]]; then
        baseline_kib=$(du -sk -- "$baseline" | awk '{print $1}')
        available_kib=$(df -Pk -- "$steam_root" | awk 'NR == 2 {print $4}')
        results_kib=$(df -Pk -- "$repo_dir" | awk 'NR == 2 {print $4}')
        steam_device=$(df -Pk -- "$steam_root" | awk 'NR == 2 {print $1}')
        results_device=$(df -Pk -- "$repo_dir" | awk 'NR == 2 {print $1}')
        required_kib=$((baseline_kib + 1048576))
        if [[ $steam_device == "$results_device" ]]; then
            required_kib=$((baseline_kib + IL2_DIAG_RESULTS_HEADROOM_KIB))
        fi
        printf '       Steam filesystem free: %.1f GiB; result filesystem free: %.1f GiB\n' \
            "$(awk -v value="$available_kib" 'BEGIN {print value / 1048576}')" \
            "$(awk -v value="$results_kib" 'BEGIN {print value / 1048576}')"
        if [[ $baseline_kib =~ ^[0-9]+$ && $available_kib =~ ^[0-9]+$ &&
              $results_kib =~ ^[0-9]+$ ]] && ((available_kib > required_kib)) &&
            ((results_kib > IL2_DIAG_RESULTS_HEADROOM_KIB)); then
            pass 'space is available for the isolated Proton copy and six diagnostic runs'
        else
            fail 'insufficient free space (reserve the Proton copy plus 8 GiB for results)'
            failures=$((failures + 1))
        fi
    fi

    if il2_diag_terms_accepted "$repo_dir"; then
        pass "tester notice $IL2_DIAG_TERMS_VERSION was accepted locally"
    else
        warn 'tester notice has not been accepted yet; setup will ask before installation'
    fi
    if il2_diag_steam_running; then
        warn 'Steam is running; fully exit Steam before install or uninstall'
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
    while IFS= read -r stale_staging; do
        [[ -n $stale_staging ]] || continue
        warn "preserved incomplete install copy uses disk space: $stale_staging"
        warn 'ask the coordinator to inspect it before deleting it with the file manager'
    done < <(find "$steam_root/compatibilitytools.d" -mindepth 1 -maxdepth 1 -type d \
        -name '.IL2-Xid109-installing-*' -print 2>/dev/null)

    printf '\n'
    if ((failures)); then
        fail "$failures blocking prerequisite(s)"
        return 1
    fi
    pass 'doctor completed with no blockers'
}

cmd_terms() {
    sed -n '1,260p' "$repo_dir/TESTER-TERMS.md"
}

cmd_accept_terms() {
    local answer terms_hash acceptance temporary
    if il2_diag_terms_accepted "$repo_dir"; then
        printf 'Tester notice %s is already accepted for this unchanged notice.\n' \
            "$IL2_DIAG_TERMS_VERSION"
        return 0
    fi
    cmd_terms
    printf '\n%s\n' \
        'Type I AGREE exactly to confirm that you understand the risk and local data collection.' \
        'Anything else cancels without making changes.'
    printf '> '
    IFS= read -r answer
    if [[ $answer != 'I AGREE' ]]; then
        printf '%s\n' 'Not accepted. Nothing was installed or changed.'
        return 1
    fi
    mkdir -p -- "$repo_dir/.state"
    acceptance="$repo_dir/.state/terms-acceptance.txt"
    temporary="$acceptance.tmp.$$"
    terms_hash=$(il2_diag_file_sha256 "$repo_dir/TESTER-TERMS.md")
    {
        printf 'terms_version=%s\n' "$IL2_DIAG_TERMS_VERSION"
        printf 'terms_sha256=%s\n' "$terms_hash"
        printf 'accepted_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } >"$temporary"
    mv -- "$temporary" "$acceptance"
    printf 'Accepted notice version %s. No software was installed yet.\n' "$IL2_DIAG_TERMS_VERSION"
}

cmd_install() {
    local steam_root baseline tool_dir staging state_dir baseline_version baseline_vkd3d_version
    local source_core target_core official_core harness_commit lock_file official_core_hash
    il2_diag_terms_accepted "$repo_dir" || {
        printf '%s\n' \
            'error: read and accept the tester notice before installation:' \
            '  ./tools/il2-diag.sh accept-terms' >&2
        exit 1
    }
    if il2_diag_steam_running; then
        printf '%s\n' 'error: fully exit Steam before installation, then run setup again' >&2
        exit 1
    fi
    cmd_doctor

    steam_root=$(il2_diag_find_steam_root)
    baseline=$(il2_diag_baseline_dir)
    tool_dir=$(il2_diag_tool_dir)
    source_core="$artifact_root/x64/d3d12core.dll"
    [[ -f $source_core && ! -L $source_core ]] || {
        printf 'error: missing or unsafe diagnostic DLL: %s\n' "$source_core" >&2
        exit 1
    }

    mkdir -p -- "$steam_root/compatibilitytools.d"
    lock_file="$steam_root/compatibilitytools.d/.il2-xid109-install.lock"
    exec 8>"$lock_file"
    flock -n 8 || { printf 'error: another install/uninstall operation is active\n' >&2; exit 1; }
    [[ ! -e $tool_dir ]] || {
        printf 'error: diagnostic tool already exists; use status or uninstall first\n' >&2
        exit 1
    }
    staging="$steam_root/compatibilitytools.d/.IL2-Xid109-installing-$$"
    [[ ! -e $staging ]] || { printf 'error: staging path already exists: %s\n' "$staging" >&2; exit 1; }

    baseline_version=$(<"$baseline/version")
    baseline_vkd3d_version=$(<"$baseline/files/lib/wine/vkd3d-proton/version")
    official_core="$baseline/files/lib/wine/vkd3d-proton/x86_64-windows/d3d12core.dll"
    [[ -f $official_core && ! -L $official_core ]] || {
        printf 'error: official Proton x64 d3d12core.dll is missing or unsafe\n' >&2
        exit 1
    }
    official_core_hash=$(il2_diag_file_sha256 "$official_core")
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
    if [[ $(il2_diag_file_sha256 "$target_core") != "$official_core_hash" ]]; then
        printf '%s\n' 'error: copied Proton core does not match the official source; staging was preserved' >&2
        exit 1
    fi
    harness_commit=$(il2_diag_harness_revision "$repo_dir")

    cp -a -- "$build_manifest" "$state_dir/build-manifest.json"
    python3 "$script_dir/install-manifest.py" \
        --output "$state_dir/install-manifest.json" \
        --baseline "$baseline" \
        --baseline-version "$baseline_version" \
        --baseline-vkd3d-version "$baseline_vkd3d_version" \
        --original-core "$target_core" \
        --diagnostic-core "$source_core" \
        --build-manifest "$build_manifest" \
        --terms-acceptance "$repo_dir/.state/terms-acceptance.txt" \
        --harness-commit "$harness_commit"

    cp -a -- "$source_core" "$target_core"
    if [[ $(il2_diag_file_sha256 "$target_core") != $(il2_diag_file_sha256 "$source_core") ]]; then
        printf '%s\n' 'error: diagnostic DLL copy verification failed; staging was preserved' >&2
        exit 1
    fi
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
    cp -a -- "$repo_dir/.state/terms-acceptance.txt" "$state_dir/terms-acceptance.txt"

    if [[ $(il2_diag_file_sha256 "$official_core") != "$official_core_hash" ]]; then
        printf '%s\n' 'error: official Proton changed unexpectedly; staging was preserved' >&2
        exit 1
    fi

    mv -- "$staging" "$tool_dir"
    printf '\nInstalled: %s\n' "$tool_dir"
    printf '%s\n' 'Restart Steam, select “IL2 Xid109 Diagnostic” once for IL-2 Korea,' \
        'then return to this folder and run ./il2-diagnostic.sh next.'
}

cmd_uninstall() {
    local steam_root tool_dir state_dir disabled_root destination timestamp
    if il2_diag_steam_running; then
        printf '%s\n' 'error: close IL-2 and fully exit Steam before uninstalling' >&2
        exit 1
    fi
    steam_root=$(il2_diag_find_steam_root) || { printf 'error: Steam root not found\n' >&2; exit 1; }
    tool_dir=$(il2_diag_tool_dir)
    state_dir="$tool_dir/.il2-xid109-diagnostic"
    [[ -r $state_dir/identity ]] || {
        printf 'error: the diagnostic compatibility tool is not installed\n' >&2
        exit 1
    }
    [[ $(<"$state_dir/identity") == "$IL2_DIAG_IDENTITY" ]] || {
        printf 'error: refusing to move an unrecognized compatibility tool\n' >&2
        exit 1
    }
    exec 9>"$state_dir/run.lock"
    flock -n 9 || {
        printf '%s\n' 'error: an IL-2 diagnostic run is active; do not uninstall yet' >&2
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
    printf '%s\n' \
        'Restart Steam, open IL-2 Korea > Properties > Compatibility, and restore the previous Proton selection.' \
        'The recoverable copy still uses disk space. Keep it until the coordinator confirms the evidence was received.'
}

cmd_trash_copy() {
    local steam_root tool_dir disabled_root lock_file answer candidate resolved
    local -a candidates=()
    if il2_diag_steam_running; then
        printf '%s\n' 'error: fully exit Steam before moving a disabled copy to Trash' >&2
        exit 1
    fi
    steam_root=$(il2_diag_find_steam_root) || { printf 'error: Steam root not found\n' >&2; exit 1; }
    tool_dir=$(il2_diag_tool_dir)
    if [[ -e $tool_dir ]]; then
        printf '%s\n' 'error: the diagnostic tool is still active; run uninstall first' >&2
        exit 1
    fi
    disabled_root="$steam_root/compatibilitytools.d-disabled"
    [[ -d $disabled_root ]] || { printf '%s\n' 'No disabled diagnostic copy was found.'; return 0; }
    disabled_root=$(cd -- "$disabled_root" && pwd -P)
    lock_file="$steam_root/compatibilitytools.d/.il2-xid109-install.lock"
    mkdir -p -- "$steam_root/compatibilitytools.d"
    exec 8>"$lock_file"
    flock -n 8 || { printf 'error: another install/uninstall operation is active\n' >&2; exit 1; }
    while IFS= read -r -d '' candidate; do
        if [[ -r $candidate/.il2-xid109-diagnostic/identity ]] &&
            [[ $(<"$candidate/.il2-xid109-diagnostic/identity") == "$IL2_DIAG_IDENTITY" ]]; then
            candidates+=("$candidate")
        fi
    done < <(find "$disabled_root" -mindepth 1 -maxdepth 1 -type d \
        -name "$IL2_DIAG_TOOL_NAME-*" -print0)
    if ((${#candidates[@]} == 0)); then
        printf '%s\n' 'No recognized disabled diagnostic copy was found.'
        return 0
    fi
    if ! command -v gio >/dev/null 2>&1; then
        printf '%s\n' \
            'Desktop Trash support (gio) is unavailable. Nothing was moved.' \
            'Ask the coordinator to help remove the listed disabled folder with the file manager.' >&2
        printf '  %s\n' "${candidates[@]}" >&2
        exit 1
    fi
    printf '%s\n' \
        'The following disabled diagnostic Proton copy or copies will be moved to desktop Trash:'
    for candidate in "${candidates[@]}"; do
        du -sh -- "$candidate" 2>/dev/null || printf '  %s\n' "$candidate"
    done
    printf '%s\n' \
        'Captured results and PRIVATE archives are not in these folders and will not be deleted.' \
        'Type MOVE DISABLED COPY TO TRASH exactly to continue, or press Enter to cancel.'
    printf '> '
    IFS= read -r answer
    [[ $answer == 'MOVE DISABLED COPY TO TRASH' ]] || {
        printf '%s\n' 'Cancelled. Nothing was moved.'
        return 1
    }
    for candidate in "${candidates[@]}"; do
        resolved=$(cd -- "$candidate" && pwd -P)
        case $resolved in
            "$disabled_root/$IL2_DIAG_TOOL_NAME-"*) ;;
            *) printf 'error: unsafe disabled-copy path: %s\n' "$resolved" >&2; exit 1 ;;
        esac
        [[ -r $resolved/.il2-xid109-diagnostic/identity ]] &&
            [[ $(<"$resolved/.il2-xid109-diagnostic/identity") == "$IL2_DIAG_IDENTITY" ]] || {
                printf 'error: identity changed before deletion: %s\n' "$resolved" >&2
                exit 1
            }
        gio trash -- "$resolved"
        printf 'Moved to desktop Trash: %s\n' "$resolved"
    done
    printf '%s\n' 'The copy remains recoverable until the desktop Trash is emptied.'
}

cmd_recover() {
    local tool_dir state_dir recovery_lock recovered=0 run_dir marker
    tool_dir=$(il2_diag_tool_dir 2>/dev/null || true)
    state_dir="$tool_dir/.il2-xid109-diagnostic"
    if [[ -r $state_dir/identity ]] && [[ $(<"$state_dir/identity") == "$IL2_DIAG_IDENTITY" ]]; then
        exec 9>"$state_dir/run.lock"
    else
        mkdir -p -- "$repo_dir/.state"
        recovery_lock="$repo_dir/.state/recovery.lock"
        exec 9>"$recovery_lock"
    fi
    flock -n 9 || {
        printf '%s\n' 'error: a diagnostic run is still active; close the game before recovery' >&2
        exit 1
    }
    while IFS= read -r -d '' marker; do
        run_dir=${marker%/.capture-in-progress}
        printf 'Recovering interrupted capture: %s\n' "$run_dir"
        "$script_dir/finalize-run.sh" --run-dir "$run_dir" --recovered
        recovered=$((recovered + 1))
    done < <(find "$repo_dir/results" -mindepth 2 -maxdepth 2 -type f \
        -name .capture-in-progress -print0 2>/dev/null)
    if ((recovered == 0)); then
        printf '%s\n' 'No interrupted captures need recovery.'
    else
        printf 'Recovered %d capture(s). Review status before continuing.\n' "$recovered"
    fi
}

cmd_ready() {
    local marker run_dir proton_pid observation_epoch observation_utc
    local epoch_tmp utc_tmp record_tmp
    local -a markers=()
    while IFS= read -r -d '' marker; do
        markers+=("$marker")
    done < <(find "$repo_dir/results" -mindepth 2 -maxdepth 2 -type f \
        -name .capture-in-progress -print0 2>/dev/null)
    if ((${#markers[@]} == 0)); then
        printf '%s\n' \
            'error: no active diagnostic run was found' \
            'Run ./il2-diagnostic.sh next, launch IL-2, and use ready only after the hangar renders.' >&2
        exit 1
    fi
    if ((${#markers[@]} != 1)); then
        printf '%s\n' \
            'error: more than one unfinished capture exists, so the active run is ambiguous' \
            'Close the game, run ./il2-diagnostic.sh recover, then review status.' >&2
        exit 1
    fi
    run_dir=${markers[0]%/.capture-in-progress}
    exec 7>"$run_dir/observation-start.lock"
    flock -n 7 || {
        printf '%s\n' 'error: another Ready operation is already recording the timer' >&2
        exit 1
    }
    [[ -f $run_dir/.capture-in-progress ]] || {
        printf '%s\n' 'error: the run finalized before Ready could record the timer; check status' >&2
        exit 1
    }
    if [[ ! -r $run_dir/proton-runtime-start-epoch.txt ||
          ! $(<"$run_dir/proton-runtime-start-epoch.txt") =~ ^[0-9]+$ ||
          ! -r $run_dir/proton-child.pid ||
          ! $(<"$run_dir/proton-child.pid") =~ ^[0-9]+$ ]]; then
        printf '%s\n' \
            'error: the game process is not ready yet; wait a moment and try Ready again' >&2
        exit 1
    fi
    proton_pid=$(<"$run_dir/proton-child.pid")
    if ! kill -0 "$proton_pid" 2>/dev/null; then
        printf '%s\n' \
            'error: the game is no longer running; Ready did not start a timer' \
            'Run ./il2-diagnostic.sh status before doing anything else.' >&2
        exit 1
    fi
    if [[ -f $run_dir/.observation-start-recorded ]]; then
        if [[ -r $run_dir/observation-start-utc.txt &&
              -n $(<"$run_dir/observation-start-utc.txt") &&
              -r $run_dir/observation-start-epoch.txt &&
              $(<"$run_dir/observation-start-epoch.txt") =~ ^[0-9]+$ ]]; then
            printf 'Ready was already recorded for this run at %s. The timer was not restarted.\n' \
                "$(<"$run_dir/observation-start-utc.txt")"
            return 0
        fi
        printf '%s\n' \
            'error: the existing Ready marker is incomplete; stop and contact the coordinator' >&2
        exit 1
    fi
    observation_epoch=$(date +%s)
    observation_utc=$(date -u -d "@$observation_epoch" +%Y-%m-%dT%H:%M:%SZ)
    epoch_tmp="$run_dir/observation-start-epoch.txt.tmp.$$"
    utc_tmp="$run_dir/observation-start-utc.txt.tmp.$$"
    record_tmp="$run_dir/.observation-start-recorded.tmp.$$"
    printf '%s\n' "$observation_epoch" >"$epoch_tmp"
    printf '%s\n' "$observation_utc" >"$utc_tmp"
    printf 'observation timer recorded\n' >"$record_tmp"
    mv -- "$epoch_tmp" "$run_dir/observation-start-epoch.txt"
    mv -- "$utc_tmp" "$run_dir/observation-start-utc.txt"
    mv -- "$record_tmp" "$run_dir/.observation-start-recorded"
    printf '%s\n' \
        "Ready: the 10-minute hangar observation started at $observation_utc." \
        'Return to the unchanged hangar now. Exit normally only after 10 full minutes without a failure.'
}

cmd_select() {
    local wanted=${1:-} tool_dir state_dir temporary authorization authorization_tmp
    [[ -n $wanted ]] || { printf 'error: select requires a case\n' >&2; il2_diag_list_cases "$matrix" >&2; exit 2; }
    if il2_diag_has_incomplete_runs "$repo_dir"; then
        printf '%s\n' \
            'error: an interrupted capture must be recovered before selecting another case' \
            '  ./tools/il2-diag.sh recover' >&2
        exit 1
    fi
    if [[ ${XDG_SESSION_TYPE:-unknown} != x11 ]]; then
        printf 'error: the controlled test requires X11; current session is %s\n' \
            "${XDG_SESSION_TYPE:-unknown}" >&2
        printf '%s\n' 'Stop and ask the coordinator before changing login-session settings.' >&2
        exit 1
    fi
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
    exec 9>"$state_dir/run.lock"
    flock -n 9 || {
        printf '%s\n' 'error: an IL-2 diagnostic run is already active' >&2
        exit 1
    }
    temporary="$state_dir/selected-case.tmp.$$"
    authorization="$state_dir/run-authorization"
    authorization_tmp="$authorization.tmp.$$"
    printf '%s\n' "$wanted" >"$temporary"
    {
        printf 'case=%s\n' "$wanted"
        printf 'authorized_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } >"$authorization_tmp"
    mv -- "$temporary" "$state_dir/selected-case"
    mv -- "$authorization_tmp" "$authorization"
    rm -f -- "$repo_dir/.state/last-launch-error.txt"
    printf 'Selected case: %s\n' "$wanted"
    printf '%s\n' \
        'One IL-2 diagnostic launch is now authorized.' \
        'Launch it normally through Steam and reproduce once.'
}

cmd_status() {
    local tool_dir state_dir selected='not installed' installed=0 run_count
    tool_dir=$(il2_diag_tool_dir 2>/dev/null || true)
    state_dir="$tool_dir/.il2-xid109-diagnostic"
    if [[ -n $tool_dir && -r $state_dir/identity ]] &&
        [[ $(<"$state_dir/identity") == "$IL2_DIAG_IDENTITY" ]]; then
        selected=$(<"$state_dir/selected-case")
        installed=1
        printf 'Installation: %s\n' "$tool_dir"
    else
        printf 'Installation: not installed\n'
    fi
    if [[ -r $repo_dir/.state/last-launch-error.txt ]]; then
        printf 'Last blocked launch:\n'
        sed 's/^/  /' "$repo_dir/.state/last-launch-error.txt"
    fi
    printf 'Selected case: %s\n' "$selected"
    printf '\n'
    run_count=$(find "$repo_dir/results" -mindepth 1 -maxdepth 1 -type d \
        -name '20*-*' -printf '.' 2>/dev/null | wc -c)
    if ((installed == 0 && run_count == 0)); then
        printf '%s\n' \
            'No game runs have been captured yet.' \
            '' \
            'Next workflow action: SETUP REQUIRED'
        return 0
    fi
    python3 "$script_dir/workflow-status.py"
}

require_no_incomplete_runs() {
    if il2_diag_has_incomplete_runs "$repo_dir"; then
        printf '%s\n' \
            'error: recover interrupted captures before analysis or packaging:' \
            '  ./tools/il2-diag.sh recover' >&2
        exit 1
    fi
}

command_name=${1:-}
case $command_name in
    terms) shift; (($# == 0)) || { usage >&2; exit 2; }; cmd_terms ;;
    accept-terms) shift; (($# == 0)) || { usage >&2; exit 2; }; cmd_accept_terms ;;
    doctor) shift; (($# == 0)) || { usage >&2; exit 2; }; cmd_doctor ;;
    install) shift; (($# == 0)) || { usage >&2; exit 2; }; cmd_install ;;
    uninstall) shift; (($# == 0)) || { usage >&2; exit 2; }; cmd_uninstall ;;
    trash-copy) shift; (($# == 0)) || { usage >&2; exit 2; }; cmd_trash_copy ;;
    select) shift; (($# == 1)) || { usage >&2; exit 2; }; cmd_select "$1" ;;
    ready) shift; (($# == 0)) || { usage >&2; exit 2; }; cmd_ready ;;
    recover) shift; (($# == 0)) || { usage >&2; exit 2; }; cmd_recover ;;
    status) shift; (($# == 0)) || { usage >&2; exit 2; }; cmd_status ;;
    analyze) shift; (($# == 0)) || { usage >&2; exit 2; }; require_no_incomplete_runs; exec python3 "$repo_dir/analyzer/analyze.py" ;;
    pack) shift; (($# == 0)) || { usage >&2; exit 2; }; require_no_incomplete_runs; exec "$script_dir/pack-results.sh" ;;
    cases) shift; (($# == 0)) || { usage >&2; exit 2; }; il2_diag_list_cases "$matrix" ;;
    help|--help|-h|'') usage ;;
    *) printf 'error: unknown command: %s\n' "$command_name" >&2; usage >&2; exit 2 ;;
esac
