# DirectX 9, DirectX 10 and 32-bit Feeder NR

In **Packages → Feeder setup**, keep a verified local Feeder stack and NR model,
then choose **Get DX9/DX10 support**. rtxForge downloads pinned public Feeder,
ReShade and dgVoodoo2 archives into its own storage. It does not run their
installers or change any game during this step. The consumer and NR model
remain the same verified, locally supplied files as the existing Feeder route.

Rescan the library. A supported game offers **Install Feeder NR**. Review its
recipe and file changes before installing. These additional routes are
experimental; file validation does not establish rendering quality in a game.

Game details lists each built-in install route and its requirements. Discovery
checks the executable's renderer, architecture and native DLSS evidence for each
package independently of the installed package. A DirectX 11 executable with a
retained DLSS DLL can qualify for Feeder without qualifying for Skynizz. Feeder's
own SR runtime is not treated as evidence of game-native DLSS. When another
package owns the current files, restore it before switching so its original-file
recovery boundary remains intact.

| Game | Recipe |
| --- | --- |
| 32-bit DX9 | dgVoodoo2 translates DX9 to DX11; 32-bit ReShade and Feeder send frames to a separate 64-bit helper. |
| 64-bit DX9 | dgVoodoo2 translates DX9 to DX11; the existing 64-bit Feeder route processes the frames. |
| 32-bit DX10 | 32-bit ReShade and Feeder send frames to the 64-bit helper. |
| 64-bit DX10 | Feeder's 64-bit helper add-on sends frames to the helper process. Upstream has not qualified this route in a game. |
| 32-bit DX11 | 32-bit ReShade and Feeder send frames to the 64-bit helper. |

The game and helper keep their own architecture-correct hooks. Helper recipes
put the NR runtime and consumer under `host64`, alongside the helper executable.
Game-side shaders stay beside the game. The supplied Lumenite shader supports
the non-compute path needed by DX10. These recipes provide NR only.

DX9 setup starts with the dgVoodoo watermark enabled so the translation layer
can be checked. It uses DX11 output and 1 GB of reported VRAM. After confirming
the wrapper and a moving-scene NR result, the watermark can be disabled in
`dgVoodoo.conf`. Later repairs preserve this file and existing depth/tuning
configuration. Use borderless mode for the helper's compositor panel; the
standard in-game panel package update does not install an x64 panel in an x86
game.

Install refuses existing foreign graphics hooks and helper folders. Restore
those mods through their owner before switching routes. rtxForge records the
exact originals of every file its recipe changes. **Restore Original Files**
uses those originals, including the wrapper and helper. Running games, changed
review inputs, and conflicting graphics hooks remain blocked. Anti-cheat games
can use an otherwise compatible recipe only after acknowledging the reviewed
offline-only notice. This does not disable anti-cheat or support online play.
Use the game's offline mode and restore original files before going online.
The acknowledgement is specific to the current review and executable; changed
game or anti-cheat files require another review. Automatic offline launch is
offered only for a matching game-specific profile, currently Gears E-Day.

If discovery picked a launcher or prerequisite, use **Game details → Overview →
Game executable → Choose EXE**. Choose the actual Windows EXE inside the game's
folder. Support is rescanned after saving. **Use detected** clears the choice.
Restore installed features before moving the target to another subfolder so
their restore records stay accessible.

Offline imports can put the files listed in `providers/feeder-legacy.json` in a
`legacy` subfolder of the local stack. Each file must match the pinned size,
SHA-256 and architecture. The public archives are retained in app storage;
the provider does not redistribute their binaries.

Upstream instructions: [Feeder's pinned DX9/DX10 and helper documentation](https://github.com/jlrouzies-fr/DLSS5-Feeder/blob/3c09eabcd138a68d144b6cc396a23e6b493eea4d/README.md).
