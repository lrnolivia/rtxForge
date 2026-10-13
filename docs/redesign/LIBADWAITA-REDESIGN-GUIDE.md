# rtxForge — Libadwaita Redesign Guide

## Authoritative direction

This document records the current approved redesign direction.

When older mockups or historical guidance conflict with this file, this file wins.

## Product goal

rtxForge should feel like a polished native GNOME gaming application.

Use stock Adwaita neutral surfaces for chrome; let game artwork supply color.

Do not turn rtxForge into a generic optimizer/control-panel aesthetic.

## Shell

Locked unless explicitly changed.

- Adw.ApplicationWindow
- Adw.ToolbarView
- Adw.NavigationSplitView
- permanent left sidebar
- seamless flat headerbar/content
- full-width content pages
- current enlarged branding and left inset
- current taller navigation/selectable controls

Navigation:

- Home
- Game Library
- Forge
- Settings
- separator
- Recovery

Tools is intentionally absent.

## Home

Exact approved composition:

1. cinematic game hero using Assassin's Creed Unity as the current target;
2. `Bring newer RTX features to your games.` with RTX green;
3. Review Library;
4. Forge Available Games;
5. four summary cards;
6. Recent Games horizontal strip;
7. System Status;
8. Quick Actions.

Responsive behavior:

- four stat cards -> 2x2 compact
- Recent Games stays horizontal and scrolls
- Quick Actions may stack compact
- icon wells stay centered
- text remains intentional and left aligned

Do not add new Home features until responsive presentation is visually approved.

## Game Library

The finished classic viewport is the migration target.

Do not reinterpret its layout or interaction.

Preserve:

- card geometry/styling/behavior
- selection
- filters
- artwork-size slider
- artwork scaling
- Poster/Wide Capsule behavior

Color harmonization is allowed later if behavior/layout are preserved.

List view is being rebuilt separately and is not a redesign target right now.

## Forge

Full-width page.

Use native Adwaita groups/rows.

Contains:

- Feature Mode: NR / MFG / Both
- NR Strength
- Sharpening
- MFG multiplier
- review-first Library actions

## Settings

Full-width page.

Contains appearance/layout, metadata/artwork, runtime, and diagnostics.

Approved visually.

## Recovery

Full-width page.

Contains safety/review-first messaging, recovery records, old NR cleanup, and reports.

Approved visually.

## Standalone windows

Game Details and Game Settings remain standalone windows.

Do not convert them into main-stack pages or modals.

## Progress / Done

Progress is strongly protected.

Done is less protected and may be reconsidered later.

## Migration strategy

Finish Home first.

Then transplant the finished Library viewport into the shell intact.

Only after those boundaries are stable should redesign controls begin wiring to production
state.
