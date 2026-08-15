# IL-2 Korea NVIDIA Xid 109 diagnostic

## Start here — this is for the invited tester

This tool collects evidence from a known NVIDIA GPU hang in **IL-2 Sturmovik: Korea**. It is not a fix. The intended test is approximately four game launches on the affected Arch/CachyOS computer.

You do not need to understand Linux diagnostics, compile code, edit environment variables, or change Steam launch options between runs. The scripts select each controlled case and save the evidence automatically.

Important: this test intentionally attempts to reproduce a GPU timeout. The game, screen, or desktop may freeze or turn black, and a computer restart may be necessary. Save your work and read [Tester safety, privacy, and participation terms](TESTER-TERMS.md) before continuing.

## What you need

- The **prepared tester archive** and matching `.sha256` file supplied by the investigation coordinator. The coordinator must also send the expected SHA256 through the existing authenticated private conversation. A normal Git clone is not enough because it intentionally does not contain diagnostic DLL binaries.
- An x86-64 Arch-family installation such as CachyOS, using native Steam rather than Flatpak Steam.
- IL-2 Sturmovik: Korea installed in Steam (AppID `247970`).
- The NVIDIA proprietary driver and a working `nvidia-smi` command.
- The exact dated Proton Experimental Bleeding Edge build described below.
- Read access to the system kernel journal.
- Enough free disk space for one private Proton copy and at least 8 GiB of possible logs/shader dumps.
- About one hour for setup and four runs.

The known failing control used X11. A Wayland run is not an equivalent control; the checker stops on a non-X11 session. Ask the coordinator before changing login-session settings.

## Before setup

1. Save all work and close unrelated applications.
2. Take screenshots of these three current Steam settings so you can restore them later: **Proton Experimental → Properties → Betas**, **IL-2 Korea → Properties → General → Launch Options**, and **IL-2 Korea → Properties → Compatibility**.
3. Copy any existing IL-2 launch-option text into a private note, then make the **Launch Options** box empty.
4. In Steam, open **Library**, enable **Tools** in the library filter, find **Proton Experimental**, open **Properties → Betas**, and select its `bleeding-edge` beta.
5. Let Steam finish downloading it.
6. Fully exit Steam using **Steam → Exit**. Do not merely close its window.

Changing Proton Experimental's beta can also affect other games configured to use Proton Experimental. Do not launch those games during this test, and restore the previous beta selection afterward.

The checker requires this exact baseline:

```text
experimental-bleeding-edge-11.0-414018-20260814-p3b5456-w34e7d5-d3a4c6f-v238f15
```

Proton Bleeding Edge updates automatically. If Steam has already moved to another build, the checker will stop. Do not substitute a newer build and do not try to repair this yourself; send the checker output to the coordinator. Once installation succeeds, the diagnostic copy is isolated from later Steam updates.

## Step 1 — extract and verify the prepared archive

Put both supplied files in the same folder. Their names resemble:

```text
il2-korea-xid109-diagnostics-tester-<version>.tar.gz
il2-korea-xid109-diagnostics-tester-<version>.tar.gz.sha256
```

Open a terminal in that folder and run:

```bash
sha256sum il2-korea-xid109-diagnostics-tester-*.tar.gz
sha256sum -c il2-korea-xid109-diagnostics-tester-*.tar.gz.sha256
```

The result must say `OK`, and the printed digest must match the value the coordinator sent through the existing authenticated conversation. The `.sha256` file detects accidental corruption; receiving an archive and checksum together does not by itself prove who created them. If either check differs, stop and request a fresh archive.

Extract the `.tar.gz` with the file manager. Open the extracted folder, right-click an empty area, and choose **Open Terminal Here**. The folder contains `il2-diagnostic.sh`.

Do not move, rename, delete, edit, or update this extracted folder until testing is finished and the custom tool has been uninstalled. Steam's installed diagnostic launcher refers back to this exact location.

## Step 2 — one-command setup

With Steam fully closed, run:

```bash
./il2-diagnostic.sh setup
```

The assistant will:

1. show the tester notice;
2. ask you to type `I AGREE` if you choose to continue;
3. perform read-only computer, Steam, journal, Vulkan, disk, and binary checks;
4. create a private copy of the exact Proton installation; and
5. add `IL2 Xid109 Diagnostic` as a Steam compatibility tool.

It never installs packages or uses `sudo`. `[PASS]` lines are expected. A `[FAIL]` is a stop condition: copy the complete terminal output and send it to the coordinator. Do not improvise a replacement Proton or driver.

The copy can take several minutes. Official Steam-managed Proton files are not edited.

## Step 3 — select the tool once in Steam

After setup succeeds:

