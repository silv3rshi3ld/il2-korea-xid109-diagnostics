# Privacy and evidence handling

This harness is intentionally local-only. It has no upload code, telemetry endpoint, account integration, or automatic network submission.

## Normal result archive

`./il2-diagnostic.sh finish` creates a file whose name begins with `PRIVATE-`. It can contain local paths, system and GPU identifiers, kernel messages, Proton/VKD3D logs, and game shader bytecode. The archive is intended for private diagnostic transfer to the investigation coordinator, not public posting.

The harness suppresses the journal hostname field and does not run a hostname-collection command. Usernames or hostnames can still appear inside local paths or upstream Proton/VKD3D text. The bracketed full kernel window can also contain unrelated kernel events and identifiers such as device names, MAC addresses, or IP addresses. Automatic redaction could destroy diagnostically important relationships, so the raw private archive is preserved instead of pretending to be anonymous.

The ordinary archive excludes `results/nvidia-reports/`. An NVIDIA bug report is substantially broader than the four-run capture and should be transferred separately only when the coordinator requests it.

## Local retention

- Raw runs: `results/<timestamp>-<case>/`
- Analysis: `results/analysis-summary.*`
- Candidate evidence: `results/culprit-candidate/`
- Optional NVIDIA report: `results/nvidia-reports/`
- Disabled custom Proton copy: Steam root `compatibilitytools.d-disabled/`

All result paths are ignored by Git. Do not add them manually to a commit.

## Before sharing

For a nontechnical tester, the safest workflow is to send the `PRIVATE-...` archive and matching `.sha256` only through the pre-agreed private channel to the person who supplied the tester archive. Raw evidence must not be sent upstream or published without the tester's separate permission. The technical coordinator should perform any necessary redaction before filing a public NVIDIA, VKD3D-Proton, Proton, or game report. The default recipient retention/deletion conditions are stated in [the tester terms](TESTER-TERMS.md).

Game shader dumps may be copyrighted material. Their presence in a candidate region does not prove that the shader is defective and does not grant permission for public redistribution.

## Removing local data

Do not remove evidence until the coordinator confirms receipt. After uninstalling, `./il2-diagnostic.sh trash-copy` can move only disabled Proton copies recognized by the harness to desktop Trash; it requires a typed confirmation. After receipt is confirmed and cleanup is complete, the tester may move the entire extracted tester folder to Trash with the file manager, including `results/`, `PRIVATE-...` archives, and `.state/terms-acceptance.txt`. The harness never permanently deletes captured evidence automatically.
