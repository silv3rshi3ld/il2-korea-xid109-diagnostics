#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
umask 077

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
control="$script_dir/tools/il2-diag.sh"
workflow="$script_dir/tools/workflow-status.py"

usage() {
    printf '%s\n' \
        'IL-2 Korea Xid 109 diagnostic assistant' \
        '' \
        'Usage: ./il2-diagnostic.sh COMMAND' \
        '' \
        '  setup       Read terms, check the computer, and install the private tool' \
        '  check       Run read-only checks' \
        '  next        Recover if needed and select the next controlled run' \
        '  ready       Start the 10-minute timer once the hangar is fully rendered' \
        '  status      Show completed, interrupted, and inconclusive runs' \
        '  recover     Recover a capture after a freeze or reboot' \
        '  finish      Analyze and create the PRIVATE results archive' \
        '  uninstall   Disable the custom Proton copy after testing' \
        '  trash-copy  Move a previously disabled custom Proton copy to desktop Trash' \
        '  terms       Read the tester safety/privacy notice'
}

print_steam_steps() {
    printf '\n%s\n' \
        'STEAM SETUP — do this once:' \
        '1. Start Steam again.' \
        '2. Open Library and right-click IL-2 Sturmovik: Korea.' \
        '3. Choose Properties, then Compatibility.' \
        '4. Enable “Force the use of a specific Steam Play compatibility tool”.' \
        '5. Select “IL2 Xid109 Diagnostic”.' \
        '6. Leave the diagnostic folder exactly where it is until uninstall is complete.'
}

cmd_setup() {
    printf '%s\n' \
        'Before setup: save your work, close IL-2, and fully exit Steam.' \
        'This diagnostic intentionally reproduces a GPU hang and may require a reboot.' \
        ''
    if ! "$control" accept-terms; then
        printf '%s\n' 'Setup stopped because the notice was not accepted.'
        exit 1
    fi
    "$control" install
    print_steam_steps
    printf '\nWhen Steam is configured, return here and run: ./il2-diagnostic.sh next\n'
}

print_run_instructions() {
    local case_name=$1
    printf '\n%s\n' \
        "NEXT RUN: $case_name" \
        '' \
        '1. Save work and close unrelated applications.' \
        '2. Launch IL-2 Korea normally from Steam.' \
        '3. Open the same known-failing hangar scene with unchanged graphics settings.' \
        '4. When the hangar is fully rendered, return to this folder and run:' \
        '   ./il2-diagnostic.sh ready' \
        '5. Start the 10-minute observation only after Ready confirms the timer started.' \
        '6. If it does not fail, leave it running for 10 full minutes, then exit normally.' \
        '7. If rendering freezes but the desktop responds, wait 60 seconds for logs to flush,' \
        '   use Steam Stop once, and wait another 30 seconds.' \
        '8. If the entire desktop remains unusable for about two minutes, restart the computer.' \
        '   After signing in, open this same folder and run ./il2-diagnostic.sh recover.' \
        '9. After the capture finalizes, run ./il2-diagnostic.sh status, then next.'
}

cmd_next() {
    local action
    action=$(python3 "$workflow" --next)
    if [[ $action == RECOVER ]]; then
        "$control" recover
        action=$(python3 "$workflow" --next)
    fi
    case $action in
        STOP_BASELINE_NO_XID)
            printf '%s\n' \
                'STOP: the forensic baseline completed 10 minutes without Xid 109.' \
                'The control did not reproduce, so later comparisons would be misleading.' \
                'Send ./il2-diagnostic.sh status output to the investigation coordinator.'
            ;;
        REVIEW)
            printf '%s\n' \
                'STOP: the latest case captured information, but it is not valid for' \
                'automatic progression. Status explains the missing or conflicting evidence.' \
                'Do not select another case yet. Send ./il2-diagnostic.sh status output' \
                'and your visible-outcome note to the investigation coordinator for a decision.'
            ;;
        COMPLETE)
            printf '%s\n' \
                'All four controlled cases have a conclusive capture.' \
                'Run: ./il2-diagnostic.sh finish'
            ;;
        baseline|single-queue|no-descriptor-buffer|sync)
            "$control" select "$action"
            print_run_instructions "$action"
            ;;
        *) printf 'error: unknown workflow state: %s\n' "$action" >&2; exit 1 ;;
    esac
}

cmd_finish() {
    local action
    action=$(python3 "$workflow" --next)
    case $action in
        COMPLETE|STOP_BASELINE_NO_XID) ;;
        *)
            printf '%s\n' \
                'The evidence set is not ready for the novice Finish step.' \
                'Run ./il2-diagnostic.sh status and follow its next action.' >&2
            exit 1
            ;;
    esac
    "$control" pack
    printf '\n%s\n' \
        'Nothing was uploaded. Send exactly the new PRIVATE results archive and its' \
        'matching .sha256 file through the privately agreed channel.' \
        'In the same private chat, paste the visible-outcome note for every run.' \
        'The notes are not inside the archive. Do not post the files or notes publicly.' \
        'The optional NVIDIA report is separate and should be collected only when requested.'
}

interactive_menu() {
    local choice
    printf '%s\n' \
        'IL-2 Korea Xid 109 diagnostic assistant' \
        '' \
        '1. First-time setup' \
        '2. Check this computer' \
        '3. Select the next run' \
        '4. Start the timer after the hangar is fully rendered' \
        '5. Show progress' \
        '6. Recover after a freeze/reboot' \
        '7. Analyze and create the private archive' \
        '8. Uninstall the custom compatibility tool' \
        '9. Move a disabled custom Proton copy to desktop Trash' \
        '10. Read the safety/privacy terms'
    printf '\nChoose 1-10: '
    IFS= read -r choice
    case $choice in
        1) cmd_setup ;;
        2) "$control" doctor ;;
        3) cmd_next ;;
        4) "$control" ready ;;
        5) "$control" status ;;
        6) "$control" recover ;;
        7) cmd_finish ;;
        8) "$control" uninstall ;;
        9) "$control" trash-copy ;;
        10) "$control" terms ;;
        *) printf '%s\n' 'No valid choice selected.' >&2; exit 2 ;;
    esac
}

case ${1:-} in
    setup) (($# == 1)) || { usage >&2; exit 2; }; cmd_setup ;;
    check) (($# == 1)) || { usage >&2; exit 2; }; exec "$control" doctor ;;
    next) (($# == 1)) || { usage >&2; exit 2; }; cmd_next ;;
    ready) (($# == 1)) || { usage >&2; exit 2; }; exec "$control" ready ;;
    status) (($# == 1)) || { usage >&2; exit 2; }; exec "$control" status ;;
    recover) (($# == 1)) || { usage >&2; exit 2; }; exec "$control" recover ;;
    finish) (($# == 1)) || { usage >&2; exit 2; }; cmd_finish ;;
    uninstall) (($# == 1)) || { usage >&2; exit 2; }; exec "$control" uninstall ;;
    trash-copy) (($# == 1)) || { usage >&2; exit 2; }; exec "$control" trash-copy ;;
    terms) (($# == 1)) || { usage >&2; exit 2; }; exec "$control" terms ;;
    help|--help|-h) usage ;;
    '') interactive_menu ;;
    *) usage >&2; exit 2 ;;
esac
