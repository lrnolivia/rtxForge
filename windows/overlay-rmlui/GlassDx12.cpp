#include <GlassOverlay.h>
#include <d3d11on12.h>
#include <wrl/client.h>
#include <mutex>
#include <unordered_map>
using Microsoft::WRL::ComPtr;
extern "C" bool __cdecl ForgeGlassDraw(const ForgeGlass::Host*,ForgeGlass::Frame*);
namespace {
std::mutex bridgeMutex;
struct Wrapped {ComPtr<ID3D12Resource> source;ComPtr<ID3D11Resource> texture;ComPtr<ID3D11RenderTargetView> view;};
struct Bridge {
    ComPtr<ID3D12Device> game;ComPtr<ID3D12CommandQueue> queue;
    ComPtr<ID3D11Device> device;ComPtr<ID3D11DeviceContext> context;ComPtr<ID3D11On12Device> interop;
    std::unordered_map<ID3D12Resource*,Wrapped> images;
} bridge;
bool Init(ForgeGlass::Frame12& f) {
    if(bridge.game.Get()==f.device&&bridge.queue.Get()==f.queue)return true;
    bridge={};if(f.queue->GetDesc().Type!=D3D12_COMMAND_LIST_TYPE_DIRECT)return false;
    IUnknown* queues[]={f.queue};D3D_FEATURE_LEVEL level;
    const HRESULT result=D3D11On12CreateDevice(f.device,D3D11_CREATE_DEVICE_BGRA_SUPPORT,nullptr,0,queues,1,0,&bridge.device,&bridge.context,&level);
    if(FAILED(result)||FAILED(bridge.device.As(&bridge.interop))){bridge={};return false;}
    bridge.game=f.device;bridge.queue=f.queue;return true;
}
}
void ReleaseGlassBridge12(){std::lock_guard lock(bridgeMutex);if(bridge.context)bridge.context->Flush();bridge={};}
extern "C" __declspec(dllexport) bool __cdecl ForgeGlassDraw12(const ForgeGlass::Host* host,ForgeGlass::Frame12* frame) {
    if(!host||!frame||host->abi!=ForgeGlass::Abi||host->size!=sizeof(*host)||frame->abi!=ForgeGlass::Abi||frame->size!=sizeof(*frame)||!frame->device||!frame->queue||!frame->target||frame->input.colorSpace!=0)return false;
    std::unique_lock lock(bridgeMutex,std::try_to_lock);if(!lock.owns_lock())return true;if(!Init(*frame))return false;
    auto& image=bridge.images[frame->target];
    if(!image.texture){
        // Keep references until resize/shutdown explicitly releases the bridge.
        // A finite swapchain cannot grow this cache without bound.
        if(bridge.images.size()>8){bridge.images.erase(frame->target);return false;}
        D3D11_RESOURCE_FLAGS flags{};flags.BindFlags=D3D11_BIND_RENDER_TARGET;
        if(FAILED(bridge.interop->CreateWrappedResource(frame->target,&flags,frame->before,frame->after,IID_PPV_ARGS(&image.texture)))){bridge.images.erase(frame->target);return false;}
        if(FAILED(bridge.device->CreateRenderTargetView(image.texture.Get(),nullptr,&image.view))){bridge.images.erase(frame->target);return false;}image.source=frame->target;
    }
    ID3D11Resource* resources[]={image.texture.Get()};bridge.interop->AcquireWrappedResources(resources,1);
    auto input=frame->input;input.device=bridge.device.Get();input.target=image.view.Get();
    const bool rendered=ForgeGlassDraw(host,&input);frame->input.visible=input.visible;
    bridge.interop->ReleaseWrappedResources(resources,1);bridge.context->Flush();
    return rendered;
}