1. Start Steam again.
2. Open **Library**.
3. Right-click **IL-2 Sturmovik: Korea** and choose **Properties**.
4. Open **Compatibility**.
5. Enable **Force the use of a specific Steam Play compatibility tool**.
6. Select **IL2 Xid109 Diagnostic**.
7. Close the Properties window.

Never select this diagnostic compatibility tool for another game.

## Step 4 — run the four controlled cases

Before every run, save your work and close unrelated GPU-accelerated applications. Use the aircraft/hangar view that previously reproduced the problem. Once that hangar is fully rendered, leave it idle: do not enter a mission, change aircraft, open settings, change the camera, or alter DLSS, resolution, or graphics options. If the coordinator gave a more specific known-failing action, repeat that same action in every case.

Run this command before each game launch:

```bash
./il2-diagnostic.sh next
```

It selects the correct next case in this order:

1. `baseline` — ordinary failing workload with passive breadcrumbs
2. `single-queue` — disables asynchronous compute/transfer queue use
3. `no-descriptor-buffer` — disables only `VK_EXT_descriptor_buffer`
4. `sync` — uses synchronized breadcrumb markers

The assistant will not advance past an interrupted, warned, unattributed, or scientifically inconclusive capture. `REVIEW REQUIRED` means stop and send the `status` output to the coordinator.

For each selected case:

1. Launch IL-2 Korea normally from Steam.
2. Enter the same known-failing hangar scene.
3. Start timing when the hangar is fully rendered.
4. If the failure occurs, follow the freeze instructions below.
5. If no failure occurs, keep the hangar running for **10 full minutes**, then exit the game normally.
6. Write down the visible outcome (`freeze`, `jumping`, `black screen`, or `no visible failure`) and the approximate time after the hangar rendered. Send that short note with the archive.
7. Run `./il2-diagnostic.sh status` and then `./il2-diagnostic.sh next`.

A three-second launch, startup error, interrupted capture, or short no-hang run cannot be treated as evidence that a diagnostic setting prevented the Xid.

### If the game or screen freezes

If the desktop still responds:

1. Wait 60 seconds so VKD3D and journal output can flush.
2. Click **Stop** in Steam once.
3. Wait another 30 seconds for automatic finalization.
4. Run `./il2-diagnostic.sh status`.

If the entire desktop remains unusable for about two minutes:

1. Restart the computer using the safest method available to you.
2. Sign in again.
3. Do not launch the game yet.
4. Open a terminal in this same diagnostic folder.
5. Run:

```bash
./il2-diagnostic.sh recover
./il2-diagnostic.sh status
```

The live journal spool often preserves the Xid even when normal shutdown was impossible. A recovered capture is marked interrupted and never counts as a stable no-Xid result.

## Optional NVIDIA report

One NVIDIA report after a representative failure is normally sufficient, and only when the coordinator requests it:

```bash
./tools/collect-nvidia-report.sh
./tools/collect-nvidia-report.sh --run
```

The first command explains the action without doing it. The second displays the exact `sudo nvidia-bug-report.sh` command and asks for confirmation. The report can take several minutes; password characters are not displayed while typing.

An NVIDIA report is much broader and more privacy-sensitive than the normal run logs. It is excluded from the ordinary results archive and must be transferred separately and privately.

## Step 5 — analyze and create the private archive

After the assistant reports four conclusive cases, run the following. If the baseline itself stayed stable, stop first; use `finish` only when the coordinator asks you to package that stopped control run.

```bash
./il2-diagnostic.sh finish
```

The packer explains the private contents and asks you to type `CREATE PRIVATE ARCHIVE`. It creates a file such as:

```text
PRIVATE-il2-xid109-results-<timestamp>.tar.zst
```

or `.tar.gz`, plus a `.sha256` file. Nothing is uploaded. Send exactly that new archive and its matching checksum through the privately agreed channel. Do not post the archive, shader dumps, or NVIDIA report publicly.

See [Privacy and evidence handling](PRIVACY.md) for the exact data boundaries.

## Step 6 — restore Steam after testing

Wait until the coordinator confirms that the evidence was received. Then:

1. Close IL-2 and fully exit Steam.
2. Run:

```bash
./il2-diagnostic.sh uninstall
```

3. Start Steam.
4. Open **IL-2 Korea → Properties → Compatibility**.
5. Disable the forced compatibility-tool checkbox or restore the Proton selection you used before testing.
6. Restore the previous **IL-2 Korea → General → Launch Options** text from your screenshot/private note.
7. Restore the previous **Proton Experimental → Properties → Betas** selection. Let Steam finish any resulting update.

Uninstall is deliberately reversible: it moves the custom Proton copy out of Steam's active scan directory instead of deleting it. That retained copy still uses disk space. After the coordinator confirms the evidence was received and the copy is no longer needed, fully exit Steam and run:

