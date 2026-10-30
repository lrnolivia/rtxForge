#pragma once
#include <windows.h>
#include <d3d11.h>
#include <d3d12.h>
namespace ForgeGlassHooks {
bool Prepare(HWND window);
void Draw11(ID3D11Device*,ID3D11RenderTargetView*);
void Draw12(ID3D12Device*,ID3D12CommandQueue*,ID3D12Resource*);
void Shutdown();
}
