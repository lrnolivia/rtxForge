# MASTER — rtxForge: active coordination context

Authority: Lauren's latest instruction, relayed by LPM under DEC-20260911-001.
Canonical directive:
`/home/loew/Tools/PJM/01_NIGHTFALL_TO_RTXFORGE_PROJECT_MANAGER_DIRECTIVE.md`.

This master-owned record supersedes historical Ada/NIGHTFALL handoff guidance for
active production direction. It is an architectural decision, not an implementation
completion or local runtime verification claim.

## Identity and ownership

- Current production project: `/home/loew/Repos/RTXForge`.
- `/home/loew/Ops/ada-graphics` is obsolete and was absent on inspection.
- Canonical production master: `01a06f50-83ea-7b72-86f0-e49464f58782`.
- Sole implementation owner, WORKER — rtxForge:
  `01a082a3-dad5-7a73-bbc0-2571286c3149`.
- LPM: `01a06f53-3d25-7d41-9516-3eea1dab4cf8`.
- Do not redo the rename, audit old worker histories, launch cleanup audits,
  create replacement workers, or resume a separate NIGHTFALL implementation.
- The production worker already received the correction. Do not resend it.
- Leave worker-owned `WORKER_CONTEXT.md`, `NOTES.md`, and implementation files
  to the production owner; this update does not edit them concurrently.

## One shipping runtime

Use `y4my4my4m/OptiScaler_DLSSNR_Multipass_MFG`:

- Tag: `v10.0.0-dev-fork-y4my4my4m-v4`.
- Commit: `7b7220bbb4994a9c8ae60cfc75a44cb67995efb8`.
- Package: `with_DLSS`.
- SHA-256: `9d7824cc9cfb15265bc6438b4638aad74ff9cd6d1d3488ab73724affb386a8b0`.
- Bundled DLSS 310.9 and Streamline 2.14.

These are user-verified pin details relayed by LPM. Neither this master-context
update nor LPM independently downloaded the package. The implementation owner
must verify the actual artifact before consuming it.

Integrated native Ada MFG and multipass/dual-feature NR share this runtime.
For RTX 4070: `AdaMfgUnlock=true`, `AdaBlackwellKernels=true`.
Use one proxy DLL and `WINEDLLOVERRIDES="<proxy>=n,b"`.
Retire the active rtxEngine-added NVAPI/NVCUDA recipe; recognize legacy values
only for safe removal of settings demonstrably owned by rtxEngine. Preserve
unrelated user settings.

NR follows v4's DLSS enlargement and y4my model pipeline, superseding earlier
NR recipes and blanket dual-feature-off guidance. Preserve a suitable existing
`nvngx_dlssnr.dll` or accept a locally supplied copy; refuse game mutation when
the required runtime is missing. Preserve unknown DLSS-G signature refusal.
Do not represent hybrid FSR extra frames as native NVIDIA MFG.

No parallel v3e, Universal RTXMFG, user-facing MFG route selection or per-game
profiles unless later evidence establishes an unavoidable compatibility exception.
The old DLSS-Unlocked-production/separate-classic-NIGHTFALL split is superseded.

## Evidence and boundaries

v3e is retired as active architecture. Preserve its historical commits, hashes,
logs and reported multiplier successes as regression cases, including repeated
2X/3X/4X transitions and fatal/SetOptions-error checks. Retain prior Cyberpunk
failures as evidence. Old wins do not justify keeping two implementations.
Do not destroy history or delete/repoint tags. Project 188 implementation status
is unverified here.

Upstream Cyberpunk/Proton reports are not local runtime proof. No new live game,
Home, destructive-history or real-launch authority is granted. Existing scoped
deployment approvals and clone-storage constraints remain applicable.

## Coordination

Use one implementation owner and serial execution. Send one complete actionable
handoff only when needed, then do independent authorized work or end the turn.
No polling, waiting loops, receipt relays, routine acknowledgements or monitoring
automations. Reuse existing evidence and do not repeat verification without cause.
Resume on a substantive result or new instruction.
