# rtxForge 0.5.7

Global and per-game controls now edit NR Strength, Sharpening and MFG Multiplier directly in each managed game’s OptiScaler.ini. NR and sharpening offer independent Off / Light / Medium / Strong choices. MFG offers Off / 2× / 3× / 4× / 5× / 6×.

NR Light/Medium/Strong uses intensity and skin structure 1.00/1.50/2.00. Sharpening uses 0.25/0.375/0.50. Off disables the relevant effect; files remain installed. Existing provider/profile ownership, native FG routing and settings backups remain intact. NR Only skips MFG writes and MFG Only skips NR writes.

Changing any global control changes Reset All Settings to Apply Settings. Applying updates eligible managed games and saves the global defaults. Per-game Apply changes only that game's INI. Saved INI values populate the panel; unmatched values show as Custom or Game-controlled. Close affected games before applying. Actual generated-frame ratios require runtime support; enabling frame generation in game remains necessary.

Validation: five focused tests passed for preset install/repair/reset, independent sharpening and Off settings, 2×–6× mapping, profile exclusions, per-game versus global preference scope, and no-download/no-Steam-write reset. GTK demo check passed for Apply/Reset label transitions, independent per-game controls, selection and Settings; screenshots inspected. No live game writes or game launches were performed. GitHub publishing is deferred at Lauren's request.
