# Game Mode delivery qualification - 2 November 2026

Native Game Mode enables reviewed engine operations by default. The browser demo
remains read-only; `RTXFORGE_PREVIEW_READ_ONLY=1` also disables native operations.
It is installed separately from Desktop, with previous versions retained.

## Verified

- 42 Python adapter, screening, routing and lifecycle tests; 17 JavaScript unit
  tests; TypeScript checking and the production frontend/native builds.
- Windows and Linux complete native packages, private Python/engine resolution,
  offline screenshot worker, full payload verification and installed-host
  `hello`/`settings_get` smoke from outside the source checkout. Both native CI
  jobs passed source `8243238f2c334587aeb057efc9ceff616b8635f4`.
- Review fixtures cover exact targets and tokens, trust acknowledgements,
  progress, cancellation, discard, failure and restoration. Real subprocess
  fixtures verify transaction drain on EOF and concurrent one-time review
  consumption. Live game files were not changed for these checks.
- Synthetic standard-mapping controller input covers menus, fields, steppers,
  checkboxes, shoulder guards and focus restoration. This is fixture evidence,
  not a physical controller acceptance result.
- Responsive shell, hero, screenshot loading/cropping and contrast checks cover
  narrow layouts and full-width 4K at 150%. The shell stays fixed on scroll;
  only Details' hero collapses. Library shows two complete rows at default size.
- The installed Windows release opens fullscreen, reads 50 real library games
  and shared Desktop artwork/accents, and enables the reviewed operation host.
  Closing the previous revision also removed its owned WebView processes.
- Reviewed native 3840x2160 Library, Details and Presets captures were supplied
  to the website worker. Their manifest records the keyboard-prompt deviation;
  they do not claim connected-controller evidence.

## Native resource measurements

On the measured Windows machine, a settled 4K Library at 150% (CSS 2560x1440,
DPR 1.5) used approximately 693 MiB of private process memory and 490 MiB of
dedicated GPU memory. Eight samples over roughly 15 seconds measured 1.65% of
one CPU core. Summed working sets were about 705 MiB and can double-count shared
pages. These are observations on one machine, not a cross-device budget pass.

First contentful paint was 352 ms and Library readiness 1.78 s. Completing all
50 artwork conversions took about 31 s; the Library was usable earlier. The
offline screening process is temporary, uses one CPU inference thread and exits
after each batch. Six test images took 2.84 s and peaked around 474 MiB private
memory. Glass rendering still has a substantial GPU footprint at 4K.

## Evidence still needed

- Physical controller families, reconnect behavior and couch use.
- Native Linux WebKitGTK/Gamescope GUI and controller acceptance. Successful
  compilation, package validation and host smoke do not establish these.
- Actual install, restore, repair, adoption, Steam writes and shared-settings
  changes against disposable game installations, followed by gameplay checks.
- Signing and production updater integration. Game Mode does not replace the
  existing Desktop updater or publish new updater assets.

Screenshot screening rejects text-heavy promotional panels and many text HUDs,
but icon-only HUDs can escape and environmental signs can be false positives.
Failed screening does not admit unknown images. See SCREENSHOT_SCREENING.md.
The Desktop hero port remains deferred at the user's request.
