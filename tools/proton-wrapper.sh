#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

tool_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
launcher="$tool_dir/.il2-xid109-diagnostic/il2-diag-launch.sh"
real_proton="$tool_dir/proton.real"

if [[ ! -x $launcher || ! -x $real_proton ]]; then
    printf 'IL-2 Xid109 diagnostic tool is incomplete. Reinstall it from the repository.\n' >&2
    exit 1
fi

exec "$launcher" "$real_proton" "$@"
