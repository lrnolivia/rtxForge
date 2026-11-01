# Game Mode parity

This inventory compares the prototype against `gui/game_mode*.py`, Windows `GameModeView.*`, `Views/GamePage.xaml`, `Services/EngineForgeService.cs`, the shared `DesktopService`, and the Windows JSON host at the prototype's base revision `fe0fd231bad19fa2e40d0c37595ac44c60be4c57`.

“Connected” means the UI calls the existing service contract. It does not mean a real install, restore, game launch, Steam write or settings write was performed during development. Those actions were deliberately not exercised against the user's installation.

## Implemented

| Function | Prototype implementation | Evidence |
| --- | --- | --- |
| Library discovery | Existing manifest/VDF parsers, actual saved game folders, removed-game preference | Five fixture tests; real local reader passed (50 games at latest check); count reflects the current local snapshot |
| Cached artwork | Saved role overrides take priority; bounded initial snapshot, lazy local artwork hydration and exact-app-ID Steam CDN fallbacks | Reader fixtures and real cache checks; large saved images load without overflowing the snapshot |
| Library layouts | Posters, wide artwork and list; direct tile-to-details flow; no duplicate summary card | Headless responsive checks |
| Library presets | Desktop Presets layout, MFG modes/ratios, ordered shared control schema, reset/select/apply-to-all | Fixture verifies configured exact targets and tuning units; default token runs after successful reviewed game batches |
| Search | Immediate local title search and honest no-results state | Headless search/reset check |
| Batch selection | Select game tiles, review selected install or restore | Connected to exact selected engine rows |
| Details composition | Compact full-width fading hero, Bakbak title/poster, sidebar sections by default (Tabs optional), scroll collapse275→128px, translucent cards | Desktop and narrow screenshots |
| Compatibility/ownership | Targeted existing-service scan; unverified state stays explicit until scanned | Adapter binds actual service; no invented eligibility |
| Feature package / mode | Per-operation package and NR/MFG mode choices | Existing `prepare` settings contract |
| Feature tuning | Existing 38-control schema, original runtime units, package availability rules | Schema loaded from `providers/skynizz-bridge/controls.json` |
| Install, apply, reset | Fresh exact-target scan → `prepare` → confirm exact `execute` token | Contract fixtures verify token and target preservation |
| Repair / restore | Existing reviewed operation routes and recovery ownership | Connected; no real game mutation acceptance claimed |
| Adoption | Existing detected-adoption route; availability from engine record | Connected; no real adoption performed |
| Native DLSS update / restore | Existing `prepare_dlss` / `update_dlss` and `dlss_restore_review` / `run` | Connected exact-token routes |
| Review/trust/errors | Engine-ready and skipped rows, warnings, source/offline acknowledgement, refusal states | Headless trust gate and no-execute-before-confirm checks |
| Progress/cancel/discard | Real host events; safe cancellation; exact token release | Contract fixtures verify cancel and discard |
| Package catalog | Source lock records plus on-demand hardware-aware existing catalog | Local reader and connected `packages` method |
| Package choice | Reviewed shared default-provider change | Existing shared settings service |
| Custom package | Existing archive inspector and trusted exact inspection token for selection | Connected `package_inspect` / `package_use` |
| ReShade / RenoDX extras | Exact source path, existing review/apply and tool recovery routes | Connected `extra_review` / `extra_restore_review` / `run` |
| Matching RenoDX HDR | Existing game-specific HDR install/remove review | Connected `hdr_review` / `run` |
| Notes | Existing note record loaded before editing; saves preserve the record | Connected `notes_get` / `notes_save` |
| Functional tests | Existing start/finish service; observations remain distinct from user-visible quality | Connected, no actual test run against a game |
| Diagnostics | Existing exact-game diagnostic report | Connected `diagnose` |
| Bug reports | Existing dynamic required fields, corrected facts, optional logs/notes, exact redacted review, local ZIP save | Connected `report_draft` / `report_preview` / `run`; no upload exposed |
| Shell appearance | Global Clear/Light/Dark; independent Details-only tint; strictly scoped actual per-game accent or neutral; local text size/motion | Headless theme/tint/reduced-motion checks |
| Shared settings | Reviewed Graphics, Overlay, Library and Controller preferences | Existing settings load/save and shared overlay validation |
| Global NR/MFG | One-time bulk review through existing managed-package plans | Connected `global_review` |
| Native menus / overlay packages | Existing reviewed menu and package updates | Connected `overlay_ui_review` / `overlay_package_review` |
| Recovery | Existing interrupted-operation / restore records and exact review | Connected `recoveries` / `recovery_review` |
| Steam launch | Valid numeric app ID handed to the same OS Steam URI route used by the native shell | Connected; deliberately not launched in verification |
| Steam shortcut | Existing shortcut/artwork review and exact installation token | Connected; deliberately not applied |
| Windows storage | Existing inventory and unreferenced-download cleanup review | Connected; deliberately not cleaned |
| Windows app update | Existing check and verified-installer download; prototype never replaces installed app | Connected; not downloaded or launched in verification |
| Native file selection | System picker for package and extra source paths | Native compile; picker deliberately not opened |
| Controller foundation | Spatial focus, select/back, shoulder navigation, focused-select adjustment | Synthetic standard-mapping test; polling stops while hidden |
| Keyboard/mouse | Tab/arrows, Enter/Escape, section shortcuts, accessible controls | Headless navigation and form checks |
| Windows native build | Real Tauri/WebView2 executable using project-local Rust | Release build succeeds; read-only native preview launched |

