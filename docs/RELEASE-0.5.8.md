# RTXForge 0.5.8

Focused global and per-game settings pages, adaptive tabs and wider sidebars with normal row spacing. Compact tuning pods, consistent unfilled profile icons, and game accent colors.

Artwork prefers the current Steam account’s local custom grid and cached library images. Cached artwork persists until explicitly refreshed; artwork jobs do not block game operations.

Compact progress dialogs provide Cancel for enhancement and settings operations. Cancellation completes the current safe game boundary, then restores session snapshots in reverse order. External file changes or a newly running game/Steam block unsafe recovery; copies and a receipt remain in desktop-operations. Legacy cleanup/Undo tools retain their existing behavior.

Validation: GTK demo smoke; focused engine reset/cancellation tests; scoped recovery copy test. No live game modifications or runtime stability claim. GitHub publication remains deferred. DLSS updater follows separately.
