# BG3 Vulkan frame generation candidate

`source.json` identifies the unmodified [bg3fgvk v1.2.0 release](https://github.com/thierbig/bg3fgvk/releases/tag/v1.2.0), its exact source commit, archive digest and all 13 archive members. It is a package integration candidate. rtxForge does not install it, offer it in the catalog, or claim runtime support from this record. `deployable`, `runtime_verified` and `default_promoted` remain false.

## Route contract

The target is Baldur's Gate 3's x64 `bg3.exe` with the Vulkan renderer and native DLSS Super Resolution or DLAA enabled. The mod reads the game's NGX Vulkan evaluation inputs and supplies depth, motion vectors, jitter and reset data to a private Streamline DLSS-G instance. It provides frame generation; a separate compatible provider must supply any Neural Rendering.

The upstream loader is BG3 Native Mod Loader, which replaces `bink2w64.dll` and loads `NativeMods/fgvk.dll`. The release does not include that loader. A deployment adapter must establish loader provenance, redistribution terms, ownership and exact recovery before replacing anything. Loading after the game's Vulkan instance/device creation is too late for this interposition model.

The initial qualification target is RTX 40 at 2x displayed frames, with HAGS enabled on Windows and working Reflex. Upstream's default `DLSSGFrames=3` requests three generated frames, or 4x displayed frames; it is not evidence that an RTX 40 produces 4x. An Ada unlock, other GPUs, Proton and NR coexistence each need their own reviewed stack and runtime evidence.

## Package integrity and recovery

- Verify the archive digest, then enforce the complete member allowlist, sizes and digests in `source.json`. The release uses backslash ZIP names; the manifest uses forward slashes. A dedicated adapter must normalize separators while rejecting traversal, absolute paths, duplicates, links and case collisions. Keep the generic custom-import path validation intact.
- The manifest's member names describe the upstream archive. They are not an instruction to copy root-level README, INSTALL or LICENSE files over a game's files.
- Keep all seven Streamline runtime DLLs together. `nvngx_dlssg.dll` has its own file version within this bundle. Individual DLSS updater replacement must not mix this private stack with game-native or other provider runtimes.
- Preserve the mod's MIT notice and the runtime notice at the recorded license paths when distributing their payloads. Loader and any additional NR/unlock dependencies need separate notices and distribution review.
- Review existing `NativeMods`, loader proxies, `fgvk.ini`, private runtimes and generated diagnostics individually. The upstream mod creates/migrates its INI and writes logs at launch; these changes belong in the adapter's recovery design. Refuse writes while the game is running and preserve user-owned files and unrelated mods.
- Reusing an already loaded `sl.interposer.dll` and NVIDIA App plugin overrides can defeat the intended private runtime selection. Detect/report the actual loaded stack before assigning runtime provenance.

## General Vulkan adapter requirements

The [pinned source](https://github.com/thierbig/bg3fgvk/tree/66082e6f691fba1c48e319b688a25fa5ae196e56) includes BG3 input assumptions beyond its loader:

- `src/inputs.cpp` supplies synthetic camera constants (0.84 radian FOV, near 0.05, far 10000) and identity reprojection matrices. It assumes depth/motion attachment layouts, one viewport, and a particular frame-token handoff between evaluation and presentation.
- `src/slboot.cpp` hard-codes NGX application ID `0xE658703`. A general adapter must resolve an appropriate identity and feature support for each target.
- `TagHUDLess` and `TagUI` default off. The optional UI tag creates a transparent image; it does not extract the game's HUD. Enabling the SR-output tag does not establish correct post-processing color space or clean UI recomposition.
- The gate enables generation after 60 consecutive presents with successfully tagged inputs and suspends after 30 without them. This is a DLSS activity heuristic; a menu that continues rendering through DLSS can still satisfy it. Focus/minimize behavior needs runtime qualification too.
- Streamline/overlay dispatch routing, resource lifetimes, queue ownership, swapchain recreation and shutdown need validation for each engine. Merely replacing Native Mod Loader does not make the BG3 binary universal.

Games with a live native Vulkan DLSS-SR call are research candidates. RDR2 and Enshrouded have no rtxForge support claim from this pin.

## Admission and qualification

A future adapter must expose an explicit Experimental route and distinguish upstream reports from rtxForge results. Keep the existing D3D12-only Skynizz NR refusal for BG3: this separate Vulkan FG candidate cannot make that provider's D3D12 hook execute on Vulkan.

Before enabling installation, validate fixture-backed install, repair, cancellation, conflict and exact restore behavior. Before promoting runtime support, record the exact package/loader/NR/unlock/driver/GPU configuration and demonstrate actual presented-frame counts, pacing, HUD/text quality, loading/menu transitions, focus changes, resolution/HDR changes, swapchain recreation and overlay coexistence. A successful source build or host test run does not satisfy these game criteria.
