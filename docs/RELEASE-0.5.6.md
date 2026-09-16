# rtxForge 0.5.6

Reset Settings is available on each game card, in game details and for selected games. Reset All Settings updates managed games across the library to the app’s current sharpening, NR and menu-font defaults, including games marked Bench. Each game retains its installed provider and feature profile. Running, unmanaged or incomplete installations are skipped with an explanation.

Reset writes only OptiScaler.ini, backs up the prior bytes, and leaves runtime DLLs, game saves and Steam launch options unchanged. Steam may remain open; the affected game must be closed. Repair Files continues to preserve explicit saved tuning.

Actions now say Add Enhancements, Repair Files, Remove Enhancements and Reset Settings. Library-wide actions explicitly say All.

Current visual defaults are the Avatar Strong settings introduced in 0.5.5. Reset also applies UseHQFont=false, the upstream Vulkan menu-font workaround already used on install/repair. Avatar and Crimson already had it disabled during read-only inspection, so this is not a proven fix for their reported menu instability.

Validation: five focused checks cover fresh defaults, repair preservation, config-only reset and backup, running/unmanaged/linked refusal, idempotence, and the desktop path with Steam open and downloads/launch writes forbidden. GTK demo smoke passed with file writes disabled. No live game reset or runtime testing was performed.
