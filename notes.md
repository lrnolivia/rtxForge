## 2026-09-18 — Classic UI 0.6.4 checkpoint

### Preserve

- Current dashboard / Library visual direction.
- Existing Active Process / Progress presentation.
- Existing Done presentation.
- Progress and Done must never expose a generic Gtk.ScrolledWindow scrollbar.
- Current Game Details redesign and compact hero.
- Current artwork-derived game accent treatment.
- NR Strength and Sharpening retain granular decimal controls.
- Enhancement Mode-style segmented controls are preferred for small mutually exclusive option sets.
- Boolean Settings options remain normal switches.
- Numeric continuous options remain sliders / numeric controls.

### Library completed

- Artwork Size works live.
- A live Library artwork-size slider sits beside the view controls.
- Poster and Wide Capsule geometry is bounded and consistent.
- Poster and Wide Capsule cards within a view share uniform dimensions.
- Card height normalizes to the tallest footer so Details buttons remain aligned.
- Compact card titles may wrap while shorter titles gain elastic space above Details.
- Poster artwork retains its fixed portrait frame.
- Wide Capsule uses actual capsule artwork rather than borrowing poster artwork.
- Artwork overlays, badges, fallback text, and selection controls do not determine card geometry.
- Details buttons use full artwork-derived accent backgrounds with contrast-aware text.
- Poster / Wide Capsule / List selection in Settings uses a segmented control and previews live.

### Game Details completed

- Long Game Details titles are never ellipsized.
- Titles wrap naturally when needed.
- Longer titles step down through smaller font sizes to remain readable within the hero.
- Preserve the existing hero, artwork credit, navigation, and close-control behavior.

### Progress / Done completed

- Active Process hover scrollbar regression is fixed.
- Done hover scrollbar regression is fixed.
- The generic dialog ScrolledWindow is removed when Progress takes over the dialog.

### Next and only planned classic-UI feature

Build the **compact sticky Library / Dashboard header**.

The sticky header should:

- appear once the large dashboard controls scroll away;
- remain much shorter than the full dashboard;
- keep only genuinely useful persistent Library controls / context;
- feel native to the existing GTK/libadwaita design;
- avoid recreating the entire dashboard in miniature.

### Release path

1. 0.6.4 — completed Library / Game Details polish checkpoint.
2. Sticky Library / Dashboard header.
3. 0.7.
4. Freeze classic UI apart from maintenance and approved fixes.
