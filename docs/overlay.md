# In-game tuning

The overlay opens for the compatible game you are playing. It keeps frame
generation and neural rendering visible, with Look, fine tuning, sharpening
and performance controls in expandable sections. The glass presentation offers Side Panel, Advanced and Bar layouts,
with a complete Settings screen and separate Appearance editor. Clear is the
default; Light and Dark have their own fixed material presets. Theme, text size
are available in Settings; overlay scale is adjusted in-game. The styling prototype retains
experimental font and material controls.

Reset icons restore individual values or sections to their documented
defaults. The main Reset action restores supported controls together. Undo and Redo keep
up to 32 edits for the current game process, including resets and preset loads.
These actions do not delete saved presets or change the startup preset.

The preset selector holds up to 12 named presets per game executable. Save
updates the named preset, or creates another when you enter a new name. A
changed name therefore duplicates the current tuning. An asterisk and Unsaved
changes distinguish session edits from the last loaded or saved configuration.
Saving retains the existing package-specific startup behavior. Delete removes
the named entry; current settings and the separate startup preset remain.
Presets from a different installed package remain listed but cannot be loaded.
Existing single saved presets appear as Saved preset.

Compare offers On / Off for neural rendering or two compatible saved presets.
Choose a mode, then switch between its two buttons while looking at the game.
Session edits remain separate from saved presets; comparison never saves a
preset automatically. Some settings, including DLSS render presets, take
effect when the game next creates the corresponding feature rather than on
the next displayed frame.

The DirectX 12 NR route supports independent settings for passes 2 and 3 when
multiple passes are selected. Inherit shared tuning preserves the previous
behavior, including any native-menu pass-style choice. Turning inheritance
off exposes the pass's own style, strength, local structure, local tone and
skin structure. Each pass keeps its own temporal history. Changing its model
tuning rebuilds that pass using the runtime's existing staggered creation
path. Other routes do not expose these overrides.

Performance history records up to 30 seconds of reported NR GPU time, rendered
FPS and displayed FPS while the panel is open. Missing or invalid measurements
produce gaps, and unsupported metrics say Not reported by this package. File
ownership indicators do not establish runtime activity. A requested frame
generation multiplier is separate from measured output.

Feeder reads model tuning at launch. Its panel saves those changes for the
next launch and switches NR through RenoDX's live toggle. It offers reset,
undo and named presets, with a restart message, but does not offer live A/B
tuning or independent pass overrides. Named presets need the updated
background helper; ordinary in-game editing and undo work without it.

The compact status card keeps indicators above a short, two-column frame
generation and neural-rendering readout. It expands into metadata and recent
measurements; Advanced shows that expanded view on Overview. Readouts use
reported runtime data and omit unavailable measurements.

The glass renderer uses the existing control bindings and helper protocol.
DX11 and DX12 adapters have native render fixtures for SDR and supported
scRGB/HDR10 output; gameplay acceptance and other API routes remain separate.
Unsupported output routes retain the
established renderer. The local screenshot preview stays available for styling.

Windows and Linux bundles that advertise a required glass revision automatically refresh
managed overlay packages. The refresh preserves tuning, named presets and
original-file recovery records, adds new DLLs only to verified empty locations,
and retries running or conflicting games. It does not replace foreign files.

Linux AppImage and Flatpak builds use native artifacts built from the same source
revision as the app. Packaging verifies their hashes, revision and matching glass
DLL before enabling the required refresh. Local source-only builds do not enable it.

Desktop and Game Mode expose illustrated layout choices, theme and text size.
Overlay scale is adjusted in-game, where its effect is visible. These choices are app-wide;
game-specific menu and shortcut choices remain separate. Windows shares these
preferences with the native appearance file, including edits made while the
overlay is open. Theme selection restores its material defaults while preserving
text size, scale and layout.

Refresh completion and unfinished games appear in an app notification. The last
update report remains available in Overlay settings; retries preserve earlier
successful updates. A verified shared installation record and portable original
backups let Windows and Linux recognize managed package updates made by the
other OS. Local Proton setup and original-file recovery are preserved. Changed
or unknown loaders and damaged backups still require attention.

The main NR controls include render resolution and a side-by-side processing-stage
and pass-count row. Counts use bounded steppers; continuous values use sliders.
Live NR dimensions appear only when the host reports a fresh completed model
evaluation. The expanded session card reports the observed runtime stack separately
from the graphics API; absent data stays unreported.

RenoDX HDR appears as a popout in Side Panel and Bar and as a dedicated Advanced
page when installed. Verified Mass Effect Legendary Edition and Control Resonant
add-on hashes have source-matched startup settings adapters. They expose all numeric
and choice shader preferences from those profiles. Peak-brightness calibration is
preserved by Reset. Changes queue while a game runs and apply after it closes;
restart the game to use them. These controls do not imply a live RenoDX settings
API. Other add-ons retain their native settings menu. Native-menu conflicts and
changed package files retain pending edits for review instead of overwriting them.

Each game's Tools page also accepts an optional architecture-matched custom
`.addon32` or `.addon64` HDR add-on. The review freezes the selected bytes and SHA-256;
future repairs keep this game-specific choice rather than replace it with the
automatic catalog. Automatic matching remains the default.

Clear keeps warm-white text and glyphs, with light accent headings. A restrained
shadow follows the actual foreground ink over bright surfaces, treating labels,
glyphs and values consistently. Existing glass gently softens bright highlights;
no extra row rectangles or shadow boxes are introduced. Dark surfaces receive no
added ink shadow. Light and Dark retain their own foreground palettes.
