# IL-2 Korea NVIDIA Xid 109 diagnostic

## Start here — invited testers

This tool collects evidence from a known NVIDIA GPU hang in **IL-2 Sturmovik: Korea**. It is an experimental evidence collector, not a fix or workaround.

> **Do not use GitHub's Download ZIP button or a normal Git clone for testing.** The public repository contains inspectable source code, but deliberately omits the diagnostic DLL binaries. Use only the prepared tester `.tar.gz` archive and matching `.sha256` file sent to you privately by the investigation coordinator.

This test intentionally tries to reproduce a GPU timeout. The game, screen, or entire desktop may freeze or turn black, and restarting the computer may become necessary. Save your work and read the [tester safety, privacy, and participation terms](TESTER-TERMS.md) before continuing.

Nothing starts merely because you download or extract the archive. You remain in control of every game launch. The diagnostic tool does not upload evidence automatically.

## Can I do this?

This guide is for a tester who has never used Linux diagnostic tools. You should be able to complete it if you can:

- download and extract an archive;
- open a terminal in a folder and paste one command at a time;
- find a game's **Properties** in Steam; and
- restart your computer if its desktop becomes unusable.

You do not need to understand the diagnostic output or program, compile anything, or edit environment variables. The tool never installs packages. If a required program is missing, stop and let the coordinator decide what to do; do not install or update packages on your own.

Normal diagnostic commands do not use `sudo`. The optional NVIDIA report is the only documented step that can use it, and you should run that step only when the coordinator asks.

Keep the coordinator's private chat available throughout the test. If the affected computer is your only way to communicate, keep another device available before starting.

## Terminal basics and stop rules

1. Open a terminal **inside the extracted diagnostic folder**. The folder must contain `il2-diagnostic.sh`.
2. Copy only the command inside each code block, paste it into the terminal, and press **Enter**. Run one command at a time.
3. In most Linux terminals, **Ctrl+Shift+V** pastes and **Ctrl+Shift+C** copies selected output. Plain **Ctrl+C stops a running command**, so do not use it as Copy.
4. Wait until the command finishes and the normal prompt returns. Some copying and analysis steps can be quiet for several minutes; do not close the terminal while they are working.
5. When asked for words such as `I AGREE` or `CREATE PRIVATE ARCHIVE`, type them exactly as shown and press **Enter**. Any other answer safely cancels that action.
6. Leave the extracted folder in the same location until testing and uninstall are complete.

Unless the troubleshooting table gives an exact safe action for the message, stop and contact the coordinator if:

- you see `[FAIL]`, a line beginning with `error:`, `STOP`, or `REVIEW REQUIRED`;
- the final success message described in the current step does not appear;
- the instructions or Steam screen differ from this guide; or
- you are unsure what to click or what happened.

`[WARN]` means the tool noticed something important, but it is not always a blocker. Read the final lines. If the command still reports success, keep the warning with your notes; if you are unsure, send the complete output to the coordinator.

Do not manually choose, skip, or repeat a diagnostic case. The `next` command makes that decision. Do not change any other Steam, game, graphics, driver, or login-session setting unless this guide or the coordinator explicitly tells you to.

You can run `./il2-diagnostic.sh` without another word to display a numbered menu. This guide uses named commands so each action is explicit.

## What will happen

