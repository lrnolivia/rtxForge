# rtxForge Worker Context

**Canonical living source of truth for the rtxForge production project**

Read this file completely before changing the project.

Then read `NOTES.md`.

Do not create another worker handoff unless the user explicitly asks for one.

---

# 0. Documentation model

The active rtxForge documentation model is intentionally small:

```text
WORKER_CONTEXT.md = current project brain
NOTES.md          = user-editable scratchpad / inbox
Git history       = archaeology
issues / PRs      = task-specific history when used
```

`WORKER_CONTEXT.md` is not an archive.

Every worker that materially changes the project must leave this file more accurate and less stale than it found it.

At startup:

```text
read WORKER_CONTEXT.md
read NOTES.md
inspect actual repositories
inspect actual manifests/runtime selection
correct stale assumptions before acting
continue the highest-priority unfinished work
```

At closeout:

```text
update current state
remove completed active tasks
rewrite superseded architecture statements
fold durable discoveries into the right section
process NOTES.md
delete duplicate/stale guidance
do not append another handoff document
```

Use Git history for old detail.

Do not preserve completed work as active instructions merely because it used to matter.

---

# 1. Canonical architecture
Lauren's 2026-09-14 instruction supersedes DEC-20260911-001's one-provider restriction. Users choose y4my Multipass or DLSS-Unlocked. Each is a complete provider, never a mixture of one provider's loader with the other's NR layer. One transaction engine serves the GUI and terminal frontend.

`providers/lock.json` pins current default branches and release artifacts, verified against GitHub on 2026-09-14:
- y4my `dlss-neural-rendering`: `7b7220bbb4994a9c8ae60cfc75a44cb67995efb8`, v4 with_DLSS archive SHA `9d7824cc9cfb15265bc6438b4638aad74ff9cd6d1d3488ab73724affb386a8b0`.
- DLSS-Unlocked `main`: `00fbc5873363cd0a2e93867b365506e90732687f`, NR-v0.8.6 standalone SHA `61e1111f266cf960668466f654174372e6d994e61b0042783dacd985f6ea02e3`.

The GUI uses `scripts/engine_bridge.py` over `engine/rtxengine.py`, derived from the supplied RC1.38 typed-baseline package. `rtxforge` now enters the same engine via `scripts/engine_cli.py`. Legacy app transaction helpers remain for Undo of old app records.

Keep NVIDIA Ada frame generation native. Do not select OptiScaler DLSS-G replacement input/output for the default native-game path. RC1.38 used Enabled=false with FGInput/FGOutput=dlssg, but upstream initializes active routes independently and creates the private Streamline output at D3D12 device creation. Corrected policy is FGInput=nofg, FGOutput=nofg, Enabled=false: this leaves game-native DLSS-G intact. AdaMfgUnlock and AdaBlackwellKernels are independently enabled by the explicit startup-effects switch. This code correction is NOT cross-game launch proof.

No root native DLSS/Streamline replacement, no alternate/hybrid FG payload, no automatic provider fallback. Upstream signature refusal remains unchanged. NR differs by provider: y4my dual-feature/DLSS enlargement with a local model; DLSS-Unlocked owns its pre-SR package. MFG Only omits NR. Startup effects are explicitly selectable and default dormant while launch failures remain unverified.

---

# 2. Current project/chat identity

The rename is already complete.

Current identity:

```text
Project: rtxForge
Master chat: MASTER— rtxForge
Primary worker chat: WORKER — rtxForge
```

Do not rename these again.

Do not create duplicate rtxForge master/worker chats to redo an already-completed migration.

`Ada Graphics` is historical naming only.

---

# 3. Runtime ownership
One production owner and one transaction engine with two explicit providers. Historical Nightfall research remains reference. Do not create new worker tasks for the superseded split.

---


# 4. Historical runtime evidence
v3e is retired as active architecture. Preserve its tag, commits, hashes and logs without repointing history. Its reported TOW2 2X/3X/4X wins become regression cases, including repeated transitions and absence of fatal/SetOptions errors. Prior Cyberpunk failures remain evidence, not a reason to keep two runtimes.
Lauren deployed v3e across her library before this change and will perform game testing. This task does not launch or redeploy games.

