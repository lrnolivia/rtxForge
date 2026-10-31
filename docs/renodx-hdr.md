# RenoDX HDR

RenoDX HDR is optional and independent of neural rendering and frame generation.
Open a game's **Tools → RenoDX HDR → Install HDR**. rtxForge identifies the
matching mod, downloads it with the add-on-enabled ReShade runtime, and prepares
one review. No upstream installer runs and no mod file needs to be selected.

The catalog comes from RenoDX's official `games-index.json` snapshot, source
`43c067b755a6a741f6500b2b936570f1462dcfbe`, published October 29, 2026.
Game IDs take precedence; installations without an ID use exact normalized
titles or published aliases. Ambiguous variants, external-only downloads,
unsupported architectures, known extra prerequisites and detected anti-cheat
are reported as unavailable. Names are never guessed from partial matches.

Every add-on is pinned to its official GitHub release asset ID, size and
SHA-256. ReShade 6.8.0 with full add-on support is downloaded from its official
site and extracted as a ZIP; its installer is never executed. The archive and
selected runtime DLL are both verified. The MIT notices accompany the game
files and the application.

Managed OptiScaler uses `[Plugins] LoadReShade=true` and `ReShade64.dll`.
An existing matching ReShade hook, including the Feeder runtime, is reused
instead of loading a second copy. Otherwise, the game's PE imports determine
the DirectX or OpenGL hook. Another tool's DLL is never overwritten.

**Remove HDR** removes only recorded, unchanged HDR files. Reused NR/MFG files
stay installed. Removing the OptiScaler setting restores its previous value
while retaining subsequent tuning. Each operation keeps a separate verified
transaction backup; a failed operation rolls back its partial changes.
The HDR receipt uses game-relative paths so a shared library can identify
the HDR files from either operating system.

Shared OptiScaler installations can supply a verified loader even when the
current OS has no private installation record. Removal also checks the shared
ownership record before removing a host, so another OS's NR/MFG package cannot
lose a runtime it has since adopted.

Enable HDR in the display session before playing. Turn off Auto HDR and RTX HDR
for the game to avoid double tone mapping. Installing a package does not prove
that the game is rendering HDR correctly; that requires an in-game check.

For a standalone DirectX/OpenGL hook under Proton, rtxForge records and applies
the matching per-game DLL override, then restores only that override on removal.
The prefix must already exist and be idle. Managed OptiScaler's existing Proton
loader hosts the side-loaded runtime without a new override.

The current implementation does not install a Vulkan layer. That route remains
unavailable until its separate loading setup is implemented and verified.

Windows Control Resonant was checked in a clean fresh HDR10 startup and a 3D
scene, with NR model activity, measured GPU time, three generated frames per
rendered frame, camera input and the glass overlay's Look & detail controls.
An initial test before ReShade settings initialization produced startup
corruption; the final initialized configuration passed the fresh-launch check.
ME2's automatic package preparation, install/removal and reuse of its Feeder
host were verified, but its EA launcher did not start the game during this
check. These results do not qualify other games or Proton HDR rendering.

Upstream references: [RenoDX mods](https://github.com/clshortfuse/renodx/wiki/Mods),
[OptiScaler's ReShade compatibility guide](https://github.com/optiscaler/OptiScaler/wiki/Compatibility-with-other-mods-%28Reshade%2C-SpecialK%29),
[ReShade](https://reshade.me/).
