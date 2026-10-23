#pragma once
// The rtxForge panel (providers/skynizz-bridge/ForgePanel.h) in its own Dear
// ImGui context, drawn into a DirectX 11 back buffer. No ImGui types here, so
// the ReShade add-on can include this beside ReShade's own ImGui wrappers.
#include <d3d11.h>

namespace feeder_panel
{
enum class Output { sdr, scrgb, hdr10 };

struct Frame
{
    ID3D11RenderTargetView *target;
    float width, height;
    float mouse_x, mouse_y, wheel;
    bool mouse[3];
    Output output;
};

bool Init(ID3D11Device *device, HWND window);
// Returns true while the panel wants keyboard and mouse input.
bool Draw(const Frame &frame);
void Shutdown();
// Called when a game's DirectX 11 device goes away.
void Release();
}
