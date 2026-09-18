# rtxForge development notes

## 2026-09-18 — 0.7 classic freeze + redesign handoff

Production/classic rtxForge is 0.7.0 plus later maintenance work on `main`.

The classic UI is frozen apart from maintenance, compatibility, accessibility, bug fixes,
and explicitly approved changes.

### Preserve from classic

- finished Library viewport
- card geometry/style/behavior
- selection/filters
- live artwork-size slider
- artwork scaling
- Poster/Wide Capsule rules
- standalone Game Details
- standalone Game Settings
- Progress boxes/flow
- native NVIDIA/provider safety architecture

List view is being reworked separately.

### Redesign shell

User-approved and locked:

- Home
- Game Library
- Forge
- Settings
- Recovery separated at bottom
- no Tools
- full-width content
- current branding/inset/control sizing/spacing

### Page status

Forge: built.

Settings: built and visually approved.

Recovery: built and visually approved.

Home: exact supplied mockup; responsive visual polish active.

### Git workflow

GitHub `main` is again the shared source of truth.

Push coherent approved increments normally.

Do not force-push.

Redesign beta workflow is manual-only and should not auto-publish on source pushes.

### Next

Finish Home visual polish, then build migration plumbing for the finished Library viewport.
