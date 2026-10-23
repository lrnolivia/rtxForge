# Independent rendering bridge

An experimental, pass-through DirectX 12 diagnostic add-on. It observes native
resource lifetimes, shader fingerprints, descriptor updates, command-list
recording and submission. This first stage does not enable DLSS SR or FG.

The shared recorder is independent of the game adapter. Valhalla's adapter stays
unprofiled until captures establish native scene color, depth, geometric motion,
jitter and the TAA/HUD boundary. Texture size/format alone is not verification.
The current `providers/render-bridge/source.json` records that distinction.

Build with Visual Studio 2022 C++ tools and a checkout of ReShade at the SDK commit
in the source receipt:

```powershell
windows/build/Build-RenderBridge.ps1 -SdkPath G:/path/to/reshade -Output G:/path/to/output
```

The output is an unbundled `rtxforge-render-bridge.addon64`; the app does not
automatically install it. Use a separate test directory with a compatible x64
ReShade build that enables full add-on support. Keep all existing graphics
providers in the original game directory. This add-on accepts D3D12 only.

The first capture starts after 180 presents and lasts two presents. Press F10
while the target process is foreground to capture another two. Reports go to
`%LOCALAPPDATA%/rtxForge/diagnostics/render-bridge/<pid>/`. An optional
`rtxforge-render-bridge.ini` beside the add-on accepts `[Capture] AutoFrame`,
`Frames` (1–4) and `MaxEvents` (64–8192). Set AutoFrame=0 for manual capture.
Capturing and writing a report may hitch; this is a diagnostic, not a benchmark.

Reports explicitly use CPU command-recording order. Submission observations link
command lists; they do not establish GPU execution order. Unbounded descriptor
ranges are sampled to 64 entries and truncation is reported. Resource, pipeline,
descriptor and event budgets are finite. Missing inputs remain missing.
Empty descriptor banks do not consume the view/descriptor budgets. Reports
include catalog sizes, individual drop reasons and constant sample truncation.

Use `python windows/render-bridge/analyze_capture.py <capture.json>` to inspect
coverage and the observed texture/shader binding graph. This reports attachment
and descriptor observations, not semantic input identification or GPU order.
Older captures without expected descriptor types have incomplete coverage counts.

The controlled D3D12 harness accepts `--descriptor-stress` to initialize 262,145
null SRVs before its scene views. Validate its actual capture with
`python windows/render-bridge/tests/verify_harness_capture.py <capture.json>`.
The same scene/motion/depth graph must survive null initialization with zero drops.

For an isolated failure reproduction, `[Diagnostics] LogExceptions=1` enables
bounded, local first-chance fault observations in `exceptions.txt` beside the
capture reports. It records native addresses, stack frames and a module catalog;
it preserves the application's exception handling. An observed exception may be
handled normally and does not alone prove a crash. Logging is off by default.
The harness `--exception-probe` raises and handles a synthetic access violation
to verify that observation leaves the application's handler and rendering intact.

The next stages are GPU readback/visual verification of candidates, a Valhalla
TAA/upscale adapter, SR evaluation, then native 2x FG and the existing rtxForge
Universal MFG component. Source/build success does not satisfy those stages.
