# Privacy and evidence handling

The diagnostic collector is intentionally local-only. It has no upload code, telemetry endpoint, account integration, or automatic evidence submission. Creating an archive does not transmit it.

This applies to the collector, not to Steam or IL-2. The harness does not block those applications from using their normal network connections.

## Normal result archive

`./il2-diagnostic.sh finish` creates a file whose name begins with `PRIVATE-`. It can contain local paths, system and GPU identifiers, kernel messages, Proton/VKD3D logs, game command information, and game shader bytecode.

The `PRIVATE-` prefix is only a warning label. **The archive is not encrypted or password-protected**, and its `.sha256` checksum does not hide its contents. Anyone who receives the archive can read the evidence. It is intended for private diagnostic transfer to the identified investigation coordinator, not public posting.

The harness suppresses the journal hostname field and does not run a hostname-collection command. Usernames or hostnames can still appear in local paths or upstream Proton/VKD3D text. Full kernel logs from the run interval can contain unrelated kernel events and identifiers such as device names, MAC addresses, or IP addresses. Automatic redaction could destroy diagnostically important relationships, so the raw private archive is preserved instead of being described as anonymous.

The ordinary archive always excludes `results/nvidia-reports/`. An NVIDIA bug report is substantially broader than a normal matrix capture and should be transferred separately only when the coordinator requests it.

## Local retention and disk use

- Raw runs: `results/<timestamp>-<case>/`
- Analysis: `results/analysis-summary.*`
- Candidate evidence: `results/culprit-candidate/`
- Optional NVIDIA report: `results/nvidia-reports/`
- Local acceptance record: `.state/terms-acceptance.txt`
- Disabled custom Proton copy: Steam root `compatibilitytools.d-disabled/`

The setup checker requires space for a complete Proton copy and at least 8 GiB of result headroom. Eight GiB is a minimum reserve, not a maximum. Per-run shader dumping has no fixed size cap, so evidence can consume more space.

Result paths and top-level private archives are ignored by Git, but ignore rules are not encryption or access control. Do not force-add evidence to a commit. The public source repository does not make any captured evidence public.

## Before sharing

For a nontechnical tester, the safest workflow is to send only the new `PRIVATE-...` archive and its matching `.sha256` as files through the pre-agreed private channel to the person who supplied the prepared tester archive. Paste the required visible-outcome notes as ordinary chat text; those notes are not collected automatically or stored in the archive. A checksum verifies integrity; it does not encrypt or redact the archive.

Raw evidence must not be sent upstream or published without the tester's separate permission. The technical coordinator should perform any necessary redaction before filing a public NVIDIA, VKD3D-Proton, Proton, or game report. Default recipient use, retention, and deletion conditions are stated in the [tester terms](TESTER-TERMS.md).

Game shader dumps can be copyrighted material. Their presence in a candidate region does not prove that a shader is defective and does not grant permission for public redistribution.

## Removing local data or withdrawing

If you submitted evidence and want it analyzed, keep the local files until the coordinator confirms that the archive was received and usable. After that, uninstall the custom tool, restore Steam, and run `./il2-diagnostic.sh trash-copy`. The command can move only disabled Proton copies recognized by the harness to desktop Trash and requires a typed confirmation.

If you withdraw before sending evidence, you may clean up immediately; you do not need receipt confirmation. Fully exit IL-2 and Steam, run `./il2-diagnostic.sh uninstall`, restore the three saved Steam settings, run `./il2-diagnostic.sh trash-copy`, and then move the extracted tester folder to Trash.

The extracted folder can contain `results/`, `PRIVATE-...` archives, checksums, and `.state/terms-acceptance.txt`. The harness never permanently deletes captured evidence automatically. Files moved to desktop Trash remain recoverable until Trash is emptied.

If you already sent evidence and then withdraw, request recipient-side deletion through the same private channel.
