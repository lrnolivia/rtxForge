# Provider-specific NR

Supersedes the historical v3e plus separate NR-layer design. Version 0.5.0 uses complete pinned providers; never combine one provider's loader with another provider's NR files.

- y4my Multipass: its own dual-feature/DLSS enlargement settings, plus a suitable local NR model. Missing models refuse installation before writes.
- DLSS-Unlocked: its standalone NR-v0.8.6 package, `RunBeforeSR=true`, `DeferredDLSS=false`, with y4my-only NR options removed.

NR + MFG enables NR before launch when **Enable effects at startup** is on. Off creates a dormant diagnostic setup. MFG Only omits NR DLLs and forwarders; stock upstream NR panels may remain visible. No runtime success is inferred from an installed file or a visible panel.
