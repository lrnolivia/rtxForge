# In-game panel on Linux (Proton)

Status: candidate bridge and Linux host implemented; synthetic protocol tests pass.
The exact-source native DLL build and real Proton validation are still required.
The panel draws inside the game through OptiScaler's ImGui hook. The candidate
bridge detects Wine and uses prefix-local file mappings; Windows keeps its existing
named pagefile mappings.

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

## 2. Control channel (candidate implementation)

`ForgePanelChannel.h` uses `ntdll!wine_get_version` to select a file-backed mapping
under `%LOCALAPPDATA%\rtxForge`: `panel.<WinePID>.map` carries the 64-byte header and
two 32768-byte JSON slots; `controls.<WinePID>.map` carries the 512-byte controls
mailbox. Both keep the Windows protocol unchanged. Files use exclusive creation
and delete-on-close; a stale file is never truncated to admit a new session.

`scripts/linux_overlay_host.py` binds a channel only when a live Linux process has
the exact managed executable and channel mapped and an exact matching `WINEPREFIX`.
It opens files without following symlinks and checks owner, single-link count and
size. Wine PIDs and Linux PIDs are kept separate. Mailbox sequence fields use
explicit signed 32-bit access: Linux `ctypes.c_long` is not the Windows LONG type.

The app starts the helper when enabled. It answers hello/status/save/reset and
replays presets using the shared recipe-bound store and acknowledged mailbox.
Dynamic MFG requires confirmed per-game capability; unknown support is not an
opt-in. Replay retries a failed apply and stops when the app exits. The helper
routes global/menu reviews through the guarded shared APIs. Reviews expire after
five minutes and are bound to the exact Linux process and mapping inode; Apply
is single-use and rechecks files. Overlay setting changes still use the main app. It does not edit a running game's INI.

Synthetic tests cover message acknowledgement, mapping identity, unsafe file
rejection and bound save dispatch. They do not prove Wine mapping visibility,
real NR/MFG operation, focus behavior or game-rendered overlay output.

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
3. Save persists and replays on the next launch, and Dynamic and
   DLSS presets round-trip.
