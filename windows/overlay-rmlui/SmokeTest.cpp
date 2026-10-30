#include <GlassOverlay.h>
#include <wrl/client.h>
#include <array>
#include <dxgi1_4.h>
#include <iostream>
#include <vector>
#include <stdexcept>
#include <cstring>
using Microsoft::WRL::ComPtr;
static void Need(bool ok,const char* message){if(!ok)throw std::runtime_error(message);}
static void Test12(HMODULE dll,ForgeGlass::Release release,bool hdr=false){
    const auto draw=reinterpret_cast<ForgeGlass::Draw12>(GetProcAddress(dll,"ForgeGlassDraw12"));Need(draw,"DX12 export missing");
    ComPtr<ID3D12Device> device;if(FAILED(D3D12CreateDevice(nullptr,D3D_FEATURE_LEVEL_11_0,IID_PPV_ARGS(&device)))){ComPtr<IDXGIFactory4> factory;Need(SUCCEEDED(CreateDXGIFactory1(IID_PPV_ARGS(&factory))),"DXGI factory failed");ComPtr<IDXGIAdapter> warp;Need(SUCCEEDED(factory->EnumWarpAdapter(IID_PPV_ARGS(&warp)))&&SUCCEEDED(D3D12CreateDevice(warp.Get(),D3D_FEATURE_LEVEL_11_0,IID_PPV_ARGS(&device))),"DX12 fixture device failed");}
    D3D12_COMMAND_QUEUE_DESC q{};q.Type=D3D12_COMMAND_LIST_TYPE_DIRECT;ComPtr<ID3D12CommandQueue> queue;Need(SUCCEEDED(device->CreateCommandQueue(&q,IID_PPV_ARGS(&queue))),"DX12 queue failed");
    D3D12_HEAP_PROPERTIES heap{};heap.Type=D3D12_HEAP_TYPE_DEFAULT;D3D12_RESOURCE_DESC desc{};desc.Dimension=D3D12_RESOURCE_DIMENSION_TEXTURE2D;desc.Width=2560;desc.Height=1440;desc.DepthOrArraySize=desc.MipLevels=1;desc.Format=hdr?DXGI_FORMAT_R10G10B10A2_UNORM:DXGI_FORMAT_R8G8B8A8_UNORM;desc.SampleDesc.Count=1;desc.Flags=D3D12_RESOURCE_FLAG_ALLOW_RENDER_TARGET;
    ComPtr<ID3D12Resource> target;Need(SUCCEEDED(device->CreateCommittedResource(&heap,D3D12_HEAP_FLAG_NONE,&desc,D3D12_RESOURCE_STATE_RENDER_TARGET,nullptr,IID_PPV_ARGS(&target))),"DX12 target failed");
    D3D12_DESCRIPTOR_HEAP_DESC hd{};hd.Type=D3D12_DESCRIPTOR_HEAP_TYPE_RTV;hd.NumDescriptors=1;ComPtr<ID3D12DescriptorHeap> descriptors;Need(SUCCEEDED(device->CreateDescriptorHeap(&hd,IID_PPV_ARGS(&descriptors))),"DX12 RTV failed");const auto rtv=descriptors->GetCPUDescriptorHandleForHeapStart();device->CreateRenderTargetView(target.Get(),nullptr,rtv);
    ComPtr<ID3D12CommandAllocator> allocator;Need(SUCCEEDED(device->CreateCommandAllocator(q.Type,IID_PPV_ARGS(&allocator))),"DX12 allocator failed");ComPtr<ID3D12GraphicsCommandList> list;Need(SUCCEEDED(device->CreateCommandList(0,q.Type,allocator.Get(),nullptr,IID_PPV_ARGS(&list))),"DX12 list failed");const float scene[4]={.25f,.30f,.18f,1};list->ClearRenderTargetView(rtv,scene,0,nullptr);
    D3D12_RESOURCE_BARRIER barrier{};barrier.Type=D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;barrier.Transition={target.Get(),D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES,D3D12_RESOURCE_STATE_RENDER_TARGET,D3D12_RESOURCE_STATE_PRESENT};list->ResourceBarrier(1,&barrier);Need(SUCCEEDED(list->Close()),"DX12 list close failed");ID3D12CommandList* lists[]={list.Get()};queue->ExecuteCommandLists(1,lists);
    ForgeGlass::Host host{sizeof(ForgeGlass::Host),ForgeGlass::Abi};host.log=[](void*,const char* text){std::cerr<<text<<'\n';};host.read=[](void*,ForgeGlass::Snapshot* s){static const ForgeGlass::Value values[]={{"enabled",1},{"intensity",.75f},{"style",1},{"passes",3},{"preset",0}};*s={"DX12 RENDERER TEST","#d58975",values,uint32_t(std::size(values)),true,true,false,false,false,false,2.34,60,-1,-1,true,false,true};return true;};
    ForgeGlass::Frame12 frame{};frame.size=sizeof(frame);frame.abi=ForgeGlass::Abi;frame.device=device.Get();frame.queue=queue.Get();frame.target=target.Get();frame.before=frame.after=D3D12_RESOURCE_STATE_PRESENT;frame.input.size=sizeof(frame.input);frame.input.abi=ForgeGlass::Abi;frame.input.visible=true;frame.input.colorSpace=hdr?2:0;
    // Present normally limits frames in flight. Fence each fixture frame as
    // well, so six 1440p software frames cannot accumulate behind one wait.
    ComPtr<ID3D12Fence> frameFence;Need(SUCCEEDED(device->CreateFence(0,D3D12_FENCE_FLAG_NONE,IID_PPV_ARGS(&frameFence))),"DX12 frame fence failed");
    for(int i=0;i<6;i++){
        Need(draw(&host,&frame),"DX12 game-facing draw failed");
        HANDLE done=CreateEventW(nullptr,FALSE,FALSE,nullptr);Need(done,"DX12 frame event failed");
        Need(SUCCEEDED(queue->Signal(frameFence.Get(),i+1))&&SUCCEEDED(frameFence->SetEventOnCompletion(i+1,done)),"DX12 frame submission failed");
        const auto completed=WaitForSingleObject(done,5000);CloseHandle(done);Need(completed==WAIT_OBJECT_0,"DX12 frame did not complete");
    }
    UINT64 bytes{};D3D12_PLACED_SUBRESOURCE_FOOTPRINT footprint{};device->GetCopyableFootprints(&desc,0,1,0,&footprint,nullptr,nullptr,&bytes);
    D3D12_HEAP_PROPERTIES readHeap{};readHeap.Type=D3D12_HEAP_TYPE_READBACK;D3D12_RESOURCE_DESC buffer{};buffer.Dimension=D3D12_RESOURCE_DIMENSION_BUFFER;buffer.Width=bytes;buffer.Height=buffer.DepthOrArraySize=buffer.MipLevels=1;buffer.SampleDesc.Count=1;buffer.Layout=D3D12_TEXTURE_LAYOUT_ROW_MAJOR;
    ComPtr<ID3D12Resource> readback;Need(SUCCEEDED(device->CreateCommittedResource(&readHeap,D3D12_HEAP_FLAG_NONE,&buffer,D3D12_RESOURCE_STATE_COPY_DEST,nullptr,IID_PPV_ARGS(&readback))),"DX12 readback allocation failed");
    ComPtr<ID3D12CommandAllocator> copyAllocator;ComPtr<ID3D12GraphicsCommandList> copyList;Need(SUCCEEDED(device->CreateCommandAllocator(q.Type,IID_PPV_ARGS(&copyAllocator)))&&SUCCEEDED(device->CreateCommandList(0,q.Type,copyAllocator.Get(),nullptr,IID_PPV_ARGS(&copyList))),"DX12 readback list failed");
    barrier.Transition.StateBefore=D3D12_RESOURCE_STATE_PRESENT;barrier.Transition.StateAfter=D3D12_RESOURCE_STATE_COPY_SOURCE;copyList->ResourceBarrier(1,&barrier);D3D12_TEXTURE_COPY_LOCATION destination{};destination.pResource=readback.Get();destination.Type=D3D12_TEXTURE_COPY_TYPE_PLACED_FOOTPRINT;destination.PlacedFootprint=footprint;D3D12_TEXTURE_COPY_LOCATION source{};source.pResource=target.Get();source.Type=D3D12_TEXTURE_COPY_TYPE_SUBRESOURCE_INDEX;copyList->CopyTextureRegion(&destination,0,0,0,&source,nullptr);std::swap(barrier.Transition.StateBefore,barrier.Transition.StateAfter);copyList->ResourceBarrier(1,&barrier);Need(SUCCEEDED(copyList->Close()),"DX12 readback close failed");ID3D12CommandList* copies[]={copyList.Get()};queue->ExecuteCommandLists(1,copies);
    ComPtr<ID3D12Fence> fence;Need(SUCCEEDED(device->CreateFence(0,D3D12_FENCE_FLAG_NONE,IID_PPV_ARGS(&fence))),"DX12 fence failed");HANDLE event=CreateEventW(nullptr,FALSE,FALSE,nullptr);Need(event,"DX12 event failed");Need(SUCCEEDED(queue->Signal(fence.Get(),1))&&SUCCEEDED(fence->SetEventOnCompletion(1,event)),"DX12 submission failed");const auto wait=WaitForSingleObject(event,5000);CloseHandle(event);Need(wait==WAIT_OBJECT_0,"DX12 renderer did not complete");void* mapped{};D3D12_RANGE range{0,SIZE_T(bytes)};Need(SUCCEEDED(readback->Map(0,&range,&mapped)),"DX12 readback mapping failed");const auto* pixels=static_cast<const unsigned char*>(mapped)+footprint.Offset;const auto* corner=pixels+1439*footprint.Footprint.RowPitch+2559*4;const auto* panel=pixels+300*footprint.Footprint.RowPitch+200*4;if(hdr){uint32_t packed;std::memcpy(&packed,corner,4);Need((packed&1023)==256&&((packed>>10)&1023)==307&&((packed>>20)&1023)==184&&(packed>>30)==3,"DX12 HDR scene outside the overlay changed");}else Need(corner[0]>=63&&corner[0]<=64&&corner[1]>=76&&corner[1]<=77&&corner[2]>=45&&corner[2]<=46&&corner[3]==255,"DX12 scene outside the overlay changed");Need(std::memcmp(panel,corner,4)!=0,"DX12 glass did not reach the image");D3D12_RANGE empty{0,0};readback->Unmap(0,&empty);release();std::cout<<"dx12_interop_checks=passed frames=6 submitted_scene=preserved transfer="<<(hdr?"PQ-Rec2020":"SDR")<<"\n";
}
static void TestHdr11(ForgeGlass::Draw draw,ForgeGlass::Release release,ID3D11Device* device,ID3D11DeviceContext* context){
    for(unsigned space=1;space<=2;space++){
        D3D11_TEXTURE2D_DESC desc{};desc.Width=2560;desc.Height=1440;desc.MipLevels=desc.ArraySize=1;desc.Format=space==1?DXGI_FORMAT_R16G16B16A16_FLOAT:DXGI_FORMAT_R10G10B10A2_UNORM;desc.SampleDesc.Count=1;desc.BindFlags=D3D11_BIND_RENDER_TARGET;
        ComPtr<ID3D11Texture2D> target;ComPtr<ID3D11RenderTargetView> view;Need(SUCCEEDED(device->CreateTexture2D(&desc,nullptr,&target))&&SUCCEEDED(device->CreateRenderTargetView(target.Get(),nullptr,&view)),"HDR target failed");
        const float scrgb[4]={5,3,1,1},pq[4]={.65f,.70f,.60f,1};context->ClearRenderTargetView(view.Get(),space==1?scrgb:pq);
        desc.Usage=D3D11_USAGE_STAGING;desc.BindFlags=0;desc.CPUAccessFlags=D3D11_CPU_ACCESS_READ;ComPtr<ID3D11Texture2D> staging;Need(SUCCEEDED(device->CreateTexture2D(&desc,nullptr,&staging)),"HDR readback failed");
        const unsigned stride=space==1?8:4;std::array<unsigned char,8> original{};D3D11_MAPPED_SUBRESOURCE mapped{};context->CopyResource(staging.Get(),target.Get());Need(SUCCEEDED(context->Map(staging.Get(),0,D3D11_MAP_READ,0,&mapped)),"HDR baseline map failed");std::memcpy(original.data(),mapped.pData,stride);context->Unmap(staging.Get(),0);
        ForgeGlass::Host host{sizeof(host),ForgeGlass::Abi};host.log=[](void*,const char* message){std::cerr<<message<<'\n';};host.read=[](void*,ForgeGlass::Snapshot* snapshot){static const ForgeGlass::Value values[]={{"enabled",1},{"intensity",1},{"style",1},{"passes",1},{"preset",0}};*snapshot={"HDR COMPOSITION TEST","#d58975",values,5,true,true,false,false,false,false,2.3,60,-1,-1,true,false,true};return true;};
        ForgeGlass::Frame frame{};frame.size=sizeof(frame);frame.abi=ForgeGlass::Abi;frame.device=device;frame.target=view.Get();frame.visible=true;frame.colorSpace=space;
        for(unsigned i=0;i<3;i++)Need(draw(&host,&frame),"HDR composition rejected a valid format/transfer pair");
        context->CopyResource(staging.Get(),target.Get());Need(SUCCEEDED(context->Map(staging.Get(),0,D3D11_MAP_READ,0,&mapped)),"HDR final map failed");
        const auto* pixels=static_cast<const unsigned char*>(mapped.pData);const auto* corner=pixels+1439*mapped.RowPitch+2559*stride;Need(std::memcmp(corner,original.data(),stride)==0,"HDR scene outside the panels changed");unsigned changed=0;
        for(unsigned y=0;y<1440;y++)for(unsigned x=0;x<2560;x++){const auto* pixel=pixels+y*mapped.RowPitch+x*stride;if(std::memcmp(pixel,original.data(),stride)!=0)changed++;if(space==1)for(unsigned channel=0;channel<3;channel++){uint16_t half;std::memcpy(&half,pixel+channel*2,2);Need((half&0x7c00)!=0x7c00,"HDR composition produced a non-finite channel");}}
        context->Unmap(staging.Get(),0);Need(changed>10000,"HDR UI did not reach the scene");frame.colorSpace=255;Need(!draw(&host,&frame),"Unknown HDR transfer accepted");release();
        std::cout<<"hdr_composition_checks=passed transfer="<<(space==1?"scRGB":"PQ-Rec2020")<<" outside_scene=bit_preserved finite=passed\n";
    }
}
int wmain(int argc,wchar_t** argv){try{
    Need(argc==2,"Supply the exact glass DLL to test");
    HMODULE dll=LoadLibraryExW(argv[1],nullptr,LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR|LOAD_LIBRARY_SEARCH_SYSTEM32);Need(dll,"Could not load glass DLL");
    const auto draw=reinterpret_cast<ForgeGlass::Draw>(GetProcAddress(dll,"ForgeGlassDraw"));const auto release=reinterpret_cast<ForgeGlass::Release>(GetProcAddress(dll,"ForgeGlassRelease"));Need(draw&&release,"Glass exports missing");
    ComPtr<ID3D11Device> device;ComPtr<ID3D11DeviceContext> context;
    const bool hardware=SUCCEEDED(D3D11CreateDevice(nullptr,D3D_DRIVER_TYPE_HARDWARE,nullptr,0,nullptr,0,D3D11_SDK_VERSION,&device,nullptr,&context));if(!hardware)Need(SUCCEEDED(D3D11CreateDevice(nullptr,D3D_DRIVER_TYPE_WARP,nullptr,0,nullptr,0,D3D11_SDK_VERSION,&device,nullptr,&context)),"DX11 fixture device failed");std::cout<<"fixture_device="<<(hardware?"hardware":"WARP")<<"\n";
    unsigned renders=0;
    for(const auto format:{DXGI_FORMAT_R8G8B8A8_UNORM,DXGI_FORMAT_B8G8R8A8_UNORM}){
        D3D11_TEXTURE2D_DESC desc{};desc.Width=2560;desc.Height=1440;desc.MipLevels=desc.ArraySize=1;desc.Format=format;desc.SampleDesc.Count=1;desc.BindFlags=D3D11_BIND_RENDER_TARGET;
        ComPtr<ID3D11Texture2D> target;Need(SUCCEEDED(device->CreateTexture2D(&desc,nullptr,&target)),"Target failed");ComPtr<ID3D11RenderTargetView> view;Need(SUCCEEDED(device->CreateRenderTargetView(target.Get(),nullptr,&view)),"View failed");
        const float scene[4]={.25f,.30f,.18f,1};context->ClearRenderTargetView(view.Get(),scene);
        auto* original=view.Get();context->OMSetRenderTargets(1,&original,nullptr);D3D11_VIEWPORT viewport{7,11,1222,777,.2f,.8f};context->RSSetViewports(1,&viewport);
        ForgeGlass::Host host{sizeof(ForgeGlass::Host),ForgeGlass::Abi};
        host.read=[](void*,ForgeGlass::Snapshot* s){static const ForgeGlass::Value values[]={{"enabled",1},{"intensity",.75f},{"style",1},{"passes",3},{"preset",0},{"multiplier",3},{"dynamic_mfg",0}};*s={"LIVE RENDERER TEST","#d58975",values,uint32_t(std::size(values)),true,true,false,true,true,true,2.34,60,180,3,true,true,true};s->helperJson=R"({"revision":1,"ready":true,"pending":false,"named_supported":true,"settings":{"panel_key":35,"panel_modifiers":0,"panel_hotkey":"End"},"review":{},"presets":[{"name":"Quiet","compatible":true,"values":{"intensity":0.75}},{"name":"Detailed","compatible":true,"values":{"intensity":1}}]})";return true;};
        host.apply=[](void*,const ForgeGlass::Value*,uint32_t){return true;};host.log=[](void*,const char* text){std::cerr<<text<<'\n';};
        ForgeGlass::Frame frame{};frame.size=sizeof(frame);frame.abi=ForgeGlass::Abi;frame.device=device.Get();frame.target=view.Get();frame.visible=true;frame.welcome=true;
        for(unsigned i=0;i<6;i++){Need(draw(&host,&frame),"Game-facing renderer rejected SDR target");renders++;}
        ComPtr<ID3D11RenderTargetView> restored;context->OMGetRenderTargets(1,&restored,nullptr);Need(restored.Get()==original,"Game render target was not restored");D3D11_VIEWPORT after{};UINT count=1;context->RSGetViewports(&count,&after);Need(count==1&&after.TopLeftX==7&&after.TopLeftY==11&&after.Width==1222&&after.Height==777&&after.MinDepth==.2f&&after.MaxDepth==.8f,"Game viewport was not restored");
        desc.Usage=D3D11_USAGE_STAGING;desc.BindFlags=0;desc.CPUAccessFlags=D3D11_CPU_ACCESS_READ;ComPtr<ID3D11Texture2D> staging;Need(SUCCEEDED(device->CreateTexture2D(&desc,nullptr,&staging)),"Readback failed");context->CopyResource(staging.Get(),target.Get());D3D11_MAPPED_SUBRESOURCE pixels{};Need(SUCCEEDED(context->Map(staging.Get(),0,D3D11_MAP_READ,0,&pixels)),"Map failed");
        const auto* top=static_cast<const unsigned char*>(pixels.pData);const auto* panel=top+300*pixels.RowPitch+200*4;Need(top[3]==255,"Scene outside overlay changed");Need(panel[0]!=top[0]||panel[1]!=top[1]||panel[2]!=top[2],"Glass UI did not composite over game target");context->Unmap(staging.Get(),0);
        frame.colorSpace=1;Need(!draw(&host,&frame),"Unvalidated HDR route must be rejected");release();
    }
    TestHdr11(draw,release,device.Get(),context.Get());Test12(dll,release);Test12(dll,release,true);FreeLibrary(dll);std::cout<<"game_facing_dx11_checks=passed formats=RGBA,BGRA frames="<<renders<<" state_restore=passed hdr_rejection=passed\n";return 0;
}catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}}
