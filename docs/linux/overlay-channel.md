# In-game panel on Linux (Proton)

Status: host side implemented and fixture-tested only (`scripts/proton_overlay.py`,
`tests/linux_runtime/test_proton_overlay.py`). Nothing here has been run with a real
game under Proton yet.

The panel (ForgePanel) is drawn inside the game by the Skynizz bridge through
OptiScaler's existing ImGui hook, so the Windows build runs under Proton unchanged.
Two host-side pieces differ on Linux.

## 1. Preferences (implemented)

The bridge reads these once at game start with `RegGetValueW(HKEY_CURRENT_USER, ...)`:

| Value | Type | Source setting |
|---|---|---|
| `Software\rtxForge\Overlay\InGamePanel` | DWORD | `overlay_renderer == 'game'` |
| `PanelKey`, `PanelModifiers` | DWORD | `panel_hotkey` (Windows VK codes; Ctrl=2, Alt=1, Shift=4) |
| `Advanced` | DWORD | `overlay_controls == 'classic'` |
| `UseOptiScaler`, `ShortcutKey` | DWORD | `optiscaler_ui`, `optiscaler_hotkey` (Insert 0x2D, F8 0x77, Disabled 0) |
| `Software\rtxForge\Overlay\Games\<exe path>` | SZ | `#RRGGBB|Title` (accent and title only) |

Under Proton, HKCU is the game prefix's `pfx/user.reg`. `proton_overlay.plan()` shows
exactly which values would change. `apply()` writes only those values and records what
was there before. `restore()` puts back only values that still hold what rtxForge
wrote, so later edits made in the prefix are kept. The engine also runs `restore()`
when the game is restored. Every write refuses while anything runs in the prefix,
because wineserver owns `user.reg` then and would overwrite the edit on exit. It also
refuses when the file changed since review.

Unverified:
- The exact DOS spelling the game reports from `GetModuleFileNameW` (for example
  `Z:\home\...` versus `Z:\var\home\...` on Bazzite). The engine writes both spellings,
  and only the accent and title depend on this.
- Whether a Proton update rewrites `user.reg` keys outside `Software\Wine`. It should
  not, but a real session has not checked it yet.

## 2. Control channel (prototype; needs a decision)

The panel creates `Local\rtxForge.panel.<pid>` (header and seqlock in
`providers/skynizz-bridge/ForgePanelChannel.h`, 64 + 2×32768 bytes). Per-game presets use
`Local\rtxForge.controls.<pid>`. A native Linux process cannot open a Wine named section.
Until the channel exists, the panel shows "Waiting for the background helper" and its
controls still apply live in process. Only Save, Reset, preset replay and the reviews
need the helper.

| Option | How | For | Against |
|---|---|---|---|
| **A. Wine-side relay exe** | A tiny console exe started in the game's prefix (the game's Proton `wine64` with the same `WINEPREFIX`) opens both mappings as the Windows helper does and forwards JSON over an AF_UNIX socket (or 127.0.0.1 TCP with a per-session token) to the Linux app. | No bridge change. | A second Windows binary to build in CI (mingw) and sign. It must reach the *same* wineserver: a Proton or wine version mismatch starts a second server and the mapping is invisible. Process lifetime, and a launch per game session. Adds latency. |
| **B. File-backed mapping (recommended)** | Under Wine only (`ntdll!wine_get_version` present), `ForgePanelChannel::Init` maps `C:\users\steamuser\AppData\Local\rtxForge\panel.<pid>.map` (`CreateFileW` + `CreateFileMappingW`) instead of a pagefile section. Wine maps file sections with `mmap(MAP_SHARED)` of the Unix file, so the Linux app's `mmap` of `pfx/drive_c/.../panel.<pid>.map` sees the same bytes. | Same protocol and seqlock, with no extra process. The Linux half already exists (`PanelChannelFile`, `channel_path`). Windows keeps the pagefile name. | Needs a bridge change and the native owner's CI build plus a Windows regression check. Stale files after a crash need validation: the helper must check magic, version and that `visible` is set, and remove files whose Wine PID is gone. The Wine PID is not the Linux PID, so the helper finds channels by globbing the prefix folder. |
| C. Read Wine's anonymous section | Find the game's `anonmap` file through `/proc/<pid>/map_files`. | No change anywhere. | Depends on Wine internals and CAP_SYS_ADMIN or ptrace rules. Rejected. |

Recommendation: B. The bridge change is small and confined to `Init`/`Lifetime`
(Wine-only path, then delete the file on clean exit). A is the fallback if a bridge
change is not wanted. Either way the Linux helper answers with the same handlers as
`windows/engine-host/companion_controls.py` and `NativePanelCoordinator`. Today
`proton_overlay.handle()` answers only `hello`/`status`/`discard-review`, and refuses
writes honestly ("Use rtxForge on Linux for this").

## 3. Shortcut and focus

The panel key is read in the game process by OptiScaler's input hook (`OptiInput`). The
Linux host never registers a global grab for it, so opening the panel cannot move focus
to another window. This holds by construction on X11, Wayland and Gamescope alike, but
it has not been observed in a real game yet.

A separate desktop-wide shortcut is needed only for the standalone companion window:

- **Wayland (KDE Plasma 6, GNOME 48+):** `org.freedesktop.portal.GlobalShortcuts`
  (`CreateSession` → `BindShortcuts`). The user approves the binding in a system
  dialog. The compositor delivers `Activated` without focus changes. Not available on
  older GNOME or wlroots without the portal backend.
- **X11:** `XGrabKey` works but intercepts the key from the game. Avoid it, or limit
  it to keys the game does not use.
- **Gamescope / Steam Game Mode:** third-party apps get no global shortcut or
  always-on-top surface. The Steam overlay belongs to Steam. The in-game panel is the
  only reliable surface there. Treat the standalone companion as Desktop Mode only.

## Verification still needed (Ada, real Proton)

1. Prefix preferences reach the bridge: the log shows `rtxForge panel startup: enabled true`.
2. Backtick opens and closes the panel with no focus change or stutter (KDE Wayland,
   X11, and Gamescope separately).
3. Once B or A exists: Save persists and replays on the next launch, and Dynamic and
   DLSS presets round-trip.
