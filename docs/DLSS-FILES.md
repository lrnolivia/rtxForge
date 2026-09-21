# DLSS Files

Older native DLSS files are updated automatically during feature installation.
The default-on **DLSS Files** switch is in Settings → Graphics →
Installation. Game Details → DLSS Files shows current native files and provides **Update Files** and
**Restore Files** for an individual game, with no separate selection wizard.

Restore uses the most recent verified backup for that game. It refuses files
changed by a game update or another tool, preserving backups instead of
overwriting those changes. Repeated restores walk back earlier updates.

Supported native files:

- `nvngx_dlss.dll` — Super Resolution
- `nvngx_dlssd.dll` — Ray Reconstruction
- `nvngx_dlssg.dll` — Frame Generation

Only existing files are replaced. Same-version, newer and unknown installed versions are
left untouched. OptiScaler/private runtime
folders and files recorded as feature-provider ownership are excluded. NR,
Streamline, FSR and XeSS changes are outside this first native DLSS file-management scope.
Anti-cheat detections, links/shared files, changed review inputs and running games
are refused. No launch options or global driver configuration are changed.

The default catalog is [Recol/DLSS-Updater-DLLs](https://github.com/Recol/DLSS-Updater-DLLs).
Each check resolves a single immutable commit. Downloads must match that commit's
Git blob ID, byte size and x64 PE version; transactions additionally record SHA-256
hashes. This verifies source integrity, not NVIDIA Authenticode signatures or
compatibility with every game. A game launch is still needed to establish runtime
compatibility. Downloaded DLLs are never executed by the tool. Automatic management applies
only to the games whose feature installation completed successfully. Network
failures are recorded in Activity without failing an otherwise successful feature
installation.

`providers/runtime_sources.json` defines the repository/ref/manifest/directory
adapter. A provider config's `runtime_source` object can override the same fields
for a compatible fork. Supported filenames remain explicitly constrained in the
runtime module. Existing source catalog and GUI dependencies are not imported from
DLSS Updater: this implementation uses rtxForge's discovery, process/ownership
checks, storage and hash-guarded transaction engine.

Backups live under the configured rtxForge state root's `runtime-transactions/`.
A failed partial game write attempts immediate rollback; earlier completed games
remain individually recoverable. Cache files live in `runtime-cache/`. Neither
location is inside the game folder. Do not remove transaction backups while they
are needed for recovery.

## Verification record

Research: Recol/DLSS-Updater commit `42c85404b906ac4af47cd132dde3dc1408201157`,
including catalog resolution and backup code. Observed DLL catalog commit
`676365de1718fe65e4ff71c4406c9ebae3b2489c`: SR/RR/FG `310.9.1.0`.
A real FG download passed source-content, size and PE-version verification
(SHA-256 `ff6e90eb78b827927dff5b4ecc6b1c870c2e9bca29ed9f48c7d348cc9e170b82`).
Lifecycle/guard/failure tests use disposable folders; no installed games were
updated to validate the tool.
