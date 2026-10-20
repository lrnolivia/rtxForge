# Universal MFG Unlocker

The pinned 1.6.1 release is a separate integration candidate from the RenoDX **MFG Unlock 1.4.4** component. It is not yet an installable rtxForge package or a replacement for the integrated NR + Ada MFG bridge.

Upstream lists RTX 30 and 40 support; RTX 20 remains experimental. Its OptiScaler DLSSG output on RTX 30 is also experimental. These are upstream compatibility claims, not rtxForge runtime validation.

The supported plugin route requires OptiScaler 10, loading the pinned DLL as `OptiScaler/plugins/MFGUnlocker.asi` with `[Plugins] LoadAsiPlugins=true`. OptiScaler owns the multiplier and the unlocker's separate menu stays hidden. No second proxy or ReShade addon host is required for this route. A compatible NR composition must disable competing internal unlocks and pass exact-recipe install, live controls, restore and game testing before this candidate is offered for deployment.

[source.json](source.json) pins the upstream commit, archive, extracted Windows x64 DLL and notices. Obtain `LICENSE` and `NOTICE.md` from that exact commit alongside the package. The DLL embeds Intel-derived XeSS program data subject to Intel's terms; the MIT license alone does not cover those programs. Preserve all upstream and embedded third-party notices.

[Release](https://github.com/dashdogy/MFG-Unlocker/releases/tag/v1.6.1) · [Pinned source and instructions](https://github.com/dashdogy/MFG-Unlocker/tree/29504cdd5d209a25e3b91e809a7e0d6f9db8cbdc)
