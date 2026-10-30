#pragma once
#include <windows.h>
#include <d3d11.h>
#include <d3d12.h>
#include <cstdint>

// Versioned, synchronous boundary. Every borrowed string is valid for the call;
// the renderer never retains a game-owned resource or callback result pointer.
#pragma pack(push,8)
namespace ForgeGlass {
inline constexpr uint32_t Abi=2;
struct Value {const char* key;float value;};
struct Snapshot {
    const char* title;const char* accent;
    const Value* values;uint32_t count;
    bool nrKnown,nrRunning,nrWarming,fgKnown,fgRunning,framesKnown;
    double nrGpuMs,gameFps,displayedFps,measuredRatio;
    bool nrAvailable,fgAvailable,liveTuning;
    const char* helperJson{};
    const Value* defaults{};uint32_t defaultCount{};
};
struct Host {
    uint32_t size,abi;
    void* user;
    bool (*read)(void*,Snapshot*);
    bool (*apply)(void*,const Value*,uint32_t);
    // Existing panel helper JSON protocol, outside rendering; false means busy.
    bool (*request)(void*,const char*);
    void (*log)(void*,const char*);
};
struct Frame {
    uint32_t size,abi;
    ID3D11Device* device;
    ID3D11RenderTargetView* target;
    HWND window;
    float mouseX,mouseY,wheel;
    bool mouse[3],keys[256];
    bool visible,welcome;
    // 0: SDR; 1: linear scRGB (80 nits/unit); 2: PQ/Rec.2020 HDR10.
    // Unknown transfer functions are rejected.
    uint32_t colorSpace;
};
using Draw=bool(__cdecl*)(const Host*,Frame*);
// Call only after all game work for this image has been submitted to queue.
// The swapchain adapter owns the authoritative before/after resource states.
struct Frame12 {
    uint32_t size,abi;
    ID3D12Device* device;ID3D12CommandQueue* queue;ID3D12Resource* target;
    D3D12_RESOURCE_STATES before,after;
    Frame input;
};
using Draw12=bool(__cdecl*)(const Host*,Frame12*);
using Release=void(__cdecl*)();
static_assert(sizeof(void*)==8,"The glass overlay boundary requires a 64-bit host");
static_assert(sizeof(Value)==16 && sizeof(Snapshot)==104 && sizeof(Host)==48);
static_assert(sizeof(Frame)==312 && sizeof(Frame12)==352);
}
#pragma pack(pop)
