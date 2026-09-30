# Windows rebuild plan

## Status

Planned rebuild. This document defines the intended Windows architecture for rtxForge before implementation begins.

The existing Linux application remains a separate product surface. The Windows version should not be a GTK port or a compatibility wrapper around the Linux UI. It should be rebuilt as a native Windows application in **WinUI 3**, while preserving the product principles that already define rtxForge: compact presentation, explicit game state, reversible changes, and a clean separation between the user-facing controls and the ugly per-game DLL work required underneath.

## Product goal

On Windows, rtxForge should become the orchestration layer for NVIDIA rendering upgrades rather than a thin frontend for one upstream mod package.

The user experience should remain simple:

- choose a game
- see what the game actually supports
- enable Neural Rendering, Super Resolution, Ray Reconstruction, Frame Generation, or Multi Frame Generation where valid
- choose an MFG mode and multiplier where supported
- install
- verify
- restore cleanly if needed

rtxForge should own discovery, compatibility decisions, configuration generation, installation, verification, updates, and rollback.

Upstream projects provide engines and runtime components. They should not dictate rtxForge's UI, profile model, or installation workflow.

## Windows application stack

### UI shell

**WinUI 3 / Windows App SDK**

The Windows rebuild should use WinUI 3 as the primary application shell.

Goals:

- native Windows windowing and input behavior
- compact layout rather than a web-dashboard aesthetic
- proper light/dark theme support
- Windows 11 materials only where they improve hierarchy rather than adding visual noise
- fast startup
- strong keyboard support
- clear install / installed / update / restore states
- no exposed dependency jargon unless the user opens Advanced

The UI should display product concepts such as **Neural Rendering**, **Frame Generation**, **MFG**, **Ray Reconstruction**, and **Injection**. It should not force users to understand proxy DLL names, Streamline revisions, OptiScaler INI keys, or upstream package layouts.

### NR and rendering substrate

**OptiScaler-DLSSNR / Pre-SR Multipass**

Use the current OptiScaler DLSS Neural Rendering implementation as the initial NR substrate.

Responsibilities delegated to this layer can include:

- Neural Rendering integration
- DLSS / DLAA routing where applicable
- Ray Reconstruction routing where applicable
- Pre-SR Multipass support
- configuration generation
- supported proxy / injection mechanisms

rtxForge must not hard-depend on another project's installer. It should consume versioned upstream assets directly through a manifest and generate the required configuration itself.

### RTX 40 Multi Frame Generation

**Universal RTXMFG**

Use Universal RTXMFG as the initial Ada / RTX 40 MFG engine.

rtxForge should surface its useful concepts directly:

- Native / game-controlled Frame Generation
- Multi Frame Generation
- Fixed multiplier
- Follow Game
- Dynamic MFG
- target FPS where the backend supports it

The normal UI should initially expose conservative RTX 40 choices:

- 2x
- 3x
- 4x

Higher experimental multipliers may be exposed later under Advanced when the backend and game integration make them meaningful.

Universal RTXMFG should be treated as an engine, not as rtxForge's UI. rtxForge owns configuration and lifecycle.

### Injection layer

Use **OptiScaler-supported proxy / injection routes** as the initial injection substrate.

Per-game recipes may select among routes such as:

- `dxgi.dll`
- `version.dll`
- `winmm.dll`
- `d3d12.dll`
- ASI or another supported loader route

The user-facing default is **Injection: Auto**.

The compatibility recipe resolves Auto to the safest known method for that title.

Advanced may allow a manual override, but manual injection should never be required for the normal workflow.

### NVIDIA and Streamline runtimes

rtxForge should manage NVIDIA runtime components as **versioned dependencies**, not loose files copied ad hoc into game folders.

This includes, where applicable:

- DLSS Super Resolution runtime
- DLSS Frame Generation runtime
- Ray Reconstruction runtime
- Streamline
- NR-specific forwarders or patched components required by the selected engine

Runtime versions must be declared in a manifest and may be pinned by game recipe.

Do not hard-code a single Streamline or NVIDIA DLL version in UI code.

## Architecture

