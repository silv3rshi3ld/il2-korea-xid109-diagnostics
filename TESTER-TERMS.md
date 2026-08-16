# Tester safety, privacy, and participation terms

Notice version: `2026-08-16.2`

Read this document before installing or running the prepared diagnostic tool. It is a plain-language participation notice, not a substitute for legal advice.

## Purpose and risk

This project intentionally tries to reproduce a known NVIDIA GPU timeout in IL-2 Sturmovik: Korea. It collects evidence; it is not a fix or workaround.

During a run, the game can freeze, the screen can turn black, the desktop can stop responding, audio can continue briefly, and restarting the computer can become necessary. Unsaved work in other applications can be lost. A GPU or driver fault carries risks that software cannot eliminate.

Before every run:

1. Save all work and close unrelated applications, especially GPU-accelerated applications.
2. Do not perform important work on the computer during the test.
3. Make sure you know how to restart the computer if its desktop becomes unusable.
4. Keep another communication device available if the affected computer is your only contact method.
5. Check that adequate disk space remains. The tool requires at least 8 GiB of result-space headroom, but shader dumping has no fixed size cap and can consume more.

Participation is voluntary. You may stop before any run or withdraw at any time. Do not use this tool on a computer you do not own or have permission to diagnose.

## Use the prepared tester archive only

The public GitHub repository exists so its source can be inspected. A Git clone or GitHub Download ZIP intentionally lacks the diagnostic DLL binaries and is not a tester package.

Use only the prepared tester `.tar.gz` archive and matching `.sha256` supplied privately by the identified investigation coordinator. Verify its digest against the value sent separately through the established private conversation before changing Steam settings or running setup.

## What changes on the computer

The preparation steps temporarily change Proton Experimental's selected beta, IL-2 Korea's Launch Options, and IL-2 Korea's forced compatibility-tool selection. Record all three previous values and restore them afterward. Changing Proton Experimental can affect other games configured to use it, so do not launch those games during the test.

The setup script creates a private copy of the exact installed Proton Experimental compatibility tool. Inside that private copy, it replaces the x64 VKD3D-Proton `d3d12core.dll` with the diagnostic build and replaces the copied Proton entry point with a small wrapper; the original copied entry point is retained as `proton.real`. The wrapper activates evidence collection only for IL-2 Korea AppID `247970` during real Proton launch actions. The copied tool still contains the diagnostic DLL, so never select it for another game.

The tool does not edit Steam's official Proton installation in place, modify the NVIDIA driver, patch IL-2 files, or install system packages. Normal diagnostic commands do not invoke `sudo`. The optional NVIDIA report is separate, displays the exact privileged command, and asks immediately before invoking `sudo`.

Launching IL-2 through any Proton compatibility tool can create or update IL-2's existing per-game Wine prefix under Steam's `compatdata/247970` area. That prefix can contain local configuration. If it contains irreplaceable local-only data, stop and ask the coordinator how to preserve it before testing.

The custom tool refers to the extracted diagnostic folder by its exact path. Do not move, rename, edit, update, or delete that folder until the custom tool has been uninstalled.

## What remains manual

The tool selects cases and captures evidence, but it cannot see the game screen. It cannot automatically tell when the agreed hangar has fully rendered or confirm the chosen aircraft, hangar, camera, graphics settings, or visible symptom.

The tester must run `./il2-diagnostic.sh ready` exactly when the agreed hangar is fully rendered. That command creates the READY observation marker from which the tool measures the controlled ten-minute window. Proton runtime is recorded separately and starts earlier. A no-failure run counts as a clean negative only when at least 600 seconds were captured after READY and all other capture checks pass.

The READY command records what the tester declares; it cannot verify that the scene is actually ready or correct. Marking READY too early, using the wrong scene or settings, or leaving before ten full minutes makes the protocol scientifically invalid even if the files are otherwise complete. The tester must also provide a short note describing the visible outcome. That note is not collected automatically or placed in the archive; paste it as ordinary text in the agreed private chat when sending the archive and checksum, or whenever a run requires review.

