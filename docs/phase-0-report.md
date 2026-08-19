# Phase 0 source investigation

Investigation date: 2026-08-15 UTC.

## 1. Failing Proton build

The exact Git tag is:

`experimental-bleeding-edge-11.0-414018-20260814-p3b5456-w34e7d5-d3a4c6f-v238f15`

It points to Proton commit `0dda688b3840c381dfb76f87b81c9e50c846d627`, committed at 2026-08-14 12:36:01 UTC. The tag suffix encodes Proton `3b5456`, Wine `34e7d5`, DXVK `3a4c6f`, and VKD3D-Proton `238f15` provenance.

Source: [ValveSoftware/Proton commit](https://github.com/ValveSoftware/Proton/commit/0dda688b3840c381dfb76f87b81c9e50c846d627).

## 2. Exact VKD3D-Proton commit

The Proton tree pins `vkd3d-proton` to `238f157e1d64f90e0d90593557c092ab8af6e0a3`, described as `v3.0.1-276-g238f157e`.

Pinned nested submodules:

| Path | Commit |
|---|---|
| `khronos/SPIRV-Headers` | `f88a2d766840fc825af1fc065977953ba1fa4a91` |
| `khronos/Vulkan-Headers` | `0e9de566b7d4051c5cc1b762e242c46565956bdf` |
| `subprojects/dxil-spirv` | `cc75a0c98d34d7bcc03560527c799b52e48b4d1f` |

Source: [VKD3D-Proton commit](https://github.com/HansKristian-Work/vkd3d-proton/commit/238f157e1d64f90e0d90593557c092ab8af6e0a3).

## 3. Breadcrumb implementation

At the target commit, breadcrumbs are compile-time guarded by `VKD3D_ENABLE_BREADCRUMBS`. Meson defines this when trace support is enabled. `VKD3D_CONFIG=breadcrumbs` then activates the runtime path.

The trace records markers, shader hashes and stages, draw, indexed draw, dispatch, ExecuteIndirect variants, copy, tiled copy, resolve, queries, barriers, clears, discards, ray tracing, vertex/index/root state, resource cookies, and other newer command types. On device loss or queue timeout the reporter searches pending command-list contexts and emits a potential crash region between the latest bottom-of-pipe completion and furthest top-of-pipe progress.

Shader hashes are therefore present in breadcrumb reports when the relevant pipeline state was recorded. With `VKD3D_SHADER_DUMP_PATH`, the same hash names the dumped `.dxil`, `.dxbc`, and `.spv` files where those representations are available.

## 4. Required build flags

`meson_options.txt` defines `enable_trace` as `auto`, `true`, or `false`. `auto` is enabled for `debug` and `debugoptimized` builds but disabled for a normal release build. Proton's own `UNSTRIPPED_BUILD` path explicitly adds `-Denable_trace=true` to VKD3D-Proton. Descriptor QA is independently disabled by default and must be compiled with `-Denable_descriptor_qa=true`.

The diagnostic build uses:

```text
--buildtype=release
--strip
-Denable_trace=true
-Denable_descriptor_qa=true
```

This avoids unrelated debug-build differences while retaining trace and breadcrumbs.

## 5. NVIDIA checkpoint path

The NVIDIA implementation is `VK_NV_device_diagnostic_checkpoints`:

- `vkCmdSetCheckpointNV` records encoded command-list context and marker values.
- `vkGetQueueCheckpointDataNV` retrieves progress after a loss/timeout.
- Direct, compute, and copy queue families are queried.
- Top-of-pipe and bottom-of-pipe marker progress delimit the potential region.

The target source does not integrate NVIDIA Aftermath or another proprietary crash-dump SDK. The diagnostic patch only adds the missing queue class/index label before a nonempty NVIDIA checkpoint report; it does not alter checkpoints or submission.

## 6. Verified diagnostic configuration

| Mechanism | Exact target behavior |
|---|---|
| `VKD3D_CONFIG=breadcrumbs` | Enables breadcrumb command instrumentation |
| `breadcrumbs_sync` | Implies breadcrumbs; ends the current render pass and inserts an all-commands write-to-read memory barrier at every signal |
| `single_queue` | Avoids asynchronous compute and transfer queues |
| `descriptor_qa_checks` | Enables GPU-assisted descriptor access instrumentation when descriptor QA was compiled in |
| `descriptor_heap` | Opts into the `VK_EXT_descriptor_heap` path when supported |
| `vk_debug` | Enables Vulkan debug extensions and loads the validation layer |
| `fault` | Opts into `VK_EXT_device_fault` and address-binding reporting when supported |
| `VKD3D_DEBUG` | `none`, `err`, `info`, `fixme`, `warn`, or `trace` |
| `VKD3D_SHADER_DEBUG` | Same levels for shader compiler messages |
| `VKD3D_LOG_FILE` | Redirects VKD3D debug output to the named file |
| `VKD3D_SHADER_DUMP_PATH` | Dumps `$hash.{spv,dxbc,dxil}` |
| `VKD3D_DESCRIPTOR_QA_LOG` | Writes descriptor heap/update records and descriptor-QA fault fields to the named file |
| `VKD3D_VULKAN_DEVICE` | Zero-based physical-device index |
| `VKD3D_FILTER_DEVICE_NAME` | Skips devices whose name lacks the substring |
| `VKD3D_DISABLE_EXTENSIONS` | Comma/semicolon-separated exact Vulkan extension names |

The harness uses `VKD3D_DEBUG=info`, not `trace`: breadcrumb crash reports are error-level, while info retains configuration/device confirmation without per-call trace volume. `VKD3D_SHADER_DEBUG=err` retains shader failures; dumping does not require shader trace logging.

`vk_debug` is not in the default matrix because validation changes locking, memory, and timing and is not required for checkpoint reporting.

## 7. Descriptor-buffer disable mechanism

The exact supported mechanism is:

```text
VKD3D_DISABLE_EXTENSIONS=VK_EXT_descriptor_buffer
```

The source matches the provided name against enumerated extensions and omits matching extensions. There is no target-revision `VKD3D_CONFIG` shorthand for this test.

## 8. `breadcrumbs_sync`

It exists in the target parser even though it is not listed in the main environment-variable table. It sets both `BREADCRUMBS` and `BREADCRUMBS_SYNC`.

Its semantics are stronger than passive logging: each breadcrumb signal ends the current render pass and emits a `VkMemoryBarrier2` with all-commands source/destination stages, memory-write source access, and memory-read destination access. It is isolated to the final `sync` case.

## 9. Expected failure output

A useful NVIDIA failure should contain:

```text
Device lost observed, analyzing breadcrumbs ...
Reporting NVIDIA checkpoints for direct|compute|copy queue N.
Found pending command list context [...] in executable state,
TOP_OF_PIPE marker N, BOTTOM_OF_PIPE marker M.
===== Potential crash region BEGIN =====
Command: ...
hash: 0123456789abcdef, stage: ...
===== Potential crash region END =====
Done analyzing breadcrumbs ...
```

The source also supports opt-in `VKD3D_CONFIG=fault`. When the driver exposes `VK_EXT_device_fault`, it can log fault addresses/vendor records and write a vendor blob. It is intentionally excluded from the six default cases: the target code hard-codes `vkd3d-proton.fault.bin` in the game's working directory, and enabling driver fault/address instrumentation is less behavior-neutral than the selected baseline.

## 10. Proton packaging

The installer validates the exact installed Proton tag and its VKD3D version file, then copies `Proton - Experimental` to a distinct custom compatibility-tool directory. It replaces only:

- x64 `files/lib/wine/vkd3d-proton/x86_64-windows/d3d12core.dll`
- the copied tool's `compatibilitytool.vdf`
- the copied tool's `proton` entry point with a collector wrapper, preserving the original as `proton.real`

All original Wine, DXVK, DXVK-NVAPI, Proton, runtime, and prefix behavior remains from the known failing build. Installation provenance records both original and diagnostic DLL hashes.
