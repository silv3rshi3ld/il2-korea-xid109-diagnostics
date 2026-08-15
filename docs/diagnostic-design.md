# Diagnostic design

The design optimizes for maximum passive evidence per crash and four orthogonal Korea launches.

```text
IL-2 D3D12 workload
        ↓
VKD3D command list and submission
        ↓
NV checkpoint top/bottom progress
        ↓
candidate draw / dispatch / copy / barrier region
        ↓
shader hashes + already-dumped DXIL/SPIR-V
        ↓
VK_ERROR_DEVICE_LOST + kernel Xid 109 correlation
```

## Passive instrumentation in every case

- `PROTON_LOG=1`
- `VKD3D_CONFIG=breadcrumbs` or a case-specific superset
- `VKD3D_DEBUG=info`
- `VKD3D_SHADER_DEBUG=err`
- `VKD3D_LOG_FILE=<run>/vkd3d.log`
- `VKD3D_SHADER_DUMP_PATH=<run>/shaders`
- UTC run boundaries and journal cursor
- unfiltered kernel journal within the run boundary
- filtered NVIDIA/Xid context
- system, driver, Vulkan, exact build, and selected-environment metadata

The harness never enables `VKD3D_DEBUG=trace` in the matrix. Trace support is compiled in because breadcrumbs require it; per-call trace output is unnecessary and can produce extreme overhead.

## Behavioral discriminators

Only one behavioral change is applied in each non-baseline case:

1. `single-queue`: adds `single_queue` to breadcrumbs.
2. `no-descriptor-buffer`: disables exactly `VK_EXT_descriptor_buffer` while retaining ordinary queue behavior.
3. `sync`: uses `breadcrumbs_sync`, which implies breadcrumbs and adds strong barriers.

The order places the high-value queue discriminator before the heavier synchronization case.

## Per-run lifecycle

The copied Proton entry point checks AppID 247970. Other AppIDs are handed directly to the original Proton entry point with no diagnostic environment.

For Korea, it locks against concurrent runs, allocates a unique UTC directory, snapshots provenance and system state, records a journal cursor, sets the chosen matrix environment, and invokes the unmodified copied `proton.real`. When Proton returns, it captures the journal after the cursor and produces parsed artifacts. An interrupted run retains `.capture-in-progress`; no later run overwrites it.

`kernel-full.log` is the unfiltered kernel journal inside the run bracket. `kernel-window.log` keeps NVRM, Xid, timeout, and IL2 process lines plus nearby context. Despite the name, the former is not the whole boot journal and does not collect unrelated userspace services.

## Provenance

`build-manifest.json` records source/submodule commits, expected patch and diff hashes, dirty state, Meson arguments, reproducibility environment, compiler/linker/dependency versions, timestamps, sizes, and SHA256 values for every built DLL.

`install-manifest.json` records the exact installed Proton/VKD3D version strings and both the original and replacement x64 `d3d12core.dll` hashes.

## Candidate generation threshold

The analyzer normalizes the ordered commands and shader hashes in the first parsed crash region and hashes that representation. It creates the candidate bundle only when at least two runs meet all of these conditions:

- Xid 109 observed
- device loss observed
- a nonempty command or shader region parsed
- identical normalized region fingerprints

This deliberately favors precision over aggressive matching. Similar but non-identical regions remain visible in the comparison report without generating a candidate bundle.