---


# 5. Product scope

rtxForge is a Linux/Bazzite/Proton application for making community RTX work coherent, safe, reversible, and practical.

Core thesis:

> **Make NVIDIA hardware on Linux do everything it reasonably can.**

Product direction:

```text
Linux / Bazzite / Proton
GNOME first
KDE may follow
AppImage
Windows client: not active
```

Do not turn rtxForge into:

```text
a Windows client
a generic mod downloader
an arbitrary injector manager
```

Windows tools may be studied as product or implementation references.

The practical user goal matters:

> **The user should be able to play games instead of becoming the graphics stack's full-time QA department.**

---

# 6. Production repository/runtime discovery

Repository names and branches may change during refactors.

Do not trust stale paths from an old handoff.

At startup, discover the actual current repos and inspect:

```bash
git fetch origin
git status --short
git branch --show-current
git rev-parse HEAD
git remote -v
git tag --points-at HEAD
```

Also inspect the active rtxForge provider/package manifests.

Before editing, determine:

```text
which repo is the production app
which code/package is the unified y4my production runtime
which historical branches contain useful evidence
which runtime is actually pinned/shipped
which capability IDs/hashes are current
```

Repository/manifests reality wins over old prose.

If any of those mappings materially change, update this file.

---

# 7. Production runtime policy
Use the complete selected provider for both effects. Keep native NVIDIA frame generation, upstream signature refusal and attribution. Record exact fork commit, build, capability and DLL SHA separately from game verification. The prior custom Off/Auto/Dynamic fork candidate is historical development evidence and is not substituted into either pinned upstream provider.

---


# 8. Native NVIDIA MFG policy

This is a project-level rule:

> **No hybrid MFG in the supported rtxForge Ada path.**

For RTX 40 / Ada, supported production MFG must remain NVIDIA-generated.

Do not silently substitute:

```text
FSR frame generation
DLSSG-to-FSR-generated extra frames
hybrid NVIDIA + FSR MFG
OptiFG-style alternate generation
another non-NVIDIA backend
```

A research package may contain such components upstream.

That does not authorize rtxForge to enable them in the supported Ada production route.

If a package bundles multiple FG backends, the worker must verify which one is actually active before calling the result native NVIDIA MFG.

---

# 9. Neural Rendering
The y4my provider uses multipass / dual-feature NR with DLSS enlargement. It requires a locally supplied or suitable existing NR model, and refuses missing models before game mutation. The DLSS-Unlocked provider uses its complete pinned package and pre-SR NR settings. Never transplant NR files between these providers. Effect startup is controlled by the explicit Settings switch. No runtime success has been inferred from packaging.

---

# 10. Provider/package model

The default supported provider is the currently verified rtxForge production stack.

Conceptual provider classes:

```text
Official rtxForge production stack
Community provider
Experimental / unverified provider
```

Do not silently downgrade from the supported production stack.

Do not expose arbitrary repository URLs as a normal install workflow.

Future community providers should be manifest-driven.

A provider manifest should identify:

```text
source
exact version/commit
asset
hashes
layout
license/provenance
capabilities
GPU/API support
conflicts
verification state
install/uninstall behavior
```

---

# 11. App ownership/adoption lifecycle

Preserve the managed-state model:

```text
CLEAN
no recognizable active external stack
-> fresh install

MANAGED
rtxForge manifest + managed files exist
-> repair / profile change / uninstall

EXTERNAL
recognizable external runtime exists
no valid rtxForge ownership
-> adoption may be offered
```

Rules:

```text
historical state alone never forces adoption
clean post-uninstall games remain installable
adoption requires recognizable files that exist now
incomplete external installs are not silently adopted
messages report the real conflict/recognition reason
```

---

# 12. Prepared-package cache

Prepared payloads are disposable derived cache.

Correct behavior:

```text
valid payload + matching manifest
-> reuse

manifest/listing/payload drift
-> reject derived cache
-> delete only invalid derived payload/manifest
-> retain pinned source archive
-> verify source archive
-> rebuild extraction
-> regenerate file manifest
-> verify rebuilt payload
-> continue
```

Security rule:

> **Self-healing must never mean accepting drift.**

