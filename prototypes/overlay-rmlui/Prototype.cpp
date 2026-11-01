#include <windows.h>
#include <d3d11.h>
#include <wincodec.h>
#include <wrl/client.h>
#include <RmlUi/Core.h>
#include <RmlUi/Core/RenderManager.h>
#include <RmlUi/Core/ComputedValues.h>
#include <RmlUi/Core/ElementScroll.h>
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
#include <memory>
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
struct ParentWatch { HANDLE handle{}; ~ParentWatch(){if(handle)CloseHandle(handle);} };
static int pendingWidth=0,pendingHeight=0;
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
    if(message==WM_SIZE){if(w!=SIZE_MINIMIZED){pendingWidth=LOWORD(l);pendingHeight=HIWORD(l);}return 0;}
    if(message==WM_GETMINMAXINFO){RECT client{0,0,960,640};AdjustWindowRect(&client,DWORD(GetWindowLongPtrW(window,GWL_STYLE)),FALSE);auto* limits=reinterpret_cast<MINMAXINFO*>(l);limits->ptMinTrackSize={client.right-client.left,client.bottom-client.top};return 0;}
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
    void SetMouseCursor(const Rml::String& cursor) override {SetCursor(LoadCursorW(nullptr,cursor=="resize-ew"?IDC_SIZEWE:cursor=="resize-ns"?IDC_SIZENS:cursor=="move"?IDC_SIZEALL:cursor=="pointer"?IDC_HAND:cursor=="text"?IDC_IBEAM:IDC_ARROW));}
};
struct Image { unsigned width{},height{}; std::vector<Rml::byte> rgba; };
static std::array<float,4> CropImage(const Image& image,int width,int height,float crop) {
    const float available=image.width*(1-crop),factor=std::max(width/available,float(height)/image.height),shownWidth=width/factor,shownHeight=height/factor;
    return {(image.width*crop+(available-shownWidth)*.5f)/image.width,(image.height-shownHeight)*.5f/image.height,shownWidth/image.width,shownHeight/image.height};
}
static Image LoadImage(const fs::path& path);
#include "PreviewLibrary.h"
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
static void CheckChromePaint(ID3D11Device* device,ID3D11DeviceContext* context,ID3D11Texture2D* texture,ForgeGlass::Controller& controls)
{
    D3D11_TEXTURE2D_DESC desc{};texture->GetDesc(&desc);desc.Usage=D3D11_USAGE_STAGING;desc.BindFlags=0;desc.CPUAccessFlags=D3D11_CPU_ACCESS_READ;desc.MiscFlags=0;
    ComPtr<ID3D11Texture2D> staging;Check(device->CreateTexture2D(&desc,nullptr,&staging));context->CopyResource(staging.Get(),texture);
    D3D11_MAPPED_SUBRESOURCE pixels{};Check(context->Map(staging.Get(),0,D3D11_MAP_READ,0,&pixels));
    bool painted=true;
    for(const auto* id:{"open-settings","defaults"}){auto* button=controls.Element(id);const auto at=button->GetAbsoluteOffset(Rml::BoxArea::Border),size=button->GetBox().GetSize(Rml::BoxArea::Border);int ink=0;
        for(int y=std::max(0,int(at.y));y<std::min(int(desc.Height),int(at.y+size.y));++y)for(int x=std::max(0,int(at.x));x<std::min(int(desc.Width),int(at.x+size.x));++x)ink+=static_cast<const BYTE*>(pixels.pData)[size_t(y)*pixels.RowPitch+x*4+3]>128;
        painted&=ink>8;
    }
    context->Unmap(staging.Get(),0);Require(painted,"Sticky header or footer has hit targets but no painted ink");std::cout<<"native_sticky_chrome_paint_checks=passed\n";
}
using ForgeGlass::Controller;
// Demonstration data belongs to this executable, never the injected runtime.
static ForgeSession::Snapshot PreviewSession(const Controller& c,int app,int width,int height,double time)
{
    ForgeSession::Snapshot s;s.nrKnown=s.fgKnown=true;s.nrRunning=c.values.at("enabled")!=0;s.fgRunning=c.values.at("mfg_enabled")!=0;
    const double phase=(app%97)*.13,base=58+(app%7)*5;
    s.gameFps=base+std::sin(time*.7+phase)*2.6+std::sin(time*1.9+phase)*.7;
    const double requested=c.values.at("multiplier"),ratio=requested>=2?requested:requested==1?3:4;
    s.framesKnown=true;s.measuredRatio=s.fgRunning?ratio:1;s.displayedFps=s.gameFps*s.measuredRatio;
    s.nrGpuMs=s.nrRunning?2.15+std::sin(time*.8+phase)*.16+(c.values.at("passes")-1)*.52:-1;
    const float scale=std::clamp(c.values.at("work_scale"),.25f,2.f);s.nrWidth=unsigned(std::round(width*scale/2))*2;s.nrHeight=unsigned(std::round(height*scale/2))*2;
    return s;
}
static void ShowPreviewSession(Controller& c,int app,int width,int height,double time)
{
    c.Session(PreviewSession(c,app,width,height,time));
    if(c.session.fgRunning)c.Element("compact-frames")->SetInnerRML(ForgeSession::Number(c.session.gameFps)+" <img class=\"sample-flow glyph\" src=\"icons/arrow-left-light.png\"/> "+ForgeSession::Number(c.session.displayedFps)+" FPS");
    const char* api=app==1086940?"Vulkan":app==1328670?"DirectX 11":"DirectX 12";
    for(const auto* prefix:{"compact","overview","popup"})c.Element((std::string(prefix)+"-api").c_str())->SetInnerRML(api);
    for(const auto* prefix:{"overview","popup"})c.Element((std::string(prefix)+"-stack").c_str())->SetInnerRML("OptiScaler + ReShade · simulated");
    for(const auto* id:{"status-sr","status-rr","status-nr","status-fg"}){
        auto* e=c.Element(id);const bool active=std::string(id)=="status-nr"?c.session.nrRunning:std::string(id)=="status-fg"?c.session.fgRunning:std::string(id)=="status-rr"?app==1091500:true;
        for(const auto* state:{"installed","unavailable","waiting","active"})e->SetClass(state,std::string(state)==(active?"active":"unavailable"));
    }
    Rml::ElementList notes;c.document->QuerySelectorAll(notes,".preview-badge,.status-note");for(auto* e:notes)e->SetInnerRML("Sample data");
    Rml::ElementList headings;c.document->QuerySelectorAll(headings,".session-heading");for(auto* e:headings)e->GetChild(1)->SetInnerRML("Preview activity");
    std::string bars;for(int i=0;i<64;++i){const double value=31+std::sin(time*.7-i*.16)*7+std::sin(time*1.9-i*.4)*3;bars+="<div class=\"sample-history-bar\" style=\"left: "+std::to_string(i*1.5625)+"%; height: "+std::to_string(value)+"%\"/>";}
    Rml::ElementList histories;c.document->QuerySelectorAll(histories,".history-empty");for(auto* e:histories){if(auto* p=e->QuerySelector("p"))p->SetProperty("display","none");auto* chart=e->QuerySelector(".sample-history");if(!chart){auto fresh=c.document->CreateElement("div");fresh->SetClass("sample-history",true);chart=e->AppendChild(std::move(fresh));}chart->SetInnerRML(bars);}
}
static void TestLayout(Controller& c,Rml::Context* context)
{
    const auto originalView=context->GetDimensions();const auto originalScale=c.overlayScale,originalCopy=c.copySize;const auto originalValues=c.values;
    auto settle=[&](){for(int i=0;i<3;++i){context->Update();c.Reflow();}context->Update();};
    const auto rect=[](Rml::Element* e){const auto at=e->GetAbsoluteOffset(Rml::BoxArea::Border),size=e->GetBox().GetSize(Rml::BoxArea::Border);return std::array<float,4>{at.x,at.y,at.x+size.x,at.y+size.y};};
    auto contains=[&](const char* id,const std::array<float,4>& outer){const auto b=rect(c.Element(id));if(b[0]<outer[0]-2||b[1]<outer[1]-2||b[2]>outer[2]+2||b[3]>outer[3]+2)throw std::runtime_error(std::string("Layout bounds: ")+id+" at "+std::to_string(b[0])+","+std::to_string(b[1])+","+std::to_string(b[2])+","+std::to_string(b[3])+" outer "+std::to_string(outer[0])+","+std::to_string(outer[1])+","+std::to_string(outer[2])+","+std::to_string(outer[3])+" layout="+c.layout+" scale="+std::to_string(c.overlayScale)+" copy="+std::to_string(c.copySize));};
    for(const auto view:{Rml::Vector2i{1280,720},Rml::Vector2i{1920,1080},Rml::Vector2i{2560,1440}})for(int scale:{100,150})for(int copy:{20,22,24}){
        context->SetDimensions(view);c.overlayScale=scale;c.copySize=copy;c.Typography();
        const std::array<float,4> viewport{0,0,float(view.x),float(view.y)};
        for(const auto* mode:{"floating","centered","bar"}){
            c.Layout(mode);c.values["multiplier"]=3;c.Sync();settle();contains("main-panel",viewport);
            contains("open-settings",rect(c.Element("main-panel")));contains("close",rect(c.Element("main-panel")));contains("defaults",rect(c.Element("main-panel")));
            const float copyPx=copy*context->GetDensityIndependentPixelRatio();for(const auto* id:{"presets","model-preset","processing-stage","font-select"})Require(std::fabs(c.Element(id)->GetComputedValues().font_size()-copyPx)<.2f,"Shared control typography drifted between panels");
            Require(std::fabs(c.Element("preview-original")->GetComputedValues().font_size()-(copy-3)*context->GetDensityIndependentPixelRatio())<.2f,"Preview action lost its utility type role");
            const auto icon=c.Element("open-settings")->QuerySelector(".glyph");Require(std::fabs(icon->GetBox().GetSize(Rml::BoxArea::Border).x-copyPx)<.2f,"Chrome glyph does not follow the text scale");
            const auto header=rect(c.document->QuerySelector(".brand-row")),footer=rect(c.Element("tuning-footer"));auto* scroll=c.Element("overview");if(scroll->GetClientHeight()<=30)throw std::runtime_error("Tuning scroll region collapsed: "+c.layout+" "+std::to_string(view.x)+"x"+std::to_string(view.y)+" scale="+std::to_string(scale)+" copy="+std::to_string(copy)+" height="+std::to_string(scroll->GetClientHeight()));scroll->SetScrollTop(scroll->GetScrollHeight());settle();const auto headerAfter=rect(c.document->QuerySelector(".brand-row")),footerAfter=rect(c.Element("tuning-footer"));Require(std::fabs(header[1]-headerAfter[1])<2&&std::fabs(footer[1]-footerAfter[1])<2,"Header or footer scrolled with content");scroll->SetScrollTop(0);settle();
            if(c.layout=="bar"){
                settle();contains("feature-status",rect(c.Element("open-session")));contains("bar-live",rect(c.Element("main-panel")));
                const auto stats=rect(c.Element("bar-live")),actions=rect(c.document->QuerySelector(".window-actions"));Require(stats[2]<=actions[0]+2||stats[3]<=actions[1]+2||actions[3]<=stats[1]+2,"Bar stats overlap window actions");
                contains("preview-original",rect(c.Element("main-panel")));contains("defaults",rect(c.Element("main-panel")));
                const auto history=rect(c.Element("defaults")),compare=rect(c.Element("preview-original"));Require(history[2]<=compare[0]+2||history[3]<=compare[1]+2||compare[3]<=history[1]+2,"Bar history and comparison overlap");
                c.Open("look");c.Settings(true);settle();contains("inspector",viewport);Require(c.Element("settings-screen")->GetParentNode()->GetId()=="settings-modal-host"&&c.Element("overview")->IsVisible()&&!c.Element("look-inspector")->IsVisible(),"Bar Settings is not an isolated modal over its bar");const auto modal=rect(c.Element("inspector"));Require(std::fabs((modal[0]+modal[2])*.5f-view.x*.5f)<2,"Bar Settings must be centered");c.ToggleOverlay();Require(!c.settingsOpen&&!c.document->IsClassSet("bar-settings"),"Closing Bar Settings trapped the overlay");c.ToggleOverlay();settle();Require(c.Element("main-panel")->IsVisible(),"Bar did not reopen after Settings");
            }
            if(c.layout=="centered"){
                c.Page("nav-overview");settle();auto* facts=c.document->QuerySelector("#overview-metadata .session-facts");Require(facts->GetScrollWidth()<=facts->GetClientWidth()+2,"Session metadata overflows its content card");
                Require(c.Element("feature-status")->GetParentNode()==c.Element("overview-metadata"),"Advanced status lights must belong to Overview");
                auto* sidebar=c.document->QuerySelector(".sidebar");Require(sidebar->GetChild(sidebar->GetNumChildren()-1)->GetId()=="nav-settings","Settings must be the final sidebar destination");
                for(const auto* id:{"nav-overview","nav-neural","nav-look","nav-passes","nav-frame","nav-hdr","nav-settings"}){auto* nav=c.Element(id);Require(nav->GetScrollWidth()<=nav->GetClientWidth()+2,"Advanced navigation clips at the selected text size");}
                for(const auto* panel:{"look","passes","hdr"}){c.Open(panel);settle();contains("inspector",rect(c.Element("main-panel")));auto* slot=c.Element("overview");const auto at=slot->GetAbsoluteOffset(Rml::BoxArea::Border),editor=c.Element("inspector")->GetAbsoluteOffset(Rml::BoxArea::Border);Require(std::fabs(at.x-editor.x)<2&&std::fabs(at.y-editor.y)<2,"Advanced pages use different content slots");auto* bar=c.Element("inspector")->GetElementScroll()->GetScrollbar(Rml::ElementScroll::VERTICAL);if(bar&&bar->IsVisible(true)){const auto bounds=rect(c.Element("inspector")),scrollbar=rect(bar);Require(bounds[2]-scrollbar[2]>=14*context->GetDensityIndependentPixelRatio(),"Advanced scrollbar lost its inner gutter");}if(std::string(panel)=="passes"){auto* choice=c.Element("pass-style-cinematic");const auto label=rect(choice->QuerySelector(".button-label")),button=rect(choice);Require(label[0]>=button[0]+8&&label[2]<=button[2]-8,"Cinematic choice lost its side padding");}}
                c.Settings(true);settle();contains("settings-screen",rect(c.Element("main-panel")));Require(c.Element("nav-settings")->IsClassSet("selected"),"Settings did not select its sidebar destination");c.Settings(false);Require(c.Element("nav-overview")->IsClassSet("selected"),"Settings did not restore the previous destination");
            }
        }
        c.welcomePosition="top-center";c.Welcome();settle();contains("welcome",viewport);const auto toast=rect(c.Element("welcome")),toolbar=rect(c.document->QuerySelector(".prototype-toolbar"));Require(toast[1]>=toolbar[3]+1,"Welcome overlaps the scene selector");
        c.Notify("Neural rendering settings restored to the saved game preset");settle();contains("welcome",viewport);const auto toastWide=rect(c.Element("welcome"));Require(std::fabs((toastWide[0]+toastWide[2])*.5f-view.x*.5f)<2,"Variable-width toast is not centered");
    }
    context->SetDimensions({2560,1440});c.overlayScale=100;c.copySize=22;c.Typography();c.Layout("floating");
    const auto originalSide=c.sidePanelSide;
    for(const auto* side:{"left","right"}){
        c.PanelSide(side);settle();const auto main=rect(c.Element("main-panel"));
        const float inset=36*context->GetDensityIndependentPixelRatio();
        Require(std::fabs(std::string(side)=="right"?2560-main[2]-inset:main[0]-inset)<2,"Side Panel did not dock to its chosen edge");
        c.Open("look");settle();const auto popup=rect(c.Element("inspector"));
        Require(std::string(side)=="right"?popup[2]<main[0]:popup[0]>main[2],"Side Panel pop-out did not open inward");
        c.ShowAppearance();settle();const auto appearance=rect(c.Element("type-panel"));
        Require(std::string(side)=="right"?appearance[2]<main[0]:appearance[0]>main[2],"Side Panel Appearance did not open inward");
    }
    c.PanelSide(originalSide);c.Visible("type-panel",false);
    std::cout<<"native_side_panel_edge_checks=passed left_right_inward_popouts\n";
    c.overlayScale=originalScale;c.copySize=originalCopy;c.values=originalValues;context->SetDimensions(originalView);c.Typography();c.Layout("floating");c.Sync();c.Visible("welcome",false);settle();
    std::cout<<"native_layout_matrix_checks=passed cases=54\n";
}
static void TestController(Controller& c,Rml::Context* context)
{
    for(const auto& scene:ScenePresets){const auto a=PreviewSession(c,scene.app,2560,1440,0),b=PreviewSession(c,scene.app,2560,1440,1);Require(a.nrRunning&&a.fgRunning&&a.framesKnown&&a.nrWidth>0&&a.nrHeight>0&&a.displayedFps>a.gameFps&&a.gameFps!=b.gameFps,"A preview scene lost its animated sample activity");}
    std::cout<<"native_preview_scene_samples=passed games="<<std::size(ScenePresets)<<"\n";
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
    {using Json=nlohmann::json;std::string command;c.effects.send=[&](const std::string& text){command=text;return true;};
        const Json fields=Json::array({Json{{"id",0},{"label","Custom <effect>"},{"effect","Paid.fx"},{"kind","toggle"},{"value",0}},Json{{"id",1},{"label","Unknown parameter"},{"effect","Paid.fx"},{"kind","number"},{"value",7.25}},Json{{"id",2},{"label","Custom choice"},{"effect","Paid.fx"},{"kind","choice"},{"choices",Json::array({"One","Two"})},{"value",1}},Json{{"id",3},{"label","Custom INI setting"},{"effect","Add-on settings"},{"kind","text"},{"value","original"}}});
        c.effects.Set(Json{{"generation",uint64_t(7)},{"fields",fields}});c.Open("effects");context->Update();Require(c.Element("effect-field-1")&&c.Element("effect-field-2"),"Reflected custom controls were not built");click("effect-field-0");const auto sent=Json::parse(command);Require(sent["generation"]==7&&sent["id"]==0&&sent["value"]==1,"Reflected toggle lost its runtime identity");Require(c.Element("effects-fields")->GetInnerRML().find("Custom &lt;effect&gt;")!=std::string::npos,"Reflected labels must be escaped");auto* numeric=dynamic_cast<Rml::ElementFormControl*>(c.Element("effect-field-1"));numeric->SetValue("12.5");numeric->DispatchEvent("change",{});c.effects.Set(Json{{"generation",uint64_t(7)},{"fields",fields}});Require(numeric->GetValue()=="12.5","A runtime refresh erased an uncommitted parameter");click("effect-apply-1");Require(Json::parse(command)["value"]==12.5,"Unknown numeric parameter did not apply");auto* text=dynamic_cast<Rml::ElementFormControl*>(c.Element("effect-field-3"));text->SetValue("custom & <value>");text->DispatchEvent("change",{});click("effect-apply-3");Require(Json::parse(command)["value"]=="custom & <value>","Custom INI text did not round-trip");c.effects.Set(Json{{"generation",uint64_t(8)},{"fields",Json::array()}});Require(!c.document->GetElementById("effect-field-0"),"Reload retained a stale parameter");c.effects.send={};c.Visible("inspector",false);std::cout<<"native_reflected_effect_controls_checks=passed\n";
    }
    click("pass-minus");Require(c.values["passes"]==2,"Pass stepper did not decrement");
    click("pass-plus");Require(c.values["passes"]==3,"Pass stepper did not increment");
    click("pass-plus");Require(c.values["passes"]==3,"Pass stepper exceeded the supported limit");
    c.Element("render-resolution")->ScrollIntoView();context->Update();c.Element("render-resolution")->Focus();const auto scale=c.values["work_scale"];
    context->ProcessKeyDown(Rml::Input::KI_RIGHT,0);context->ProcessKeyUp(Rml::Input::KI_RIGHT,0);context->Update();Require(c.values["work_scale"]>scale,"Resolution slider did not update the runtime scale");
    {const auto saved=c.values;const auto history=c.edits.past.size();auto* button=c.Element("preview-original");button->ScrollIntoView();context->Update();const auto at=button->GetAbsoluteOffset(Rml::BoxArea::Border),size=button->GetBox().GetSize(Rml::BoxArea::Border);context->ProcessMouseMove(int(at.x+size.x*.5f),int(at.y+size.y*.5f),0);context->ProcessMouseButtonDown(0,0);Require(c.nrPreviewActive&&c.values["enabled"]==0&&c.values["mfg_enabled"]==saved.at("mfg_enabled"),"Original preview must temporarily pause NR only");context->ProcessMouseButtonUp(0,0);Require(!c.nrPreviewActive&&c.values==saved&&c.edits.past.size()==history,"Original preview changed tuning or history");button->Focus();context->ProcessKeyDown(Rml::Input::KI_SPACE,0);Require(c.nrPreviewActive,"Keyboard original preview did not start");context->ProcessKeyUp(Rml::Input::KI_SPACE,0);Require(!c.nrPreviewActive&&c.values==saved,"Keyboard original preview did not restore NR");}
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
    click("accent-tint");Require(c.appearance==4&&c.BaseAppearance()==3&&c.accentCharacter==10&&c.accentSaturation==200,"Accent tint did not preserve Clear");click("theme-light");Require(c.appearance==4&&c.BaseAppearance()==1&&c.accentCharacter==50&&c.accentSaturation==200,"Accent Light differs from the approved midpoint");click("theme-dark");Require(c.appearance==4&&c.BaseAppearance()==2&&c.accentSaturation==94,"Accent Dark differs from the approved saturation");click("accent-tint");Require(c.appearance==2,"Removing Accent Tint lost the base style");click("theme-clear");
    Require(c.clearOpacity==20&&c.blurRadius==48&&c.surfaceBlend=="soft-light"&&c.blendStrength==50,"Clear defaults differ from approved settings");
    c.UseTheme(2);Require(c.darkOpacity==80&&c.blurRadius==48&&c.surfaceBlend=="overlay"&&c.blendStrength==15,"Dark defaults differ from approved settings");
    c.UseTheme(1);Require(c.lightOpacity==100&&c.blurRadius==44&&c.surfaceBlend=="overlay"&&c.blendStrength==35,"Light defaults differ from approved settings");c.UseTheme(3);
    ForgeSession::Snapshot live;live.nrKnown=live.nrRunning=live.fgKnown=live.fgRunning=live.framesKnown=true;live.gameFps=60;live.displayedFps=180;live.measuredRatio=3;live.nrGpuMs=2.34;live.nrWidth=1920;live.nrHeight=1080;
    c.Session(live);Require(c.Element("render-resolution-value")->GetInnerRML().find("(1920 × 1080)")!=std::string::npos,"Render resolution lost measured dimensions");Require(c.Element("compact-frames")->GetInnerRML().find("180")!=std::string::npos,"Compact card lost actual displayed FPS");
    Require(c.Element("compact-nr-size")->GetInnerRML().find("1920")!=std::string::npos,"NR card lost reported dimensions");
    c.Session({});Require(c.Element("compact-nr-size")->GetInnerRML().find("not reported")!=std::string::npos,"Missing dimensions were guessed");
    live.framesKnown=false;c.Session(live);Require(c.Element("compact-ratio")->GetInnerRML().empty(),"Unmeasured multiplier must stay hidden");c.Session({});
    c.Visible("type-panel",false);click("open-settings");Require(c.settingsOpen&&c.Element("settings-screen")->IsVisible(),"Settings must be a full screen");
    click("setting-notifications");Require(!c.showNotifications,"Notification preference did not change");click("setting-notifications");
    click("setting-original-labels");Require(c.originalLabels,"Original label preference did not enable");Require(c.Element("extra-popup-interval")->GetParentNode()->QuerySelector("label")->GetInnerRML()=="Max frames between runs","Original label does not match the pinned menu");click("setting-original-labels");Require(c.Element("extra-popup-interval")->GetParentNode()->QuerySelector("label")->GetInnerRML()=="Refresh interval","Friendly label did not restore");Require(c.Element("extra-popup-interval")->GetParentNode()->QuerySelector("label")->GetAttribute<Rml::String>("title","")=="Max frames between runs","Friendly label lost its upstream tooltip");
    click("setting-stats");Require(!c.showStats&&!c.Element("compact-live")->IsVisible(),"Stats preference should hide compact data");click("setting-stats");click("window-back");
    click("open-layout");context->Update();Require(c.Element("layout-picker")->IsVisible(),"Quick layout selector did not open");click("quick-centered");Require(c.layout=="centered"&&!c.Element("layout-picker")->IsVisible(),"Quick layout selector did not switch and dismiss");
    c.ShowAppearance();context->Update();
    c.Layout("centered");click("nav-neural");Require(c.document->IsClassSet("neural-page"),"Neural rendering needs its own sidebar page");click("nav-passes");Require(c.stacking.back()=="inspector","Centered inspectors must paint above the main window");
    click("nav-hdr");Require(c.document->IsClassSet("hdr-page"),"HDR needs its own Advanced page");
    auto* hdrGame=dynamic_cast<Rml::ElementFormControl*>(c.Element("hdr-main-ToneMapGameNits"));hdrGame->SetValue("250");hdrGame->DispatchEvent("change",{});Require(c.hdr.pending.at("ToneMapGameNits")==250,"HDR changes were not captured");
    c.hdr.Reset();Require(c.hdr.pending.at("ToneMapGameNits")==203,"HDR reset lost the source default");Require(!c.hdr.pending.contains("ToneMapPeakNits"),"HDR reset must preserve calibrated peak brightness");
    Require(c.hdr.Flush([](const std::string& request){return request.find("hdr-save")!=std::string::npos;}),"HDR save request was not sent");
    click("window-back");Require(c.activeNavigation=="nav-passes","Universal back did not restore Advanced navigation history");c.Layout("centered");Require(c.Element("feature-status")->IsVisible(true),"Advanced lost its status lights");
    c.Layout("bar");click("open-hdr");Require(c.inspectorPanel=="hdr"&&c.inspectorAnchored,"Bar HDR needs an attached popout");context->Update();c.pendingEntrance.clear();c.entrances.clear();c.Reflow();context->Update();const auto stable=c.Element("inspector")->GetAbsoluteOffset(Rml::BoxArea::Border);for(int frame=0;frame<90;++frame){c.Reflow();context->Update();const auto at=c.Element("inspector")->GetAbsoluteOffset(Rml::BoxArea::Border);if(std::fabs(at.x-stable.x)>=.25f||std::fabs(at.y-stable.y)>=.25f)throw std::runtime_error("Anchored Bar popup vibrates at rest: frame="+std::to_string(frame)+" at="+std::to_string(at.x)+","+std::to_string(at.y)+" initial="+std::to_string(stable.x)+","+std::to_string(stable.y)+" height="+std::to_string(c.Element("inspector")->GetBox().GetSize(Rml::BoxArea::Border).y)+" source="+std::to_string(c.Element("open-hdr")->GetAbsoluteOffset(Rml::BoxArea::Border).y));}
    c.Layout("bar");c.Session(live);context->Update();Require(c.Element("feature-status")->IsVisible(true)&&c.Element("bar-live")->IsVisible(true),"Bar lost status or inline telemetry");Require(c.Element("compact-live")->GetParentNode()==c.Element("bar-live")&&c.Element("compact-live")->IsVisible(true),"Bar must reuse the compact live cards");Require(c.Element("compact-frame-time")->GetInnerRML()=="Frame 16.67 ms"&&c.Element("compact-neural")->GetInnerRML()=="2.34 ms","Bar cards do not match session data");click("open-passes");Require(c.inspectorAnchored,"Bar inspectors should attach to their source");c.Settings(true);context->Update();Require(c.Element("main-panel")->GetAbsoluteOffset(Rml::BoxArea::Border).y>=0,"Bottom Bar settings moved above the viewport");c.Settings(false);c.Layout("floating");context->Update();Require(c.Element("compact-live")->IsVisible()&&c.Element("compact-live")->GetParentNode()==c.Element("open-session"),"Sidebar must retain its compact live cards");
    for(const auto* mode:{"floating","centered","bar"}){
        c.Layout(mode);c.pendingEntrance.clear();c.entrances.clear();c.Reflow();context->Update();c.Reflow();context->Update();
        auto* main=c.Element("main-panel");const auto beforeAt=main->GetAbsoluteOffset(Rml::BoxArea::Border);const auto before=main->GetBox().GetSize(Rml::BoxArea::Border);auto* edge=c.Element(std::string(mode)=="bar"?"resize-top":"resize-right");const auto at=edge->GetAbsoluteOffset(Rml::BoxArea::Border),size=edge->GetBox().GetSize(Rml::BoxArea::Border);const int x=int(at.x+size.x*.5f),y=int(at.y+size.y*.5f);
        context->ProcessMouseMove(x,y,0);context->ProcessMouseButtonDown(0,0);Require(c.resizing,"Resize edge did not accept pointer input");context->ProcessMouseMove(x+(std::string(mode)=="bar"?0:80),y-(std::string(mode)=="bar"?45:0),0);context->ProcessMouseButtonUp(0,0);context->Update();c.Reflow();context->Update();const auto after=main->GetBox().GetSize(Rml::BoxArea::Border);
        const auto afterAt=main->GetAbsoluteOffset(Rml::BoxArea::Border);if(std::string(mode)!="bar")Require(std::fabs(beforeAt.x+before.x*.5f-afterAt.x-after.x*.5f)<1&&std::fabs(beforeAt.y+before.y*.5f-afterAt.y-after.y*.5f)<1,"Resizing moved the panel center");Require(!c.resizing,"Resize did not release pointer state");if(std::string(mode)=="bar"){Require(after.y>before.y+20&&std::fabs(after.x-before.x)<2,"Bar must resize vertically while retaining full width");}else Require(after.x>before.x+30,"Panel did not resize horizontally");
    }
    c.layoutSizes.clear();c.Layout("floating");context->Update();std::cout<<"native_panel_resize_checks=passed\n";
    c.preview=true;c.moreOpen=true;c.godModeOpen=false;c.Materials();c.ShowAppearance();context->Update();Require(c.Element("blur-radius")->IsVisible(true)&&!c.Element("tint-opacity")->IsVisible(true),"God Mode controls escaped into normal More options");click("appearance-god-mode");Require(c.Element("tint-opacity")->IsVisible(true),"God Mode did not reveal preview tuning");
    c.preview=false;c.moreOpen=true;c.Materials();context->Update();Require(c.Element("blur-radius")->IsVisible(true)&&c.Element("motion-effects")->IsVisible(true)&&!c.Element("appearance-god-mode")->IsVisible(true)&&!c.Element("tint-opacity")->IsVisible(true)&&!c.Element("heading-accent-mode")->IsVisible(true)&&!c.Element("toast-rounded")->IsVisible(true),"Production Appearance must expose only Blur and Motion fine tuning");
    c.UseTheme(4);context->Update();Require(!c.Element("accent-character")->IsVisible(true)&&!c.Element("accent-saturation")->IsVisible(true),"Accent tuning escaped into production Appearance");c.preview=true;c.godModeOpen=true;c.Materials();context->Update();Require(c.Element("accent-character")->IsVisible(true),"God Mode lost its Accent tuning slider");auto* character=dynamic_cast<Rml::ElementFormControl*>(c.Element("accent-character"));for(int value:{0,50,100}){character->SetValue(std::to_string(value));character->DispatchEvent("change",{});context->Update();Require(c.accentCharacter==value&&!c.customTheme,"Accent character must remain part of the standard theme");const auto tint=c.SurfaceTint();for(float channel:tint)Require(std::isfinite(channel)&&channel>=0&&channel<=1,"Accent surface produced an invalid tint");}Require(!c.AccentLight(),"Dark Accent did not change its foreground palette");
    {auto* saturation=dynamic_cast<Rml::ElementFormControl*>(c.Element("accent-saturation"));Require(saturation->IsVisible(true),"Accent needs its public saturation slider");for(int value:{0,100,200}){saturation->SetValue(std::to_string(value));saturation->DispatchEvent("change",{});context->Update();Require(c.accentSaturation==value&&!c.customTheme,"Saturation did not retain the standard Accent theme");const auto tint=c.SurfaceTint();for(float channel:tint)Require(std::isfinite(channel)&&channel>=0&&channel<=1,"Saturated tint escaped the display gamut");if(!value)Require(std::fabs(tint[0]-tint[1])<.00001f&&std::fabs(tint[1]-tint[2])<.00001f,"Zero saturation did not neutralize the surface");}c.UseTheme(4);Require(c.accentSaturation==100,"Accent reset did not restore saturation");}
    c.UseTheme(3);c.preview=true;c.godModeOpen=false;c.Materials();c.moreOpen=false;c.Materials();c.Visible("type-panel",false);
    c.Capabilities(false,false);context->Update();Require(!c.Element("neural-section")->IsVisible(true)&&!c.Element("nav-frame")->IsVisible(true)&&!c.Element("nav-neural")->IsVisible(true)&&!c.Element("presets")->IsVisible(true)&&!c.Element("tuning-footer")->IsVisible(true),"Standalone ReShade must not advertise NR/MFG tuning or presets");c.Session({});Require(!c.Element("compact-live")->IsVisible(true),"Standalone ReShade showed unavailable NR/MFG cards");c.Capabilities(true,true);context->Update();
    {float restored=-1;{Controller held;held.nrPreviewActive=true;held.nrBeforePreview=1;held.restorePreview=[&](float value){restored=value;return true;};}Require(restored==1,"Renderer/controller teardown failed to restore the preview NR state");}
    c.values=initial;c.edits={};c.edits.Start(initial);c.appearance=appearance;c.pass=2;c.Sync();c.Element("theme-label")->SetInnerRML(c.appearance==1?"Light":c.appearance==3?"Clear":c.appearance==4?"Accent":"Dark");
    c.Open("passes");c.Element("main-panel")->SetScrollTop(0);c.Element("inspector")->SetScrollTop(0);c.document->Focus();context->ProcessMouseMove(1800,1000,0);
    for(const auto* id:{"open-settings","open-layout","window-back","appearance-back","inspector-back","open-frame-options","open-processing","inspector-close"}){auto* button=c.Element(id);if(!button->IsVisible())continue;auto* glyph=button->QuerySelector(".glyph");if(!glyph)continue;const auto at=button->GetAbsoluteOffset(Rml::BoxArea::Border),size=button->GetBox().GetSize(Rml::BoxArea::Border),iconAt=glyph->GetAbsoluteOffset(Rml::BoxArea::Border),iconSize=glyph->GetBox().GetSize(Rml::BoxArea::Border);Require(std::fabs(at.x+size.x*.5f-iconAt.x-iconSize.x*.5f)<1.5f&&std::fabs(at.y+size.y*.5f-iconAt.y-iconSize.y*.5f)<1.5f,"Icon-only glyph is not centered");}
    c.Visible("type-panel",false);c.Layout("centered");c.pendingEntrance.clear();c.entrances.clear();c.coasting.clear();
    auto* main=c.Element("main-panel");main->SetProperty("left","120px");main->SetProperty("top","120px");c.mainMoved=true;context->Update();c.Reflow();context->Update();const auto moved=main->GetAbsoluteOffset(Rml::BoxArea::Border);
    for(const auto* page:{"nav-neural","nav-frame","nav-look","nav-passes","nav-overview"}){click(page);c.pendingEntrance.clear();c.entrances.clear();c.Reflow();context->Update();const auto at=main->GetAbsoluteOffset(Rml::BoxArea::Border);Require(std::fabs(at.x-moved.x)<.5f&&std::fabs(at.y-moved.y)<.5f,"Advanced navigation recenters a moved window");}
    c.Settings(true);c.Settings(false);context->Update();Require(std::fabs(main->GetAbsoluteOffset(Rml::BoxArea::Border).x-moved.x)<.5f,"Settings recenters a moved Advanced window");
    const auto view=context->GetDimensions();c.layoutSizes.clear();context->SetDimensions({1920,1080});c.Layout("centered");context->Update();const auto smallerSize=main->GetBox().GetSize(Rml::BoxArea::Border);context->SetDimensions({3840,2160});c.Reflow();context->Update();const auto largerSize=main->GetBox().GetSize(Rml::BoxArea::Border);Require(largerSize.x>smallerSize.x*1.35f&&largerSize.y>smallerSize.y*1.7f,"Advanced does not grow with the viewport");context->SetDimensions(view);c.Layout("floating");
    c.BeginSetup();context->Update();Require(c.setupStep==0&&!c.Element("main-panel")->IsVisible()&&c.Element("theme-menu")->IsVisible(true)&&!c.Element("font-select")->IsVisible(true)&&!c.Element("appearance-more")->IsVisible(true)&&!c.Element("appearance-god-mode")->IsVisible(true),"Setup appearance step leaked advanced settings");click("theme-light");click("accent-tint");Require(!c.Element("appearance-more")->IsVisible(true),"Theme change exposed setup fine tuning");click("setup-next");context->Update();Require(c.setupStep==1&&c.Element("setup-layout-centered")->IsVisible(true)&&!c.Element("theme-menu")->IsVisible(true),"Setup layout step is incomplete");click("setup-layout-centered");Require(c.layout=="centered"&&c.setupStep==1,"Setup layout choice did not update the live preview");click("appearance-back");Require(c.setupStep==0,"Setup cannot go back");click("setup-next");click("setup-next");Require(c.setupComplete&&c.setupStep<0&&!c.Element("type-panel")->IsVisible(),"Setup does not complete");c.MaybeSetup();Require(!c.Element("type-panel")->IsVisible(),"Completed setup reopens");c.BeginSetup();click("setup-skip");Require(c.setupComplete&&c.setupStep<0,"Setup skip did not complete");
    c.UseTheme(3);c.Layout("floating");c.QuickLayouts(true);context->Update();Require(c.Element("layout-picker")->GetProperty("--accent")->Get<Rml::String>()==c.AccentTone(0,false),"Layout picker uses the document fallback accent");const auto picker=c.Element("layout-picker")->GetAbsoluteOffset(Rml::BoxArea::Border),pickerSize=c.Element("layout-picker")->GetBox().GetSize(Rml::BoxArea::Border),trigger=c.Element("open-layout")->GetAbsoluteOffset(Rml::BoxArea::Border),triggerSize=c.Element("open-layout")->GetBox().GetSize(Rml::BoxArea::Border);Require(std::fabs(picker.y+pickerSize.y*.5f-trigger.y-triggerSize.y*.5f)<1,"Quick layouts moved off the header line");c.QuickLayouts(false);
    c.Layout("centered");Require(!c.Element("open-hdr")->IsVisible(true)&&c.Element("nav-hdr")->IsVisible(true),"Advanced duplicates the HDR entry");c.Layout("floating");
    Require(!c.document->GetElementById("global-review"),"Library-wide controls remain in overlay Settings");
    {
        const auto previousView=context->GetDimensions();context->SetDimensions({3840,2160});c.Layout("centered");
        for(const auto* host:{"hdr-main-fields","extra-neural","extra-frame","extra-look","pass-fields","settings-cards"}) {
            if(std::string(host)=="settings-cards")c.Settings(true);
            else {c.Settings(false);if(std::string(host)=="hdr-main-fields")c.Page("nav-hdr");else if(std::string(host)=="extra-neural")c.Page("nav-neural");else if(std::string(host)=="extra-frame")c.Page("nav-frame");else c.Open(std::string(host)=="extra-look"?"look":"passes");}
            for(int i=0;i<3;++i){c.Reflow();context->Update();}
            auto* container=c.Element(host);if(!container->IsVisible())continue;Rml::ElementList columns;container->QuerySelectorAll(columns,".mosaic-column");Require(columns.size()==2,"Wide page lost its two balanced stacks");
            for(auto* column:columns){float bottom=-1;for(int i=0;i<column->GetNumChildren();++i){auto* card=column->GetChild(i);if(!card->IsVisible())continue;const auto at=card->GetAbsoluteOffset(Rml::BoxArea::Border),size=card->GetBox().GetSize(Rml::BoxArea::Border);Require(bottom<0||at.y>=bottom+10,"Mosaic cards overlap or lose their gutter");bottom=at.y+size.y;}}
        }
        c.Settings(false);context->SetDimensions(previousView);c.Layout("floating");c.Visible("inspector",false);c.Page("nav-overview");context->Update();
        std::cout<<"native_balanced_page_stacks_checks=passed pages=6\n";
    }
    std::cout<<"native_advanced_position_resolution_and_onboarding_checks=passed\n";
    c.Message("Preview · no game connected.");
    std::cout<<"native_interaction_checks=passed\n";
}
int wmain(int argc,wchar_t** argv)
{
    try {
        fs::path assets,background,output,font,gameCatalog;DWORD parentProcess=0;int width=2560,height=1440,appearance=3,requestedCopy=22,requestedScale=100;bool gameCapture=false,thumbnail=false,desktopPreview=false,pickerPreview=false,onboarding=false,productionUI=false,appearanceOpen=false,detailsOpen=false,inspector=false,blur=true,selfTest=false,layoutTest=false,customMfg=false,reduceMotion=false,welcome=false,settings=false;float crop=0,requestedTint=-1,requestedCharacter=35,requestedSaturation=100;std::array<float,3> accent{.19f,.46f,.80f};std::string gameTitle,requestedLayout="floating",requestedBlend,requestedPage;
        for(int i=1;i<argc;++i) {
            const std::wstring arg=argv[i];
            const auto next=[&] {Require(i+1<argc,"Missing argument value");return std::wstring(argv[++i]);};
            if(arg==L"--assets")assets=next();else if(arg==L"--background")background=next();else if(arg==L"--output")output=next();
            else if(arg==L"--font")font=next();else if(arg==L"--width")width=std::stoi(next());else if(arg==L"--height")height=std::stoi(next());
            else if(arg==L"--dark")appearance=2;else if(arg==L"--light")appearance=1;else if(arg==L"--clear")appearance=3;else if(arg==L"--accent-theme")appearance=4;else if(arg==L"--accent-character")requestedCharacter=std::clamp(std::stof(next()),0.f,100.f);else if(arg==L"--inspector")inspector=true;else if(arg==L"--no-blur")blur=false;else if(arg==L"--crop-left")crop=std::stof(next());
            else if(arg==L"--accent-saturation")requestedSaturation=std::clamp(std::stof(next()),0.f,200.f);
            else if(arg==L"--layout-picker")pickerPreview=true;else if(arg==L"--onboarding")onboarding=true;else if(arg==L"--self-test")selfTest=true;else if(arg==L"--reduce-motion")reduceMotion=true;else if(arg==L"--welcome")welcome=true;else if(arg==L"--settings")settings=true;
            else if(arg==L"--page")requestedPage=Utf8(next());
            else if(arg==L"--desktop-preview"){desktopPreview=productionUI=true;}
            else if(arg==L"--game-title")gameTitle=Utf8(next());
            else if(arg==L"--game-catalog")gameCatalog=next();
            else if(arg==L"--parent-process")parentProcess=std::stoul(next());
            else if(arg==L"--thumbnail")thumbnail=true;else if(arg==L"--game-capture")gameCapture=true;
            else if(arg==L"--layout-test")layoutTest=true;else if(arg==L"--production-ui")productionUI=true;else if(arg==L"--appearance")appearanceOpen=true;else if(arg==L"--more")detailsOpen=appearanceOpen=true;
            else if(arg==L"--custom-mfg")customMfg=true;
            else if(arg==L"--text-size")requestedCopy=std::stoi(next());
            else if(arg==L"--scale")requestedScale=std::stoi(next());
            else if(arg==L"--layout") {requestedLayout=Utf8(next());Require(requestedLayout=="floating"||requestedLayout=="centered"||requestedLayout=="bar","Use --layout floating, centered, or bar");}
            else if(arg==L"--blend") {requestedBlend=Utf8(next());Require(MaterialColor::Valid(requestedBlend),"Unsupported blend mode");}
            else if(arg==L"--tint") {requestedTint=std::stof(next());Require(requestedTint>=0 && requestedTint<=100,"Use --tint 0..100");}
            else if(arg==L"--accent") {const auto color=next();Require(color.size()==7 && color[0]=='#' && color.find_first_not_of(L"0123456789abcdefABCDEF",1)==std::wstring::npos,"Use --accent #RRGGBB");const auto value=std::stoul(color.substr(1),nullptr,16);accent={float((value>>16)&255)/255,float((value>>8)&255)/255,float(value&255)/255};}
            else throw std::runtime_error("Unknown prototype option");
        }
        Require(!assets.empty() && !background.empty() && !font.empty(),"Supply --assets, --background and --font. Optional --output renders a PNG without opening a window.");
        PreviewLibrary library(gameCatalog);
        ParentWatch parent;if(parentProcess){parent.handle=OpenProcess(SYNCHRONIZE,FALSE,parentProcess);Require(parent.handle!=nullptr,"Preview parent is unavailable");}
        Require(width>=960 && width<=3840 && height>=640 && height<=2160 && crop>=0 && crop<.8,"Invalid viewport or crop");
        Require(requestedCopy>=20&&requestedCopy<=24&&requestedScale>=70&&requestedScale<=150,"Invalid text or overlay scale");
        Check(CoInitializeEx(nullptr,COINIT_MULTITHREADED));
        HWND window=nullptr;
        if(output.empty()) {
            SetProcessDPIAware();WNDCLASSW wc{};wc.lpfnWndProc=WindowProc;wc.hInstance=GetModuleHandleW(nullptr);wc.lpszClassName=L"RtxForgeRmlPreview";wc.hCursor=LoadCursorW(nullptr,IDC_ARROW);RegisterClassW(&wc);
            const DWORD style=desktopPreview?WS_POPUP|WS_THICKFRAME:WS_OVERLAPPEDWINDOW;RECT rectangle{0,0,width,height};AdjustWindowRect(&rectangle,style,FALSE);
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
        const auto fontRoot=fs::exists(assets/L"RobotoVariable.ttf")?assets:assets.parent_path().parent_path()/L"gui/fonts";
        Require(Rml::LoadFontFace(Utf8(fontRoot/L"BakbakOne-Regular.ttf")),"Heading font could not load");
        Require(Rml::LoadFontFace(Utf8(fontRoot/L"RobotoVariable.ttf")),"Roboto could not load");
        const auto inter=fs::exists(fontRoot/L"InterVariable.ttf")?fontRoot/L"InterVariable.ttf":assets.parent_path().parent_path()/L"windows/RtxForge.Windows/Assets/Fonts/InterVariable.ttf";
        Require(Rml::LoadFontFace(Utf8(inter)),"Inter could not load");
        auto* context=Rml::CreateContext("overlay",{width,height});Require(context!=nullptr,"RmlUi context could not be created");inputContext=context;
        auto* document=context->LoadDocument(Utf8(assets/L"overlay.rml"));Require(document!=nullptr,"Overlay document could not load");
        Controller controller;controller.document=document;controller.preview=!productionUI;controller.appearance=appearance;controller.accent=accent;controller.UseTheme(appearance);if(appearance==4){controller.accentCharacter=requestedCharacter;controller.accentOpacity=100*MaterialColor::AccentOpacity(requestedCharacter);controller.accentSaturation=requestedSaturation;}if(window||desktopPreview)controller.LoadPreferences(desktopPreview);
        if(desktopPreview){controller.preferences.clear();controller.setupComplete=true;controller.closePreview=[]{closed=true;};controller.Element("main-panel")->QuerySelector("h1")->SetInnerRML(Rml::StringUtilities::EncodeRml(gameTitle));document->SetClass("desktop-preview",true);if(library.names.empty())document->QuerySelector(".prototype-toolbar")->SetProperty("display","none");else document->QuerySelector(".preview-label")->SetInnerRML("Game");if(window){SetWindowTextW(window,L"rtxForge · Overlay preview");controller.Element("preview-chrome")->SetProperty("display","block");}}
        if(!gameTitle.empty())controller.Element("main-panel")->QuerySelector("h1")->SetInnerRML(Rml::StringUtilities::EncodeRml(gameTitle));document->SetClass("preview-thumbnail",thumbnail);
        if(!window&&!desktopPreview){controller.copySize=requestedCopy;controller.overlayScale=requestedScale;}if(customMfg)controller.values["multiplier"]=3;
        controller.monitorPreviewFocus=window!=nullptr;controller.InstallExtraControls();
        std::vector<ForgeGlass::HdrField> hdrPreview;for(const auto& f:PreviewHdrFields)hdrPreview.push_back({f.key,f.label,f.section,f.kind,f.options,f.unit,f.minimum,f.maximum,f.step,f.initial,f.initial,f.reset,!f.reset});
        if(!desktopPreview)controller.hdr.Set(std::move(hdrPreview),true,true,"Preview HDR preferences. These sample controls do not change a game; connected controls save startup preferences for verified add-on builds.");
        if(!requestedBlend.empty())controller.surfaceBlend=requestedBlend;if(requestedTint>=0){if(controller.appearance==1)controller.lightOpacity=requestedTint;else if(controller.appearance==3)controller.clearOpacity=requestedTint;else if(controller.appearance==4)controller.accentOpacity=requestedTint;else controller.darkOpacity=requestedTint;}
        controller.presets["natural"]=controller.values;controller.presets["cinematic"]=controller.values;controller.presets["cinematic"]["style"]=2;controller.presets["cinematic"]["intensity"]=.8f;
        for(const auto* event:{"click","change","keydown","keyup","blur","mouseover","mouseout","mousedown","mousemove","mouseup"})document->AddEventListener(event,&controller);
        controller.Typography();controller.Materials();
        BOOL animate=TRUE;if(SystemParametersInfoW(SPI_GETCLIENTAREAANIMATION,0,&animate,0) && !animate)reduceMotion=true;
        document->SetClass("reduce-motion",reduceMotion);controller.reducedMotion=reduceMotion||!controller.motionEnabled;
        controller.Element("theme-label")->SetInnerRML(controller.appearance==1?"Light":controller.appearance==3?"Clear":controller.appearance==4?"Accent":"Dark");
        controller.edits.Start(controller.values);controller.Sync();controller.SyncSettings();controller.Session({});controller.Metadata();controller.Visible("inspector",inspector);
        controller.Visible("welcome",welcome);if(welcome)controller.Welcome();
        // The stock DX11 backdrop filter did not affect both panels reliably
        // in pixel comparisons. Keep scene blur at the explicit host boundary.
        document->GetElementById("main-panel")->SetProperty("backdrop-filter","none");
        document->GetElementById("inspector")->SetProperty("backdrop-filter","none");
        document->GetElementById("welcome")->SetProperty("backdrop-filter","none");
        document->Show();
        controller.Layout((window||desktopPreview)?controller.layout:requestedLayout);if(!requestedPage.empty()){Require(requestedPage=="overview"||requestedPage=="frame"||requestedPage=="neural"||requestedPage=="hdr"||requestedPage=="look"||requestedPage=="passes","Use --page overview, frame, neural, hdr, look, or passes");document->SetClass("overview-page",requestedPage=="overview");document->SetClass("frame-page",requestedPage=="frame");document->SetClass("neural-page",requestedPage=="neural");document->SetClass("hdr-page",requestedPage=="hdr");controller.Navigation("nav-"+requestedPage);if(requestedPage=="look"||requestedPage=="passes")controller.Open(requestedPage);controller.Visible("type-panel",false);}if(inspector)controller.Open("passes");if(settings)controller.Settings(true);if(appearanceOpen){controller.moreOpen=detailsOpen;controller.Materials();controller.ShowAppearance();}
        if(onboarding)controller.BeginSetup();
        if(thumbnail&&controller.layout=="centered")controller.Page("nav-neural");
        auto image=LoadImage(background);
        float activeCrop=crop;const auto cropUv=CropImage(image,width,height,activeCrop);
        auto backdrop=std::make_unique<Backdrop>(device.Get(),width,height,image.rgba.data(),image.width,image.height,cropUv.data());
        const int initialWidth=width,initialHeight=height;
        const auto resizeTargets=[&](int nextWidth,int nextHeight){
            if(nextWidth<1||nextHeight<1||(width==nextWidth&&height==nextHeight))return;
            immediate->ClearState();view.Reset();target.Reset();windowView.Reset();windowSource.Reset();windowLayer.Reset();inkView.Reset();inkSource.Reset();inkLayer.Reset();
            width=nextWidth;height=nextHeight;
            if(window){Check(swapchain->ResizeBuffers(0,width,height,DXGI_FORMAT_UNKNOWN,0));Check(swapchain->GetBuffer(0,IID_PPV_ARGS(&target)));}
            else{D3D11_TEXTURE2D_DESC desc{};desc.Width=width;desc.Height=height;desc.MipLevels=1;desc.ArraySize=1;desc.Format=DXGI_FORMAT_R8G8B8A8_UNORM;desc.SampleDesc.Count=1;desc.BindFlags=D3D11_BIND_RENDER_TARGET;Check(device->CreateTexture2D(&desc,nullptr,&target));}
            Check(device->CreateRenderTargetView(target.Get(),nullptr,&view));target->GetDesc(&windowDesc);windowDesc.BindFlags=D3D11_BIND_RENDER_TARGET|D3D11_BIND_SHADER_RESOURCE;windowDesc.Usage=D3D11_USAGE_DEFAULT;windowDesc.CPUAccessFlags=0;windowDesc.MiscFlags=0;
            Check(device->CreateTexture2D(&windowDesc,nullptr,&windowLayer));Check(device->CreateRenderTargetView(windowLayer.Get(),nullptr,&windowView));Check(device->CreateShaderResourceView(windowLayer.Get(),nullptr,&windowSource));Check(device->CreateTexture2D(&windowDesc,nullptr,&inkLayer));Check(device->CreateRenderTargetView(inkLayer.Get(),nullptr,&inkView));Check(device->CreateShaderResourceView(inkLayer.Get(),nullptr,&inkSource));
            renderer.SetViewport(width,height);context->SetDimensions({width,height});const auto uv=CropImage(image,width,height,activeCrop);backdrop=std::make_unique<Backdrop>(device.Get(),width,height,image.rgba.data(),image.width,image.height,uv.data());controller.filtered={};controller.lastAdapt=-1;controller.mainMoved=false;controller.fittedLayout.clear();controller.coasting.clear();controller.entrances.clear();controller.pendingEntrance.clear();controller.QuickLayouts(false);controller.Metadata();controller.Reflow();
        };
        wchar_t localFolder[32768]{};GetEnvironmentVariableW(L"LOCALAPPDATA",localFolder,32768);const auto sceneCache=fs::path(localFolder)/L"rtxForge/prototypes/scenes";
        std::string sceneOptions="<option value=\"0\">Current scene</option>";
        for(const auto& scene:ScenePresets)if(fs::exists(sceneCache/scene.file))sceneOptions+="<option value=\""+std::to_string(scene.app)+"\">"+Rml::StringUtilities::EncodeRml(scene.title)+"</option>";
        if(!library.names.empty()){sceneOptions.clear();for(size_t i=0;i<library.names.size();++i)sceneOptions+="<option value=\""+std::to_string(i)+"\">"+Rml::StringUtilities::EncodeRml(library.names[i])+"</option>";}
        controller.Element("scene-select")->SetInnerRML(sceneOptions);
        std::vector<double> costs;int frames=0;double lastPreferences=0,nextSample=0;int selectedScene=0;auto stableAccent=accent;
        if(!desktopPreview)for(const auto& scene:ScenePresets)if(background.stem()==fs::path(scene.file).stem()){selectedScene=scene.app;controller.sceneRequest=scene.app;break;}
        auto lastStyle=fs::last_write_time(assets/L"overlay.rcss");double nextStyleCheck=0;
        if(window)ShowWindow(window,SW_SHOW);
        do {
            if(parent.handle&&WaitForSingleObject(parent.handle,0)!=WAIT_TIMEOUT)break;
            MSG message;while(PeekMessageW(&message,nullptr,0,0,PM_REMOVE)){TranslateMessage(&message);DispatchMessageW(&message);}
            if(window&&IsIconic(window)){Sleep(16);continue;}
            if(window&&pendingWidth&&pendingHeight){resizeTargets(pendingWidth,pendingHeight);pendingWidth=pendingHeight=0;}
            if(selfTest&&frames==2)resizeTargets(1280,720);
            if(selfTest&&frames==4){resizeTargets(initialWidth,initialHeight);std::cout<<"native_render_target_resize_checks=passed\n";}
            if(closed)break;if(window && controller.prefsDirty && system.GetElapsedTime()-lastPreferences>.5){controller.SavePreferences();lastPreferences=system.GetElapsedTime();}
            if(window && system.GetElapsedTime()>nextStyleCheck) {nextStyleCheck=system.GetElapsedTime()+.5;const auto stamp=fs::last_write_time(assets/L"overlay.rcss");if(stamp!=lastStyle){document->ReloadStyleSheet();lastStyle=stamp;}}
            if(!output.empty())system.frameTime=frames/60.;
            if((layoutTest||selfTest)&&frames==8)TestLayout(controller,context);
            if(selfTest && frames==8)TestController(controller,context);
            if(controller.sceneRequest>=0&&!library.names.empty()){library.Choose(controller.sceneRequest);controller.sceneRequest=-1;document->QuerySelector(".preview-label")->SetInnerRML("Loading…");}
            if(controller.sceneRequest>=0){const int chosen=controller.sceneRequest;controller.sceneRequest=-1;try{
                fs::path path=background;float selectedCrop=crop;std::array<float,3> selectedAccent=accent;std::string title="Overlay preview";
                for(const auto& scene:ScenePresets)if(scene.app==chosen){path=sceneCache/scene.file;selectedCrop=0;selectedAccent={float((scene.accent>>16)&255)/255,float((scene.accent>>8)&255)/255,float(scene.accent&255)/255};title=scene.title;}
                if(!gameTitle.empty())title=gameTitle;auto next=LoadImage(path);const auto uv=CropImage(next,width,height,selectedCrop);backdrop->SetPhoto(next.rgba.data(),next.width,next.height,uv.data());image=std::move(next);activeCrop=selectedCrop;selectedScene=chosen;nextSample=0;controller.accent=selectedAccent;controller.Element("main-panel")->QuerySelector("h1")->SetInnerRML(Rml::StringUtilities::EncodeRml(title));dynamic_cast<Rml::ElementFormControl*>(controller.Element("scene-select"))->SetValue(std::to_string(chosen));document->SetProperty("--accent",Controller::Hex(selectedAccent[0],selectedAccent[1],selectedAccent[2]));controller.filtered={};controller.lastAdapt=-1;
            }catch(const std::exception&){controller.Notify("Could not load preview scene");}}
            if(!library.names.empty())if(auto reply=library.Poll())try{
                const auto& value=*reply;
                if(value.contains("error"))throw std::runtime_error(value["error"].get<std::string>());
                const auto color=value.at("accent").get<std::string>();
                Require(color.size()==7&&color[0]=='#'&&color.find_first_not_of("0123456789abcdefABCDEF",1)==std::string::npos,"Invalid preview accent");
                const auto packed=std::stoul(color.substr(1),nullptr,16);
                const std::array<float,3> selectedAccent{float((packed>>16)&255)/255,float((packed>>8)&255)/255,float(packed&255)/255};
                if(value.contains("path")){
                    const auto selectedCrop=value.value("crop",0.f);Require(selectedCrop>=0&&selectedCrop<.8f,"Invalid preview crop");
                    auto next=LoadImage(fs::u8path(value.at("path").get<std::string>()));const auto uv=CropImage(next,width,height,selectedCrop);
                    backdrop->SetPhoto(next.rgba.data(),next.width,next.height,uv.data());image=std::move(next);activeCrop=selectedCrop;stableAccent=selectedAccent;
                    library.selected=value.at("index").get<int>();
                    controller.Element("main-panel")->QuerySelector("h1")->SetInnerRML(Rml::StringUtilities::EncodeRml(value.at("title").get<std::string>()));
                    document->QuerySelector(".preview-label")->SetInnerRML("Game");controller.Metadata();
                }
                controller.accent=selectedAccent;document->SetProperty("--accent",Controller::Hex(selectedAccent[0],selectedAccent[1],selectedAccent[2]));controller.filtered={};controller.lastAdapt=-1;
            }catch(const std::exception& error){
                controller.accent=stableAccent;document->QuerySelector(".preview-label")->SetInnerRML("Game");
                document->SetProperty("--accent",Controller::Hex(stableAccent[0],stableAccent[1],stableAccent[2]));
                dynamic_cast<Rml::ElementFormControl*>(controller.Element("scene-select"))->SetValue(std::to_string(library.selected));controller.Notify(error.what());
            }
            const auto start=std::chrono::steady_clock::now();
            if(!productionUI&&!selfTest&&!layoutTest&&system.GetElapsedTime()>=nextSample){ShowPreviewSession(controller,selectedScene,width,height,controller.reducedMotion?0:system.GetElapsedTime());nextSample=system.GetElapsedTime()+.25;}
            controller.reducedMotion=reduceMotion||!controller.motionEnabled;document->SetClass("reduce-motion",controller.reducedMotion);controller.Animate(system.GetElapsedTime());controller.Adapt(backdrop->measured,system.GetElapsedTime());
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
            controller.AdaptiveForeground(*backdrop,system.GetElapsedTime());context->Update();
            if(selfTest&&frames==44){
                const auto savedAccent=controller.accent;
                auto paint=[&]{controller.Adapt(backdrop->measured,system.GetElapsedTime());controller.AdaptiveForeground(*backdrop,system.GetElapsedTime());context->Update();};
                auto* label=document->QuerySelector(".field-heading label");auto* glyph=controller.Element("open-settings")->QuerySelector(".glyph");
                controller.UseTheme(3);paint();Require(label->GetProperty("color")->Get<Rml::Colourb>().red>=225,"Clear label is not light");
                controller.accent={.9f,.7f,.4f};paint();controller.headingAccentBlend="hard-light";controller.controlAccentBlend="soft-light";controller.Materials();paint();
                controller.UseTheme(1);paint();Require(label->GetProperty("color")->Get<Rml::Colourb>().red<160&&glyph->GetProperty("image-color")->Get<Rml::Colourb>().red<160,"Clear foreground leaked into Light after changing accents");
                controller.accent={.2f,.5f,.9f};paint();const auto normal=controller.Element("main-panel")->QuerySelector("h1")->GetProperty("color")->Get<Rml::Colourb>();controller.headingAccentBlend="hard-light";paint();Require(normal!=controller.Element("main-panel")->QuerySelector("h1")->GetProperty("color")->Get<Rml::Colourb>(),"Light heading blend changes did not update its accent");
                controller.UseTheme(2);paint();auto* selectedMode=controller.Element("mfg-mode")->QuerySelector(".selected");Require(selectedMode,"Frame-generation mode selection missing");selectedMode->SetProperty("transition","none");paint();const auto screen=selectedMode->GetProperty("background-color")->Get<Rml::Colourb>();controller.controlAccentBlend="multiply";paint();Require(screen!=selectedMode->GetProperty("background-color")->Get<Rml::Colourb>(),"Dark control blend changes did not update its accent");selectedMode->RemoveProperty("transition");
                controller.UseTheme(3);paint();controller.UseTheme(1);paint();Require(label->GetProperty("color")->Get<Rml::Colourb>().red<160,"Repeated Clear to Light transition leaked ink");
                controller.accent={252.f/255,238.f/255,9.f/255};controller.UseTheme(1);paint();
                const auto yellowHeading=controller.Element("main-panel")->QuerySelector("h1")->GetProperty("color")->Get<Rml::Colourb>();Require(std::abs(int(yellowHeading.red)-int(yellowHeading.green))<12,"Light yellow headings must use neutral ink");Require(controller.AccentTone(0,false).starts_with("#fcee"),"Light controls turned vivid Cyberpunk yellow into a muddy shade");Require(controller.headingAccentBlend=="multiply"&&controller.controlAccentBlend=="normal","Light accent defaults differ from the requested modes");
                controller.accent=savedAccent;controller.UseTheme(3);paint();std::cout<<"native_theme_transition_checks=passed clear_light_dark_accent_blends=passed\n";
            }
            if(selfTest&&frames==60&&controller.appearance==3){Rml::ElementList ink;document->QuerySelectorAll(ink,"label,.glyph");for(auto* e:ink)if(e->IsVisible()){bool glass=false;for(auto* parent=e;parent;parent=parent->GetParentNode())glass|=parent->IsClassSet("glass");if(glass){bool heading=false;for(auto* p=e;p;p=p->GetParentNode())heading|=p->GetTagName()=="h1"||p->GetTagName()=="h2"||p->GetTagName()=="h3";if(heading)continue;const auto color=e->GetProperty(e->IsClassSet("glyph")?"image-color":"color")->Get<Rml::Colourb>();Require(color.red>=230&&color.green>=225&&color.blue>=220,"Clear must never invert a label or glyph to dark ink");}}std::cout<<"clear_white_foreground_checks=passed\n";}

            if(pickerPreview&&frames==68)controller.QuickLayouts(true);
            std::vector<Backdrop::Panel> panels;
            for(const auto* id : {"main-panel","inspector","welcome","type-panel"}) {
                auto* e=document->GetElementById(id);
                if(e->IsVisible()) {
                    const auto at=e->GetAbsoluteOffset(Rml::BoxArea::Border);const auto size=e->GetBox().GetSize(Rml::BoxArea::Border);
                    Backdrop::Panel panel{at.x,at.y,size.x,size.y,24*context->GetDensityIndependentPixelRatio()};panel.sampleIndex=std::string(id)=="main-panel"?0:std::string(id)=="inspector"?1:std::string(id)=="welcome"?2:3;panel.scale=context->GetDensityIndependentPixelRatio();if(std::string(id)=="inspector" && controller.inspectorAnchored){panel.arrow=1;panel.anchorX=std::clamp(controller.inspectorAnchorX,at.x+24,at.x+size.x-24);}
                    const auto variable=[e](const char* name,float fallback){const auto* p=e->GetProperty(name);if(!p)return fallback;try{return std::stof(p->Get<Rml::String>());}catch(...){return fallback;}};
                    panel.colored=controller.appearance==4;panel.tint=controller.SurfaceTint();panel.readability=(controller.appearance==3||(controller.appearance==4&&!controller.AccentLight()))?1.f:0.f;panel.inkShadow=controller.textDepth?.14f:0.f;panel.blur=controller.blurRadius;panel.radius=std::clamp(variable("--corner-radius",24.f),0.f,100.f)*panel.scale;panel.saturation=std::clamp(variable("--material-saturation",1.12f),0.f,2.f);panel.grain=std::clamp(variable("--material-texture",.028f),0.f,.08f);panel.luminosity=std::clamp(variable("--material-luminosity",.04f),0.f,.25f);
                    panel.shadowOpacity=std::clamp(variable("--shadow-opacity",.30f),0.f,.5f);panel.shadowRadius=std::clamp(variable("--shadow-radius",28.f),8.f,60.f);panel.shadowOffset=std::clamp(variable("--shadow-offset",12.f),0.f,24.f);
                    panel.opacity=std::clamp(variable("--window-opacity",1.f),0.f,1.f);panel.tone=std::clamp(variable("--surface-tone",.96f),0.f,1.f);panel.grounding=std::clamp(variable("--surface-grounding",.52f),0.f,1.f);panel.blendAmount=std::clamp(variable("--material-blend-opacity",.3f),0.f,1.f);
                    if(const auto* blend=e->GetProperty("--material-blend")) {const auto name=blend->Get<Rml::String>();panel.blendMode=float(MaterialColor::Mode(name));}
                    if(const auto* blend=e->GetProperty("--shadow-blend")) {const auto name=blend->Get<Rml::String>();panel.shadowBlend=name=="overlay"?1.f:name=="soft-light"?2.f:0.f;}
                    panels.push_back(panel);
                }
            }
            // Compose each window and its UI as a unit. A front window must
            // frost the already composited lower windows, not leave their text on top.
            backdrop->Draw(target.Get(),view.Get(),{},false);
            backdrop->Sample(panels,system.GetElapsedTime());
            std::map<std::string,Backdrop::Panel> byId;size_t panelIndex=0;
            for(const auto* id:{"main-panel","inspector","welcome","type-panel"})if(controller.Element(id)->IsVisible())byId[id]=panels.at(panelIndex++);
            const auto renderUi=[&](Rml::Element* root,ID3D11RenderTargetView* destination=nullptr) {if(!destination)destination=view.Get();immediate->OMSetRenderTargets(1,&destination,nullptr);D3D11_VIEWPORT viewport{0,0,float(width),float(height),0,1};immediate->RSSetViewports(1,&viewport);renderer.BeginFrame();auto& manager=context->GetRenderManager();manager.PrepareRender({width,height});static_cast<PaintRoot*>(root)->Paint();manager.ResetState();renderer.EndFrame(destination);};
            for(const auto& id:controller.stacking)if(byId.contains(id)) {
                const float clearLayer[4]={};immediate->ClearRenderTargetView(windowView.Get(),clearLayer);if(!(id=="inspector"&&controller.layout=="centered"))backdrop->Draw(target.Get(),windowView.Get(),{byId.at(id)},blur,false);
                const float clearInk[4]={};immediate->ClearRenderTargetView(inkView.Get(),clearInk);renderUi(controller.Element(id.c_str()),inkView.Get());if(selfTest&&frames==70&&id=="main-panel")CheckChromePaint(device.Get(),immediate.Get(),inkLayer.Get(),controller);backdrop->DrawInk(windowView.Get(),inkSource.Get(),byId.at(id),blur);const auto velocity=controller.windowVelocity[id];backdrop->ComposeLayer(view.Get(),windowSource.Get(),velocity.x,velocity.y,controller.reducedMotion);
            }
            if((!desktopPreview||!library.names.empty())&&!gameCapture)renderUi(document->QuerySelector(".prototype-toolbar"));
            if(desktopPreview&&window)renderUi(controller.Element("preview-chrome"));
            for(const auto* popup:{"layout-picker","tooltip"})if(controller.Element(popup)->IsVisible()){
                if(std::string(popup)=="layout-picker"&&byId.contains("main-panel")){const auto panel=controller.QuickLayoutSurface(byId.at("main-panel"));const float clear[4]={};immediate->ClearRenderTargetView(windowView.Get(),clear);backdrop->Draw(target.Get(),windowView.Get(),{panel},blur,false);immediate->ClearRenderTargetView(inkView.Get(),clear);renderUi(controller.Element(popup),inkView.Get());backdrop->DrawInk(windowView.Get(),inkSource.Get(),panel,blur);backdrop->ComposeLayer(view.Get(),windowSource.Get(),0,0,true);}
                else renderUi(controller.Element(popup));
            }
            if(frames>=8)costs.push_back(std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count());
            if(window)swapchain->Present(1,0);
            ++frames;
        } while(window || frames<80);
        if(!output.empty())SaveImage(device.Get(),immediate.Get(),target.Get(),output);
        double total=0;for(double n:costs)total+=n;
        std::cout<<"renderer="<<(hardware ? "hardware":"WARP")<<" viewport="<<width<<'x'<<height<<" blur="<<(blur ? "on":"off")<<" cpu_submit_ms="<<std::fixed<<std::setprecision(3)<<(costs.empty()?0:total/costs.size())<<" samples="<<costs.size()<<"\n";
        std::cout<<"Static-scene prototype only; GPU/gameplay/HDR/Proton performance is not established.\n";
        std::cout<<"backdrop_adapter=quarter-resolution-separable-gaussian panels="<<(inspector?2:1)<<'\n';
        std::cout<<"appearance="<<(controller.appearance==1?"light":controller.appearance==3?"clear":controller.appearance==4?"accent":"dark")<<" scene_sample_main="<<backdrop->measured[0].valid<<" scene_sample_inspector="<<backdrop->measured[1].valid<<'\n';
        std::cout<<"surface_blend="<<controller.surfaceBlend<<" blur="<<controller.blurRadius<<"dp clear_text_contrast=adaptive\n";
        if(window && controller.prefsDirty)controller.SavePreferences();inputContext=nullptr;for(const auto* event:{"click","change","keydown","keyup","blur","mouseover","mouseout","mousedown","mousemove","mouseup"})document->RemoveEventListener(event,&controller);Rml::Shutdown();
        if(window)DestroyWindow(window);
        return 0;
    } catch(const std::exception& error) {std::cerr<<error.what()<<'\n';return 1;}
}
