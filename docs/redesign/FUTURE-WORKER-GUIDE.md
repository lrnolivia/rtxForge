# rtxForge Future Worker Guide

## Current workflow

The repository is normally:

```text
~/Repos/rtxForge
```

GitHub `main` is the current shared source of truth.

Before substantial work:

```bash
cd ~/Repos/rtxForge
git fetch origin
git status --short
git branch --show-current
git log -5 --oneline
```

Read `docs/redesign/CURRENT-STATUS.md` and `docs/redesign/DEVELOPMENT-HANDOFF.md` before
redesign work.

Use exact source, not remembered line numbers.

## Git rules

After a coherent increment is approved and validated, commit and push normally to `main`.

Never force-push `main`.

The redesign beta workflow is manual-only; ordinary redesign pushes must not automatically
publish a beta.

Do not tag, release, or publish stable builds unless explicitly asked.

## Terminal safety

For multi-step mutation blocks, use a child shell:

```bash
bash <<'RTXFORGE_TASK'
set -euo pipefail
cd "$HOME/Repos/rtxForge" || exit 1
# guarded work
RTXFORGE_TASK
```

This prevents failures from closing or poisoning the user's interactive terminal.

## Architecture invariants

rtxForge is Linux/Bazzite-focused and uses native NVIDIA implementations.

Preserve:

- native NVIDIA DLSS-G ownership
- native Ada MFG
- provider provenance
- root-runtime safety checks
- DLSS-Unlocked private Streamline ownership
- no hybrid FG product path

Do not refactor backend/provider behavior during unrelated UI work.

## Redesign boundaries

The approved shell is locked.

Protected production UX:

- finished Library viewport/card behavior/artwork-size slider
- standalone Game Details
- standalone Game Settings
- Progress boxes/operation flow

List view is being reworked separately.

Done is less protected.

## Current redesign status

Forge, Settings, Recovery: presentation shells built.

Settings/Recovery: visually approved.

Home: exact supplied mockup target; responsive polish in progress.

See `docs/redesign/CURRENT-STATUS.md` for details.

## Validation

At minimum for redesign work:

```bash
python3 -m py_compile redesign/gui/rtxforge_redesign_lab.py
python3 redesign/gui/rtxforge_redesign_lab.py --smoke-test
git diff --check
```

Then visually launch the lab.

For broad checkpoints involving production code, run the repository's production compilation,
tests, and smoke test as well.

---

## 2026-09-19 — Golden Classic responsive-layout warning

Before continuing Classic Library work, read:

docs/redesign/ASTRA-CLASSIC-UI-HANDOFF-2026-09-19.md

The late UI iteration regressed the previously correct Poster/Wide responsive grid.

Use commit d442c7ad ("Finalize responsive classic library") as the primary golden implementation reference for grid/resize mechanics.

Do not wholesale revert newer UI styling.

Restore the proven responsive layout behavior from the golden commit while preserving newer approved visual changes.
