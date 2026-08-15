#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
umask 022

readonly VKD3D_REPOSITORY='https://github.com/HansKristian-Work/vkd3d-proton.git'
readonly VKD3D_COMMIT='238f157e1d64f90e0d90593557c092ab8af6e0a3'

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
repo_dir=$(cd -- "$script_dir/.." && pwd -P)
work_dir=${IL2_DIAG_BUILD_ROOT:-"$script_dir/work"}
source_dir="$work_dir/source"
prefix_dir="$script_dir/output/vkd3d-proton-diag"
patch_file="$script_dir/patches/0001-label-nvidia-checkpoint-queues.patch"
manifest="$repo_dir/build-manifest.json"
started=$(date -u +%Y-%m-%dT%H:%M:%SZ)

usage() {
    printf '%s\n' \
        'Usage: ./build/build-vkd3d-diag.sh [--source PATH]' \
        '' \
        'Builds the exact failing VKD3D-Proton revision as release binaries with' \
        'trace/breadcrumb support and one report-only queue-label patch.' \
        '--source seeds the private build checkout from a local Git clone; it is not modified.'
}

source_override=''
while (($#)); do
    case $1 in
        --source)
            (($# >= 2)) || { printf 'error: --source requires a path\n' >&2; exit 2; }
            source_override=$2
            shift 2
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            printf 'error: unknown argument: %s\n' "$1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

required_commands=(git meson ninja python3 glslangValidator \
    x86_64-w64-mingw32-gcc i686-w64-mingw32-gcc)
missing=()
for command_name in "${required_commands[@]}"; do
    command -v "$command_name" >/dev/null 2>&1 || missing+=("$command_name")
done
if ! command -v widl >/dev/null 2>&1 &&
    { ! command -v x86_64-w64-mingw32-widl >/dev/null 2>&1 ||
      ! command -v i686-w64-mingw32-widl >/dev/null 2>&1; }; then
    missing+=("widl (or both MinGW WIDL tools)")
fi
if ((${#missing[@]})); then
    printf 'error: missing build commands: %s\n' "${missing[*]}" >&2
    printf '%s\n' 'On Arch/CachyOS, install the corresponding meson, ninja, glslang,' \
        'mingw-w64-gcc, mingw-w64-tools, git, and Python packages yourself.' >&2
    printf '%s\n' 'This script never invokes sudo or a package manager.' >&2
    exit 1
fi

mkdir -p -- "$work_dir" "$script_dir/output"

if [[ -n $source_override ]]; then
    source_override=$(cd -- "$source_override" && pwd -P)
    [[ -d $source_override/.git ]] || {
        printf 'error: --source is not a Git checkout: %s\n' "$source_override" >&2
        exit 1
    }
    if [[ ! -d $source_dir/.git ]]; then
        git clone --recursive --no-hardlinks "$source_override" "$source_dir"
    fi
elif [[ ! -d $source_dir/.git ]]; then
    git clone --recursive "$VKD3D_REPOSITORY" "$source_dir"
fi

[[ -d $source_dir/.git ]] || { printf 'error: not a Git checkout: %s\n' "$source_dir" >&2; exit 1; }

# Meson may leave this transient lock in the source tree even for an out-of-tree
# build. It is not source input and must not contaminate recorded provenance.
if [[ -e $source_dir/subprojects/.wraplock ]] &&
    ! git -C "$source_dir" ls-files --error-unmatch subprojects/.wraplock >/dev/null 2>&1; then
    rm -- "$source_dir/subprojects/.wraplock"
fi
source_status=$(git -C "$source_dir" status --porcelain)
if [[ -n $source_status ]]; then
    if ! git -C "$source_dir" apply --reverse --check "$patch_file" >/dev/null 2>&1; then
        printf 'error: source checkout has unexpected local changes: %s\n' "$source_dir" >&2
        exit 1
    fi
    if [[ $(git -C "$source_dir" diff --name-only) != 'libs/vkd3d/breadcrumbs.c' ]] ||
        [[ $(git -C "$source_dir" diff --numstat) != $'9\t4\tlibs/vkd3d/breadcrumbs.c' ]] ||
        grep -qv '^ M libs/vkd3d/breadcrumbs.c$' <<<"$source_status"; then
        printf 'error: source checkout contains changes beyond the diagnostic patch\n' >&2
        exit 1
    fi
fi

if ! git -C "$source_dir" cat-file -e "$VKD3D_COMMIT^{commit}" 2>/dev/null; then
    git -C "$source_dir" fetch origin "$VKD3D_COMMIT"
fi

if [[ $(git -C "$source_dir" rev-parse HEAD) != "$VKD3D_COMMIT" ]]; then
    if [[ -n $(git -C "$source_dir" status --porcelain) ]]; then
        printf 'error: refusing to switch a modified source checkout\n' >&2
        exit 1
    fi
    git -C "$source_dir" switch --detach "$VKD3D_COMMIT"
fi
git -C "$source_dir" submodule update --init --recursive

if git -C "$source_dir" apply --check "$patch_file" >/dev/null 2>&1; then
    git -C "$source_dir" apply "$patch_file"
elif ! git -C "$source_dir" apply --reverse --check "$patch_file" >/dev/null 2>&1; then
    printf 'error: queue-label patch is neither applicable nor already applied\n' >&2
    exit 1
fi

expected_submodules=(
    'khronos/SPIRV-Headers=f88a2d766840fc825af1fc065977953ba1fa4a91'
    'khronos/Vulkan-Headers=0e9de566b7d4051c5cc1b762e242c46565956bdf'
    'subprojects/dxil-spirv=cc75a0c98d34d7bcc03560527c799b52e48b4d1f'
)
for expected in "${expected_submodules[@]}"; do
    path=${expected%%=*}
    commit=${expected#*=}
    actual=$(git -C "$source_dir/$path" rev-parse HEAD)
    [[ $actual == "$commit" ]] || {
        printf 'error: submodule %s is %s, expected %s\n' "$path" "$actual" "$commit" >&2
        exit 1
    }
done

export LC_ALL=C
export TZ=UTC
export ZERO_AR_DATE=1
SOURCE_DATE_EPOCH=$(git -C "$source_dir" show -s --format=%ct "$VKD3D_COMMIT")
export SOURCE_DATE_EPOCH

configure_arch() {
    local arch=$1
    local cross_file=$2
    local build_dir="$work_dir/build.$arch"
    local bindir="x$arch"

    if [[ -f $build_dir/meson-private/coredata.dat ]]; then
        meson setup --reconfigure "$build_dir" "$source_dir" \
            --cross-file "$source_dir/$cross_file" \
            --buildtype=release --strip -Denable_trace=true \
            --prefix "$prefix_dir" --bindir "$bindir" --libdir "$bindir"
    else
        meson setup "$build_dir" "$source_dir" \
            --cross-file "$source_dir/$cross_file" \
            --buildtype=release --strip -Denable_trace=true \
            --prefix "$prefix_dir" --bindir "$bindir" --libdir "$bindir"
    fi
    ninja -C "$build_dir" install
}

configure_arch 64 build-win64.txt
configure_arch 86 build-win32.txt

if [[ -e $source_dir/subprojects/.wraplock ]] &&
    ! git -C "$source_dir" ls-files --error-unmatch subprojects/.wraplock >/dev/null 2>&1; then
    rm -- "$source_dir/subprojects/.wraplock"
fi
source_status=$(git -C "$source_dir" status --porcelain)
if [[ $(git -C "$source_dir" diff --name-only) != 'libs/vkd3d/breadcrumbs.c' ]] ||
    [[ $(git -C "$source_dir" diff --numstat) != $'9\t4\tlibs/vkd3d/breadcrumbs.c' ]] ||
    grep -qv '^ M libs/vkd3d/breadcrumbs.c$' <<<"$source_status"; then
    printf 'error: build produced unexpected source-tree changes\n' >&2
    git -C "$source_dir" status --short >&2
    exit 1
fi

python3 "$script_dir/write-build-manifest.py" \
    --source "$source_dir" \
    --prefix "$prefix_dir" \
    --patch "$patch_file" \
    --started "$started" \
    --output "$manifest"

printf 'Diagnostic VKD3D-Proton build complete.\n'
printf 'Artifacts: %s\n' "$prefix_dir"
printf 'Manifest:  %s\n' "$manifest"
