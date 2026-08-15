# VKD3D-Proton target-source debug notes

These notes apply specifically to commit `238f157e1d64f90e0d90593557c092ab8af6e0a3`. VKD3D debugging variables are not a stable public API; re-verify them before changing the source pin.

## Breadcrumb compilation and activation

- `enable_trace=auto` follows Meson's debug/debugoptimized build type.
- `enable_trace=true` defines `VKD3D_ENABLE_BREADCRUMBS` independently of build type.
- A trace-capable build does not emit trace-level logs unless `VKD3D_DEBUG=trace` is selected.
- Runtime activation is `VKD3D_CONFIG=breadcrumbs`.
- NVIDIA requires `VK_NV_device_diagnostic_checkpoints`; AMD uses `VK_AMD_buffer_marker`.

## `breadcrumbs_sync`

The config parser explicitly maps `breadcrumbs_sync` to both breadcrumb and sync flags. At every signal, VKD3D ends the current render pass and emits an all-commands `VkMemoryBarrier2` from memory writes to memory reads. This is why it is a separate behavioral case rather than extra baseline logging.

## Queue behavior

`single_queue` prevents use of asynchronous compute and transfer queues. It does not mean the application submits only graphics commands; it changes how VKD3D maps work to Vulkan queues.

The upstream target iterates direct, compute, and copy queues after device loss but does not print which loop produced a checkpoint set. The repository patch adds only:

```text
Reporting NVIDIA checkpoints for direct|compute|copy queue N.
```

## Shader dumping and hashes

`VKD3D_SHADER_DUMP_PATH` writes `$hash.spv`, `$hash.dxil`, or `$hash.dxbc` where available. Breadcrumb `set_shader_hash` entries print a 64-bit VKD3D hash and Vulkan stage bits. The harness manifest indexes file size and SHA256 and content-deduplicates repeated dumps through an ignored content store.

A pipeline can set multiple shader hashes before a draw. A hash inside the region identifies relevant code; it does not identify which invocation stalled or whether the shader is defective.

## Logging levels

Breadcrumb analysis uses error-level output. `info` additionally confirms configuration, device, and extension choices without enabling function-call traces. The harness uses:

```text
VKD3D_DEBUG=info
VKD3D_SHADER_DEBUG=err
```

`VKD3D_LOG_FILE` opens the destination directly. Each run receives a unique path so no prior VKD3D log is overwritten.

## Device selection

`VKD3D_VULKAN_DEVICE` is parsed as an unsigned, zero-based device index. `VKD3D_FILTER_DEVICE_NAME` filters on a device-name substring. The controlled launcher unsets both to retain the known display-GPU baseline.

## Extension disablement

`VKD3D_DISABLE_EXTENSIONS` is parsed as a comma/semicolon-separated debug list. `VK_EXT_descriptor_buffer` is the exact extension token used in Case D.

## Optional device fault path

`VKD3D_CONFIG=fault` conditionally enables `VK_EXT_device_fault`, `VK_EXT_device_address_binding_report`, and debug utilities. On device loss VKD3D queries fault counts/details, logs address and vendor records, and can write a vendor binary. In this revision the output filename is fixed to `vkd3d-proton.fault.bin` in the current working directory. It is documented for a possible later phase but excluded from the default matrix.

## References

- [Pinned VKD3D-Proton source](https://github.com/HansKristian-Work/vkd3d-proton/tree/238f157e1d64f90e0d90593557c092ab8af6e0a3)
- [VKD3D-Proton README at the pin](https://github.com/HansKristian-Work/vkd3d-proton/blob/238f157e1d64f90e0d90593557c092ab8af6e0a3/README.md)
- [Breadcrumb implementation at the pin](https://github.com/HansKristian-Work/vkd3d-proton/blob/238f157e1d64f90e0d90593557c092ab8af6e0a3/libs/vkd3d/breadcrumbs.c)
- [Device/config implementation at the pin](https://github.com/HansKristian-Work/vkd3d-proton/blob/238f157e1d64f90e0d90593557c092ab8af6e0a3/libs/vkd3d/device.c)