```text
rtxForge for Windows
│
├── WinUI 3 application
│   ├── Library
│   ├── Game detail
│   ├── Install state
│   ├── Settings
│   └── Advanced
│
├── Game discovery
│   ├── Steam
│   ├── Epic
│   ├── GOG
│   ├── Xbox / Game Pass where accessible
│   ├── EA / Ubisoft where practical
│   └── Manual EXE
│
├── Capability detector
│   ├── existing DLSS integration
│   ├── existing Streamline integration
│   ├── existing Frame Generation integration
│   ├── Ray Reconstruction capability
│   ├── graphics API
│   └── known conflicts
│
├── Compatibility database
│   └── per-game recipes
│
├── NR engine
│   └── OptiScaler-DLSSNR / Pre-SR Multipass
│
├── MFG engine
│   └── Universal RTXMFG
│
├── Injection engine
│   ├── dxgi
│   ├── version
│   ├── winmm
│   ├── d3d12
│   └── ASI / supported alternatives
│
├── Runtime manager
│   ├── DLSS
│   ├── DLSS-G
│   ├── Ray Reconstruction
│   └── Streamline
│
└── Transaction manager
    ├── inspect
    ├── backup
    ├── install
    ├── verify
    ├── update
    └── restore
```

## Compatibility recipes

Game-specific behavior belongs in data, not scattered conditionals.

A recipe should describe what a game supports, what rtxForge may safely install, and how installation should occur.

Illustrative shape:

```yaml
id: witcher3-remastered
platforms:
  - steam

graphics_api: dx12

capabilities:
  dlss_sr: true
  ray_reconstruction: true
  native_frame_generation: true
  neural_rendering: true
  mfg: true

engines:
  neural_rendering: optiscaler-dlssnr
  mfg: universal-rtxmfg

injection:
  preferred: dxgi
  fallbacks:
    - version

runtime_policy:
  streamline: pinned
  dlss: managed
  dlss_g: managed
  ray_reconstruction: managed

mfg:
  default_mode: fixed
  default_multiplier: 4
  visible_multipliers:
    - 2
    - 3
    - 4

conflicts:
  reshade: inspect
  anti_cheat: block
```

The final schema can change. The important rule is that the recipe remains declarative and reviewable.

## Capability-aware UI

rtxForge must not show every feature switch for every game.

Examples:

- if a title has no usable Streamline Frame Generation integration, do not offer Universal RTXMFG as if it will work
- if NR is not supported for a title, display it as unavailable with a concise reason
- if an anti-cheat or protected executable makes injection unsafe, block installation rather than offering a destructive experiment
- if a recipe requires a specific injection route, Auto should silently resolve to it
- if a game is unknown, offer an Experimental flow with explicit backup and reduced assumptions

A normal game page should be able to look roughly like this:

```text
The Witcher 3: Wild Hunt

Neural Rendering        On
DLSS Super Resolution   Latest
Ray Reconstruction      Latest

Frame Generation        Multi Frame Generation
Mode                    Fixed
Multiplier              4x
Target FPS              120

Injection               Auto
Runtime policy          Auto

[ Install ]
```

Advanced can reveal the resolved engine, injection route, runtime versions, generated configuration, and changed files.

## Transactional installation

Every install must behave like a transaction.

### Before install

1. resolve the game recipe
2. inspect the target directory
3. detect existing proxy DLLs, ReShade, OptiScaler, Streamline, and related mods
4. calculate the exact file/config changes
5. create a backup manifest
6. preserve originals before writing

### Install

1. fetch only the required versioned assets
2. verify hashes
3. stage files outside the game directory
4. write the resolved configuration
5. move the staged set into place
6. record every changed path and source version

### Verify

After installation rtxForge should verify:

- expected files exist
- expected hashes match
- generated configuration parses
- conflicting duplicate proxy files were not introduced
- the install manifest matches disk state

Launch-time or runtime verification can be added later where practical.

### Restore

Restore must be first-class, not an uninstall afterthought.

A restore operation should:

- remove only files owned by the rtxForge transaction
- restore backed-up originals
- preserve unrelated user files
- report drift when files changed after installation
- avoid destructive overwrite when state is ambiguous

## Runtime manifest

Upstream components must be represented through a machine-readable manifest.

Conceptually:

```json
{
  "optiscaler_nr": {
    "version": "pinned-version",
    "source": "upstream",
    "sha256": "..."
  },
  "universal_rtxmfg": {
    "version": "pinned-version",
    "source": "upstream",
    "sha256": "..."
  },
  "streamline": {
    "version": "recipe-or-default",
    "source": "nvidia-or-upstream",
    "sha256": "..."
  }
}
```

The manifest should allow rtxForge to update engines independently without rebuilding the whole app.

No upstream installer should become a hidden mandatory dependency.

## Game discovery