Readonly/dry-run remains non-mutating.

---

# 13. Game-specific compatibility knowledge

Only active/current exceptions belong here.

## Forza Horizon 6 historical exception

Known game-side file:

```text
winmm.dll
SHA256:
bfe362f716b95b830206a1b986e2e94735691e8d7dd71f9148f7b9cfd3c5f435
```

The compatibility exception was intentionally exact:

```text
game identity + filename + SHA256
```

Do not generalize this into “ignore every winmm.dll.”

If the current app/runtime no longer uses this exception, remove this section after verifying it is obsolete.

---

# 14. Verification philosophy

Compilation, CI, deployment, or reaching a title screen are not runtime verification.

For runtime experiments:

```text
verify exact source
change one conceptual variable
build exact commit
identify exact artifact
verify provenance/hash
back up live files
deploy exact artifact
verify live hash where practical
test in a real game
preserve relevant result/log
```

Support states:

```text
VERIFIED
COMMUNITY VERIFIED
SUPPORTED / UNVERIFIED
EXPERIMENTAL
UNSUPPORTED
```

Never claim success without real game testing.

Maintain separate verification records for:

```text
exact runtime hash / game / feature / test result
```

Historical results do not automatically verify a new build.

---

# 15. Production validation targets

For native MFG, validate as applicable:

```text
cold launch
native 2X / 3X / 4X
repeated multiplier transitions
Off
Auto/Dynamic if exposed
menu open/close
save/load or comparable transition
longer gameplay session
normal shutdown
no DLSS-G SetOptions failures
native NVIDIA backend confirmed
```

For combined production:

```text
selected provider NR enabled
native NVIDIA MFG enabled
both coexist
no hidden hybrid FG backend
performance acceptable
image quality stable
clean uninstall/restore
cross-game validation
```

---

# 16. Product/UI state
Implemented: full-ratio posters/capsules, artwork-led details, native Steam launch, folder opening, compact progress, view icons, settings/provider buttons, startup-effects switch, per-game notes, Untested/Working/Problem/Bench status, explicit start/finish test records, bounded adjacent-log capture and support ZIP export. Bench excludes bulk install/repair. Tests are user-recorded, not automatic evidence. Existing tests persist across app restarts; finish capture is manual.

Outstanding: confident Non-Steam metadata matching, automatic session completion across desktop/Game Mode, independently updateable provider catalog, controlled game validation, native KDE frontend. No Windows client.

---

# 17. Naming/branding rules

Product:

```text
rtxForge
```

New machine namespace:

```text
rtxForge.*
```

Examples:

```text
rtxForge.NativeMfgMenu.v4
rtxForge.DlssNr.Proton.v1
rtxForge.StreamlineBridge.v1
```

Experimental iterations may use:

```text
v4a
v4b
v4c
```

Stable contract becomes:

```text
v4
```

Historical `RTXForge.*` IDs/tags remain historical.

Do not rewrite old provenance just for casing.

---

# 18. Mass Effect release naming

Major-ish public releases get Mass Effect codenames.

The major version establishes an era, but minor releases do not need a rigid family tree.

Example:

```text
rtxForge 1.0 — Normandy
rtxForge 1.1 — Afterlife
rtxForge 1.2 — Charge
rtxForge 1.3 — Singularity
rtxForge 1.4 — Calibrations
rtxForge 1.5 — Omega-4
rtxForge 1.6 — Silversun
rtxForge 1.7 — Solus' Wrath
```

Patch releases normally get no new codename.

Valid sources include:

```text
characters
cities
bars/clubs
stores
manufacturers
ships
weapons
biotic powers
tech powers
missions
factions
species sayings
deep-cut jokes
original elcor-style phrases
```

Names should fit the personality of the release.

If the fit cannot be explained in one sentence, pick another.

Internal projects may be sillier.

Permanent prohibition:

```text
Miranda
```

No appeals process.

---

# 19. Attribution and lineage

For shipped third-party/community work:

```text
preserve license obligations
preserve authorship
credit upstream
record meaningful provenance
```

Current production documentation must distinguish:

