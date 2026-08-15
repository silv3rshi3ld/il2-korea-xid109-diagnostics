#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
umask 077

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
repo_dir=$(cd -- "$script_dir/.." && pwd -P)
report_dir="$repo_dir/results/nvidia-reports"

usage() {
    printf '%s\n' \
        'Usage: ./tools/collect-nvidia-report.sh [--run]' \
        '' \
        'Without --run, this command only explains the privileged operation.' \
        'With --run, it asks for confirmation immediately before invoking sudo.'
}

case ${1:-} in
    '')
        printf '%s\n' \
            'No command was run.' \
            'After one representative diagnostic Xid 109 failure, use:' \
            '  ./tools/collect-nvidia-report.sh --run' \
            '' \
            'That mode will clearly prompt before running sudo nvidia-bug-report.sh.' \
            'The report is broad and privacy-sensitive; send it separately and privately.'
        exit 0
        ;;
    --run) ;;
    --help|-h) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
esac

command -v nvidia-bug-report.sh >/dev/null 2>&1 || {
    printf 'error: nvidia-bug-report.sh is not installed\n' >&2
    exit 1
}
if [[ -d $report_dir ]] && find "$report_dir" -maxdepth 1 -type f -name 'nvidia-bug-report*.log.gz' -print -quit \
    | grep -q .; then
    printf 'A report already exists in %s. One representative report is normally sufficient.\n' "$report_dir" >&2
    printf 'Move that report elsewhere first only if a new report is diagnostically necessary.\n' >&2
    exit 1
fi

timestamp=$(date -u +%Y-%m-%dT%H%M%SZ)
output_base="$report_dir/nvidia-bug-report-$timestamp.log"
printf 'About to run this explicit privileged command:\n'
printf '  sudo nvidia-bug-report.sh --output-file %q\n' "$output_base"
printf '%s\n' \
    'It can take several minutes. If sudo asks for your password, typed characters are not displayed.' \
    'This report is excluded from the ordinary PRIVATE results archive.'
printf 'Continue? [y/N] '
IFS= read -r answer
case $answer in
    y|Y|yes|YES) ;;
    *) printf 'Cancelled; sudo was not invoked.\n'; exit 1 ;;
esac

mkdir -p -- "$report_dir"
sudo -- nvidia-bug-report.sh --output-file "$output_base"
if [[ -f $output_base.gz ]]; then
    output=$output_base.gz
elif [[ -f $output_base ]]; then
    output=$output_base
else
    printf 'warning: report command completed, but the expected output was not found\n' >&2
    output=$output_base
fi
printf 'NVIDIA report saved to: %s\n' "$output"
printf '%s\n' \
    'Never post this report publicly. Send it separately through the agreed private channel' \
    'only when the investigation coordinator requested it.'
