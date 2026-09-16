# RTXForge 0.5.1

Updates DLSS-Unlocked to NR-v0.9.1 and y4my to the September 15 nightly. Both archives are SHA-256 pinned. The y4my nightly uses the same source commit as v4; its private NVIDIA runtimes are extracted from a separately pinned same-provider v4 archive. No game-native NVIDIA DLL replacement is introduced.

Non-Steam matching now requires the executable to belong to the selected game directory. Desktop preparation checks launch-settings availability before installation. NR receipts distinguish DLSS-Unlocked pre-SR from y4my dual-feature configuration.

Validation: actual new archives extracted and hashed; y4my combined payload validated; Crimson Desert lab deployment loads DLSS-Unlocked 0.9.1 and reports successful Ada architecture-gate/kernel patches against game-native DLSS-G 310.6.0. Actual multi-frame gameplay remains unverified. Earlier NR worked according to the user, with severe slowdown after tuning. Default NR tuning has been restored.