| Stage | What you do | What happens automatically | What to expect |
|---|---|---|---|
| Receive | Verify and extract the two files supplied privately by the coordinator. | Nothing runs. | A Git clone or GitHub source ZIP is not a tester package. |
| Prepare | Save three Steam settings, select the required Proton build, and fully exit Steam. | Nothing runs. | Your Proton Experimental beta selection changes temporarily. |
| Set up once | Run `setup`, read the notice, and type `I AGREE` only if you choose to participate. | Checks prerequisites, copies Proton, verifies the diagnostic files, and registers one local Steam compatibility tool. | Many `[PASS]` lines, followed by several minutes of copying that may be quiet. Official Steam-managed Proton files are not edited. |
| Configure Steam once | Select **IL2 Xid109 Diagnostic** for IL-2 Korea only. | Waits until you launch the game. | Never select this tool for another game. |
| Run cases | Run `next`, launch IL-2, enter the agreed hangar scene, run `ready`, and keep the scene unchanged for ten full minutes or until it fails. | Selects the proper case, authorizes one game launch, records READY timing, and captures Proton, VKD3D, shader, system, and kernel evidence. | Usually up to four conclusive cases; an invalid capture may require an automatically selected repeat. |
| Recover if needed | Use Steam Stop for a frozen game when the desktop responds, or restart if the whole desktop remains unusable. | Preserves and finalizes as much evidence as possible. | After a restart, run `recover` before launching the game again. |
| Finish | Run `finish` only when the tool or coordinator directs you, then privately send the two new files and paste your visible-outcome notes as chat text. | Analyzes runs and creates one `PRIVATE-...` archive plus its `.sha256` checksum. | The files and notes remain on your computer until you send them. |
| Restore | Run `uninstall`, restore the three saved Steam settings, and later run `trash-copy`. | Disables the private Proton copy and can move recognized disabled copies to desktop Trash. | Nothing is permanently deleted automatically. |

Plan for about **60–90 minutes** when all four captures work the first time. A stable baseline can stop the matrix after one run. Freezes, restarts, reviews, or repeated inconclusive captures can make the test take longer and require more than four game launches.

You need free space for a complete private Proton copy **plus at least 8 GiB for evidence**. Eight GiB is a minimum reserve, not a maximum: per-run shader dumping has no fixed size cap and can consume more space.

## What the tool cannot know or do for you

The tool cannot:

- automatically tell when the hangar has finished rendering;
- verify that you used the agreed aircraft, hangar, camera, and graphics settings;
- see what appeared on your screen or write your visible-outcome note;
- decide the safest physical restart method for your computer;
- encrypt the results archive, choose a trustworthy recipient, or send any file; or
- prove that a setting fixed the problem from a short or incorrectly performed run.

The tool records two separate durations. Proton runtime starts before the hangar is ready. The controlled observation starts only when you run `ready`. The tool cannot verify what is on the screen, so you must run `ready` honestly and only after the agreed hangar is fully rendered with the correct settings. A clean no-failure result requires at least 600 recorded seconds after READY plus all other capture checks.

## What you need

- The prepared tester archive and matching `.sha256` file supplied by the coordinator.
- The expected SHA256 digest sent separately through the same established private conversation.
- The exact known-failing workload: aircraft, hangar, camera, graphics settings, and any action supplied by the coordinator or already known to reproduce the issue.
- An x86-64 Arch-family installation such as CachyOS, using native Steam rather than Flatpak Steam.
- IL-2 Sturmovik: Korea installed in Steam (AppID `247970`).
- The NVIDIA proprietary driver and a working `nvidia-smi` command.
- The exact dated Proton Experimental Bleeding Edge build shown below.
- Read access to the system kernel journal.
- Free space for one complete Proton copy and at least 8 GiB of evidence, with additional space available if shader dumps grow.
- About 60–90 minutes, possibly longer for restarts or repeated captures.
- A private way to contact the coordinator, preferably on a second device.

The known failing control used X11. A Wayland run is not an equivalent control, and the checker stops on a non-X11 session. Ask the coordinator before changing login-session settings.

## Step 1 — verify and extract the prepared archive

Do this **before changing anything in Steam**.

Create or use a folder containing only the current pair of files. Their names resemble:

```text
il2-korea-xid109-diagnostics-tester-<version>.tar.gz
il2-korea-xid109-diagnostics-tester-<version>.tar.gz.sha256
```

Open a terminal in that folder and run one command at a time:

```bash
sha256sum il2-korea-xid109-diagnostics-tester-*.tar.gz
```

The first command prints a 64-character digest. It must exactly match the digest the coordinator sent separately through the established private conversation.

```bash
sha256sum -c il2-korea-xid109-diagnostics-tester-*.tar.gz.sha256
```