```bash
./il2-diagnostic.sh trash-copy
```

The command lists only copies bearing this harness's identity marker and asks you to type `MOVE DISABLED COPY TO TRASH`. It never moves official Proton or captured results. The copy stays recoverable until you empty the desktop Trash.

After receipt is confirmed, uninstall is complete, and the disabled copy is in Trash, you may move the entire extracted tester folder to desktop Trash with your file manager. That includes the raw results, PRIVATE archives, and local terms-acceptance record. Keep the matching archive/checksum until the coordinator confirms they are usable; empty Trash only when you no longer need recovery.

## Troubleshooting

| What you see | What to do |
|---|---|
| Checksum does not say `OK` | Stop and request a fresh prepared archive. |
| `native Steam root was not found` | This release does not support Flatpak Steam. Contact the coordinator. |
| Proton version does not match | Do not use a newer build. Send the full output to the coordinator. |
| Kernel journal check fails | Do not run the game. On Arch, `wheel` or `systemd-journal` membership normally provides read access; ask the coordinator for help and sign out/in after any approved group change. |
| `vulkaninfo` is missing | Do not install/update packages blindly. Ask the coordinator; the usual Arch package is `vulkan-tools`. |
| Diagnostic tool is absent from Steam | Fully exit and restart Steam, then check Compatibility again. |
| Game closes immediately | Run `./il2-diagnostic.sh status`, preserve the folder, and send the output. Do not count it as a stable run. |
| Capture says `INCOMPLETE` | Run `./il2-diagnostic.sh recover`. |
| Capture says `INCONCLUSIVE` | Repeat the same case using `./il2-diagnostic.sh next`. |
| Capture says `REVIEW REQUIRED` | Stop. Send the complete `./il2-diagnostic.sh status` output to the coordinator. |
| Session check says Wayland or unknown | Stop. This controlled run requires X11; ask the coordinator before changing login-session settings. |
| Baseline reaches 10 minutes without Xid | Stop the matrix and contact the coordinator; the control did not reproduce. |
| Disk-space check fails | Free space without deleting this folder, official Proton, or unreceived evidence. |

## What the harness changes and collects

- Diagnostic collection and environment variables are gated to IL-2 Korea AppID `247970`. The copied tool still contains the diagnostic VKD3D DLL, so never select it for another game.
- It intercepts only real Proton `run`/`waitforexitandrun` actions, not helper queries.
- It uses `PROTON_LOG=1`, VKD3D breadcrumbs, per-run shader dumping, and a live kernel-journal spool.
- Every run receives a unique UTC `results/<timestamp>-<case>/` directory.
- It copies the actual installation manifest into every run, records exact build/install provenance, and never overwrites a prior run.
- It does not change the NVIDIA driver, IL-2 files, official Proton files, Wine NUMA behavior, terrain behavior, or shaders.
- It does not select the second GPU or use Great Battles as a control.
- It does not upload anything.

## Maintainer-only build and release instructions

The tester should not use this section.

The source investigation is in [docs/phase-0-report.md](docs/phase-0-report.md). The exact pins are:

- Proton build: `experimental-bleeding-edge-11.0-414018-20260814-p3b5456-w34e7d5-d3a4c6f-v238f15`
- Proton commit: `0dda688b3840c381dfb76f87b81c9e50c846d627`
- VKD3D-Proton commit: `238f157e1d64f90e0d90593557c092ab8af6e0a3`

Build and verify:

```bash
./build/build-vkd3d-diag.sh
python3 tools/verify-build.py \
  --manifest build-manifest.json \
  --artifact-root build/output/vkd3d-proton-diag
```

After committing a clean, audited harness revision, create the single tester archive:

```bash
./build/make-tester-bundle.sh
```

The packager includes the four verified DLLs, build manifest, internal checksums, LGPL notice, and complete patched corresponding VKD3D-Proton source with nested submodules. It does not include or redistribute Valve's official Proton installation. See [Third-party software notices](THIRD-PARTY-NOTICES.md).

Validation:

```bash
python3 -m unittest discover -s tests -v
python3 -m ruff check analyzer tools tests build/write-build-manifest.py
```

Relevant upstream guidance:

- [Valve Proton local compatibility tools](https://github.com/ValveSoftware/Proton#install-proton-locally)
- [ArchWiki Steam compatibility selection](https://wiki.archlinux.org/title/Steam#Force_Proton_usage)
- [ArchWiki system-journal access](https://wiki.archlinux.org/title/Systemd/Journal#Accessing_the_journal)

This diagnostic repository must remain independent of the earlier IL-2 Linux investigation. Do not publish or push it until explicitly authorized.