```text
DLSS-Unlocked upstream
OptiScaler upstream
DLSS Enabler/headless where present
Dagherbou NR work where present
other bundled upstreams
rtxForge adaptations
Nightfall-derived ideas/code
```

Do not imply that rtxForge invented upstream techniques it integrated.

When appropriate, preserve cherry-pick authorship and provenance.

---

# 20. README policy

The public README describes what ships now.

Do not let it become a worker diary.

Rewrite stale claims instead of stacking corrections.

The README should make clear:

```text
what rtxForge is
Linux/Proton scope
current production runtime lineage
unified y4my multipass v4 Linux/Proton direction
native NVIDIA Ada MFG policy
Neural Rendering
capability/support state
safety/backups/rollback
installation/use
known limitations
verification philosophy
credits/provenance
non-affiliation
```

Project Nightfall may appear in a short developer/research section.

Normal users do not need to understand Nightfall to use rtxForge.

---

# 21. Current priorities

Workers must verify these against the actual repo before acting.

Delete completed items.

## P0 — production

```text
verify both complete provider integrations
make Proton/Bazzite loading repeatable
make NR cold-start and runtime behavior reliable
ensure Ada MFG path is actual NVIDIA MFG
validate NR + MFG together
harden install/uninstall/rollback
cross-game validate
surface clear per-game state in rtxForge
```

## P1 — shared lifecycle

Verify which remain open:

```text
Deep Clean normalization
Install -> Uninstall -> Install coverage
Steam Verify / external deletion recovery
cache self-healing regression coverage
recognition/adoption/conflict messaging
```

## P2 — UI/product

Use Section 16.

Lauren subsequently authorized real game launches, input, package deployment and testing in isolated Forge Lab copies. Preserve original installations and prefixes. Crimson Desert launch failure is the current priority.

---

# 22. Do-not-regress checklist
- Two explicit complete providers; no hidden mixing, hybrid FG or fallback.
- y4my model remains local; DLSS-Unlocked uses its declared upstream package. No NVIDIA DLLs rehosted in our release.
- Preserve signature refusal, ownership, backups, drift checks and rollback.
- Do not claim runtime verification from compilation or file hashes.
- Preserve unrelated source and game state; no unsolicited fleet deployment.
- Preserve upstream licenses and historical tags.
- Keep WORKER_CONTEXT and NOTES current; no duplicate handoffs.
- Never use Miranda as a release name.

---


# 23. NOTES.md contract

`NOTES.md` is the user's scratchpad/inbox.

The user may put anything there.

Workers must read it at startup.

For each note:

```text
durable fact
-> verify if needed
-> fold into WORKER_CONTEXT.md
-> remove from NOTES.md once safely represented

real task/requirement
-> capture in the live priority/task system
-> remove from NOTES.md once safely represented

resolved/irrelevant
-> remove

ambiguous user note
-> preserve until its meaning is clear
```

Do not silently discard ambiguous user-authored notes.

Do not turn `NOTES.md` into another permanent backlog or archive.

---

# 24. Worker closeout

Before substantial work is declared complete:

```text
[ ] actual repo state verified
[ ] actual runtime/provider selection verified
[ ] real tests performed where required
[ ] WORKER_CONTEXT updated
[ ] stale active instructions removed
[ ] NOTES.md processed
[ ] priorities contain only unfinished work
[ ] provenance preserved
[ ] no new handoff document created
```

---

# 25. Current mission
0.5.0 is published. Current mission: investigate Crimson Desert launch failure in Forge Lab, then verify NR + MFG gameplay in isolated copies. Lauren explicitly authorized copied games, separate prefixes, package installs and in-game interaction. Upstream runtime/menu semantics are inherited from the selected pin; historical custom v4 changes are not silently transplanted.

---


## Current observed failure and limits — 2026-09-14
Lauren reports RC1.38 games do not start and the previous uninstall removed built-in 2x FG across the library. The available PRAGMATA log shows older active DLSS-G output and RSYNC / Present failures; it does not prove the latest dormant build executed. Cyberpunk currently has native DLSS-G/Streamline files and no installed OptiScaler proxy. Restored terminal receipts inspected do not list native root DLSS-G files as originals/managed entries and contain no NVAPI/NVCUDA tokens. Do not claim the library is repaired: no live changes or game launches were performed.

