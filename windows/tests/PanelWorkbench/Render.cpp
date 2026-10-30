#include <Config.h>
#include <d3d11.h>
#include <ForgePanel.h>
#include <imgui/imgui_impl_dx11.h>
#include <wincodec.h>
#include <wrl/client.h>
#include <stdexcept>
#include <iostream>

using Microsoft::WRL::ComPtr;
static void Check(HRESULT result) { if(FAILED(result)) throw std::runtime_error("Native renderer operation failed"); }
static void Require(bool condition) { if(!condition) throw std::runtime_error("Panel state assertion failed"); }

int wmain(int argc, wchar_t** argv)
{
    try {
        if(argc < 5) throw std::runtime_error("Usage: PanelWorkbench output.png width height dark|light [passes]");
        const int width=_wtoi(argv[2]),height=_wtoi(argv[3]);
        Require(width>=640 && width<=3840 && height>=480 && height<=2160);
        Check(CoInitializeEx(nullptr,COINIT_MULTITHREADED));
        ComPtr<ID3D11Device> device; ComPtr<ID3D11DeviceContext> context;
        Check(D3D11CreateDevice(nullptr,D3D_DRIVER_TYPE_WARP,nullptr,0,nullptr,0,D3D11_SDK_VERSION,&device,nullptr,&context));
        D3D11_TEXTURE2D_DESC description{};
        description.Width=width; description.Height=height; description.MipLevels=1; description.ArraySize=1;
        description.Format=DXGI_FORMAT_B8G8R8A8_UNORM; description.SampleDesc.Count=1;
        description.Usage=D3D11_USAGE_DEFAULT; description.BindFlags=D3D11_BIND_RENDER_TARGET;
        ComPtr<ID3D11Texture2D> target; Check(device->CreateTexture2D(&description,nullptr,&target));
        ComPtr<ID3D11RenderTargetView> view; Check(device->CreateRenderTargetView(target.Get(),nullptr,&view));
        ImGui::CreateContext();
        auto& io=ImGui::GetIO(); io.IniFilename=nullptr; io.LogFilename=nullptr;
        io.DisplaySize=ImVec2(float(width),float(height)); io.DeltaTime=1.f/60;
        io.ConfigFlags|=ImGuiConfigFlags_NavEnableKeyboard;
        ImFontConfig options; options.FontDataOwnedByAtlas=false;
        options.FontLoader=ForgePanel::PanelFontLoader();
        ForgePanel::font=io.Fonts->AddFontFromMemoryTTF(ForgePanel::forgeInter,sizeof(ForgePanel::forgeInter),18,&options);
        ForgePanel::bold=io.Fonts->AddFontFromMemoryTTF(ForgePanel::forgeInterSemiBold,sizeof(ForgePanel::forgeInterSemiBold),18,&options);
        ForgePanel::brandFont=io.Fonts->AddFontFromMemoryTTF(ForgePanel::forgeBakbak,sizeof(ForgePanel::forgeBakbak),24,&options);
        Require(ImGui_ImplDX11_Init(device.Get(),context.Get()));
        feeder_panel::host.focused=[] { return true; };
        ForgePanel::enabled=ForgePanel::selected=ForgePanel::nrAllowed=ForgePanel::mfgAllowed=true;
        ForgePanel::title="Overlay test fixture"; ForgePanel::animation=1;
        ForgePanel::lightTheme=std::wstring(argv[4])==L"light";
        ForgePanel::accent=ImVec4(.73f,.40f,.29f,1);
        State::Instance().dlssgMfgMax=5; State::Instance().dlssgGameDMFGSupported=true;
        ForgePanelChannel::needsHello=false; ForgePanelChannel::helperReady=true; ForgePanelChannel::namedSupported=true;
        auto& cfg=*Config::Instance();
        cfg.FGDLSSGOverrideInterpolationCount=std::nullopt;
        cfg.DlssNrEnabled=true;
        const auto start=ForgePanel::Values(cfg);
        const auto intensity=std::find_if(std::begin(ForgePanel::controls),std::end(ForgePanel::controls),[](const auto& f){ return std::strcmp(f.key,"intensity")==0; });
        ForgePanel::Commit(*intensity,cfg,.6f); ForgePanel::Flush(cfg,true);
        Require(std::fabs(cfg.DlssNrIntensity.value_or_default()-.6f)<.001f);
        Require(ForgePanel::ApplyValues(cfg,ForgePanel::edits.Undo(ForgePanel::Values(cfg)),false)); ForgePanel::Flush(cfg,true);
        Require(ForgeWorkbench::Equal(start,ForgePanel::Values(cfg)));
        auto invalid=start; invalid["pass2_strength"]=10;
        Require(!ForgePanel::ApplyValues(cfg,invalid)); Require(ForgeWorkbench::Equal(start,ForgePanel::Values(cfg)));
        ForgePanel::edits.BeginComparison(start);
        auto other=start; other["pass2_inherit"]=0; other["pass2_strength"]=.4f;
        Require(ForgePanel::ApplyValues(cfg,other)); ForgePanel::Flush(cfg,true);
        Require(ForgePanel::ApplyValues(cfg,ForgePanel::edits.Compare(1,ForgePanel::Values(cfg)))); ForgePanel::Flush(cfg,true);
        Require(ForgeWorkbench::Equal(start,ForgePanel::Values(cfg)));
        ForgePanel::edits.EndComparison(start); ForgePanel::edits={};
        if(argc>5) cfg.DlssNrPasses=3;
        ForgePanelChannel::namedPresets=nlohmann::json::array({{{"name","Test preset"},{"compatible",true},{"values",{{"intensity",1.}}}}});
        bool visible=true;
        for(int frame=0;frame<8;++frame) {
            ImGui_ImplDX11_NewFrame(); ImGui::NewFrame();
            ForgePanel::Draw(visible,1);
            if(argc>5) for(auto* window : ImGui::GetCurrentContext()->Windows)
                if(std::string(window->Name).find("content_")!=std::string::npos)
                    window->StateStorage.SetInt(window->GetID("Pass tuning"),1);
            ImGui::Render();
            const float background[]={.12f,.13f,.14f,1}; auto* rtv=view.Get();
            context->OMSetRenderTargets(1,&rtv,nullptr); context->ClearRenderTargetView(rtv,background);
            ImGui_ImplDX11_RenderDrawData(ImGui::GetDrawData());
        }
        description.Usage=D3D11_USAGE_STAGING; description.BindFlags=0; description.CPUAccessFlags=D3D11_CPU_ACCESS_READ;
        ComPtr<ID3D11Texture2D> readback; Check(device->CreateTexture2D(&description,nullptr,&readback));
        context->CopyResource(readback.Get(),target.Get());
        D3D11_MAPPED_SUBRESOURCE pixels{}; Check(context->Map(readback.Get(),0,D3D11_MAP_READ,0,&pixels));
        ComPtr<IWICImagingFactory> factory; Check(CoCreateInstance(CLSID_WICImagingFactory,nullptr,CLSCTX_INPROC_SERVER,IID_PPV_ARGS(&factory)));
        ComPtr<IWICStream> stream; Check(factory->CreateStream(&stream)); Check(stream->InitializeFromFilename(argv[1],GENERIC_WRITE));
        ComPtr<IWICBitmapEncoder> encoder; Check(factory->CreateEncoder(GUID_ContainerFormatPng,nullptr,&encoder)); Check(encoder->Initialize(stream.Get(),WICBitmapEncoderNoCache));
        ComPtr<IWICBitmapFrameEncode> output; Check(encoder->CreateNewFrame(&output,nullptr)); Check(output->Initialize(nullptr)); Check(output->SetSize(width,height));
        auto format=GUID_WICPixelFormat32bppBGRA; Check(output->SetPixelFormat(&format));
        Check(output->WritePixels(height,pixels.RowPitch,pixels.RowPitch*height,static_cast<BYTE*>(pixels.pData)));
        Check(output->Commit()); Check(encoder->Commit()); context->Unmap(readback.Get(),0);
        ImGui_ImplDX11_Shutdown(); ImGui::DestroyContext();
        std::cout<<"Native editing assertions passed; rendered panel fixture saved. No game was opened.\n";
        return 0;
    } catch(const std::exception& error) { std::cerr<<error.what()<<'\n'; return 1; }
}
