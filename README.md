# IL-2 Korea Xid 109 diagnostics

This is a standalone remote diagnostic harness for a reproducible NVIDIA Xid 109 (`CTX SWITCH TIMEOUT`) in IL-2 Sturmovik: Korea (Steam AppID 247970) under Proton and VKD3D-Proton. It is designed to turn approximately four controlled game launches into a command-region, checkpoint, shader, and kernel evidence bundle.

This phase does **not** fix or work around the bug. It does not modify IL-2, Steam's official Proton installation, Wine NUMA behavior, the terrain fix, shaders, or the NVIDIA driver. It does not use IL-2 Great Battles as a control.

The source and test design are pinned to the known failing build:

- Proton: `experimental-bleeding-edge-11.0-414018-20260814-p3b5456-w34e7d5-d3a4c6f-v238f15`
- Proton commit: `0dda688b3840c381dfb76f87b81c9e50c846d627`
- VKD3D-Proton: `238f157e1d64f90e0d90593557c092ab8af6e0a3`

See [Phase 0 source report](docs/phase-0-report.md) for the source-level verification.

## Safety model

- Installation creates `IL2 Xid109 Diagnostic` under the user's Steam `compatibilitytools.d` directory.
- The installer makes an isolated, reflink-aware copy of the exact installed Proton Experimental baseline.
- Only the custom copy's x64 `d3d12core.dll`, compatibility manifest, and Proton entry wrapper are changed.
- Official Steam-managed files are never edited in place.
- No command installs packages, edits global configuration, or invokes sudo implicitly.
- `uninstall` moves the custom tool outside Steam's scan directory instead of deleting it.
- Captured logs and build products are ignored by Git by default.

## Preparing the diagnostic build

The maintainer should preferably build the DLLs once and provide the repository plus the resulting `build/output/` and `build-manifest.json` to the tester. This keeps compilation out of the remote reproduction loop.

To build from the exact pin on Arch/CachyOS:

```bash
./build/build-vkd3d-diag.sh
```

The script never invokes sudo or a package manager. It checks for Git, Meson, Ninja, glslang, both MinGW compilers, and either Wine WIDL or both MinGW WIDL tools. The build uses `--buildtype=release -Denable_trace=true --strip`, applies one report-only queue-label patch, verifies all pinned submodules, and writes `build-manifest.json` with the toolchain and DLL hashes.

Do not replace the pin with current VKD3D-Proton master. If the exact source or exact installed Proton baseline cannot be obtained, stop and record the mismatch before testing.

## Remote tester workflow

Run the read-only checks first:

```bash
./tools/il2-diag.sh doctor
./tools/il2-diag.sh install
```

Restart Steam, open IL-2 Korea's Compatibility properties, and select `IL2 Xid109 Diagnostic` once. Keep the in-game workload and rendering settings the same between cases.

Run the cases in this order, launching Korea normally through Steam once after each selection:

```bash
./tools/il2-diag.sh select baseline
# Launch Korea and reproduce once.

./tools/il2-diag.sh select single-queue
# Launch Korea once.

./tools/il2-diag.sh select no-descriptor-buffer
# Launch Korea once.

./tools/il2-diag.sh select sync
# Launch Korea once.
```

The launcher automatically creates a never-reused directory such as `results/2026-08-15T143000Z-baseline/`. It captures the selected environment, system summary, Proton log, VKD3D log, bracketed kernel journal, parsed Xids, breadcrumb report, dumped shaders, shader manifest, metadata, and a run summary.

After the matrix:

```bash
./tools/il2-diag.sh analyze
./tools/il2-diag.sh pack
```

The archive can contain private hostnames, usernames, local paths, hardware identifiers, and game logs. Review it before sharing.

One NVIDIA report after a representative failure is normally enough:

```bash
./tools/collect-nvidia-report.sh
./tools/collect-nvidia-report.sh --run
```

The first command only explains the action. The second prints the exact `sudo nvidia-bug-report.sh` command and asks for confirmation immediately before invoking it.

To remove the active custom compatibility tool without deleting it:

```bash
./tools/il2-diag.sh uninstall
```

## Four controlled cases

| Order | Case | Controlled change | Purpose |
|---:|---|---|---|
| 1 | `baseline` | Breadcrumbs and shader dumping only | Capture the ordinary failing workload and crash region |
| 2 | `single-queue` | Add `single_queue` | Test whether async compute/transfer use is necessary for reproduction |
| 3 | `no-descriptor-buffer` | Disable only `VK_EXT_descriptor_buffer` | Test whether the descriptor-buffer path is necessary for reproduction |
| 4 | `sync` | Use `breadcrumbs_sync` | Improve marker precision and test timing/synchronization sensitivity |

The authoritative machine-readable matrix is [config/test-matrix.conf](config/test-matrix.conf). Behavioral changes are never combined.

## Evidence standard

Reports distinguish `OBSERVED`, `INFERRED`, and `PROVEN`. A shader in a crash region is not automatically defective. A stable synchronized run does not prove a synchronization bug. A stable single-queue run does not prove async compute caused the failure.

If at least two Xid 109/device-lost runs have the same normalized command/shader-region fingerprint, the analyzer creates `results/culprit-candidate/`. That bundle is labeled **CANDIDATE CRASH REGION**, never **ROOT CAUSE**.

See [diagnostic design](docs/diagnostic-design.md) and [interpretation guide](docs/interpretation-guide.md) before drawing conclusions.
