#!/usr/bin/env bash

readonly IL2_DIAG_TOOL_NAME='IL2 Xid109 Diagnostic'
# These constants are consumed by scripts that source this library.
# shellcheck disable=SC2034
readonly IL2_DIAG_IDENTITY='il2-korea-xid109-diagnostics:v1:247970'
readonly IL2_DIAG_EXPECTED_PROTON_BUILD='experimental-bleeding-edge-11.0-414018-20260814-p3b5456-w34e7d5-d3a4c6f-v238f15'
readonly IL2_DIAG_EXPECTED_VKD3D_COMMIT='238f157e1d64f90e0d90593557c092ab8af6e0a3'
readonly IL2_DIAG_TERMS_VERSION='2026-08-15.2'
# shellcheck disable=SC2034
readonly IL2_DIAG_RESULTS_HEADROOM_KIB='8388608'
# shellcheck disable=SC2034
readonly IL2_DIAG_PER_RUN_HEADROOM_KIB='2097152'

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

il2_diag_library_roots() {
    local steam_root=$1
    local library_file="$steam_root/steamapps/libraryfolders.vdf"
    printf '%s\n' "$steam_root"
    [[ -r $library_file ]] || return 0
    python3 - "$library_file" <<'PY'
import pathlib
import re
import sys

text = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
seen = set()
for match in re.finditer(r'^\s*"path"\s+"((?:\\.|[^"\\])*)"', text, re.MULTILINE):
    value = match.group(1).replace(r"\\", "\\").replace(r'\"', '"')
    if value not in seen:
        seen.add(value)
        print(value)
PY
}

il2_diag_tool_dir() {
    local steam_root
    steam_root=$(il2_diag_find_steam_root) || return 1
    printf '%s/compatibilitytools.d/%s\n' "$steam_root" "$IL2_DIAG_TOOL_NAME"
}

il2_diag_baseline_dir() {
    local steam_root library candidate first=''
    if [[ -n ${IL2_DIAG_PROTON_BASELINE:-} ]]; then
        [[ -d $IL2_DIAG_PROTON_BASELINE ]] || return 1
        cd -- "$IL2_DIAG_PROTON_BASELINE" && pwd -P
        return
    fi
    steam_root=$(il2_diag_find_steam_root) || return 1
    while IFS= read -r library; do
        [[ -n $library ]] || continue
        candidate="$library/steamapps/common/Proton - Experimental"
        [[ -x $candidate/proton ]] || continue
        [[ -n $first ]] || first=$candidate
        if [[ -r $candidate/version && -r $candidate/files/lib/wine/vkd3d-proton/version ]] &&
            grep -Fq -- "$IL2_DIAG_EXPECTED_PROTON_BUILD" "$candidate/version" &&
            grep -Fq -- "$IL2_DIAG_EXPECTED_VKD3D_COMMIT" \
                "$candidate/files/lib/wine/vkd3d-proton/version"; then
            cd -- "$candidate" && pwd -P
            return
        fi
    done < <(il2_diag_library_roots "$steam_root")
    [[ -n $first ]] || return 1
    cd -- "$first" && pwd -P
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

il2_diag_terms_accepted() {
    local repo_dir=$1
    local terms_file="$repo_dir/TESTER-TERMS.md"
    local acceptance="$repo_dir/.state/terms-acceptance.txt"
    local expected_hash
    [[ -r $terms_file && -r $acceptance ]] || return 1
    expected_hash=$(il2_diag_file_sha256 "$terms_file")
    grep -Fxq "terms_version=$IL2_DIAG_TERMS_VERSION" "$acceptance" &&
        grep -Fxq "terms_sha256=$expected_hash" "$acceptance"
}

il2_diag_harness_revision() {
    local repo_dir=$1
    if [[ -d $repo_dir/.git ]] && command -v git >/dev/null 2>&1; then
        git -C "$repo_dir" rev-parse HEAD 2>/dev/null && return
    fi
    if [[ -r $repo_dir/bundle-info.json ]]; then
        python3 - "$repo_dir/bundle-info.json" <<'PY'
import json
import pathlib
import sys

try:
    value = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    print(value.get("harness_commit") or "unknown")
except (OSError, ValueError):
    print("unknown")
PY
        return
    fi
    printf '%s\n' unknown
}

il2_diag_steam_running() {
    command -v pgrep >/dev/null 2>&1 || return 1
    pgrep -u "$(id -u)" -x steam >/dev/null 2>&1
}

il2_diag_has_incomplete_runs() {
    local repo_dir=$1
    find "$repo_dir/results" -mindepth 2 -maxdepth 2 -type f \
        -name .capture-in-progress -print -quit 2>/dev/null | grep -q .
}
