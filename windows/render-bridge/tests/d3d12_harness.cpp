#include <Windows.h>
#include <d3d12.h>
#include <dxgi1_4.h>
#include <d3dcompiler.h>
#include <wrl/client.h>
#include <array>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <string>
using Microsoft::WRL::ComPtr;
static LONG WINAPI crash(EXCEPTION_POINTERS *p) {
    if(p->ExceptionRecord->ExceptionCode!=EXCEPTION_STACK_OVERFLOW && p->ExceptionRecord->ExceptionCode!=EXCEPTION_ACCESS_VIOLATION) return EXCEPTION_CONTINUE_SEARCH;
    HANDLE out = CreateFileW(L"harness-crash.txt", GENERIC_WRITE, FILE_SHARE_READ, nullptr, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if(out == INVALID_HANDLE_VALUE) return EXCEPTION_EXECUTE_HANDLER;
    CONTEXT context = *p->ContextRecord;
    for(unsigned i=0;i<48;++i) {
        DWORD64 base=0; const auto entry=RtlLookupFunctionEntry(context.Rip,&base,nullptr); char text[256]{};
        sprintf_s(text,"%u code 0x%lx base 0x%llx offset 0x%llx\r\n",i,p->ExceptionRecord->ExceptionCode,base,context.Rip-base);
        DWORD written=0; WriteFile(out,text,static_cast<DWORD>(std::strlen(text)),&written,nullptr);
        if(!entry) break;
        void *data=nullptr; DWORD64 establisher=0;
        RtlVirtualUnwind(UNW_FLAG_NHANDLER,base,context.Rip,entry,&context,&data,&establisher,nullptr);
        if(!context.Rip) break;
    }
    CloseHandle(out); return EXCEPTION_CONTINUE_SEARCH;
}
static void check(HRESULT hr) { if (FAILED(hr)) throw std::runtime_error("D3D12 harness HRESULT=" + std::to_string(static_cast<unsigned>(hr))); }
static void exception_probe() {
    for (unsigned i = 0; i < 20; ++i) {
        __try { RaiseException(EXCEPTION_ILLEGAL_INSTRUCTION, 0, 0, nullptr); }
        __except (GetExceptionCode() == EXCEPTION_ILLEGAL_INSTRUCTION ? EXCEPTION_EXECUTE_HANDLER : EXCEPTION_CONTINUE_SEARCH) {}
    }
    __try { ULONG_PTR parameters[] = {0, 0x1234}; RaiseException(EXCEPTION_ACCESS_VIOLATION, 0, 2, parameters); }
    __except (GetExceptionCode() == EXCEPTION_ACCESS_VIOLATION ? EXCEPTION_EXECUTE_HANDLER : EXCEPTION_CONTINUE_SEARCH) {}
}
static D3D12_CPU_DESCRIPTOR_HANDLE at(ID3D12Device *d, ID3D12DescriptorHeap *heap, D3D12_DESCRIPTOR_HEAP_TYPE type, unsigned n) {
    auto h = heap->GetCPUDescriptorHandleForHeapStart(); h.ptr += d->GetDescriptorHandleIncrementSize(type) * n; return h;
}
static ComPtr<ID3DBlob> shader(const char *text, const char *entry, const char *target) {
    ComPtr<ID3DBlob> code, error;
    const auto hr = D3DCompile(text, std::strlen(text), nullptr, nullptr, nullptr, entry, target, D3DCOMPILE_OPTIMIZATION_LEVEL3, 0, &code, &error);
    if (FAILED(hr) && error) std::cerr << static_cast<const char *>(error->GetBufferPointer()); check(hr); return code;
}
static const char *hlsl = R"(
cbuffer Camera : register(b0) { float4x4 view; float4 jitter; };
struct V { float4 p:SV_Position; float2 uv:TEXCOORD; };
V vs(uint id:SV_VertexID) { V o; o.uv=float2((id<<1)&2,id&2); o.p=float4(o.uv*float2(2,-2)+float2(-1,1),.5,1); return o; }
struct M { float4 color:SV_Target0; float2 motion:SV_Target1; };
M scene(V i) { M o; o.color=float4(i.uv,.25,1); o.motion=jitter.xy; return o; }
Texture2D<float4> colorIn:register(t0); Texture2D<float2> motionIn:register(t1); Texture2D<float> depthIn:register(t2);
float4 post(V i):SV_Target { int3 p=int3(clamp(i.uv*float2(320,180),0,float2(319,179)),0); return float4(colorIn.Load(p).rg,motionIn.Load(p).x+depthIn.Load(p)*.1,1); }
)";
int main(int argc, char **argv) {
    ULONG guarantee=65536; SetThreadStackGuarantee(&guarantee); AddVectoredExceptionHandler(1,crash);
    HWND window = nullptr; HANDLE fence_event = nullptr;
    try {
        WNDCLASSW wc{}; wc.lpfnWndProc = DefWindowProcW; wc.hInstance = GetModuleHandleW(nullptr); wc.lpszClassName = L"RtxForgeDiagnosticHarness";
        RegisterClassW(&wc);
        // A hidden test surface avoids taking foreground input from games or other work.
        window = CreateWindowW(wc.lpszClassName, L"rtxForge rendering harness", WS_OVERLAPPEDWINDOW, 0, 0, 640, 360, nullptr, nullptr, wc.hInstance, nullptr);
        if (!window) throw std::runtime_error("Could not create test surface");
        ComPtr<IDXGIFactory4> factory; check(CreateDXGIFactory1(IID_PPV_ARGS(&factory)));
        ComPtr<ID3D12Device> device; check(D3D12CreateDevice(nullptr, D3D_FEATURE_LEVEL_11_0, IID_PPV_ARGS(&device)));
        if (argc > 1 && std::string(argv[1]) == "--exception-probe") exception_probe();
        D3D12_COMMAND_QUEUE_DESC qd{}; ComPtr<ID3D12CommandQueue> queue; check(device->CreateCommandQueue(&qd, IID_PPV_ARGS(&queue)));
        DXGI_SWAP_CHAIN_DESC1 sd{}; sd.Width=640; sd.Height=360; sd.Format=DXGI_FORMAT_R8G8B8A8_UNORM; sd.SampleDesc.Count=1;
        sd.BufferUsage=DXGI_USAGE_RENDER_TARGET_OUTPUT; sd.BufferCount=2; sd.SwapEffect=DXGI_SWAP_EFFECT_FLIP_DISCARD;
        ComPtr<IDXGISwapChain1> swap1; check(factory->CreateSwapChainForHwnd(queue.Get(), window, &sd, nullptr, nullptr, &swap1));
        ComPtr<IDXGISwapChain3> swap; check(swap1.As(&swap));
        auto heap = [&](D3D12_DESCRIPTOR_HEAP_TYPE type, unsigned count, bool visible) {
            D3D12_DESCRIPTOR_HEAP_DESC d{}; d.Type=type; d.NumDescriptors=count; d.Flags=visible?D3D12_DESCRIPTOR_HEAP_FLAG_SHADER_VISIBLE:D3D12_DESCRIPTOR_HEAP_FLAG_NONE;
            ComPtr<ID3D12DescriptorHeap> result; check(device->CreateDescriptorHeap(&d,IID_PPV_ARGS(&result))); return result;
        };
        auto rtv=heap(D3D12_DESCRIPTOR_HEAP_TYPE_RTV,4,false), dsv=heap(D3D12_DESCRIPTOR_HEAP_TYPE_DSV,1,false), srv=heap(D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV,3,true);
        // Real games initialize large banks of null descriptors before creating scene views.
        // Keep that heap alive so this reproduces catalog pressure rather than heap reuse.
        ComPtr<ID3D12DescriptorHeap> null_bank;
        const bool stress = argc > 1 && std::string(argv[1]) == "--descriptor-stress";
        if (stress) {
            constexpr unsigned null_count = 262145;
            null_bank = heap(D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV, null_count, false);
            D3D12_SHADER_RESOURCE_VIEW_DESC empty{};
            empty.Format=DXGI_FORMAT_R8G8B8A8_UNORM; empty.ViewDimension=D3D12_SRV_DIMENSION_TEXTURE2D;
            empty.Shader4ComponentMapping=D3D12_DEFAULT_SHADER_4_COMPONENT_MAPPING; empty.Texture2D.MipLevels=1;
            for (unsigned i=0; i<null_count; ++i)
                device->CreateShaderResourceView(nullptr,&empty,at(device.Get(),null_bank.Get(),D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV,i));
        }
        std::array<ComPtr<ID3D12Resource>,2> back;
        for(unsigned i=0;i<2;++i) { check(swap->GetBuffer(i,IID_PPV_ARGS(&back[i]))); device->CreateRenderTargetView(back[i].Get(),nullptr,at(device.Get(),rtv.Get(),D3D12_DESCRIPTOR_HEAP_TYPE_RTV,i)); }
        auto texture = [&](DXGI_FORMAT format, D3D12_RESOURCE_FLAGS flags, D3D12_RESOURCE_STATES state) {
            D3D12_RESOURCE_DESC d{}; d.Dimension=D3D12_RESOURCE_DIMENSION_TEXTURE2D; d.Width=320; d.Height=180; d.DepthOrArraySize=1; d.MipLevels=1; d.Format=format==DXGI_FORMAT_D32_FLOAT?DXGI_FORMAT_R32_TYPELESS:format; d.SampleDesc.Count=1; d.Flags=flags;
            D3D12_HEAP_PROPERTIES hp{}; hp.Type=D3D12_HEAP_TYPE_DEFAULT;
            D3D12_CLEAR_VALUE cv{}; cv.Format=format; cv.DepthStencil.Depth=1;
            ComPtr<ID3D12Resource> r; check(device->CreateCommittedResource(&hp,D3D12_HEAP_FLAG_NONE,&d,state,&cv,IID_PPV_ARGS(&r))); return r;
        };
        auto color=texture(DXGI_FORMAT_R16G16B16A16_FLOAT,D3D12_RESOURCE_FLAG_ALLOW_RENDER_TARGET,D3D12_RESOURCE_STATE_RENDER_TARGET);
        auto motion=texture(DXGI_FORMAT_R16G16_FLOAT,D3D12_RESOURCE_FLAG_ALLOW_RENDER_TARGET,D3D12_RESOURCE_STATE_RENDER_TARGET);
        auto depth=texture(DXGI_FORMAT_D32_FLOAT,D3D12_RESOURCE_FLAG_ALLOW_DEPTH_STENCIL,D3D12_RESOURCE_STATE_DEPTH_WRITE);
        device->CreateRenderTargetView(color.Get(),nullptr,at(device.Get(),rtv.Get(),D3D12_DESCRIPTOR_HEAP_TYPE_RTV,2));
        device->CreateRenderTargetView(motion.Get(),nullptr,at(device.Get(),rtv.Get(),D3D12_DESCRIPTOR_HEAP_TYPE_RTV,3));
        D3D12_DEPTH_STENCIL_VIEW_DESC depth_desc{}; depth_desc.Format=DXGI_FORMAT_D32_FLOAT; depth_desc.ViewDimension=D3D12_DSV_DIMENSION_TEXTURE2D;
        device->CreateDepthStencilView(depth.Get(),&depth_desc,dsv->GetCPUDescriptorHandleForHeapStart());
        std::array<ID3D12Resource*,3> inputs{color.Get(),motion.Get(),depth.Get()};
        const std::array<DXGI_FORMAT,3> formats{DXGI_FORMAT_R16G16B16A16_FLOAT,DXGI_FORMAT_R16G16_FLOAT,DXGI_FORMAT_R32_FLOAT};
        for(unsigned i=0;i<3;++i) { D3D12_SHADER_RESOURCE_VIEW_DESC v{}; v.Format=formats[i]; v.ViewDimension=D3D12_SRV_DIMENSION_TEXTURE2D; v.Shader4ComponentMapping=D3D12_DEFAULT_SHADER_4_COMPONENT_MAPPING; v.Texture2D.MipLevels=1;
            device->CreateShaderResourceView(inputs[i],&v,at(device.Get(),srv.Get(),D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV,i)); }
        D3D12_DESCRIPTOR_RANGE range{}; range.RangeType=D3D12_DESCRIPTOR_RANGE_TYPE_SRV; range.NumDescriptors=3;
        D3D12_ROOT_PARAMETER params[2]{}; params[0].ParameterType=D3D12_ROOT_PARAMETER_TYPE_DESCRIPTOR_TABLE; params[0].DescriptorTable={1,&range}; params[0].ShaderVisibility=D3D12_SHADER_VISIBILITY_PIXEL;
        params[1].ParameterType=D3D12_ROOT_PARAMETER_TYPE_CBV; params[1].Descriptor.ShaderRegister=0; params[1].ShaderVisibility=D3D12_SHADER_VISIBILITY_PIXEL;
        D3D12_ROOT_SIGNATURE_DESC rd{}; rd.NumParameters=2; rd.pParameters=params; rd.Flags=D3D12_ROOT_SIGNATURE_FLAG_ALLOW_INPUT_ASSEMBLER_INPUT_LAYOUT;
        ComPtr<ID3DBlob> root_code, root_error; check(D3D12SerializeRootSignature(&rd,D3D_ROOT_SIGNATURE_VERSION_1,&root_code,&root_error));
        ComPtr<ID3D12RootSignature> root; check(device->CreateRootSignature(0,root_code->GetBufferPointer(),root_code->GetBufferSize(),IID_PPV_ARGS(&root)));
        const auto vs=shader(hlsl,"vs","vs_5_0"), ps=shader(hlsl,"scene","ps_5_0"), post=shader(hlsl,"post","ps_5_0");
        D3D12_GRAPHICS_PIPELINE_STATE_DESC pd{}; pd.pRootSignature=root.Get(); pd.VS={vs->GetBufferPointer(),vs->GetBufferSize()}; pd.PS={ps->GetBufferPointer(),ps->GetBufferSize()};
        pd.SampleMask=UINT_MAX; pd.SampleDesc.Count=1; pd.PrimitiveTopologyType=D3D12_PRIMITIVE_TOPOLOGY_TYPE_TRIANGLE;
        pd.RasterizerState.FillMode=D3D12_FILL_MODE_SOLID; pd.RasterizerState.CullMode=D3D12_CULL_MODE_NONE; pd.RasterizerState.DepthClipEnable=TRUE;
        for(auto &b:pd.BlendState.RenderTarget) { b.RenderTargetWriteMask=D3D12_COLOR_WRITE_ENABLE_ALL; b.SrcBlend=D3D12_BLEND_ONE; b.DestBlend=D3D12_BLEND_ZERO; b.BlendOp=D3D12_BLEND_OP_ADD; b.SrcBlendAlpha=D3D12_BLEND_ONE; b.DestBlendAlpha=D3D12_BLEND_ZERO; b.BlendOpAlpha=D3D12_BLEND_OP_ADD; b.LogicOp=D3D12_LOGIC_OP_NOOP; }
        pd.NumRenderTargets=2; pd.RTVFormats[0]=formats[0]; pd.RTVFormats[1]=formats[1]; pd.DSVFormat=DXGI_FORMAT_D32_FLOAT;
        pd.DepthStencilState.DepthEnable=TRUE; pd.DepthStencilState.DepthWriteMask=D3D12_DEPTH_WRITE_MASK_ALL; pd.DepthStencilState.DepthFunc=D3D12_COMPARISON_FUNC_ALWAYS;
        ComPtr<ID3D12PipelineState> scene_pso, post_pso; check(device->CreateGraphicsPipelineState(&pd,IID_PPV_ARGS(&scene_pso)));
        pd.PS={post->GetBufferPointer(),post->GetBufferSize()}; pd.NumRenderTargets=1; pd.RTVFormats[0]=sd.Format; pd.RTVFormats[1]=DXGI_FORMAT_UNKNOWN; pd.DSVFormat=DXGI_FORMAT_UNKNOWN;
        pd.DepthStencilState.DepthEnable=FALSE; check(device->CreateGraphicsPipelineState(&pd,IID_PPV_ARGS(&post_pso)));
        D3D12_RESOURCE_DESC bd{}; bd.Dimension=D3D12_RESOURCE_DIMENSION_BUFFER; bd.Width=256; bd.Height=1; bd.DepthOrArraySize=1; bd.MipLevels=1; bd.SampleDesc.Count=1; bd.Layout=D3D12_TEXTURE_LAYOUT_ROW_MAJOR;
        D3D12_HEAP_PROPERTIES upload{}; upload.Type=D3D12_HEAP_TYPE_UPLOAD;
        ComPtr<ID3D12Resource> constants; check(device->CreateCommittedResource(&upload,D3D12_HEAP_FLAG_NONE,&bd,D3D12_RESOURCE_STATE_GENERIC_READ,nullptr,IID_PPV_ARGS(&constants)));
        float *camera=nullptr; D3D12_RANGE no_read{0,0}; check(constants->Map(0,&no_read,reinterpret_cast<void**>(&camera))); std::memset(camera,0,256);
        camera[0]=camera[5]=camera[10]=camera[15]=1;
        ComPtr<ID3D12CommandAllocator> allocator; check(device->CreateCommandAllocator(D3D12_COMMAND_LIST_TYPE_DIRECT,IID_PPV_ARGS(&allocator)));
        ComPtr<ID3D12GraphicsCommandList> cmd; check(device->CreateCommandList(0,D3D12_COMMAND_LIST_TYPE_DIRECT,allocator.Get(),nullptr,IID_PPV_ARGS(&cmd))); check(cmd->Close());
        ComPtr<ID3D12Fence> fence; check(device->CreateFence(0,D3D12_FENCE_FLAG_NONE,IID_PPV_ARGS(&fence))); fence_event=CreateEventW(nullptr,FALSE,FALSE,nullptr);
        if(!fence_event) throw std::runtime_error("Fence event unavailable");
        const auto transition=[&](ID3D12Resource *r,D3D12_RESOURCE_STATES a,D3D12_RESOURCE_STATES b) { D3D12_RESOURCE_BARRIER x{}; x.Type=D3D12_RESOURCE_BARRIER_TYPE_TRANSITION; x.Transition={r,D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES,a,b}; cmd->ResourceBarrier(1,&x); };
        for(unsigned frame=0;frame<220;++frame) {
            MSG msg{}; while(PeekMessageW(&msg,nullptr,0,0,PM_REMOVE)) { TranslateMessage(&msg); DispatchMessageW(&msg); }
            camera[16]=(frame&1)?0.25f:-0.25f; camera[17]=(frame&2)?0.125f:-0.125f;
            check(allocator->Reset()); check(cmd->Reset(allocator.Get(),scene_pso.Get()));
            if(frame) { transition(color.Get(),D3D12_RESOURCE_STATE_PIXEL_SHADER_RESOURCE,D3D12_RESOURCE_STATE_RENDER_TARGET); transition(motion.Get(),D3D12_RESOURCE_STATE_PIXEL_SHADER_RESOURCE,D3D12_RESOURCE_STATE_RENDER_TARGET); transition(depth.Get(),D3D12_RESOURCE_STATE_PIXEL_SHADER_RESOURCE,D3D12_RESOURCE_STATE_DEPTH_WRITE); }
            cmd->SetGraphicsRootSignature(root.Get()); ID3D12DescriptorHeap *heaps[]={srv.Get()}; cmd->SetDescriptorHeaps(1,heaps); cmd->SetGraphicsRootDescriptorTable(0,srv->GetGPUDescriptorHandleForHeapStart()); cmd->SetGraphicsRootConstantBufferView(1,constants->GetGPUVirtualAddress());
            const D3D12_VIEWPORT scene_view{0,0,320,180,0,1}; const D3D12_RECT scene_rect{0,0,320,180}; cmd->RSSetViewports(1,&scene_view); cmd->RSSetScissorRects(1,&scene_rect);
            auto scene_rt=at(device.Get(),rtv.Get(),D3D12_DESCRIPTOR_HEAP_TYPE_RTV,2); auto depth_rt=dsv->GetCPUDescriptorHandleForHeapStart(); cmd->OMSetRenderTargets(2,&scene_rt,TRUE,&depth_rt); cmd->ClearDepthStencilView(depth_rt,D3D12_CLEAR_FLAG_DEPTH,1,0,0,nullptr);
            cmd->IASetPrimitiveTopology(D3D_PRIMITIVE_TOPOLOGY_TRIANGLELIST); cmd->DrawInstanced(3,1,0,0);
            transition(color.Get(),D3D12_RESOURCE_STATE_RENDER_TARGET,D3D12_RESOURCE_STATE_PIXEL_SHADER_RESOURCE); transition(motion.Get(),D3D12_RESOURCE_STATE_RENDER_TARGET,D3D12_RESOURCE_STATE_PIXEL_SHADER_RESOURCE); transition(depth.Get(),D3D12_RESOURCE_STATE_DEPTH_WRITE,D3D12_RESOURCE_STATE_PIXEL_SHADER_RESOURCE);
            const auto index=swap->GetCurrentBackBufferIndex(); transition(back[index].Get(),D3D12_RESOURCE_STATE_PRESENT,D3D12_RESOURCE_STATE_RENDER_TARGET);
            cmd->SetPipelineState(post_pso.Get()); auto out=at(device.Get(),rtv.Get(),D3D12_DESCRIPTOR_HEAP_TYPE_RTV,index); cmd->OMSetRenderTargets(1,&out,FALSE,nullptr);
            const D3D12_VIEWPORT full_view{0,0,640,360,0,1}; const D3D12_RECT full_rect{0,0,640,360}; cmd->RSSetViewports(1,&full_view); cmd->RSSetScissorRects(1,&full_rect); cmd->DrawInstanced(3,1,0,0);
            transition(back[index].Get(),D3D12_RESOURCE_STATE_RENDER_TARGET,D3D12_RESOURCE_STATE_PRESENT); check(cmd->Close()); ID3D12CommandList *lists[]={cmd.Get()}; queue->ExecuteCommandLists(1,lists); check(swap->Present(0,0));
            check(queue->Signal(fence.Get(),frame+1)); check(fence->SetEventOnCompletion(frame+1,fence_event)); if(WaitForSingleObject(fence_event,10000)!=WAIT_OBJECT_0) throw std::runtime_error("GPU fence timeout"); Sleep(2);
        }
        constants->Unmap(0,nullptr); CloseHandle(fence_event); DestroyWindow(window);
        std::cout << "PASS: 220 D3D12 frames; scene MRT, motion/depth SRVs and alternating camera constants; descriptor_stress=" << stress << '\n';
        return 0;
    } catch(const std::exception &e) {
        if(fence_event) CloseHandle(fence_event); if(window) DestroyWindow(window); std::cerr << e.what() << '\n'; return 1;
    }
}
