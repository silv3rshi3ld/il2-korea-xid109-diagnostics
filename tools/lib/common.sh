#!/usr/bin/env bash

readonly IL2_DIAG_APP_ID='247970'
readonly IL2_DIAG_TOOL_NAME='IL2 Xid109 Diagnostic'
readonly IL2_DIAG_IDENTITY='il2-korea-xid109-diagnostics:v1:247970'
readonly IL2_DIAG_EXPECTED_PROTON_BUILD='experimental-bleeding-edge-11.0-414018-20260814-p3b5456-w34e7d5-d3a4c6f-v238f15'
readonly IL2_DIAG_EXPECTED_VKD3D_COMMIT='238f157e1d64f90e0d90593557c092ab8af6e0a3'

il2_diag_repo_root() {
    local library_dir
    library_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
    cd -- "$library_dir/../.." && pwd -P
}

il2_diag_find_steam_root() {
    local candidate
    if [[ -n ${IL2_DIAG_STEAM_ROOT:-} ]]; then
        candidate=$IL2_DIAG_STEAM_ROOT
        [[ -d $candidate ]] || return 1
        cd -- "$candidate" && pwd -P
        return
    fi
    for candidate in "$HOME/.steam/root" "$HOME/.local/share/Steam"; do
        if [[ -d $candidate/steamapps ]]; then
            cd -- "$candidate" && pwd -P
            return
        fi
    done
    return 1
}

il2_diag_tool_dir() {
    local steam_root
    steam_root=$(il2_diag_find_steam_root) || return 1
    printf '%s/compatibilitytools.d/%s\n' "$steam_root" "$IL2_DIAG_TOOL_NAME"
}

il2_diag_baseline_dir() {
    local steam_root
    steam_root=$(il2_diag_find_steam_root) || return 1
    printf '%s/steamapps/common/Proton - Experimental\n' "$steam_root"
}

il2_diag_matrix_lookup() {
    local matrix=$1
    local wanted=$2
    local name config disabled description
    while IFS='|' read -r name config disabled description; do
        [[ -n $name && $name != \#* ]] || continue
        if [[ $name == "$wanted" ]]; then
            printf '%s|%s|%s|%s\n' "$name" "$config" "$disabled" "$description"
            return 0
        fi
    done <"$matrix"
    return 1
}

il2_diag_list_cases() {
    local matrix=$1
    local name config disabled description
    while IFS='|' read -r name config disabled description; do
        [[ -n $name && $name != \#* ]] || continue
        printf '  %-22s %s\n' "$name" "$description"
    done <"$matrix"
}

il2_diag_file_sha256() {
    sha256sum -- "$1" | awk '{print $1}'
}