The first Windows release should prioritize reliable discovery over trying to support every launcher immediately.

Suggested order:

1. Steam
2. manual EXE / folder
3. GOG
4. Epic
5. EA / Ubisoft
6. Xbox / Game Pass where permissions and packaging allow reliable mutation

Discovery must produce stable game identities so compatibility recipes and install records survive path changes where possible.

## Implementation boundaries

The Windows rebuild should keep three layers separate.

### Presentation

WinUI 3 views and view models.

Presentation should know product state, not filesystem tricks.

### Core

Shared domain logic:

- game model
- capabilities
- compatibility recipe resolver
- install plan
- runtime manifest
- transaction state
- verification results

Keep this layer UI-independent so testing does not require WinUI.

### Platform / engine adapters

Adapters own the messy details:

- registry and launcher discovery
- filesystem permissions
- process inspection
- OptiScaler configuration
- Universal RTXMFG configuration
- runtime downloading
- proxy selection
- backup / restore implementation

Upstream-specific behavior should remain behind adapters.

## Initial WinUI 3 surface

The first usable Windows shell does not need every current Linux view.

### Library

- scanned games
- artwork
- install state
- concise capability badges
- search
- rescan

### Game detail

- NR
- DLSS SR
- Ray Reconstruction
- Frame Generation / MFG
- MFG mode
- multiplier
- target FPS when relevant
- Injection: Auto / Advanced
- install / update / restore

### Settings

- game library locations
- runtime channel
- automatic asset updates
- backup location
- theme
- Advanced visibility

### Advanced

- resolved recipe
- detected integrations
- engine versions
- injection route
- exact changed files
- generated configuration
- logs

## Phased rebuild

### Phase 0 — architecture and manifests

- finalize recipe schema
- finalize runtime manifest
- define transaction format
- define engine adapter contracts
- define install-state model

No UI-first implementation before these contracts exist.

### Phase 1 — WinUI 3 shell

- application frame
- library
- game detail
- settings
- fake / fixture-backed game state
- compact design system

The shell should be developed against mock core interfaces so the UI does not block backend work.

### Phase 2 — discovery and transactions

- Steam discovery
- manual game import
- deterministic game identity
- backup / install / verify / restore
- install history

### Phase 3 — NR integration

- OptiScaler-DLSSNR adapter
- runtime manifest fetch
- configuration generator
- proxy Auto resolver
- NR capability gating

### Phase 4 — RTX 40 MFG

- Universal RTXMFG adapter
- Fixed / Follow Game / Dynamic modes
- 2x / 3x / 4x controls
- target FPS when supported
- capability detection for compatible Streamline FG titles

### Phase 5 — compatibility database

- convert known working titles into recipes
- conflict handling
- ReShade coexistence rules
- common proxy fallback logic
- recipe update channel

### Phase 6 — broader launcher support and polish

- GOG / Epic
- EA / Ubisoft where reliable
- Xbox / Game Pass investigation
- runtime self-update policy
- diagnostics export
- signed installer / packaging
- release hardening

## Reuse from current rtxForge

The Windows rebuild should reuse concepts and data where they are portable, not copy Linux implementation details blindly.

Worth preserving:

- game-library mental model
- compact presentation
- clear installed / update / restore states
- known game metadata
- runtime-fetching concepts
- compatibility knowledge already learned from Linux installs
- backup discipline
- logs and diagnostics
- artwork conventions where practical

Do not preserve solely for parity:

- GTK-specific architecture
- Linux path assumptions
- Wine / Proton assumptions
- AppImage packaging logic
- Linux-only process / prefix handling

## Non-goals for the first Windows build

- replacing NVIDIA App globally
- becoming a general mod manager
- supporting arbitrary graphics mods
- exposing every upstream toggle
- silently patching anti-cheat protected titles
- requiring users to understand DLL proxy chains
- sharing one UI codebase with Linux at the cost of native behavior

## Current upstream strategy

The initial stack is intentionally replaceable.

- **OptiScaler-DLSSNR / Pre-SR Multipass** is the initial NR and injection substrate.
- **Universal RTXMFG** is the initial RTX 40 MFG engine.
- **Streamline and NVIDIA runtimes** are versioned dependencies.
- **rtxForge** owns compatibility, configuration, UX, transactions, and rollback.

If a better NR or MFG engine appears later, the adapter and manifest should change without forcing a product rewrite.

That replaceability is a core architectural requirement of the Windows rebuild.
