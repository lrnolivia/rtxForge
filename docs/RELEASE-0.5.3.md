# RTXForge 0.5.3

Selected pipeline effects are enabled on install/repair, regardless of older saved dormant preferences. NR Only enables NR and disables the MFG unlock; MFG Only enables the unlock and disables NR; combined enables both. Game-native DLSS/FG settings remain controlled by the game. CLI offers --disable-effects for diagnosis.

No game tests or overlay-crash investigation were performed for this change. Lauren reports combined DLSS-Unlocked working in The Outer Worlds 2, NR Only in 007, and MFG Only in Cyberpunk 2077. These are user reports, not new automated runtime results.

SDK banner unchanged: standard indicator registry values inspected in the lab are already zero; replacing or patching DLLs just to remove the banner was avoided.
