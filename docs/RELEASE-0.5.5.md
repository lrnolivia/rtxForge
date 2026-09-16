# rtxForge 0.5.5

Fresh installs use Lauren’s Avatar screenshot settings: sharpness override 0.50, Depth Aware (RCAS), RCAS/DA and motion-adaptive sharpening enabled. NR modes use 75% working scale, one Cinematic pass, intensity 2.00, local structure/tone 1.00, skin structure 2.00, auto skin mask and Apply Model enabled. Existing provider routing and automatic effect activation remain unchanged. Explicit saved tuning is preserved during repair; MFG Only does not enable NR.

Two focused tests passed: installation writes defaults and repair preserves custom NR/sharpening; MFG Only does not acquire NR settings. No game writes or runtime tests.

Avatar’s saved INI still contained the prior 0.75/1.50/1.00 NR values and automatic sharpening, unlike the supplied screenshot. The pinned OptiScaler 1776cbf1 overlay has a separate Save Settings button; Close does not call SaveIni. The inspected Avatar log contains no save attempt. This supports unsaved runtime changes as a likely explanation, not proof of a failed write. Use Save Settings at the bottom of the overlay to persist later tuning.