Uninstall now refuses native root NVIDIA/Streamline deletion without original backup authority. Existing preserve-only native capability environment behavior remains. GUI reports launch-sync errors instead of declaring full success.


## 0.5.0 packaging checkpoint — 2026-09-14
The GUI, root terminal launcher, START HERE and AppImage --cli use the same provider adapter. Full imported suite: 276 passed plus 10 subtests; final focused regressions: 4 passed. Actual pinned payload install/restore fixtures passed for y4my MFG Only and DLSS-Unlocked MFG Only / NR + MFG, preserving native DLL bytes. Packaged CLI and GTK smoke checks passed. These are software/package checks, not game-launch validation.

The desktop refuses hidden interactive/sudo operations and requires Steam closed. Legacy Undo now also refuses deleting native NVIDIA/Streamline DLLs without original backup records. DLSS-Unlocked uses its own NR model while backing up/restoring an existing model; y4my retains local-model preference. Hardware installation gate is currently RTX 40/Ada; do not enable Ada unlock on RTX 50 by misclassifying it.

Outstanding: user game launch/native 2x recovery validation; investigate missing FG from actual post-uninstall logs/settings before proposing changes; independent provider update UI/flow; arbitrary repositories; automated test lifecycle monitoring; further runtime Off/Auto/Dynamic behavior only after identifying the selected provider's behavior. The previous custom fork's historical milestones remain reference.

## Forge Lab checkpoint — 2026-09-15
Five games have independent COW copies under `/var/mnt/Games/Forge Lab`: PRAGMATA, Clair Obscur, Cyberpunk, Crimson Desert and Star Wars Outlaws. Original installations and Steam metadata remain unchanged. `tools/forge_lab.py` keeps transaction state local to the lab. Pending source changes prevent same-name lab copies matching original Non-Steam shortcuts and preflight desktop Steam matching before writes (7 targeted tests passed).

PRAGMATA DLSS-Unlocked NR+MFG reached menus with DLSS loaded and direct NR feature creation, but repeated RSYNC errors remain and character movement has not been verified. SDK banner attribution is unresolved; native game DLLs also contain development-banner strings.

Crimson Desert is still an unmodified baseline. UMU reset SteamGameId to zero; direct Steam runtime preserved 3321460 and reached menus. User reports color bars, then crash after Play and return to terminal. Proton explicitly logged placeholder-video-used; the lab launcher omitted Steam's transcoded media path although a 1.7 GB cache exists. Corrected lab launcher and independent COW media cache tested on 2026-09-15: correct Steam app ID 3321460, title screen without color bars, Play video then user-confirmed in-game arrival. Logs: Forge Lab/reports/crimson-media-20260915-155350. No placeholder-video-used entries in this run. This establishes baseline launch only, not NR/MFG verification or long-session stability. Prior boot journal ends at 15:35:07; Lauren confirms manually rebooting after landing in the full-screen terminal. No recorded Xid/OOM/exception explaining that failure was found. Do not treat shader compilation/title screen as success or add an injector before baseline works.

Lauren confirmed Crimson Desert baseline established and exited, then requested the less-confident package first. DLSS-Unlocked NR-v0.8.6 NR+MFG installed into Crimson Desert lab copy with enable_effects=True, wininet proxy, AdaMfgUnlock/AdaBlackwellKernels true and DlssNr Enabled=true. Launcher `Forge Lab/Launch Crimson Desert NR+MFG.sh` preserves the corrected Steam/media context and adds wininet=n,b. Started run at 15:58:39, logs `reports/crimson-dlss-unlocked-nr-mfg-20260915-155839`; OptiScaler loaded and game window appeared. Combined gameplay and native multiplier verification remain pending. Original installation unchanged.

Crimson Desert DLSS-Unlocked combined run: user overlay screenshot shows DLSSG 310.6.0 unlock unavailable. OptiScaler.log 15:58:45.591621 confirms `MfgUnlock::TryApply MFG unlock: unsupported or ambiguous DLSSG 310.6.0 signatures; left unchanged`. Ada config is enabled but MFG patch is NOT applied. Title-screen upscaler prompt is separate; NR evaluation still unverified. Preserve signature refusal; do not claim combined success.