The second command must end with `OK`. The `.sha256` file detects accidental corruption; receiving an archive and its checksum together does not by itself prove who created them. If the digest differs or the result does not say `OK`, stop and request a fresh pair.

Extract the `.tar.gz` with the file manager. Open the newly extracted folder, right-click an empty area, and choose **Open Terminal Here**. On file managers that do not show that entry, an equivalent **Open in Terminal** action or the terminal panel opened with **F4** is also suitable.

Confirm that the folder contains `il2-diagnostic.sh`. Do not move, rename, delete, edit, or update this extracted folder until testing is finished and the custom tool has been uninstalled. Steam's installed diagnostic launcher refers back to this exact location.

## Step 2 — record and prepare Steam

1. Save all work and close unrelated applications.
2. Make sure you know the exact hangar scene and settings you will repeat. If you do not, stop and ask the coordinator now.
3. Take screenshots of these current settings so you can restore them later:
   - **Proton Experimental → Properties → Betas**
   - **IL-2 Korea → Properties → General → Launch Options**
   - **IL-2 Korea → Properties → Compatibility**
4. Copy any existing IL-2 Launch Options text into a private note outside the diagnostic folder, then make the **Launch Options** box empty.
5. In Steam, open **Library**, enable **Tools** in the library filter, find **Proton Experimental**, open **Properties → Betas**, and select its `bleeding-edge` beta.
6. Let Steam finish downloading it.
7. Fully exit Steam using **Steam → Exit**. Do not merely close its window.

Changing Proton Experimental's beta can also affect other games configured to use Proton Experimental. Do not launch those games during this test, and restore the previous beta selection afterward.

The checker requires this exact baseline:

```text
experimental-bleeding-edge-11.0-414018-20260814-p3b5456-w34e7d5-d3a4c6f-v238f15
```

Proton Bleeding Edge updates automatically. If Steam has already moved to another build, the checker stops. Do not substitute a newer build or try to repair this yourself; send the complete checker output to the coordinator. Once installation succeeds, the private diagnostic copy is isolated from later Steam updates.

## Step 3 — run one-command setup

With Steam fully closed and the terminal in the extracted diagnostic folder, run:

```bash
./il2-diagnostic.sh setup
```

The tool will:

1. display the versioned tester notice;
2. ask you to type `I AGREE` if you choose to continue;
3. perform computer, Steam, journal, Vulkan, disk, bundle, and binary checks;
4. create a private copy of the exact Proton installation; and
5. add `IL2 Xid109 Diagnostic` as a Steam compatibility tool.

It never installs packages or invokes `sudo`. `[PASS]` lines are expected. If a prerequisite is missing, do not install or update anything on your own; send the complete output to the coordinator.

The Proton copy can take several minutes and may show no progress while copying. Do not close the terminal. Setup succeeded only when the end of the output contains both an `Installed:` line and the heading:

```text
STEAM SETUP — do this once:
```

Official Steam-managed Proton files are not edited.

## Step 4 — select the tool once in Steam

Only after setup shows the success cues above:

1. Start Steam again.
2. Open **Library**.
3. Right-click **IL-2 Sturmovik: Korea** and choose **Properties**.
4. Open **Compatibility**.
5. Enable **Force the use of a specific Steam Play compatibility tool**.
6. Select **IL2 Xid109 Diagnostic**.
7. Close the Properties window.

Never select this diagnostic compatibility tool for another game. Keep the extracted diagnostic folder at the same path.

## Step 5 — perform the controlled cases

The four possible cases are:

1. `baseline` — ordinary failing workload with passive breadcrumbs
2. `single-queue` — disables asynchronous compute and transfer queue use
3. `no-descriptor-buffer` — disables only `VK_EXT_descriptor_buffer`
4. `sync` — uses synchronized breadcrumb markers

The names are for the analysis; you do not choose among them. The tool selects the next required case or repeats the same case when a previous capture was inconclusive.

For every game launch:

