# DLSS5 NR add-ons

Open a game's **Tools → DLSS5 NR add-ons**. The group has two slots:

- **Environment** — required.
- **Character** — optional; choose **None** to run one add-on.

Each slot takes the add-on, one of its pinned builds, and the **Old** or **New**
DLSS5 model. rtxForge checks the choice against the game every time it changes
and offers **Install** only when it can work. Install and Remove go through the
usual review, which lists every file and its SHA-256 before anything changes.

## Add-ons

| Add-on | Builds | How it runs |
| --- | --- | --- |
| Lecram (`renodx-dlss5.addon64`) | 10.8 | ReShade add-on. In a game without DLSS it runs through Feeder NR, which uses rtxForge's own 8.5 build. |
| ShortFuse (`renodx-dlss.addon64`) | 26.1025.0009 | Hooks the game's own DLSS calls, so it needs a 64-bit game with DLSS. |
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
- **With OptiScaler, it must be on MFG Only first.** Otherwise two NR tools
  would process the same frame.
- **Another tool's files are kept.** rtxForge refuses the install rather than
  replace them.

A pairing that hasn't been confirmed on a Forge Lab test copy is marked as
**not verified** in the check. It can still be installed.

## Combos

The **Combo** picker fills both slots at once. The built-in **Characters and
world** combo pairs:

- **Environment:** Lecram 10.8.
- **Character:** ShortFuse for character detail.

**Save combo…** stores the current slots under a name, with up to 100 saved
combos. Every combo is available for every game. Each game checks a combo
against itself, so one saved in a DLSS game is refused in a game without DLSS
when it uses ShortFuse.

Saved combos live in `nr-combos.json` in the rtxForge state folder, and both
apps share them.

## Remove

**Remove** deletes only files rtxForge recorded that are still unchanged. A
changed file is kept and listed. ReShade.ini keys are put back to the values
recorded at install, and OptiScaler's `LoadReShade` is restored. Your other
ReShade settings are kept.

## Still to confirm in a game

- ShortFuse's ReShade.ini section. It's inferred as `[renodx-dlss]` from the
  add-on file.
- Each pairing running together.
- Old and New models per add-on.