## Remaining implementation and acceptance

The prototype is **not yet a full replacement** for current Game Mode. These remaining items are explicit rather than hidden behind working-looking buttons:

| Item | Current limit |
| --- | --- |
| Linux runtime acceptance | Shared shell and Linux service adapter exist; no Linux build, GTK/WebKit runtime or game acceptance has run on this Windows host |
| Physical controllers | Standard-mapping synthetic input passes; Xbox/PlayStation/Nintendo/Steam hardware, reconnect and couch acceptance need real-device checks |
| Controller preferences | Family/hint preferences and matching labels are ported; physical hardware acceptance remains pending |
| Artwork editing | Custom paths, SteamGridDB connection/search/results and reviewed art/sync adapters are ported; account/network and real-write acceptance remain pending |
| Executable chooser and folder actions | Native selection and reviewed executable preferences and copy-location controls are ported. Opening game folders in the OS remains an explicit shell integration gap; platform/runtime acceptance remains pending |
| Per-game overlay preferences | Inherited/per-game editor and exact reviewed preference updates are ported; real-write acceptance remains pending |
| Dynamic MFG / preset UX | Automatic/Custom/Dynamic mode, ratios, ordered control schema and library Presets page are ported; dynamic availability follows each verified provider/game. No separate named-preset system is claimed |
| Legacy Feeder source setup | Intentionally superseded: managed package acquisition is required. No mandatory user-supplied Feeder/Vulkan source prompt is ported. Optional custom package imports remain available |
| App update promotion | Checking/downloading uses the existing reviewed Windows method; closing/replacing the installed app remains outside this isolated prototype |
| Linux storage/update routes | Windows-specific storage/update methods are not offered as if Linux-compatible |
| Live effect controls | Remain in the existing in-game overlay until a verified observed session is connected; this shell does not simulate live activity |
| Native distribution | Windows portable preview bundles private Python, reader and engine files and retains prior local versions. Linux bundles, signing and updater integration remain |
| Real file operations | Install/restore/repair/adoption/Steam/settings writes were tested with contract fixtures, not against installed games; native mutation/game acceptance remains pending qualification |

The browser preview defaults to the safe local reader. `Run.ps1 -Engine` makes the connected operations available for explicit local development; `RTXFORGE_PREVIEW_READ_ONLY=1` overrides engine opt-in and is used for the visible review; confirmations then invoke the real engine.


The Library uses real saved overrides or the shared artwork signature algorithm. Idle titles are neutral. Selected poster/capsule cards and complete list rows use the solid game accent with readable ink, matching the desktop selection model. Hero artwork and Details tint span the frame; section cards use one material without duplicate outer-glass layers. These visual checks do not establish native feature parity or acceptance of real game operations.