Crimson DLSS-Unlocked run exited after Lauren enabled DLSS SR, RR and FG; assistant sent no input or close command. Proton log records access violation c0000005 in vkGetPhysicalDeviceSurfaceCapabilitiesKHR at monotonic 1472.647. OptiScaler log records native FG enabled with numFramesToGenerate=1 (2x), then release/detach at 16:00:19. MFG signature refusal remains. Exact culprit among simultaneous SR/RR/FG changes is not isolated. Archived OptiScaler INI/log beside Proton run log before further tests.

Lauren reports NR working during Crimson cold relaunch, no MFG, and possible crash while tuning NR. Second crash log again has c0000005 in vkGetPhysicalDeviceSurfaceCapabilitiesKHR, this time resolving within libnvidia-glcore.so.610.57.04; cause is not isolated. With game confirmed stopped, restored only [DlssNr] from archived initial installation INI, preserving other settings and backing up current INI in lab reports. This is DLSS-Unlocked NR-v0.8.6 / OptiScaler 680cc32f, with game-native Streamline 2.11.1 and DLSS 310.6.0, official Proton Experimental and copied Steam media cache.

## Provider refresh 2026-09-15
DLSS-Unlocked NR-v0.9.1 commit d5653c217cb7efd99662cc50994bc91e948fb2ec / archive SHA 710977fcfbff2dd3a53ff2b5ba13dea23ee81007a614a92880467e960c33cd0b. y4my September 15 nightly SHA 06a82d6faa5befcc9fb818e8e15fccb98c32881b43e2974d097c67d915e2a834 retains source commit 7b7220b; paired with separately pinned v4 private runtime archive because nightly omits runtimes. Adapter verifies both hashes and takes only runtime files from companion.
Lauren clarifies second exit may have been manual after NR tuning reduced performance to ~1 FPS; do not characterize that run as a confirmed application crash solely from teardown exceptions. User confirms NR functioning.
Crimson lab restored then installed 0.9.1 with NR/MFG startup on. Latest run reports OptiScaler 1776cbf1 and successful MFG architecture gates plus 31 Blackwell kernel containers rewritten for Ada on existing 310.6.0. Actual generated-frame counts/gameplay still unverified. Lab cache moved to Forge Lab/cache; no shared Steam settings changes.

0.9.1 Crimson live 3x switch failed per user. Archived INI, OptiScaler log and game options in reports/crimson-dlss-unlocked-nr-mfg-20260915-203712. Proton records c0000005 in libnvidia-glcore.so.610.57.04 +0xcf4a74 via vkGetPhysicalDeviceSurfaceCapabilitiesKHR; no logged successful 3x. Saved game count stayed 2. Started controlled cold-3x test (only _numFramesToGenerate changed 2 -> 3; NR unchanged), run reports/crimson-dlss-unlocked-nr-mfg-20260915-203902. Result pending.

Lauren explicitly authorized newer native runtime DLLs for Crimson lab after failed 3x. Replaced matching existing root sl.* and nvngx_* (excluding managed NR) from installed DLSS-Unlocked 0.9.1 private Streamline directory. Original lab bytes and replacement hashes recorded at /var/mnt/Games/Forge Lab/reports/crimson-native-runtime-backup-20260915-204105. This is a lab-only runtime replacement experiment, not default product behavior. Restore this backup before engine uninstall/provider-switch: engine does not own these manual root replacements. Original Steam installation untouched.

New native 310.9.1/Streamline 2.14.1 run failed after Pearl Abyss screen per Lauren, with same libnvidia-glcore +0xcf4a74 surface query access violation and repeated RSYNC setDynamicMFGParams status 1. Archived logs/config in run 204105. Next controlled test disables only game-native _enableFrameGeneration, retaining newer DLLs, NR and RR; launch pending.

Correction from Lauren: 3x selection did not crash until Apply. During the purported FG-off run Lauren re-enabled FG and applied 3x, so that run is NOT evidence of a crash with FG disabled. Current run 204354 has NR disabled for isolation; read saved FG settings and actual interpolation logs before classifying. Do not infer root cause from confounded runs.

