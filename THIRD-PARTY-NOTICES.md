# Third-party software notices

The repository's top-level `LICENSE` applies to the diagnostic harness code and documentation written for this project. It does not relicense third-party software, IL-2, Steam, Proton, Wine, NVIDIA software, or captured game shaders.

## VKD3D-Proton diagnostic DLL

Prepared tester bundles contain a modified diagnostic build of VKD3D-Proton, not an unmodified upstream binary.

- Project: VKD3D-Proton
- Source: <https://github.com/HansKristian-Work/vkd3d-proton>
- Exact commit: `238f157e1d64f90e0d90593557c092ab8af6e0a3`
- Upstream license: GNU Lesser General Public License, version 2.1 or later
- Local modification: `build/patches/0001-label-nvidia-checkpoint-queues.patch`

The modification adds report-only direct/compute/copy queue labels to NVIDIA checkpoint output. It does not add checkpoints or change synchronization, queue selection, command recording, or submission.

Because that patch modifies LGPL-covered VKD3D-Proton source, the patch is offered under GNU LGPL version 2.1 or, at your option, any later version. The committed license and project notice are in `LICENSES/VKD3D-Proton-LGPL-2.1.txt` and `LICENSES/VKD3D-Proton-COPYING.txt`.

A prepared binary bundle must include:

- `LICENSES/VKD3D-Proton-LGPL-2.1.txt`;
- `LICENSES/VKD3D-Proton-COPYING.txt`;
- a machine-readable corresponding-source archive containing the exact patched source and nested submodules; and
- `build/source-lock.json`, the local patch, build script, and `build-manifest.json`.

The maintainer packaging command refuses to create a tester bundle unless these materials can be produced from the verified build source. This corresponding source is provided under the upstream licenses and is not subject to additional tester restrictions.

## Nested VKD3D-Proton dependencies

The corresponding-source archive contains the exact nested source and license files used by the build, including SPIRV-Headers, Vulkan-Headers, dxil-spirv, dxbc-spirv, SPIRV-Cross, SPIRV-Tools, and their own nested SPIR-V headers. These projects include MIT-style and Apache-2.0 licensed components. Their copyright and license notices remain in that archive.

## Proton and Steam

This project does not redistribute Valve's complete Proton installation. On the tester's machine, the installer makes a local copy of the already installed exact Proton Experimental build. Proton and its components remain under their own licenses. Valve documents local compatibility tools at <https://github.com/ValveSoftware/Proton>.

## NVIDIA and IL-2 material

NVIDIA driver tools and reports are not part of this repository. IL-2 game files are not distributed by this repository. Shader bytecode may be captured locally during an authorized diagnostic run and must be treated as private evidence unless its public redistribution has been reviewed and authorized.
