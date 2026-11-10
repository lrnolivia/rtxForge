# Split Render

Split Render uses DLSS 5 NR for the environment and characters, with a
separate character pass where supported. Open **Packages → Split Render →
Choose games** to review a setup for one or more games. Changing the setup
filters the list to compatible titles. **Select all results** selects the
games matching the current search and keeps earlier selections.
**Clear selection** clears all checked games.

**Auto** uses ShortFuse for character detail where Skynizz already runs NR.
Elsewhere it tries a single environment pass in this order: Lecram, ShortFuse,
GITC Uplift. The chosen DLSS 5 model applies to any newly installed model.
The review confirms the provider and model for each game and checks the files
before installing. You can also choose Split Render in the main installation
review. Confirm once to install each game’s main package, then apply that
game’s reviewed Split Render setup in the same run. The review lists the
exact file changes and shows when a game can only receive its main package.

For custom builds, tuning and saved combos, open a game's
**Tools → Split Render**. The group has two slots:

- **Environment** — the world, required. Where Skynizz runs NR + MFG or NR
  Only, Skynizz is the world: the slot shows **Skynizz** and nothing else.
- **Character detail** — optional; choose **None** to run one add-on.

Each slot takes an add-on and one of its pinned builds. The slots share one
**Old** or **New** DLSS 5 model. Where Skynizz already runs NR, both passes
use its installed model. rtxForge checks the choice every time it changes
and offers **Install** only when it can work. Install and Remove go through the
usual review, which lists every file and its SHA-256 before anything changes.

## Add-ons

| Add-on | Builds | How it runs |
| --- | --- | --- |
| Lecram (`renodx-dlss5.addon64`) | 10.8 | ReShade add-on for games with native DLSS and without OptiScaler. For a game without native DLSS, choose Feeder NR, which uses rtxForge's own 8.5 build. |
| ShortFuse (`renodx-dlss.addon64`) | 26.1025.0009 | Hooks the game's own DLSS calls, so it needs a 64-bit game with DLSS. ReShade loads it while it starts (`[ADDON] LoadFromDllMain`). It reads its settings from `[RENODX-DLSS]` and writes them back there when the game starts. |
| GITC Uplift | 1.8.0 | ReShade add-on with its helper and shaders. It runs alone. |

## Models

| Choice | Build | GPUs |
| --- | --- | --- |
| Old | 310.8.SF-v2 | Turing, Ampere |
| Old | 310.8.0-RTX40 | Ada |
| Old | 310.8.0 | Blackwell |
| New | 310.9.16 | Ada, Blackwell |

The model build is picked for the detected GPU family.

Every add-on archive, every file inside it and every model is pinned by URL,
size and SHA-256 in `providers/nr-addons.json`. Downloads are cached and
verified before use.

## Pairings

- **Two add-ons share one model file**, so both slots need the same Old or New
  choice.
- **Lecram stands down when another NR add-on is present.** rtxForge sets
  `ForeignNr=observe` when Lecram is paired.
- **GITC Uplift stops itself beside any other NR add-on.** It can't be paired.
- **Lecram in both slots** runs as two passes: Environment is pass 1 and
  Character is pass 2.
- **Unverified settings are never written.** If a combo carries a setting
  whose key or value encoding isn't verified for the chosen add-on, the check
  says so and the setting is left out.
- **Lecram never runs where OptiScaler is installed.** ReShade reloads Lecram
  while the game starts, and each reload hooks DLSS again. Beside OptiScaler,
  or the standalone frame-generation unlocker, that stops Ray Reconstruction
  and frame generation from starting on some launches. Use Lecram with the
  game's own frame generation.
- **With Skynizz NR + MFG**, Skynizz is the environment and **ShortFuse** adds
  character detail. rtxForge installs no NR model there: ShortFuse uses
  Skynizz's. With Skynizz on **MFG Only**, the slots work as in any other game,
  without Lecram.
- **Skynizz + ShortFuse runs close to a 12 GB card's video memory.**
  Switching windows can stall the game. Lower Character detail's resolution
  scale if it does.
- **Feeder NR games use their existing renderer.** ShortFuse hooks native DLSS,
  so it cannot use the inputs Feeder supplies to its own RenoDX renderer.
  On a verified Feeder installation, open **Tools → Feeder NR passes** in
  Desktop or Game Mode. Choose any pass from **1** through **4**, choose
  **Character** to enable its mask, and leave Skin detail at the game's
  current value or set your own. Each pass processes the whole frame. The
  mask lets Skin detail target detected skin, and one pass can use it.
  Selecting an inactive pass shows the additional full-frame work before
  you save the role for the next launch.
- **Another tool's files are kept.** rtxForge refuses the install rather than
  replace them.

A pairing that hasn't been confirmed on a Forge Lab test copy is marked as
**not verified** in the check. It can still be installed.

## Combos

The **Preset** picker fills both slots at once. One preset is built in,
**Characters + world**: ShortFuse for character detail, with the world from

- **Lecram 10.8** in games without OptiScaler, or
- **Skynizz** where it runs NR. ShortFuse then runs at a 74% resolution scale
  and shares Skynizz's model.

Both were verified in The Witcher 3 on an RTX 4070, each with Ray
Reconstruction and frame generation running.

Every combo's world works the same way: where Skynizz runs NR, Skynizz is the
world in place of the combo's Environment add-on.

**Save preset…** stores the current slots under a name, with up to 100 saved
presets. Every preset is available for every game. Each game checks a preset
against itself, so one saved in a DLSS game is refused in a game without DLSS
when it uses ShortFuse.

Saved combos live in `nr-combos.json` in the rtxForge state folder, and both
apps share them.

## In the rtxForge overlay

Where the rtxForge overlay runs, its **Split Render** section lists the settings of
each add-on rtxForge installed, under its role: **Environment · Lecram** and
**Character detail · ShortFuse**. Lecram never appears where OptiScaler is
installed. Where Skynizz is the world, its NR settings stay in the overlay's own
Skynizz NR controls.

In a Feeder NR game, **Feeder NR passes** opens the live tuning controls
for active additional full-frame passes. Turn off **Use main settings** to
tune a pass independently. The game's Tools screen configures the Character
mask role for each pass.

With the verified ShortFuse 26.1025.0009 module loaded, its overlay controls
apply while the game is running. The overlay reports whether ShortFuse
accepted the adjustment. Other providers' overlay preferences are saved
after the game closes and apply at the next launch. A value changed in
one of those providers' own ReShade panels in the meantime takes precedence.

Only settings whose key and value encoding are verified appear. ShortFuse's
resolution scale is a whole percent. A setting the game's ReShade.ini doesn't
set yet shows as **Add-on default**.

## Remove

**Remove** deletes only files rtxForge recorded that are still unchanged. A
changed file is kept and listed. ReShade.ini keys are put back to the values
recorded at install, and OptiScaler's `LoadReShade` is restored. In
`LoadFromDllMain`, only the add-ons rtxForge added are removed. Your other
ReShade settings are kept.

## Still to confirm in a game

- GITC Uplift beside other tools and with each model.
- Lecram 10.8's own Model version key.
- Old and New models per add-on.
