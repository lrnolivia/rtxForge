# RTXForge 0.5.2

Adds DLSS-Unlocked NR Only and MFG Only pipelines to the shared engine, CLI and GUI. NR Only pins NR-v0.8.6, enables NR when startup effects are selected, and disables the Ada MFG unlock; leave game FG off. MFG Only pins NR-v0.9.1, omits NR files and updates matching existing native NVIDIA/Streamline DLLs from the pinned package. The transaction backs up original DLLs and restores them during uninstall. Pipeline changes require uninstall first.

The GUI uses simple pipeline buttons; no validation badges were added. Combined NR+MFG remains separate and unverified. Startup-effects setting is still respected.

Crimson lab evidence: user reports NR working with the earlier package and confirms 3x FG applied and working in gameplay with NR disabled and newer runtimes. These observations do not establish combined or other-game compatibility. Real Steam installation is undergoing a user reinstall and was not changed here.
