# Windows preview qualification — 1 November 2026

This package is an isolated Game Mode UI preview. It reads the real local library, saved artwork and settings. Engine mutations require explicit development opt-in. It does not replace the production Desktop application or its updater.

## Passed

- TypeScript check and production Vite build; five Node tests and twenty Python fixture tests.
- Headless appearance, settings, Presets, library, library visuals, controls, UI polish, install flow, operation contracts, controller and general UI checks.
- Clear, Light and Dark materials; narrow and desktop layouts from 390 to 1440 pixels; reduced motion; direct game opening and focus restoration after artwork hydration.
- Install review, startup settings, exact target/token preservation, trust acknowledgement, progress, cancellation, discard, failure and restore paths using explicit fixtures. No installed game files were changed.
- Synthetic standard-mapping controller navigation, select adjustment, stepper/checkbox operation and keyboard navigation. Filled button text checks reached at least 4.5:1 in the tested palettes.
- Saved artwork-role precedence, large-image lazy loading, exact Steam app-ID fallbacks and refresh invalidation. The native Windows preview read 50 real local games, including saved custom artwork.
- Windows Tauri release executable. Its portable package read the library using its private Python runtime from outside the checkout.
- Windows Desktop hero presentation port: Debug build with zero warnings/errors and native fixture game opening with remote artwork. The native check caught and corrected an unsupported XAML float literal before packaging.

## Still requires qualification

- Linux compilation, WebKitGTK/Gamescope runtime and packaging.
- Physical controller families, reconnect and couch testing.
- Actual install, restore, repair, adoption, Steam integration and shared-settings mutations against disposable game installations.
- Signing, production updater integration and replacement of the existing native shells.

The Desktop hero port is included in the source change; the portable executable is the separate Game Mode preview. Build receipts identify the packaged source revision. Prior local preview versions and the existing Desktop installation are retained for rollback.
