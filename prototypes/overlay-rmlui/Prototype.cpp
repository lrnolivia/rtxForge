#include <windows.h>
#include <d3d11.h>
#include <wincodec.h>
#include <wrl/client.h>
#include <RmlUi/Core.h>
#include <RmlUi/Core/RenderManager.h>
#include <RmlUi/Core/ComputedValues.h>
#include <RmlUi/Core/ElementInstancer.h>
#include <RmlUi/Core/Elements/ElementFormControl.h>
#include <RmlUi_Renderer_DX11.h>
#include <ForgeWorkbench.h>
#include "Backdrop.h"
#include "PrototypeControls.generated.h"
#include "MaterialColor.h"
#include "Motion.h"
#include "ThemeDefaults.h"
#include "SessionData.h"
#include "../../providers/glass-overlay/OverlayController.h"
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iomanip>
#include <vector>
#include <stdexcept>
#include <unordered_set>
using Microsoft::WRL::ComPtr;
// Paint each window independently without changing DOM visibility, focus,
// hover, or pressed state between frames.
struct PaintRoot : Rml::Element {
    explicit PaintRoot(const Rml::String& tag):Rml::Element(tag) {ForceLocalStackingContext();}
    void Paint() {Render();}
};
namespace fs=std::filesystem;
static void Check(HRESULT result) { if(FAILED(result)) throw std::runtime_error("DirectX operation failed: "+std::to_string(result)); }
static void Require(bool ok,const char* message) { if(!ok) throw std::runtime_error(message); }
static std::string Utf8(const std::wstring& value) { return fs::path(value).generic_string(); }
static Rml::Context* inputContext=nullptr;
static bool closed=false;
static int Modifiers() { return (GetKeyState(VK_CONTROL)<0 ? Rml::Input::KM_CTRL:0) | (GetKeyState(VK_SHIFT)<0 ? Rml::Input::KM_SHIFT:0) | (GetKeyState(VK_MENU)<0 ? Rml::Input::KM_ALT:0); }
static Rml::Input::KeyIdentifier Key(WPARAM code)
{
    if(code>=VK_F1 && code<=VK_F12)return Rml::Input::KeyIdentifier(Rml::Input::KI_F1+code-VK_F1);
    if(code>='A' && code<='Z') return Rml::Input::KeyIdentifier(Rml::Input::KI_A+code-'A');
    switch(code) {
        case VK_TAB:return Rml::Input::KI_TAB; case VK_RETURN:return Rml::Input::KI_RETURN;
        case VK_ESCAPE:return Rml::Input::KI_ESCAPE; case VK_SPACE:return Rml::Input::KI_SPACE;
        case VK_LEFT:return Rml::Input::KI_LEFT; case VK_RIGHT:return Rml::Input::KI_RIGHT;
        case VK_UP:return Rml::Input::KI_UP; case VK_DOWN:return Rml::Input::KI_DOWN;
        case VK_BACK:return Rml::Input::KI_BACK; case VK_DELETE:return Rml::Input::KI_DELETE;
        case VK_HOME:return Rml::Input::KI_HOME; case VK_END:return Rml::Input::KI_END;
        default:return Rml::Input::KI_UNKNOWN;
    }
}
static LRESULT CALLBACK WindowProc(HWND window,UINT message,WPARAM w,LPARAM l)
{
    if(message==WM_CLOSE || message==WM_DESTROY) { closed=true; return 0; }
    if(inputContext) switch(message) {
        case WM_MOUSEMOVE:inputContext->ProcessMouseMove(short(LOWORD(l)),short(HIWORD(l)),Modifiers());return 0;
        case WM_LBUTTONDOWN:SetCapture(window);inputContext->ProcessMouseButtonDown(0,Modifiers());return 0;
        case WM_LBUTTONUP:ReleaseCapture();inputContext->ProcessMouseButtonUp(0,Modifiers());return 0;
        case WM_MOUSEWHEEL:inputContext->ProcessMouseWheel(-float(GET_WHEEL_DELTA_WPARAM(w))/WHEEL_DELTA,Modifiers());return 0;
        case WM_KEYDOWN:if(l&(1LL<<30))return 0;inputContext->ProcessKeyDown(Key(w),Modifiers());return 0;
        case WM_KEYUP:inputContext->ProcessKeyUp(Key(w),Modifiers());return 0;
        case WM_CHAR:if(w>=32) inputContext->ProcessTextInput(Rml::Character(w));return 0;
    }
    return DefWindowProcW(window,message,w,l);
}
struct System : Rml::SystemInterface
{
    std::chrono::steady_clock::time_point start=std::chrono::steady_clock::now();
    double frameTime=-1;
    double GetElapsedTime() override { return frameTime>=0 ? frameTime:std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count(); }
    bool LogMessage(Rml::Log::Type type,const Rml::String& message) override { if(type!=Rml::Log::LT_INFO)std::cerr<<message<<'\n'; return true; }
    void SetMouseCursor(const Rml::String& cursor) override {SetCursor(LoadCursorW(nullptr,cursor=="move"?IDC_SIZEALL:cursor=="pointer"?IDC_HAND:cursor=="text"?IDC_IBEAM:IDC_ARROW));}
};
struct Image { unsigned width{},height{}; std::vector<Rml::byte> rgba; };
static std::array<float,4> CropImage(const Image& image,int width,int height,float crop) {
    const float available=image.width*(1-crop),factor=std::max(width/available,float(height)/image.height),shownWidth=width/factor,shownHeight=height/factor;
    return {(image.width*crop+(available-shownWidth)*.5f)/image.width,(image.height-shownHeight)*.5f/image.height,shownWidth/image.width,shownHeight/image.height};
}
static Image LoadImage(const fs::path& path);
struct PrototypeRenderer : RenderInterface_DX11
{
    using RenderInterface_DX11::RenderInterface_DX11;
    int blurFilters{}, filterComposites{};
    Rml::TextureHandle LoadTexture(Rml::Vector2i& dimensions,const Rml::String& source) override;
    Rml::CompiledFilterHandle CompileFilter(const Rml::String& name,const Rml::Dictionary& parameters) override {
        if(name=="blur")++blurFilters;
        return RenderInterface_DX11::CompileFilter(name,parameters);
    }
    void CompositeLayers(Rml::LayerHandle source,Rml::LayerHandle destination,Rml::BlendMode blend,Rml::Span<const Rml::CompiledFilterHandle> filters) override {
        if(!filters.empty())++filterComposites;
        RenderInterface_DX11::CompositeLayers(source,destination,blend,filters);
    }
};
static Image LoadImage(const fs::path& path)
{
    ComPtr<IWICImagingFactory> factory; Check(CoCreateInstance(CLSID_WICImagingFactory,nullptr,CLSCTX_INPROC_SERVER,IID_PPV_ARGS(&factory)));
    ComPtr<IWICBitmapDecoder> decoder; Check(factory->CreateDecoderFromFilename(path.c_str(),nullptr,GENERIC_READ,WICDecodeMetadataCacheOnLoad,&decoder));
    ComPtr<IWICBitmapFrameDecode> frame; Check(decoder->GetFrame(0,&frame));
    Image image; Check(frame->GetSize(&image.width,&image.height));
    Require(image.width>0 && image.height>0 && image.width<=16384 && image.height<=16384,"Background dimensions outside prototype limits");
    ComPtr<IWICFormatConverter> converter; Check(factory->CreateFormatConverter(&converter));
    Check(converter->Initialize(frame.Get(),GUID_WICPixelFormat32bppRGBA,WICBitmapDitherTypeNone,nullptr,0,WICBitmapPaletteTypeCustom));
    image.rgba.resize(size_t(image.width)*image.height*4);
    Check(converter->CopyPixels(nullptr,image.width*4,UINT(image.rgba.size()),image.rgba.data()));
    return image;
}
Rml::TextureHandle PrototypeRenderer::LoadTexture(Rml::Vector2i& dimensions,const Rml::String& source)
{
    try {
        auto image=LoadImage(fs::path(source));dimensions={int(image.width),int(image.height)};
        for(size_t i=0;i<image.rgba.size();i+=4)for(size_t channel=0;channel<3;++channel)image.rgba[i+channel]=Rml::byte(unsigned(image.rgba[i+channel])*image.rgba[i+3]/255);
        return GenerateTexture(image.rgba,dimensions);
    } catch(const std::exception& error) {std::cerr<<error.what()<<'\n';return 0;}
}
static void SaveImage(ID3D11Device* device,ID3D11DeviceContext* context,ID3D11Texture2D* texture,const fs::path& path)
{
    D3D11_TEXTURE2D_DESC desc{};texture->GetDesc(&desc);
    desc.Usage=D3D11_USAGE_STAGING;desc.BindFlags=0;desc.CPUAccessFlags=D3D11_CPU_ACCESS_READ;desc.MiscFlags=0;
    ComPtr<ID3D11Texture2D> staging; Check(device->CreateTexture2D(&desc,nullptr,&staging));context->CopyResource(staging.Get(),texture);
    D3D11_MAPPED_SUBRESOURCE pixels{};Check(context->Map(staging.Get(),0,D3D11_MAP_READ,0,&pixels));
    ComPtr<IWICImagingFactory> factory;Check(CoCreateInstance(CLSID_WICImagingFactory,nullptr,CLSCTX_INPROC_SERVER,IID_PPV_ARGS(&factory)));
    ComPtr<IWICStream> stream;Check(factory->CreateStream(&stream));Check(stream->InitializeFromFilename(path.c_str(),GENERIC_WRITE));
    ComPtr<IWICBitmapEncoder> encoder;Check(factory->CreateEncoder(GUID_ContainerFormatPng,nullptr,&encoder));Check(encoder->Initialize(stream.Get(),WICBitmapEncoderNoCache));
    ComPtr<IWICBitmapFrameEncode> output;Check(encoder->CreateNewFrame(&output,nullptr));Check(output->Initialize(nullptr));Check(output->SetSize(desc.Width,desc.Height));
    auto format=GUID_WICPixelFormat32bppBGRA;Check(output->SetPixelFormat(&format));
    Require(IsEqualGUID(format,GUID_WICPixelFormat32bppBGRA),"Unexpected PNG pixel format");
    std::vector<BYTE> bgra(size_t(desc.Width)*desc.Height*4);
    for(UINT y=0;y<desc.Height;++y)for(UINT x=0;x<desc.Width;++x) {
        const auto* from=static_cast<BYTE*>(pixels.pData)+y*pixels.RowPitch+x*4;
        auto* to=bgra.data()+(size_t(y)*desc.Width+x)*4;
        to[0]=from[2];to[1]=from[1];to[2]=from[0];to[3]=from[3];
    }
    Check(output->WritePixels(desc.Height,desc.Width*4,UINT(bgra.size()),bgra.data()));Check(output->Commit());Check(encoder->Commit());
    context->Unmap(staging.Get(),0);
}
using ForgeGlass::Controller;
static void TestController(Controller& c,Rml::Context* context)
{
    for(const auto& mode:MaterialColor::Modes)if(mode!="reserved"){const auto color=MaterialColor::Blend({.12f,.5f,.9f},{.8f,.25f,.3f},MaterialColor::Mode(mode));for(float v:color)Require(std::isfinite(v)&&v>=0&&v<=1,"Surface blend produced invalid color");}
    const auto initial=c.values;const int appearance=c.appearance;
    auto click=[&](const char* id) {
        auto* e=c.Element(id);e->ScrollIntoView();context->Update();const auto at=e->GetAbsoluteOffset(Rml::BoxArea::Border);const auto size=e->GetBox().GetSize(Rml::BoxArea::Border);
        if(size.x<20 || size.y<15)throw std::runtime_error(std::string("Interactive control collapsed: ")+id+" "+std::to_string(size.x)+"x"+std::to_string(size.y));
        context->ProcessMouseMove(int(at.x+size.x*.5f),int(at.y+size.y*.5f),0);context->ProcessMouseButtonDown(0,0);context->ProcessMouseButtonUp(0,0);context->Update();
    };
    click("mode-custom");Require(c.values["multiplier"]==2,"Custom mode did not activate");
    click("ratio-4");Require(c.values["multiplier"]==4,"Multiplier did not change");
    Require(c.Element("mfg-hint")->GetInnerRML().find("selected")!=std::string::npos,"MFG explanation is stale");
    click("undo");Require(c.values["multiplier"]==2,"Undo did not restore the full edit");
    click("redo");Require(c.values["multiplier"]==4,"Redo did not reapply the edit");
    click("pass-minus");Require(c.values["passes"]==2,"Pass stepper did not decrement");
    click("pass-plus");Require(c.values["passes"]==3,"Pass stepper did not increment");
    click("pass-plus");Require(c.values["passes"]==3,"Pass stepper exceeded the supported limit");
    c.Element("render-resolution")->ScrollIntoView();context->Update();c.Element("render-resolution")->Focus();const auto scale=c.values["work_scale"];
    context->ProcessKeyDown(Rml::Input::KI_RIGHT,0);context->ProcessKeyUp(Rml::Input::KI_RIGHT,0);context->Update();Require(c.values["work_scale"]>scale,"Resolution slider did not update the runtime scale");
    click("compare-b");click("style-cinematic");click("compare-a");Require(c.values["style"]==initial.at("style"),"A did not retain its tuning");
    click("compare-b");Require(c.values["style"]==2,"B did not retain its tuning");
    click("open-passes");click("pass-3");Require(c.pass==3,"Pass 3 is inaccessible");
    click("inherit");Require(c.values["pass3_inherit"]==0,"Pass inheritance did not switch");
    click("pass-style-cinematic");Require(c.values["pass3_style"]==2 && c.Element("pass-style-cinematic")->IsClassSet("selected"),"Pass style selection is stale");
    c.Element("nr-toggle")->Focus();const auto enabled=c.values["enabled"];
    context->ProcessKeyDown(Rml::Input::KI_SPACE,0);context->ProcessKeyUp(Rml::Input::KI_SPACE,0);context->Update();Require(c.values["enabled"]!=enabled,"Keyboard activation failed");
    context->ProcessKeyDown(Rml::Input::KI_SPACE,0);context->ProcessKeyUp(Rml::Input::KI_SPACE,0);context->Update();
    click("open-look");c.Put("detail",.25f);c.Sync();click("reset-inspector");Require(c.values["detail"]==c.defaults.at("detail") && c.values["pass3_style"]==2,"Look reset affected the wrong section");
    c.ShowAppearance();click("theme-dark");Require(c.appearance==2,"Dark appearance did not select");
    click("theme-light");Require(c.appearance==1,"Light appearance did not select");
    click("theme-clear");Require(c.appearance==3,"Clear appearance did not select");
    Require(c.clearOpacity==20&&c.blurRadius==48&&c.surfaceBlend=="soft-light"&&c.blendStrength==50,"Clear defaults differ from approved settings");
    c.UseTheme(2);Require(c.darkOpacity==80&&c.blurRadius==48&&c.surfaceBlend=="overlay"&&c.blendStrength==15,"Dark defaults differ from approved settings");
    c.UseTheme(1);Require(c.lightOpacity==100&&c.blurRadius==44&&c.surfaceBlend=="overlay"&&c.blendStrength==35,"Light defaults differ from approved settings");c.UseTheme(3);
    ForgeSession::Snapshot live;live.nrKnown=live.nrRunning=live.fgKnown=live.fgRunning=live.framesKnown=true;live.gameFps=60;live.displayedFps=180;live.measuredRatio=3;live.nrGpuMs=2.34;live.nrWidth=1920;live.nrHeight=1080;
    c.Session(live);Require(c.Element("compact-frames")->GetInnerRML().find("180")!=std::string::npos,"Compact card lost actual displayed FPS");
    Require(c.Element("compact-nr-size")->GetInnerRML().find("1920")!=std::string::npos,"NR card lost reported dimensions");
    c.Session({});Require(c.Element("compact-nr-size")->GetInnerRML().find("not reported")!=std::string::npos,"Missing dimensions were guessed");
    live.framesKnown=false;c.Session(live);Require(c.Element("compact-ratio")->GetInnerRML().empty(),"Unmeasured multiplier must stay hidden");c.Session({});
    c.Visible("type-panel",false);click("open-settings");Require(c.settingsOpen&&c.Element("settings-screen")->IsVisible(),"Settings must be a full screen");
    click("setting-notifications");Require(!c.showNotifications,"Notification preference did not change");click("setting-notifications");
    click("setting-stats");Require(!c.showStats&&!c.Element("compact-live")->IsVisible(),"Stats preference should hide compact data");click("setting-stats");click("settings-back");
    c.ShowAppearance();context->Update();
    c.Layout("centered");click("nav-neural");Require(c.document->IsClassSet("neural-page"),"Neural rendering needs its own sidebar page");click("nav-passes");Require(c.stacking.back()=="inspector","Centered inspectors must paint above the main window");
    click("nav-hdr");Require(c.document->IsClassSet("hdr-page"),"HDR needs its own Advanced page");
    auto* hdrGame=dynamic_cast<Rml::ElementFormControl*>(c.Element("hdr-main-ToneMapGameNits"));hdrGame->SetValue("250");hdrGame->DispatchEvent("change",{});Require(c.hdr.pending.at("ToneMapGameNits")==250,"HDR changes were not captured");
    c.hdr.Reset();Require(c.hdr.pending.at("ToneMapGameNits")==203,"HDR reset lost the source default");Require(!c.hdr.pending.contains("ToneMapPeakNits"),"HDR reset must preserve calibrated peak brightness");
    Require(c.hdr.Flush([](const std::string& request){return request.find("hdr-save")!=std::string::npos;}),"HDR save request was not sent");
    c.Layout("bar");click("open-hdr");Require(c.inspectorPanel=="hdr"&&c.inspectorAnchored,"Bar HDR needs an attached popout");
    c.Layout("bar");c.Session(live);context->Update();Require(!c.Element("compact-live")->IsVisible(),"Live telemetry must not overflow Bottom Bar metadata");click("open-passes");Require(c.inspectorAnchored,"Bar inspectors should attach to their source");c.Settings(true);context->Update();Require(c.Element("main-panel")->GetAbsoluteOffset(Rml::BoxArea::Border).y>=0,"Bottom Bar settings moved above the viewport");c.Settings(false);c.Layout("floating");context->Update();Require(c.Element("compact-live")->IsVisible(),"Sidebar must retain its compact live cards");
    c.values=initial;c.edits={};c.edits.Start(initial);c.appearance=appearance;c.pass=2;c.Sync();c.Element("theme-label")->SetInnerRML(c.appearance==1?"Light":c.appearance==3?"Clear":"Dark");
    c.Open("passes");c.Element("main-panel")->SetScrollTop(0);c.Element("inspector")->SetScrollTop(0);c.document->Focus();context->ProcessMouseMove(1800,1000,0);
    c.Message("Preview · no game connected.");
    std::cout<<"native_interaction_checks=passed\n";
}
int wmain(int argc,wchar_t** argv)
{
    try {
        fs::path assets,background,output,font;int width=2560,height=1440,appearance=3;bool inspector=false,blur=true,selfTest=false,reduceMotion=false,welcome=false,settings=false;float crop=0,requestedTint=-1;std::array<float,3> accent{.19f,.46f,.80f};std::string requestedLayout="floating",requestedBlend,requestedPage;
        for(int i=1;i<argc;++i) {
            const std::wstring arg=argv[i];
            const auto next=[&] {Require(i+1<argc,"Missing argument value");return std::wstring(argv[++i]);};
            if(arg==L"--assets")assets=next();else if(arg==L"--background")background=next();else if(arg==L"--output")output=next();
            else if(arg==L"--font")font=next();else if(arg==L"--width")width=std::stoi(next());else if(arg==L"--height")height=std::stoi(next());
            else if(arg==L"--dark")appearance=2;else if(arg==L"--light")appearance=1;else if(arg==L"--clear")appearance=3;else if(arg==L"--inspector")inspector=true;else if(arg==L"--no-blur")blur=false;else if(arg==L"--crop-left")crop=std::stof(next());
            else if(arg==L"--self-test")selfTest=true;else if(arg==L"--reduce-motion")reduceMotion=true;else if(arg==L"--welcome")welcome=true;else if(arg==L"--settings")settings=true;
            else if(arg==L"--page")requestedPage=Utf8(next());
            else if(arg==L"--layout") {requestedLayout=Utf8(next());Require(requestedLayout=="floating"||requestedLayout=="centered"||requestedLayout=="bar","Use --layout floating, centered, or bar");}
            else if(arg==L"--blend") {requestedBlend=Utf8(next());Require(MaterialColor::Valid(requestedBlend),"Unsupported blend mode");}
            else if(arg==L"--tint") {requestedTint=std::stof(next());Require(requestedTint>=0 && requestedTint<=100,"Use --tint 0..100");}
            else if(arg==L"--accent") {const auto color=next();Require(color.size()==7 && color[0]=='#' && color.find_first_not_of(L"0123456789abcdefABCDEF",1)==std::wstring::npos,"Use --accent #RRGGBB");const auto value=std::stoul(color.substr(1),nullptr,16);accent={float((value>>16)&255)/255,float((value>>8)&255)/255,float(value&255)/255};}
            else throw std::runtime_error("Unknown prototype option");
        }
        Require(!assets.empty() && !background.empty() && !font.empty(),"Supply --assets, --background and --font. Optional --output renders a PNG without opening a window.");
        Require(width>=960 && width<=3840 && height>=640 && height<=2160 && crop>=0 && crop<.8,"Invalid viewport or crop");
        Check(CoInitializeEx(nullptr,COINIT_MULTITHREADED));
        HWND window=nullptr;
        if(output.empty()) {
            SetProcessDPIAware();WNDCLASSW wc{};wc.lpfnWndProc=WindowProc;wc.hInstance=GetModuleHandleW(nullptr);wc.lpszClassName=L"RtxForgeRmlPreview";wc.hCursor=LoadCursorW(nullptr,IDC_ARROW);RegisterClassW(&wc);
            const DWORD style=WS_OVERLAPPEDWINDOW & ~(WS_THICKFRAME|WS_MAXIMIZEBOX);RECT rectangle{0,0,width,height};AdjustWindowRect(&rectangle,style,FALSE);
            MONITORINFO monitor{sizeof(MONITORINFO)};GetMonitorInfoW(MonitorFromPoint({12,12},MONITOR_DEFAULTTOPRIMARY),&monitor);
            const int chromeWidth=rectangle.right-rectangle.left-width,chromeHeight=rectangle.bottom-rectangle.top-height;
            width=std::min(width,int(monitor.rcWork.right-monitor.rcWork.left)-chromeWidth-24);height=std::min(height,int(monitor.rcWork.bottom-monitor.rcWork.top)-chromeHeight-24);
            rectangle={0,0,width,height};AdjustWindowRect(&rectangle,style,FALSE);
            window=CreateWindowW(wc.lpszClassName,L"rtxForge \u00b7 Overlay prototype",style,12,12,rectangle.right-rectangle.left,rectangle.bottom-rectangle.top,nullptr,nullptr,wc.hInstance,nullptr);Require(window!=nullptr,"Could not create preview window");
        }
        ComPtr<ID3D11Device> device;ComPtr<ID3D11DeviceContext> immediate;ComPtr<IDXGISwapChain> swapchain;
        DXGI_SWAP_CHAIN_DESC swap{};swap.BufferCount=2;swap.BufferDesc.Width=width;swap.BufferDesc.Height=height;swap.BufferDesc.Format=DXGI_FORMAT_R8G8B8A8_UNORM;swap.BufferUsage=DXGI_USAGE_RENDER_TARGET_OUTPUT;swap.OutputWindow=window;swap.SampleDesc.Count=1;swap.Windowed=TRUE;swap.SwapEffect=DXGI_SWAP_EFFECT_DISCARD;
        const auto create=[&](D3D_DRIVER_TYPE type) {return window ? D3D11CreateDeviceAndSwapChain(nullptr,type,nullptr,0,nullptr,0,D3D11_SDK_VERSION,&swap,&swapchain,&device,nullptr,&immediate):D3D11CreateDevice(nullptr,type,nullptr,0,nullptr,0,D3D11_SDK_VERSION,&device,nullptr,&immediate);};
        bool hardware=SUCCEEDED(create(D3D_DRIVER_TYPE_HARDWARE));if(!hardware)Check(create(D3D_DRIVER_TYPE_WARP));
        ComPtr<ID3D11Texture2D> target;ComPtr<ID3D11RenderTargetView> view;
        if(window)Check(swapchain->GetBuffer(0,IID_PPV_ARGS(&target)));
        else {D3D11_TEXTURE2D_DESC desc{};desc.Width=width;desc.Height=height;desc.MipLevels=1;desc.ArraySize=1;desc.Format=DXGI_FORMAT_R8G8B8A8_UNORM;desc.SampleDesc.Count=1;desc.BindFlags=D3D11_BIND_RENDER_TARGET;Check(device->CreateTexture2D(&desc,nullptr,&target));}
        Check(device->CreateRenderTargetView(target.Get(),nullptr,&view));
        ComPtr<ID3D11Texture2D> windowLayer,inkLayer;ComPtr<ID3D11RenderTargetView> windowView,inkView;ComPtr<ID3D11ShaderResourceView> windowSource,inkSource;
        D3D11_TEXTURE2D_DESC windowDesc{};target->GetDesc(&windowDesc);windowDesc.BindFlags=D3D11_BIND_RENDER_TARGET|D3D11_BIND_SHADER_RESOURCE;windowDesc.Usage=D3D11_USAGE_DEFAULT;windowDesc.CPUAccessFlags=0;windowDesc.MiscFlags=0;Check(device->CreateTexture2D(&windowDesc,nullptr,&windowLayer));Check(device->CreateRenderTargetView(windowLayer.Get(),nullptr,&windowView));Check(device->CreateShaderResourceView(windowLayer.Get(),nullptr,&windowSource));Check(device->CreateTexture2D(&windowDesc,nullptr,&inkLayer));Check(device->CreateRenderTargetView(inkLayer.Get(),nullptr,&inkView));Check(device->CreateShaderResourceView(inkLayer.Get(),nullptr,&inkSource));
        System system;PrototypeRenderer renderer(device.Get());renderer.SetViewport(width,height);
        Rml::SetSystemInterface(&system);Rml::SetRenderInterface(&renderer);Require(Rml::Initialise(),"RmlUi could not initialize");
        Rml::ElementInstancerGeneric<PaintRoot> paintInstancer;Rml::Factory::RegisterElementInstancer("paint-root",&paintInstancer);
        Require(Rml::LoadFontFace(Utf8(font),"Overlay UI",Rml::Style::FontStyle::Normal),"UI font could not load");
        auto semibold=font.parent_path()/(font.stem().wstring()+L"-SemiBold.ttf");
        if(fs::exists(semibold))Rml::LoadFontFace(Utf8(semibold),"Overlay UI",Rml::Style::FontStyle::Normal,Rml::Style::FontWeight(600));
        for(const auto& [suffix,weight]:std::vector<std::pair<std::wstring,int>>{{L"-Light.ttf",300},{L"-Bold.ttf",700},{L"-ExtraBold.ttf",800},{L"-Black.ttf",900}}){const auto path=font.parent_path()/(font.stem().wstring()+suffix);if(fs::exists(path))Rml::LoadFontFace(Utf8(path),"Overlay UI",Rml::Style::FontStyle::Normal,Rml::Style::FontWeight(weight));}
        Require(Rml::LoadFontFace(Utf8(assets.parent_path().parent_path()/L"gui/fonts/BakbakOne-Regular.ttf")),"Heading font could not load");
        Require(Rml::LoadFontFace(Utf8(assets.parent_path().parent_path()/L"gui/fonts/RobotoVariable.ttf")),"Roboto could not load");
        Require(Rml::LoadFontFace(Utf8(assets.parent_path().parent_path()/L"windows/RtxForge.Windows/Assets/Fonts/InterVariable.ttf")),"Inter could not load");
        auto* context=Rml::CreateContext("overlay",{width,height});Require(context!=nullptr,"RmlUi context could not be created");inputContext=context;
        auto* document=context->LoadDocument(Utf8(assets/L"overlay.rml"));Require(document!=nullptr,"Overlay document could not load");
        Controller controller;controller.document=document;controller.appearance=appearance;controller.accent=accent;controller.UseTheme(appearance);if(window)controller.LoadPreferences();
        controller.InstallExtraControls();
        std::vector<ForgeGlass::HdrField> hdrPreview;for(const auto& f:PreviewHdrFields)hdrPreview.push_back({f.key,f.label,f.section,f.kind,f.options,f.unit,f.minimum,f.maximum,f.step,f.initial,f.initial,f.reset,!f.reset});
        controller.hdr.Set(std::move(hdrPreview),true,true,"Preview HDR preferences. These sample controls do not change a game; connected controls save startup preferences for verified add-on builds.");
        if(!requestedBlend.empty())controller.surfaceBlend=requestedBlend;if(requestedTint>=0){if(controller.appearance==1)controller.lightOpacity=requestedTint;else if(controller.appearance==3)controller.clearOpacity=requestedTint;else controller.darkOpacity=requestedTint;}
        controller.presets["natural"]=controller.values;controller.presets["cinematic"]=controller.values;controller.presets["cinematic"]["style"]=2;controller.presets["cinematic"]["intensity"]=.8f;
        for(const auto* event:{"click","change","keydown","mouseover","mouseout","mousedown","mousemove","mouseup"})document->AddEventListener(event,&controller);
        controller.Typography();controller.Materials();
        BOOL animate=TRUE;if(SystemParametersInfoW(SPI_GETCLIENTAREAANIMATION,0,&animate,0) && !animate)reduceMotion=true;
        document->SetClass("reduce-motion",reduceMotion);controller.reducedMotion=reduceMotion||!controller.motionEnabled;
        controller.Element("theme-label")->SetInnerRML(controller.appearance==1?"Light":controller.appearance==3?"Clear":"Dark");
        controller.edits.Start(controller.values);controller.Sync();controller.SyncSettings();controller.Session({});controller.Metadata();controller.Visible("inspector",inspector);
        controller.Visible("welcome",welcome);if(welcome)controller.Welcome();
        // The stock DX11 backdrop filter did not affect both panels reliably
        // in pixel comparisons. Keep scene blur at the explicit host boundary.
        document->GetElementById("main-panel")->SetProperty("backdrop-filter","none");
        document->GetElementById("inspector")->SetProperty("backdrop-filter","none");
        document->GetElementById("welcome")->SetProperty("backdrop-filter","none");
        document->Show();
        controller.Layout(window?controller.layout:requestedLayout);if(!requestedPage.empty()){Require(requestedPage=="overview"||requestedPage=="frame"||requestedPage=="neural"||requestedPage=="hdr","Use --page overview, frame, neural, or hdr");document->SetClass("overview-page",requestedPage=="overview");document->SetClass("frame-page",requestedPage=="frame");document->SetClass("neural-page",requestedPage=="neural");document->SetClass("hdr-page",requestedPage=="hdr");controller.Navigation("nav-"+requestedPage);controller.Visible("type-panel",false);}if(inspector)controller.Open("passes");if(settings)controller.Settings(true);
        auto image=LoadImage(background);
        const auto cropUv=CropImage(image,width,height,crop);
        Backdrop backdrop(device.Get(),width,height,image.rgba.data(),image.width,image.height,cropUv.data());
        wchar_t localFolder[32768]{};GetEnvironmentVariableW(L"LOCALAPPDATA",localFolder,32768);const auto sceneCache=fs::path(localFolder)/L"rtxForge/prototypes/scenes";
        std::string sceneOptions="<option value=\"0\">Current scene</option>";
        for(const auto& scene:ScenePresets)if(fs::exists(sceneCache/scene.file))sceneOptions+="<option value=\""+std::to_string(scene.app)+"\">"+Rml::StringUtilities::EncodeRml(scene.title)+"</option>";
        controller.Element("scene-select")->SetInnerRML(sceneOptions);
        std::vector<double> costs;int frames=0;double lastPreferences=0;
        auto lastStyle=fs::last_write_time(assets/L"overlay.rcss");double nextStyleCheck=0;
        if(window)ShowWindow(window,SW_SHOW);
        do {
            MSG message;while(PeekMessageW(&message,nullptr,0,0,PM_REMOVE)){TranslateMessage(&message);DispatchMessageW(&message);}
            if(closed)break;if(window && controller.prefsDirty && system.GetElapsedTime()-lastPreferences>.5){controller.SavePreferences();lastPreferences=system.GetElapsedTime();}
            if(window && system.GetElapsedTime()>nextStyleCheck) {nextStyleCheck=system.GetElapsedTime()+.5;const auto stamp=fs::last_write_time(assets/L"overlay.rcss");if(stamp!=lastStyle){document->ReloadStyleSheet();lastStyle=stamp;}}
            if(!output.empty())system.frameTime=frames/60.;
            if(selfTest && frames==8)TestController(controller,context);
            if(controller.sceneRequest>=0){const int chosen=controller.sceneRequest;controller.sceneRequest=-1;try{
                fs::path path=background;float selectedCrop=crop;std::array<float,3> selectedAccent=accent;std::string title="OVERLAY PREVIEW";
                for(const auto& scene:ScenePresets)if(scene.app==chosen){path=sceneCache/scene.file;selectedCrop=0;selectedAccent={float((scene.accent>>16)&255)/255,float((scene.accent>>8)&255)/255,float(scene.accent&255)/255};title=scene.title;for(auto& ch:title)ch=char(std::toupper(static_cast<unsigned char>(ch)));}
                auto next=LoadImage(path);const auto uv=CropImage(next,width,height,selectedCrop);backdrop.SetPhoto(next.rgba.data(),next.width,next.height,uv.data());controller.accent=selectedAccent;controller.Element("main-panel")->QuerySelector("h1")->SetInnerRML(Rml::StringUtilities::EncodeRml(title));document->SetProperty("--accent",Controller::Hex(selectedAccent[0],selectedAccent[1],selectedAccent[2]));controller.filtered={};controller.lastAdapt=-1;
            }catch(const std::exception&){controller.Notify("Could not load preview scene");}}
            const auto start=std::chrono::steady_clock::now();
            controller.reducedMotion=reduceMotion||!controller.motionEnabled;document->SetClass("reduce-motion",controller.reducedMotion);controller.Animate(system.GetElapsedTime());controller.Adapt(backdrop.measured,system.GetElapsedTime());
            if(controller.toastUntil>0 && system.GetElapsedTime()>controller.toastUntil) {controller.Visible("welcome",false);controller.toastUntil=0;}
            context->Update();
            if(selfTest) {
                const auto point=[&](const char* id,float x=.5f){auto* e=controller.Element(id);const auto at=e->GetAbsoluteOffset(Rml::BoxArea::Border);const auto size=e->GetBox().GetSize(Rml::BoxArea::Border);context->ProcessMouseMove(int(at.x+size.x*x),int(at.y+size.y*.5f),0);};
                if(frames==12) {point("mode-custom");context->ProcessMouseButtonDown(0,0);}
                if(frames==14) {context->ProcessMouseButtonUp(0,0);Require(controller.values["multiplier"]==2,"A button click across painted frames was lost");}
                if(frames==20)controller.ShowAppearance(); if(frames==25){context->Update();point("scale-plus");context->ProcessMouseButtonDown(0,0);}
                if(frames==27) {context->ProcessMouseButtonUp(0,0);Require(controller.overlayScale>100,"Scale stepper input did not survive painted frames");}
                if(frames==36) {controller.copySize=22;controller.overlayScale=100;controller.Typography();controller.Materials();controller.values=controller.defaults;controller.edits={};controller.edits.Start(controller.values);controller.Sync();controller.SyncSettings();controller.Session({});controller.Metadata();std::cout<<"native_frame_input_checks=passed\n";}
            }
            controller.AdaptiveForeground(backdrop,system.GetElapsedTime());context->Update();
            if(selfTest&&frames==60&&controller.appearance==3){Rml::ElementList ink;document->QuerySelectorAll(ink,"label,.glyph");for(auto* e:ink)if(e->IsVisible()){bool glass=false;for(auto* parent=e;parent;parent=parent->GetParentNode())glass|=parent->IsClassSet("glass");if(glass){const auto color=e->GetProperty(e->IsClassSet("glyph")?"image-color":"color")->Get<Rml::Colourb>();Require(color.red>=230&&color.green>=225&&color.blue>=220,"Clear must never invert a label or glyph to dark ink");}}std::cout<<"clear_white_foreground_checks=passed\n";}

            std::vector<Backdrop::Panel> panels;
            for(const auto* id : {"main-panel","inspector","welcome","type-panel"}) {
                auto* e=document->GetElementById(id);
                if(e->IsVisible()) {
                    const auto at=e->GetAbsoluteOffset(Rml::BoxArea::Border);const auto size=e->GetBox().GetSize(Rml::BoxArea::Border);
                    Backdrop::Panel panel{at.x,at.y,size.x,size.y,24*context->GetDensityIndependentPixelRatio()};panel.sampleIndex=std::string(id)=="main-panel"?0:std::string(id)=="inspector"?1:std::string(id)=="welcome"?2:3;panel.scale=context->GetDensityIndependentPixelRatio();if(std::string(id)=="inspector" && controller.inspectorAnchored){panel.arrow=1;panel.anchorX=std::clamp(controller.inspectorAnchorX,at.x+24,at.x+size.x-24);}
                    const auto variable=[e](const char* name,float fallback){const auto* p=e->GetProperty(name);if(!p)return fallback;try{return std::stof(p->Get<Rml::String>());}catch(...){return fallback;}};
                    panel.readability=controller.appearance==3?1.f:0.f;panel.inkShadow=controller.textDepth?.14f:0.f;panel.blur=controller.blurRadius;panel.radius=std::clamp(variable("--corner-radius",24.f),0.f,100.f)*panel.scale;panel.saturation=std::clamp(variable("--material-saturation",1.12f),0.f,2.f);panel.grain=std::clamp(variable("--material-texture",.028f),0.f,.08f);panel.luminosity=std::clamp(variable("--material-luminosity",.04f),0.f,.25f);
                    panel.shadowOpacity=std::clamp(variable("--shadow-opacity",.30f),0.f,.5f);panel.shadowRadius=std::clamp(variable("--shadow-radius",28.f),8.f,60.f);panel.shadowOffset=std::clamp(variable("--shadow-offset",12.f),0.f,24.f);
                    panel.opacity=std::clamp(variable("--window-opacity",1.f),0.f,1.f);panel.tone=std::clamp(variable("--surface-tone",.96f),0.f,1.f);panel.grounding=std::clamp(variable("--surface-grounding",.52f),0.f,1.f);panel.blendAmount=std::clamp(variable("--material-blend-opacity",.3f),0.f,1.f);
                    if(const auto* blend=e->GetProperty("--material-blend")) {const auto name=blend->Get<Rml::String>();panel.blendMode=float(MaterialColor::Mode(name));}
                    if(const auto* blend=e->GetProperty("--shadow-blend")) {const auto name=blend->Get<Rml::String>();panel.shadowBlend=name=="overlay"?1.f:name=="soft-light"?2.f:0.f;}
                    panels.push_back(panel);
                }
            }
            // Compose each window and its UI as a unit. A front window must
            // frost the already composited lower windows, not leave their text on top.
            backdrop.Draw(target.Get(),view.Get(),{},false);
            backdrop.Sample(panels,system.GetElapsedTime());
            std::map<std::string,Backdrop::Panel> byId;size_t panelIndex=0;
            for(const auto* id:{"main-panel","inspector","welcome","type-panel"})if(controller.Element(id)->IsVisible())byId[id]=panels.at(panelIndex++);
            const auto renderUi=[&](Rml::Element* root,ID3D11RenderTargetView* destination=nullptr) {if(!destination)destination=view.Get();immediate->OMSetRenderTargets(1,&destination,nullptr);D3D11_VIEWPORT viewport{0,0,float(width),float(height),0,1};immediate->RSSetViewports(1,&viewport);renderer.BeginFrame();auto& manager=context->GetRenderManager();manager.PrepareRender({width,height});static_cast<PaintRoot*>(root)->Paint();manager.ResetState();renderer.EndFrame(destination);};
            for(const auto& id:controller.stacking)if(byId.contains(id)) {
                const float clearLayer[4]={};immediate->ClearRenderTargetView(windowView.Get(),clearLayer);backdrop.Draw(target.Get(),windowView.Get(),{byId.at(id)},blur,false);
                const float clearInk[4]={};immediate->ClearRenderTargetView(inkView.Get(),clearInk);renderUi(controller.Element(id.c_str()),inkView.Get());backdrop.DrawInk(windowView.Get(),inkSource.Get(),byId.at(id),blur);const auto velocity=controller.windowVelocity[id];backdrop.ComposeLayer(view.Get(),windowSource.Get(),velocity.x,velocity.y,controller.reducedMotion);
            }
            renderUi(document->QuerySelector(".prototype-toolbar"));
            if(controller.Element("tooltip")->IsVisible())renderUi(controller.Element("tooltip"));
            if(frames>=8)costs.push_back(std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count());
            if(window)swapchain->Present(1,0);
            ++frames;
        } while(window || frames<80);
        if(!output.empty())SaveImage(device.Get(),immediate.Get(),target.Get(),output);
        double total=0;for(double n:costs)total+=n;
        std::cout<<"renderer="<<(hardware ? "hardware":"WARP")<<" viewport="<<width<<'x'<<height<<" blur="<<(blur ? "on":"off")<<" cpu_submit_ms="<<std::fixed<<std::setprecision(3)<<(costs.empty()?0:total/costs.size())<<" samples="<<costs.size()<<"\n";
        std::cout<<"Static-scene prototype only; GPU/gameplay/HDR/Proton performance is not established.\n";
        std::cout<<"backdrop_adapter=quarter-resolution-separable-gaussian panels="<<(inspector?2:1)<<'\n';
        std::cout<<"appearance="<<(controller.appearance==1?"light":controller.appearance==3?"clear":"dark")<<" scene_sample_main="<<backdrop.measured[0].valid<<" scene_sample_inspector="<<backdrop.measured[1].valid<<'\n';
        std::cout<<"surface_blend="<<controller.surfaceBlend<<" blur="<<controller.blurRadius<<"dp clear_text_contrast=adaptive\n";
        if(window && controller.prefsDirty)controller.SavePreferences();inputContext=nullptr;for(const auto* event:{"click","change","keydown","mouseover","mouseout","mousedown","mousemove","mouseup"})document->RemoveEventListener(event,&controller);Rml::Shutdown();
        if(window)DestroyWindow(window);
        return 0;
    } catch(const std::exception& error) {std::cerr<<error.what()<<'\n';return 1;}
}