1. Save your work and close unrelated GPU-accelerated applications.
2. In the terminal, run:

   ```bash
   ./il2-diagnostic.sh next
   ```

3. **Launch the game only if the output contains `NEXT RUN:` followed by a case name.** That authorizes one diagnostic launch. After the game closes, always run `next` again before clicking Play. If it says `STOP`, `REVIEW REQUIRED`, or that all cases are complete, do not launch the game; follow that message.
4. Launch IL-2 Korea normally from Steam.
5. Enter the same known-failing aircraft and hangar scene with the same camera and graphics settings. Do not enter a mission, change aircraft, open settings, change the camera, or alter DLSS, resolution, or other graphics options.
6. When the agreed hangar is fully rendered, leave the game running, switch back to the terminal in this folder, and run:

   ```bash
   ./il2-diagnostic.sh ready
   ```

7. The READY marker succeeded only if the output begins with a line like:

   ```text
   Ready: the 10-minute hangar observation started at 2026-08-16T12:34:56Z.
   Return to the unchanged hangar now. Exit normally only after 10 full minutes without a failure.
   ```

   The timestamp will differ. The command exits immediately, so the terminal does not need to remain open. Return to the unchanged hangar immediately. Running `ready` again during the same live run is safe, but it reports the original time and does not restart the timer.
8. If the failure occurs before or after READY, follow the freeze instructions below. Do not try to run `ready` after the game has failed or after a restart.
9. If no failure occurs, keep the fully rendered hangar in the agreed state for **10 full minutes after READY**, then use IL-2's normal **Quit/Exit** action. Do not use Steam Stop for a non-frozen run. The tool measures the READY interval; using your own visible timer as a reminder can help you avoid exiting early.
10. Immediately record what you saw and the approximate time after the hangar rendered in a private note outside the diagnostic folder. For example:

   ```text
   baseline — black screen — about 3m 20s after the hangar rendered
   single-queue — no visible failure during 10 full minutes
   ```

   Keep these notes for the Finish step. If status requires review, paste the current run's note into your private message to the coordinator together with the complete status output.

11. Run:

    ```bash
    ./il2-diagnostic.sh status
    ```

If status says `INCOMPLETE`, run `recover` before doing anything else. If it says `REVIEW REQUIRED` or `STOP`, stop and send the complete status output to the coordinator. Otherwise, return to the start of this list and use `next`; the tool will select the next case, automatically repeat an inconclusive case, or report that the matrix is complete. Never select or repeat a case manually.

A short launch, startup error, missing READY marker, recovered no-Xid capture, warned capture, or READY observation shorter than 10 full minutes cannot show that a diagnostic setting prevented the Xid—even if total Proton runtime exceeds 10 minutes. READY records your declaration; it cannot verify that you used the correct fully rendered scene and settings.

### If the game or screen freezes

If the desktop still responds and you can reach Steam:

1. Wait 60 seconds so VKD3D and journal output can flush.
2. Click **Stop** in Steam once.
3. Wait another 30 seconds for automatic finalization.
4. Run `./il2-diagnostic.sh status`.

If the entire desktop remains unusable for about two minutes and you cannot reach Steam:

1. Restart the computer using the safe method you already know for that computer.
2. Sign in again.
3. **Do not launch the game yet.**
4. Open a terminal in the same extracted diagnostic folder.
5. Run one command at a time:

   ```bash
   ./il2-diagnostic.sh recover
   ```

   ```bash
   ./il2-diagnostic.sh status
   ```

The live journal spool often preserves the Xid even when a normal shutdown was impossible. A READY marker recorded before the freeze is preserved, but a recovered capture is marked interrupted. It never counts as a stable no-Xid result and may require review or an automatically selected repeat. Do not run `ready` after reboot; use `recover`.

## Optional NVIDIA report

One NVIDIA report after a representative failure is normally sufficient. Run this only when the coordinator requests it:

```bash
./tools/collect-nvidia-report.sh
```

That first command only explains the operation. If the coordinator confirms that the report is needed, run:

```bash
./tools/collect-nvidia-report.sh --run
```

