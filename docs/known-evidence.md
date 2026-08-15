# Known evidence and investigation boundaries

## Affected configuration

- Tester: `@SunnyOd`
- CachyOS, X11
- Ryzen 9 9950X3D
- two NVIDIA RTX 3090 GPUs
- proprietary NVIDIA driver
- IL-2 Sturmovik: Korea, Steam AppID 247970
- D3D12 through VKD3D-Proton

The game launches and the hangar renders. Roughly 30 seconds to several minutes later, rendering freezes, jumps, or black-screens; audio can briefly continue. The kernel reports Xid 109 `CTX SWITCH TIMEOUT`, after which VKD3D observes `VK_ERROR_DEVICE_LOST` and present/swapchain/semaphore failures cascade.

Representative event:

```text
NVRM: Xid (PCI:0000:01:00): 109,
name=IL2Series.exe,
channel 0x00000028,
errorString CTX SWITCH TIMEOUT,
Info 0x1c022
```

Multiple reproductions have the same broad signature.

## Established exclusions

- The Xid predates the recent IL-2 terrain fix and reproduces on older ordinary Proton as well as the dated Proton 11 Bleeding Edge build. Do not begin with a VKD3D Git bisect.
- Wine NUMA/OpenMP startup was a separate issue and is solved in the newer Wine baseline.
- VKD3D-Proton PR #3202 fixes terrain corruption; the Xid persists with correct terrain.
- The older RADV typed texel-buffer lighting corruption is unrelated without new evidence.
- Thousands of split-barrier warnings are a workload characteristic also seen on AMD without Xid 109. They are not currently causal evidence.
- The first present or semaphore failure demonstrates where device loss was observed, not necessarily where execution wedged.
- Great Battles is a D3D11/DXVK title with a materially different engine and workload. It is a weak sanity datapoint only and is excluded from the matrix and automatic analysis.

## Negative tests not repeated by default

The Xid has already reproduced with NVIDIA 610.43.03 and 610.57.04, DLSS on and off, single and multiple monitors, a clean boot, the USB4 hub disconnected, ordinary Proton Experimental/Hotfix, and newer Bleeding Edge.

## GPU isolation

Confirmed Xids are on display GPU `0000:01:00`. The second RTX 3090 is headless. GPU1 selection is not part of this phase because presentation/offload complexity could create a second failure mode. The exact target source does support zero-based `VKD3D_VULKAN_DEVICE`, but the harness deliberately unsets device-selection overrides in the controlled matrix.
