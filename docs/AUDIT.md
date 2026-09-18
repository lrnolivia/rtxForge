# v3 audit and rewrite

Audited the supplied v3 Python source, launcher, package manifests, and pinned upstream source. The bundled opaque launcher was not executed during inspection. Extracted archive members were checked for traversal, links, duplicates and oversized entries.

| Baseline finding | RTXForge decision |
|---|---|
| NR initially disabled | NR + MFG explicitly writes Enabled=true at install; no in-game toggle required to initialize it. |
| NR-only and fallback branches | Removed. Both routes require native frame-generation evidence. |
| One-at-a-time workflow | Explicit batch selection, all-target preflight, sequential transactional application. |
| Late manifest writes and unjournaled repair | Each target uses backups, before/after hashes and a recoverable transaction journal; batch records track partial completion. |
| Broad injector/addon moves | Conflicts block; exact owned files are handled with recovery copies. |
| Global NR unlink and backup-tree deletion | Retained at user request as a separate previewed action, with verified recovery copies before any removal and explicit confirmation. |
| Native-provider restore from historical mappings | Not imported; native files remain protected. |
| Size-only NR selection and duplicate archive members | Authenticate pinned archive and select the exact root NR member. |
| NR panel called unconditionally | Deferred at user request. Stock inactive panel remains in MFG Only; optional source patch retained. |
| Changing downloaded releases | Versioned provider manifest pins release, hashes, Streamline/DLSS-G payload identity and fallback headless Git blob identities. Upgrades are explicit. |

The 0.4.2 default profile is native Streamline DLSS-G input (`FGInput=dlssg`) to DLSS-G output with `FGNvngxReplacement=none`; Ada MFG unlock and Blackwell kernels stay enabled; automatic interpolation/reflex markers remain; forced DMFG stays disabled; flip metering/reflex sync remain disabled. Artur/Enabler Headless remains packaged only as an inactive compatibility fallback. NR starts enabled with WorkingScale 0.70, DualFeature=true, PreUpscale=false, one pass and the baseline sharpness profile. Already-migrated user tuning survives subsequent installs.

## Verification on 2026-09-09 UTC

- Real pinned upstream archive, private Streamline/DLSS-G payload, fallback headless module and NR model downloaded and verified successfully.
- Six production-path fixture checks passed at 06:38 UTC: mixed routes and startup NR; route-switch rollback; tuning preservation; interrupted-write recovery; conflicting/duplicate target refusal; owned uninstall/rollback with unchanged native-file/save controls.
- Focused global cleanup check passed at 06:43 UTC: recovery of files and empty directories, external drift refusal, unrelated-file preservation, and lab/recovery scan exclusion.
- No installed game was modified or launched. These are installer checks, not graphics/runtime proof.

Local reports:

- `/var/mnt/Games/Ada-Lab/RTXForge/verification/26645fa15e3d491d927bd910e87d00bd/result.json`
- `/var/mnt/Games/Ada-Lab/RTXForge/verification/567bdde37ced4870bb42cf0c5ab6d504/result.json`

## Remaining limits

The stock NR panel is visible in MFG Only. Application state is portable by default, with optional explicit state-root override. The installer does not set launch options automatically or establish game compatibility from successful file deployment. A batch is recoverable per target, not an all-games atomic transaction. Stale operation locks require inspection of recovery state before manual removal.

## Historical panel build

An earlier private/custom-loader experiment built a bounded NR-panel patch against the pinned upstream commit. That builder and its acceptance metadata are no longer part of the public production repository; this section is retained only as historical audit context. Runtime panel behavior was never promoted to production evidence.

## Repair crash correction

Legacy manifest import referenced `re.fullmatch` without importing `re`, causing a NameError after game selection. The missing import is fixed. Focused Linux and Windows legacy-manifest regression checks pass. Unexpected menu exceptions now retain the traceback and return to the menu rather than closing the terminal.

## Report-driven correction and panel result

The user's 0.1.1 report exposed overbroad conflict checks: RenoDX attribution text was treated as an injector, as were native dependencies under other executables and engine folders. Conflict checks now examine active binaries beside the selected executable. Identified Microsoft Windows Image Helper DLLs are preserved and fingerprinted as inputs. Unknown adjacent loaders still block. The interactive menu can explicitly exclude blocked games with SKIP before presenting a new APPLY preview.

A read-only repair preflight against all 19 exact targets in the report completed: 18 ready, Forza Horizon 6 blocked by its third-party winmm.dll. No game files were written. A focused regression verified preservation of attribution text, native dependency subdirectories and identified Microsoft dbghelp.dll, while an unknown winmm.dll still blocks.

A historical GitHub Windows build succeeded and its artifact identity was verified at the time. The associated builder metadata has since been removed from the public production repository. No installed game received it automatically.

## 0.1.3 interaction update

Added animated activity and elapsed time around long operations, with per-game batch counts and plain-terminal fallback. Removed the preparation prompt and separate SKIP confirmation. Excluded games are listed explicitly; the interactive batch now has one final yes/no confirmation. Cleanup and recovery also use yes/no. Command-line confirmation flags retain their existing contract. Focused checks covered default cancellation, progress completion/error cleanup and animated terminal output. No game operations were run for this UI change.

## Prepared-payload cache recovery

`packages.py` no longer treats reconstructible prepared-payload drift as a permanent install blocker. Listing/hash/manifest/source-identity drift causes the derived `payload/` and `files.json` to be discarded and rebuilt from the still hash-pinned archive. The source archive itself remains hash-guarded. Readonly mode refuses without mutation. Focused regression tests cover listing drift, incomplete extraction, and readonly behavior.
