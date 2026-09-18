# Desktop integration

The GTK4/libadwaita UI is in `gui/rtxforge_gtk.py`. Library discovery remains toolkit-independent. `scripts/engine_bridge.py` adapts the imported transaction engine for the selected provider. Install, repair and uninstall prepare explicit previews; application occurs only after the action is confirmed.

Steam must be closed before applying. Desktop operations refuse interactive/elevated terminal operations instead of waiting invisibly. Failures are recorded per game; completed targets keep their recovery baselines.

Settings exposes MFG Only, NR + MFG, and DLSS-Unlocked NR Only. Test status, notes and manually bounded log capture live outside games in the configured report storage. Bench suppresses bulk install/repair; explicit selection remains available.

Application state defaults to the user's XDG state directory and may be overridden with `RTXFORGE_STATE_ROOT`. Existing legacy state under `/var/mnt/Games/Ada-Lab/RTXForge` is reused when it contains recognizable rtxForge state, preserving prior recovery records without making that Games-drive layout a requirement for other systems.

Older desktop Undo remains a compatibility path for prior installation records. The native-FG safeguards described in the 0.5.0 release apply to the new engine; they cannot reconstruct missing originals from older uninstalls.
