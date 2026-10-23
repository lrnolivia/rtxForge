# Linux distributions

The AppImage carries rtxForge's own code and runs it with the host's Python, GTK4 and libadwaita. It does not bundle a desktop toolkit. The engine that installs and restores features needs only Python 3 and the NVIDIA driver, so it is the same on every distribution. Only how the window opens differs.

| Host | Desktop app | Tested |
|---|---|---|
| Bazzite, Fedora 44+ | Opens directly | Native: tests, AppImage, GTK smoke, Game Mode |
| CachyOS, Arch, EndeavourOS, Manjaro | `sudo pacman -S --needed python-gobject gtk4 libadwaita`, then opens directly | CachyOS userland in a container: full Linux test set and GTK smoke |
| SteamOS 3.5+ (Desktop Mode) | Opens in a distrobox (below); no root needed | Same distrobox route tested on Bazzite; no SteamOS hardware run yet |
| Ubuntu 24.04, Debian 12 and older | libadwaita is older than 1.7, so it opens in a distrobox | Guidance tested on Ubuntu 24.04 |
| openSUSE Tumbleweed | `sudo zypper install python3-gobject typelib-1_0-Gtk-4_0 typelib-1_0-Adw-1` | Not run |

If something is missing, the app says what and how to fix it, as a dialog when opened from the menu and as text in a terminal. `RTXForge.AppImage --frontend-doctor` prints what it found.

## The distrobox route

```sh
./RTXForge.AppImage --container
```

The first run creates an Arch Linux container named `rtxforge` with PyGObject, GTK4 and libadwaita (about 600 MB, a few minutes). Later launches, including from the app menu, use it automatically. Opening the app from the menu without a container offers to set it up.

The container shares your home folder, `/run/media`, `/mnt` and `/var/mnt` (SD cards and second drives), `/proc` (so the Steam-running and game-running checks see host processes) and the NVIDIA driver (`--nvidia` when the host driver is loaded). `steam` and `xdg-open` inside it run on the host. The window uses GTK's GL renderer there, because GTK's Vulkan renderer picks the container's Mesa driver and loses the Wayland connection. Remove it with `distrobox rm rtxforge`. Game files, recovery records and settings live in your home folder, so they are kept either way.

## What else differs

- **Steam location.** Libraries are found from `~/.local/share/Steam` (SteamOS, CachyOS, Bazzite), `~/.steam/steam` and `~/.steam/root` (symlinks to the same place), Flatpak Steam (`~/.var/app/com.valvesoftware.Steam`), each root's `libraryfolders.vdf`, and mounted drives under `/run/media`, `/mnt`, `/var/mnt` and `/media`. A game's Proton prefix is looked up in its own library first, so SD-card games use the card's `compatdata`.
- **GPU check.** `nvidia-smi` is used when it works. Otherwise the model and driver version come from `/proc/driver/nvidia`, which is all a container or a minimal driver install provides.
- **Archives.** DLSS-Unlocked and Skynizz packages are ZIPs read by Python. The y4my `.7z` package uses libarchive, `7z`/`7zz` or `bsdtar`. Arch-based systems, SteamOS included, have `bsdtar` because pacman depends on libarchive.
- **AppImage without FUSE.** Setup (`install.py`) extracts instead of mounting. To run the AppImage itself on a host with no FUSE, set `APPIMAGE_EXTRACT_AND_RUN=1`.
- **SteamOS Game Mode.** Closing Steam there ends the session, so use Desktop Mode for installs that need Steam closed, or the Steam-open route, which writes the DLL override into the game's prefix instead of Steam's launch options.

None of this establishes NR or MFG in a game on these distributions. Runtime results stay per game and per OS, as in [proton-prerequisites.md](proton-prerequisites.md).
