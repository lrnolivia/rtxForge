# Skynizz NR + Ada MFG build

This combines the exact Skynizz NR source and the existing y4my Ada MFG unlock in one OptiScaler loader. `source.json` binds both revisions and the patch digest. The patch ports configuration persistence, the early NVIDIA module-load hook, the in-memory Ada capability/kernel unlock, and Streamline frame-count state handling. It retains Skynizz's NR/cache implementation and its null-function guard.

Build on Windows with Visual Studio C++ v143 and the upstream submodules checked out, using `windows/build/Build-SkynizzBridge.ps1`. The build emits only the combined loader, NR forwarder, upstream INI, license and exact-source receipt. The NVIDIA NR model remains user-supplied. The existing private NVIDIA/Streamline MFG stack is sourced separately through rtxForge's verified y4my companion package.

The patch and derived binary are GPL-3.0-only, matching both upstream projects. Full corresponding upstream source, submodule revisions, the patch and build command remain linked through the receipt. This is a combined-build candidate; source/build and staging checks do not establish RTX40 in-game NR, MFG output or frame pacing. Default promotion requires those runtime checks.