The tool cannot choose a trustworthy recipient, encrypt a file, send evidence, or decide the safest physical restart method for the computer.

## Information collected

Normal run captures can contain:

- operating-system, kernel, session, GPU, driver, VBIOS, Vulkan, and PCI information;
- local paths that can include a username or hostname;
- Steam, Proton, VKD3D-Proton, Wine, and game command information;
- kernel messages from the run window, including NVIDIA Xid events and possibly unrelated device or network identifiers;
- D3D12 shader bytecode dumped from the game, such as DXIL, DXBC, or SPIR-V; and
- timestamps, READY observation timing, case settings, process exit state, and diagnostic build/install provenance.

The optional `nvidia-bug-report.sh` output is substantially broader and can include additional system configuration and logs. It is always excluded from the normal results archive and must be handled separately.

## Upload, encryption, and sharing

The collector has no upload code, telemetry endpoint, account integration, or automatic evidence submission. Nothing is uploaded automatically, and creating an archive does not transmit it. The harness does not disable Steam or IL-2's normal network behavior, so those applications can still use their usual connections.

The word `PRIVATE-` at the beginning of a result-archive filename is only a warning label. The archive is not encrypted or password-protected, and its `.sha256` checksum does not conceal its contents. Anyone who obtains the archive can read the evidence.

Treat result archives, shader files, and NVIDIA reports as private. Send them only through the agreed private channel to the person who supplied the prepared tester archive and identified themselves as the coordinator. If no identifiable coordinator and private return channel were provided, do not send the evidence.

Unless you separately agree otherwise, the recipient may use raw evidence only for this IL-2 Xid 109 investigation, must not publish it or send raw files or shaders to NVIDIA, Valve, VKD3D-Proton, IL-2 maintainers, or anyone else, and should use redacted technical summaries for upstream discussion. The recipient must delete their raw archive and any NVIDIA report within 90 days of receipt, or sooner if you request deletion through the same private channel, and confirm deletion. Evidence already shared with another party with your separate permission cannot necessarily be recalled.

## Local storage, cleanup, and withdrawal

Raw captures remain in the extracted project's `results/` directory. The `finish` command creates a separate unencrypted `PRIVATE-...` archive at the top of that folder. Reversible uninstall retains the disabled compatibility-tool copy outside Steam's active scan directory, where it continues to use disk space.

If you intend to submit evidence, keep the extracted folder and disabled copy until the coordinator confirms that the archive was received and usable. Then follow the README's `uninstall`, Steam restoration, `trash-copy`, and folder-removal steps.

If you withdraw before sending evidence, you do not need to wait for receipt confirmation. Fully exit the game and Steam, run `./il2-diagnostic.sh uninstall`, restore the three saved Steam settings, run `./il2-diagnostic.sh trash-copy`, and remove the extracted folder when you no longer want its evidence retained.

If you already transferred evidence and then withdraw, request recipient-side deletion through the same private channel. Moving local files to desktop Trash does not permanently erase them until Trash is emptied.

## Warranty and independence

This experimental diagnostic software is provided without warranty, as also stated in its applicable licenses. It is not affiliated with or endorsed by NVIDIA, Valve, Steam, 1C Game Studios, the developers or publishers of IL-2, Wine, or VKD3D-Proton.

The harness's MIT license does not replace third-party licenses. VKD3D-Proton and its dependencies retain their own license rights, including rights to inspect, modify, and redistribute code under those licenses. See [Third-party software notices](THIRD-PARTY-NOTICES.md).

## What acceptance means

Typing `I AGREE` during setup confirms only that you:

- are authorized to run the diagnostic on this computer;
- understand the freeze, black-screen, restart, disk-space, and unsaved-data risks;
- have read what changes and what is collected;
- understand that the result archive is unencrypted and no evidence is uploaded automatically; and
- voluntarily choose to continue.

Acceptance does not remove rights granted by the MIT, LGPL, Apache, or other third-party software licenses.
