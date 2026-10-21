# Universal MFG Unlocker

The pinned 1.6.1 release is rtxForge's default MFG component for new NR + MFG and MFG Only installs with the Skynizz bridge. It is separate from the RenoDX **MFG Unlock 1.4.4** ReShade component, which remains a preview choice.

It loads through OptiScaler 10 as an ASI plugin: the pinned DLL is installed as `OptiScaler/plugins/MFGUnlocker.asi` with `[Plugins] LoadAsiPlugins=true`, and the bridge's integrated Ada unlock (`AdaMfgUnlock`, `AdaBlackwellKernels`) is turned off. The game's own Streamline DLSS Frame Generation stays the frame-generation path (`FGOutput=nofg`); OptiScaler's menu and INI own the multiplier and Dynamic MFG, and the unlocker's separate menu stays hidden. No second proxy or ReShade addon host is used. Games installed with the integrated unlock keep it until they are restored and installed again.

Upstream lists RTX 30 and 40 support; RTX 20 remains experimental. These are upstream compatibility claims. rtxForge's runtime validation in games is tracked separately and `runtime_verified` stays false until it passes.

[source.json](source.json) pins the upstream commit, archive, extracted Windows x64 DLL and notices. `LICENSE` and `NOTICE.md` are fetched from that exact commit and installed under `OptiScaler/licenses/`. The DLL embeds Intel-derived XeSS program data subject to Intel's terms; the MIT license alone does not cover those programs. Preserve all upstream and embedded third-party notices.

[Release](https://github.com/dashdogy/MFG-Unlocker/releases/tag/v1.6.1) · [Pinned source and instructions](https://github.com/dashdogy/MFG-Unlocker/tree/29504cdd5d209a25e3b91e809a7e0d6f9db8cbdc)
