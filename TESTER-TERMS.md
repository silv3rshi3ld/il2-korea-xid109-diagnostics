# Tester safety, privacy, and participation terms

Notice version: `2026-08-15.2`

Read this document before installing or running the diagnostic tool. It is a plain-language participation notice, not a substitute for legal advice.

## What this test does

This project intentionally tries to reproduce a known NVIDIA GPU timeout in IL-2 Sturmovik: Korea. It is an evidence collector, not a fix or workaround.

During a run, the game may freeze, the screen may turn black, the desktop may stop responding, audio may continue briefly, and restarting the computer may become necessary. Unsaved work in other applications may be lost. A GPU or driver fault can carry risks that software cannot eliminate.

Before every run:

1. Save all work and close unrelated applications, especially GPU-accelerated applications.
2. Do not perform important work on the computer during the test.
3. Make sure you know how to restart the computer if the desktop becomes unusable.
4. Keep another communication device available if the affected computer is your only contact method.

Participation is voluntary. You may stop before any run. Do not use this tool on a computer you do not own or have permission to diagnose.

## What the tool changes

The preparation steps temporarily change Proton Experimental's selected beta, IL-2 Korea's Launch Options, and IL-2 Korea's forced compatibility-tool selection. The tester must record the previous values and restore all three afterward. Changing Proton Experimental can affect other games configured to use it.

The script creates a private copy of the exact installed Proton Experimental compatibility tool and replaces one VKD3D-Proton DLL inside that copy. It does not edit Steam's official Proton installation in place, modify the NVIDIA driver, patch IL-2 files, or install system packages.

Launching IL-2 through any Proton compatibility tool can create or update IL-2's existing per-game Wine prefix under Steam's `compatdata/247970` area. That prefix may contain local configuration. If it contains irreplaceable local-only data, stop and ask the coordinator how to preserve it before testing.

The custom tool depends on this diagnostic folder remaining at the same path until testing is finished and the custom tool is uninstalled.

No normal diagnostic command uses `sudo`. The optional NVIDIA report command is separate, prints the exact privileged command, and asks immediately before invoking `sudo`.

## Information collected

Normal run captures can contain:

- operating-system, kernel, session, GPU, driver, VBIOS, Vulkan, and PCI information;
- local paths that may include a username;
- Steam, Proton, VKD3D-Proton, Wine, and game command information;
- kernel messages around the run, including NVIDIA Xid events;
- D3D12 shader bytecode dumped from the game (`DXIL`, `DXBC`, or `SPIR-V`);
- timestamps, case settings, process exit state, and diagnostic build provenance.

The optional `nvidia-bug-report.sh` output is much broader and can include additional system configuration and logs. It is excluded from the normal results archive unless handled separately.

Nothing is uploaded automatically. Creating an archive does not transmit it. Treat result archives, shader files, and NVIDIA reports as private. Send them only through the privately agreed channel to the person who directly supplied the tester archive and identified themselves as the investigation coordinator. If no identifiable coordinator and private return channel were provided, do not send the evidence.

Unless you separately agree otherwise, the recipient may use raw evidence only for this IL-2 Xid 109 investigation, must not publish it or send raw files/shaders to NVIDIA, Valve, VKD3D-Proton, IL-2 maintainers, or another party, and should use redacted technical summaries for upstream discussion. The recipient must delete their raw archive and any NVIDIA report within 90 days of receipt or sooner if you request deletion through the same private channel, then confirm deletion. Evidence already shared with a third party with your separate permission cannot necessarily be recalled from that third party.

## Storage, sharing, and withdrawal

Raw captures stay inside this project's `results/` directory. The `finish` command creates a separate `PRIVATE-...` archive at the top of the extracted project folder. The disabled compatibility-tool copy is retained outside Steam's active scan directory during reversible uninstall. Ask the investigation coordinator before deleting evidence that has not yet been received.

You may withdraw from testing at any time. Close the game and Steam, run the uninstall command, restore the previous Proton beta, IL-2 Launch Options, and IL-2 Compatibility settings, and then remove local results when you no longer want them retained. If you already transferred evidence, request recipient-side deletion through the same private channel.

## Warranty and independence

This experimental diagnostic software is provided without warranty, as also stated in the applicable software licenses. It is not affiliated with or endorsed by NVIDIA, Valve, Steam, 1C Game Studios, the developers or publishers of IL-2, Wine, or VKD3D-Proton.

The harness's MIT license does not replace third-party licenses. VKD3D-Proton and its dependencies retain their own license rights, including rights to inspect, modify, and redistribute code under those licenses. See `THIRD-PARTY-NOTICES.md`.

## What acceptance means

When the setup command asks you to type `I AGREE`, you confirm only that:

- you are authorized to run diagnostics on this computer;
- you understand the possible freeze, black-screen, reboot, and unsaved-data risks;
- you have read what is changed and collected;
- you understand that no data is uploaded automatically; and
- you choose to continue voluntarily.

Acceptance does not remove rights granted by the MIT, LGPL, Apache, or other third-party software licenses.
