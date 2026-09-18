# Provenance

Current provider sources, exact release URLs, branch commits and archive hashes are recorded in `providers/lock.json` (checked 2026-09-18). y4my uses the pinned `nightly` archive at commit `7b7220bbb499` plus its separately hash-pinned v4 runtime companion. DLSS-Unlocked uses NR-v0.9.1 for the current general package, while the NR Only profile is deliberately pinned to NR-v0.8.6 / `00fbc5873363`. Provider records remain marked `runtime_verified: false` unless game/runtime behavior has been explicitly established.

The transaction engine derives from the user-supplied RC1.38 archive. Original source/archive hashes and adaptation location are in `engine/SOURCE.json`. The AppImage packages this source and the desktop adapter; provider DLLs are downloaded and verified separately. Upstream license files are retained with provider payloads.

`provider.json` retains the legacy provider fields needed by the older terminal composition path and a migration hint for existing local rtxForge state. Current desktop provider selection and package identity come from `providers/lock.json`. Historical custom-loader build machinery is not part of the public production workflow.
