# Experimental BG3 Vulkan frame generation provider

`source.json` identifies the unmodified [bg3fgvk v1.2.0 release](https://github.com/thierbig/bg3fgvk/releases/tag/v1.2.0), its exact source commit, archive digest and all 13 archive members. The standalone adapter is `scripts/vulkan_dlssg_provider.py`; catalog integration remains pending. Installation requires explicit Experimental opt-in, the pinned archive and a matching locally built loader. `runtime_verified` and `default_promoted` remain false.

## Route contract

The target is Baldur's Gate 3's x64 `bg3.exe` with the Vulkan renderer and native DLSS Super Resolution or DLAA enabled. The mod reads the game's NGX Vulkan evaluation inputs and supplies depth, motion vectors, jitter and reset data to a private Streamline DLSS-G instance. It provides frame generation; a separate compatible provider must supply any Neural Rendering.

Upstream uses BG3 Native Mod Loader. This adapter supplies a narrower startup proxy built from `loader/loader.cpp`: it forwards Bink's 79 exports to a locally preserved `bink2w64_rtxforge_original.dll`, temporarily intercepts BG3's entry point, restores its bytes, then loads only `NativeMods/fgvk.dll` before game startup. DX11 keeps Bink forwarding but does not load FG. Missing fgvk preserves ordinary startup. It never enumerates or loads unrelated native mods. Loading after Vulkan instance/device creation is too late for this interposition model.

The proxy accepts only the recorded game-owned Bink hash on first install. Existing replacement loaders and orphaned provider files require separate ownership review and are refused. The game's proprietary Bink DLL is copied locally and is never distributed. Export names/trampolines derive from MIT-licensed NativeModLoader at the exact revision in the manifest; its notice accompanies the installed provider. The loader's own source is covered by the project's license.

The initial qualification target is RTX 40 at 2x displayed frames, with HAGS enabled on Windows and working Reflex. Upstream's default `DLSSGFrames=3` requests three generated frames, or 4x displayed frames; it is not evidence that an RTX 40 produces 4x. An Ada unlock, other GPUs, Proton and NR coexistence each need their own reviewed stack and runtime evidence.

## Package integrity and recovery

- The adapter verifies the archive, loader and every member digest/size, normalizes ZIP separators and rejects traversal, absolute paths, duplicates, links, encryption and case collisions. Generic import validation remains unchanged.
- The manifest's member names describe the upstream archive. They are not an instruction to copy root-level README, INSTALL or LICENSE files over a game's files.
- Keep all seven Streamline runtime DLLs together. `nvngx_dlssg.dll` has its own file version within this bundle. Individual DLSS updater replacement must not mix this private stack with game-native or other provider runtimes.
- Preserve the mod's MIT notice and the runtime notice at the recorded license paths when distributing their payloads. Loader and any additional NR/unlock dependencies need separate notices and distribution review.
- Recovery uses a journal and content-addressed originals outside the game. Backups are verified before writes; the Bink original is placed first and the proxy last. Restore puts Bink back first, restores exact original bytes and modes, then removes only empty provider-created directories. Cancellation and interrupted writes retain a resumable journal. Repair replaces missing managed files while preserving INI preferences and logs. Changed managed DLLs, damaged backups, running BG3 and review drift are refused. A process-safe operation lock releases on process exit. Runtime INI/log contents are retained in external recovery objects before restore.
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

Before promoting runtime support, record the exact package/loader/NR/unlock/driver/GPU configuration and demonstrate actual presented-frame counts, pacing, HUD/text quality, loading/menu transitions, focus changes, resolution/HDR changes, swapchain recreation and overlay coexistence. A successful source build or host test run does not satisfy these game criteria.

## Standalone use and fixture commands

Build with `providers/bg3fgvk/loader/Build-Loader.ps1 -OutputDirectory` pointing outside source. The manifest requires the exact compiled DLL hash; a different compiler/source build needs a reviewed pin update. `Test-Loader.ps1` takes a separate output directory and exercises startup against synthetic game, Bink and plugin DLLs without proprietary code.

Run `python -m unittest discover -s tests -p test_vulkan_dlssg_provider.py` for the adapter's real-filesystem failure/recovery fixtures.

`python scripts/vulkan_dlssg_provider.py --help` lists operations. `review-install`, `install` and `repair` take `--game` (the BG3 root or bin), `--archive`, `--loader`, `--state-root` and `--experimental`. `review-restore`, `restore`, `status` and `diagnose` take the same game and state root. Recovery defaults to `%LOCALAPPDATA%/rtxForge/bg3-vulkan`; retain that directory until restoration is verified. Reviews inspect without modifying game files; apply rechecks every input and destination. `diagnose` reports logged actual-frame statistics while retaining `runtime_verified=false` for the unqualified package.
