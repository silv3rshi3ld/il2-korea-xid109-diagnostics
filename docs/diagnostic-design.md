# Diagnostic design

The design optimizes for maximum passive evidence per crash and six controlled Korea launches.

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
- UTC run boundaries, original boot ID, and journal cursor
- line-buffered live kernel-journal spool with hostname-field suppression
- unfiltered kernel journal within the run boundary
- filtered NVIDIA/Xid context
- system, driver, Vulkan, exact build, and selected-environment metadata

The harness never enables `VKD3D_DEBUG=trace` in the matrix. Trace support is compiled in because breadcrumbs require it; per-call trace output is unnecessary and can produce extreme overhead.

## Behavioral discriminators

The non-baseline cases isolate these diagnostic or behavioral changes:

1. `descriptor-qa`: adds `descriptor_qa_checks` and a unique `VKD3D_DESCRIPTOR_QA_LOG=<run>/descriptor-qa.log`; normal per-run shader dumping remains enabled.
2. `descriptor-heap`: adds `descriptor_heap` to select `VK_EXT_descriptor_heap` instead of the default descriptor-buffer path.
3. `single-queue`: adds `single_queue` to breadcrumbs.
4. `no-descriptor-buffer`: disables exactly `VK_EXT_descriptor_buffer` while retaining ordinary queue behavior.
5. `sync`: uses `breadcrumbs_sync`, which implies breadcrumbs and adds strong barriers.

The order places descriptor validation immediately after the failing default-path baseline, keeps the two alternate descriptor paths adjacent, and leaves the timing-heavy synchronization case last.

The descriptor-QA log records descriptor heap/update history and GPU-assisted fault blocks. The analyzer parses each complete block, including multiple fault flags, shader hash, instruction ID, descriptor heap and resource/view cookies, desired and found descriptor types, and failed heap index. It associates the shader hash with files retained in the run's shader manifest.

## Per-run lifecycle

The copied Proton entry point checks AppID 247970. Other AppIDs are handed directly to the copied `proton.real` with no diagnostic collection environment. Because the copied tree still contains the diagnostic VKD3D DLL, the compatibility tool must never be selected for another game.

For Korea, it locks against concurrent runs, allocates a unique UTC directory, snapshots actual installation/build provenance and system state, records a journal cursor and boot ID, and sets the chosen matrix environment. Before Proton starts, a line-buffered live kernel-journal follower must remain alive through a health check. The follower and managed Proton child do not inherit the run-lock descriptor; both arm Linux's parent-death signal so their direct managed processes receive `SIGTERM` if the launcher disappears. This is not a guarantee that every descendant created later by Proton cannot outlive it.

The launcher runs the unmodified copied `proton.real` as a managed child so TERM, INT, and HUP can be forwarded while Bash is waiting. When Proton returns, normal finalization stops the follower, snapshots the original boot after the cursor, merges the snapshot with the live spool, and produces parsed artifacts. A forced power cycle leaves `.capture-in-progress`; `recover` explicitly queries the saved original boot and incorporates the already-written live spool. A recovered or warned failure requires coordinator review. A recovered or warned no-Xid capture is inconclusive and is automatically repeated; neither kind can count as a conclusive case.

`kernel-full.log` is the unfiltered kernel journal from the original boot after the run cursor through finalization/recovery. `kernel-window.log` keeps NVRM, Xid, timeout, and IL2 process lines plus nearby context. Despite the name, the former is not the whole boot journal and does not collect unrelated userspace services. It can contain unrelated kernel events inside that bracket.

## Provenance

`build-manifest.json` records source/submodule commits, expected patch and diff hashes, dirty state, Meson arguments, reproducibility environment, compiler/linker/dependency versions, timestamps, sizes, and SHA256 values for every built DLL.

`install-manifest.json` records the exact installed Proton/VKD3D version strings and both the original and replacement x64 `d3d12core.dll` hashes. A copy is placed in every run so provenance survives uninstall and removal of the disabled compatibility-tool copy.

## Candidate generation threshold

The analyzer evaluates every parsed crash region from the newest capture of each controlled case. It fingerprints queue identity and ordered command/shader/argument/tag events while normalizing run-local resource-cookie values. It creates the candidate bundle only when at least two distinct controlled cases meet all of these conditions:

- complete, internally consistent capture metadata and markers
- READY recorded before the failure
- verified raw Proton, VKD3D, and kernel evidence with a consistent parsed Xid cache
- Xid 109 attributed to `IL2Series.exe`
- completed VKD3D device-loss breadcrumb analysis
- a nonempty command or shader region parsed
- no interruption, recovery, capture warning, other Xid, or malformed metadata
- identical normalized region fingerprints

This deliberately favors precision over aggressive matching. Similar but non-identical regions remain visible in the comparison report without generating a candidate bundle. Re-running analysis with an unchanged matching run set is idempotent and does not duplicate candidate evidence.