The second command displays the exact `sudo nvidia-bug-report.sh` command and asks for confirmation immediately before invoking it. The report can take several minutes; password characters are not displayed while typing.

An NVIDIA report is broader and more privacy-sensitive than normal run logs. It is always excluded from the ordinary results archive and must be transferred separately and privately.

## Step 6 — analyze and create the results archive

Run `finish` after `next` reports that all four controlled cases are conclusive. If the baseline stayed stable, stop the matrix and use `finish` only when the coordinator asks you to package that stopped control run.

```bash
./il2-diagnostic.sh finish
```

The packer explains the contents and asks you to type `CREATE PRIVATE ARCHIVE`. It creates an archive such as:

```text
PRIVATE-il2-xid109-results-<timestamp>.tar.zst
```

or a `.tar.gz`, plus a matching `.sha256` file.

The `PRIVATE-` name is only a warning label. **The archive is not encrypted or password-protected**, and the checksum does not hide its contents. Anyone who receives the archive can read its evidence.

Nothing is uploaded automatically. Through the private channel agreed with the coordinator:

- send exactly the new archive and its matching `.sha256` file; and
- paste the visible-outcome note for every run as ordinary chat text.

The notes are not collected automatically and are not inside the archive. Do not add other files, and do not post the archive, raw logs, shader dumps, notes, or NVIDIA report publicly. See [Privacy and evidence handling](PRIVACY.md) for the exact data boundaries.

## Step 7 — restore Steam and remove local data

If you sent evidence, wait until the coordinator confirms that it was received and usable. If you withdraw without sending evidence, you may clean up immediately.

1. Close IL-2 and fully exit Steam.
2. Run:

   ```bash
   ./il2-diagnostic.sh uninstall
   ```

3. Start Steam.
4. Open **IL-2 Korea → Properties → Compatibility**.
5. Disable the forced compatibility-tool checkbox or restore the Proton selection from your screenshot.
6. Restore the previous **IL-2 Korea → General → Launch Options** text.
7. Restore the previous **Proton Experimental → Properties → Betas** selection and let Steam finish any resulting update.

Uninstall is deliberately reversible: it moves the custom Proton copy out of Steam's active scan directory instead of deleting it. The disabled copy still uses disk space. After receipt is confirmed—or immediately if you withdrew without sending evidence—fully exit Steam and run:

```bash
./il2-diagnostic.sh trash-copy
```

The command lists only disabled copies bearing this harness's identity marker and asks you to type `MOVE DISABLED COPY TO TRASH`. It never moves official Proton or captured results. A moved copy remains recoverable until you empty desktop Trash.

After uninstalling, restoring Steam, and moving the disabled copy to Trash, you may move the entire extracted tester folder to Trash with the file manager. That folder includes raw results, result archives, checksums, and the local terms-acceptance record. If you submitted evidence, keep the archive and checksum until the coordinator confirms they are usable. If you already sent evidence and then withdraw, also request recipient-side deletion through the same private channel.

## Troubleshooting

