# Glass overlay

RmlUi owns the document, controls, typography and interaction model. The local
preview and game DLL share `OverlayController.h`; the DLL embeds the same RML,
RCSS, raw logo, icons and licensed fonts.

`GlassOverlay.h` defines a size- and version-checked synchronous boundary.
The host supplies runtime measurements, supported control values/defaults and
the existing helper channel. Requested multipliers never become measured FPS.
Unknown values remain unreported. All game mutations pass through the existing
validated control bindings and recipe-bound preset helper.

The DX11 adapter composites over the supplied game render target and restores
the caller's context state. DX12 uses a D3D11On12 wrapper on the actual game
queue, after game submissions at the swapchain boundary. It acquires/releases
the image using authoritative resource states, and flushes before Present.
Resize and device cleanup must release the renderer's image references.

The material blends the scene and tint before a prefiltered Gaussian blur;
grain, optical rim and foreground are composed afterward. Window shadows
soften continuously over locally bright scenery. Adaptive foreground tuning
uses asynchronous, low-resolution scene measurements.

Build with `windows/build/Build-GlassOverlay.ps1`. It pins the dependency and
runs the native render/state fixture before writing the DLL receipt. Keep all
dependency notices with distribution packages.

## Acceptance

The standalone native fixtures exercise DX11 RGBA/BGRA rendering, context-state
restoration, teardown and DX12 queue interoperability. They do not establish
gameplay compatibility or performance. HDR and other unvalidated transfer
functions are rejected. Vulkan and legacy DirectX renderer acceptance remains
separate. The established renderer remains the fallback on unsupported routes;
do not promote a beta based solely on these fixtures.
