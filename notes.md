
## 2026-09-18 — GTK UI redesign checkpoint

Current UI work is intentionally being committed as a checkpoint for another agent to continue.

### Working / preserve

- Local --live-smoke Progress -> Done flow works correctly.
- Active Progress modal must NEVER contain or expose a scrollbar.
- Progress modal currently removes the generic Gtk.ScrolledWindow rather than merely hiding its scrollbar.
- Existing Progress / Done presentation has had substantial prior work. Do not casually replace or redesign it.
- NR Strength and Sharpening retain granular decimal controls.
- Library artwork sizing / responsive work is in progress.
- Dashboard app icon and bulk-action relocation work is partially implemented.

### Known UI regressions to fix next

- Dashboard Install All, Remove All, and Reset All buttons are cramped.
- Their labels wrap onto multiple lines. They should remain comfortable single-line controls.
- Moving those controls changed the dashboard layout enough that the lower tuning/options area is cramped toward the left.
- The lower NR Strength / Sharpening / MFG controls should retain their previous full-width layout instead of being squeezed beside the dashboard actions.
- The dashboard currently shows the OLD rtxForge icon.
- Replace it with the current rtxForge artwork/icon.
- The app artwork should be substantially larger, functioning as a real dashboard/hero illustration similar to the large artwork treatment used by GameBridge Lite rather than a tiny app-menu icon.
- Preserve the overall GNOME/libadwaita visual language.
- Do not regress the no-scroll active Progress modal while fixing the dashboard.

### Validation

Run before accepting the next UI revision:

    python3 -m py_compile gui/rtxforge_gtk.py
    git diff --check
    python3 gui/rtxforge_gtk.py --smoke-test
    python3 gui/rtxforge_gtk.py --live-smoke