| What you see | What to do |
|---|---|
| Checksum digest differs or check does not say `OK` | Stop and request a fresh prepared archive and checksum. |
| Setup never shows both `Installed:` and `STEAM SETUP — do this once:` | Stop and send the complete terminal output. |
| Any `[FAIL]` or `error:` line | Stop. Do not launch the game; send the complete output. |
| A `[WARN]` line | Read the command's final result. Preserve the warning and ask the coordinator if uncertain. |
| `native Steam root was not found` | This release does not support Flatpak Steam. Contact the coordinator. |
| Proton version does not match | Do not use a newer build. Send the complete output to the coordinator. |
| Kernel journal check fails | Do not run the game. Ask the coordinator for help; do not use `sudo` during a run. |
| `vulkaninfo` is missing | Do not install or update packages on your own. Ask the coordinator. |
| Diagnostic tool is absent from Steam | Fully exit and restart Steam, then check Compatibility again. If still absent, stop. |
| `next` does not show `NEXT RUN:` | Do not launch the game. Follow its `STOP`, review, completion, or error message. |
| Clicking Play says the launch was not authorized | Return to this folder and run `next`. Launch only if it shows `NEXT RUN:`. |
| `ready` says no active run was found | Make sure `next` selected a case and IL-2 is currently running. Never create a READY marker before the agreed hangar renders. |
| `ready` says the game process is not ready | Wait a moment and try `ready` again while IL-2 remains in the fully rendered hangar. |
| `ready` says it was already recorded | Continue from the original READY time; the timer was deliberately not restarted. |
| `ready` says more than one unfinished capture exists | Close the game, run `recover`, then review `status`. Do not mark READY or launch again. |
| `ready` says the game is no longer running | READY did not start a timer. Run `status` before doing anything else. |
| The game failed before you could run `ready` | Preserve or recover the capture normally. It cannot count as a stable ten-minute no-Xid run. |
| Status shows no captured run after you played | Stop and send the status output; the diagnostic compatibility tool may not have been selected. |
| Game closes immediately | Run `status`, preserve the folder, and send the output. Do not count it as a stable run. |
| Capture says `INCOMPLETE` | Run `./il2-diagnostic.sh recover`, then `status`. |
| Capture says `INCONCLUSIVE` without a stop condition | Run `next`; it automatically selects the same case again. |
| Capture says `REVIEW REQUIRED` | Stop and send the complete `status` output. |
| Session check says Wayland or unknown | Stop. Ask the coordinator before changing login-session settings. |
| Baseline completes the protocol without Xid | Stop the matrix and contact the coordinator; the control did not reproduce. |
| Disk-space check fails or free space is falling quickly | Stop. Eight GiB is only a minimum reserve, not a cap. Do not delete this folder, official Proton, or evidence awaiting receipt. |
| `trash-copy` says desktop Trash support is unavailable | Nothing was moved. Ask the coordinator to help remove the listed disabled folder with the file manager. |

## What the harness changes and collects

- Diagnostic collection and environment variables are gated to IL-2 Korea AppID `247970`. The copied tool still contains the diagnostic VKD3D DLL, so never select it for another game.
- It intercepts only real Proton `run` and `waitforexitandrun` actions, not helper queries.
- It uses `PROTON_LOG=1`, VKD3D breadcrumbs, per-run shader dumping, and a live kernel-journal spool.
- Every run receives a unique UTC `results/<timestamp>-<case>/` directory.
- It records system, GPU, driver, Vulkan, session, Proton, VKD3D, command, kernel, timing, and build/install provenance information.
- It never overwrites a prior captured run.
- It does not modify the NVIDIA driver, IL-2 files, official Proton files, Wine NUMA behavior, terrain behavior, or game shaders.
- It does not select the second GPU or use Great Battles as a control.
- The collector has no upload or telemetry code. It does not block Steam or IL-2 from using their normal network connections.

## Maintainer-only build and release instructions

Invited testers should not use this section.

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

After committing a clean, audited harness revision, create the tester archive:

```bash
./build/make-tester-bundle.sh
```

The packager includes four verified DLLs, the build manifest, internal checksums, LGPL notice, and complete patched corresponding VKD3D-Proton source with nested submodules. It does not include or redistribute Valve's official Proton installation. See [Third-party software notices](THIRD-PARTY-NOTICES.md).

Validation:

```bash
python3 -m unittest discover -s tests -v
python3 -m ruff check .
```

Relevant upstream guidance:

- [Valve Proton local compatibility tools](https://github.com/ValveSoftware/Proton#install-proton-locally)
- [ArchWiki Steam compatibility selection](https://wiki.archlinux.org/title/Steam#Force_Proton_usage)
- [ArchWiki system-journal access](https://wiki.archlinux.org/title/Systemd/Journal#Accessing_the_journal)

The source repository may be public for inspection. Prepared tester bundles should be distributed deliberately to invited testers, and captured evidence, result archives, shader dumps, checksums, and NVIDIA reports remain private unless the tester separately authorizes disclosure.