Lauren confirms 3x FG after Apply and gameplay with NR disabled. Requested frozen independent NR and MFG pipelines, simple GUI choices without user-tested badges. 0.5.2 adds NR Only pinned to earlier DLSS-Unlocked 0.8.6 (NR observed working; native game FG must remain off), and MFG Only 0.9.1 with matching existing root native runtime replacements backed up/restored by engine. Combined remains experimental. Shared engine/CLI/UI selects correct profile pin; uninstall required on profile switch. Five focused profile/native-restore checks passed. Real Crimson is reinstalling under Steam downloading/3321460, so no GUI failure diagnosis can be inferred from incomplete installation.

0.5.3: Lauren reports DLSS-Unlocked combined works in The Outer Worlds 2, NR Only in 007, MFG Only in Cyberpunk 2077. Requests automatic effect activation without opening OptiScaler (overlay sometimes crashes, explicitly no investigation/tests now). GUI install/repair always enables selected effects, engine and CLI default on with CLI --disable-effects escape hatch. SDK banner left unchanged: lab NGXCore ShowDlssIndicator and DLSSG_IndicatorText already zero; no proven safe removal. Build to be installed in actual host Applications using packaged installer. No game changes/tests in this update.

At Lauren’s request launched Crimson lab combined NR+MFG again with current DLSS-Unlocked 0.9.1 and newer root runtimes. Only changed DlssNr.Enabled false -> true; preserved one pass, 1.0 working scale, pre-SR, saved native FG and RR settings. Backed up INI/game options/hashes in reports/combined-ready-20260915-220955. Run logs reports/crimson-dlss-unlocked-nr-mfg-20260915-220956. User controls test; no actual Steam install changes.

Lauren requested same current combined set on all five Forge Lab games and discoverable launch shortcuts. All five now freshly deployed DLSS-Unlocked 0.9.1 NR+MFG with matching newer root native DLLs included in engine-owned backups. Crimson prior manual native replacements first restored from verified 204105 backup, then old engine install uninstalled; new baseline owns runtime replacements. PRAGMATA old deployment restored before update. Five reports *-frozen-combined.json describe installations. No games launched during this task. Prefixes Cyberpunk/Outlaws copied COW from own original Steam prefixes; Clair copied independent PRAGMATA lab prefix. User-directory external symlinks checked. Steam media caches copied COW where present. Launchers at Forge Lab/Launchers, linked from host Desktop/Forge Lab and ~/Applications/Forge Lab; five app-menu entries named Forge Lab — <game>. Steam titles use Experimental and correct app IDs; non-Steam use GE11-6 UMU. All configs checked NR/MFG on; syntax checked launchers; other-game combined gameplay unverified.

Crimson Desert normal-install launch issue resolved by Lauren: Steam had selected GE; switching the actual Steam installation to Proton Experimental allowed it to launch. Record Experimental as the user-confirmed working compatibility tool for Crimson. Do not attribute that normal-install failure to the GUI deployment or reopen the resolved launch issue without new evidence. This does not independently establish combined NR/MFG stability.

Forge Lab shortcuts opened in text editor under GNOME Files. Added native executable launch buttons named after each game, compiled on host from tools/forge_lab_launcher.c; they delegate to adjacent desktop entry via gio launch. .desktop/.sh support files hidden with .hidden; app-menu entries retained. Five --check runs verified entry paths without launching games. No global MIME association changes.

Lauren reports Crimson combined test looks perfect and requests NR defaults WorkingScale=0.75, SkinStructure=1.00, Intensity=1.50. Live lab INI confirms working scale 0.75, slider approximations intensity1.51 and skin1.02; leave running/game state untouched. 0.5.4 fresh NR installs use exact requested values; repairs preserve explicit existing values. No game tests.

Added five Forge Lab non-Steam shortcuts after Lauren closed Steam. tools/add_forge_lab_to_steam.py preserves prior VDF bytes and adds native /usr/bin/bash launchers tagged Forge Lab. Ten existing entries preserved; backup reports/shortcuts-before-forge-lab-20260915-224007.vdf. Reopened Steam. Do not force Proton on these native script entries; scripts handle dedicated prefixes/runtime. Gamescope gameplay remains user-tested.
