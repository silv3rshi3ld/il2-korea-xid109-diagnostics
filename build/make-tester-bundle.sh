#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
umask 022

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
repo_dir=$(cd -- "$script_dir/.." && pwd -P)
source_dir="$script_dir/work/source"
artifact_root="$script_dir/output/vkd3d-proton-diag"
manifest="$repo_dir/build-manifest.json"
release_dir="$script_dir/output/tester-release"

for command_name in git tar gzip sha256sum python3 find sort xargs install cmp; do
    command -v "$command_name" >/dev/null 2>&1 || {
        printf 'error: missing maintainer packaging command: %s\n' "$command_name" >&2
        exit 1
    }
done
git -C "$repo_dir" diff --quiet
git -C "$repo_dir" diff --cached --quiet
if [[ -n $(git -C "$repo_dir" status --porcelain --untracked-files=normal) ]]; then
    printf '%s\n' 'error: commit or remove untracked source files before packaging' >&2
    exit 1
fi
python3 "$repo_dir/tools/verify-build.py" \
    --manifest "$manifest" --artifact-root "$artifact_root"

[[ -d $source_dir/.git ]] || {
    printf '%s\n' 'error: verified build source is missing; rebuild before packaging' >&2
    exit 1
}
source_status=$(git -C "$source_dir" status --porcelain)
[[ $source_status == ' M libs/vkd3d/breadcrumbs.c' ]] || {
    printf '%s\n' 'error: build source state is not exactly the diagnostic patch' >&2
    exit 1
}
[[ $(git -C "$source_dir" diff --numstat) == $'9\t4\tlibs/vkd3d/breadcrumbs.c' ]] || {
    printf '%s\n' 'error: corresponding source has changes beyond the locked report-only patch' >&2
    exit 1
}
cmp -- "$source_dir/LICENSE" "$repo_dir/LICENSES/VKD3D-Proton-LGPL-2.1.txt" || {
    printf '%s\n' 'error: committed LGPL text differs from the pinned source' >&2
    exit 1
}
cmp -- "$source_dir/COPYING" "$repo_dir/LICENSES/VKD3D-Proton-COPYING.txt" || {
    printf '%s\n' 'error: committed VKD3D-Proton notice differs from the pinned source' >&2
    exit 1
}

readarray -t manifest_values < <(python3 - "$manifest" <<'PY'
import json
import pathlib
import sys

value = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
print(value["source"]["commit"])
print(value["source"]["patch"]["diff_sha256"])
print(value["build"]["source_date_epoch"])
PY
)
[[ $(git -C "$source_dir" rev-parse HEAD) == "${manifest_values[0]}" ]] || {
    printf '%s\n' 'error: corresponding source commit differs from build manifest' >&2
    exit 1
}
actual_diff_sha=$(git -C "$source_dir" diff --binary | sha256sum | awk '{print $1}')
[[ $actual_diff_sha == "${manifest_values[1]}" ]] || {
    printf '%s\n' 'error: corresponding source diff differs from build manifest' >&2
    exit 1
}

mkdir -p -- "$release_dir"
short_commit=$(git -C "$repo_dir" rev-parse --short=12 HEAD)
bundle_name="il2-korea-xid109-diagnostics-tester-$short_commit"
source_name="vkd3d-proton-238f157e-patched-corresponding-source.tar.gz"
source_archive="$release_dir/$source_name"
tar --sort=name --mtime="@${manifest_values[2]}" --owner=0 --group=0 --numeric-owner \
    --exclude='.git' --exclude='*/.git' --exclude='subprojects/.wraplock' \
    -czf "$source_archive" -C "$source_dir" .

stage_root=$(mktemp -d "$release_dir/.tester-stage.XXXXXXXX")
cleanup() {
    case $stage_root in
        "$release_dir/.tester-stage."*) find "$stage_root" -depth -delete 2>/dev/null || true ;;
    esac
}
trap cleanup EXIT
bundle_dir="$stage_root/$bundle_name"
mkdir -p -- "$bundle_dir"
git -C "$repo_dir" checkout-index --prefix="$bundle_dir/" -a
cp -a -- "$manifest" "$bundle_dir/build-manifest.json"
mkdir -p -- "$bundle_dir/build/output/vkd3d-proton-diag/x64" \
    "$bundle_dir/build/output/vkd3d-proton-diag/x86" "$bundle_dir/LICENSES" \
    "$bundle_dir/corresponding-source"
cp -a -- "$artifact_root/x64/d3d12.dll" "$artifact_root/x64/d3d12core.dll" \
    "$bundle_dir/build/output/vkd3d-proton-diag/x64/"
cp -a -- "$artifact_root/x86/d3d12.dll" "$artifact_root/x86/d3d12core.dll" \
    "$bundle_dir/build/output/vkd3d-proton-diag/x86/"
cp -a -- "$source_dir/LICENSE" "$bundle_dir/LICENSES/VKD3D-Proton-LGPL-2.1.txt"
cp -a -- "$source_dir/COPYING" "$bundle_dir/LICENSES/VKD3D-Proton-COPYING.txt"
cp -a -- "$source_archive" "$bundle_dir/corresponding-source/$source_name"

python3 - "$bundle_dir/bundle-info.json" "$short_commit" "$source_archive" "$manifest" <<'PY'
import hashlib
import json
import pathlib
import sys
from datetime import datetime, timezone

def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

output, commit, source, manifest = map(pathlib.Path, sys.argv[1:])
value = {
    "schema_version": 1,
    "bundle_created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "harness_commit": commit.name,
    "corresponding_source": {"file": source.name, "sha256": sha(source)},
    "build_manifest_sha256": sha(manifest),
    "contains_official_proton": False,
}
output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

(
    cd -- "$bundle_dir"
    find . -type f ! -name bundle-checksums.sha256 -print0 \
        | sort -z | xargs -0 sha256sum \
        | sed 's#  \./#  #' >bundle-checksums.sha256
)
python3 "$bundle_dir/tools/verify-tester-bundle.py" --root "$bundle_dir"
archive="$release_dir/$bundle_name.tar.gz"
[[ ! -e $archive ]] || { printf 'error: release archive already exists: %s\n' "$archive" >&2; exit 1; }
tar --sort=name --mtime="@${manifest_values[2]}" --owner=0 --group=0 --numeric-owner \
    -czf "$archive" -C "$stage_root" "$bundle_name"
(
    cd -- "$release_dir"
    sha256sum -- "$(basename -- "$archive")" >"$(basename -- "$archive").sha256"
)
printf 'Prepared tester bundle: %s\n' "$archive"
printf 'Outer checksum:        %s\n' "$archive.sha256"
printf '%s\n' \
    'The bundle contains no official Proton installation and must not be used unless doctor confirms the exact local baseline.'
