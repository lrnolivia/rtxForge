#include <windows.h>
#include <d3d11_1.h>
#include <d3d11on12.h>
#include <wincodec.h>
#include <wrl/client.h>
#include <RmlUi/Core.h>
#include <RmlUi/Core/RenderManager.h>
#include <RmlUi/Core/ElementInstancer.h>
#include <RmlUi_Renderer_DX11.h>
#include <GlassOverlay.h>
#include <OverlayController.h>
#include "GlassAssets.generated.h"
#include <chrono>
#include <memory>
#include <mutex>
#include <vector>
#include <json.hpp>
#include <set>
using Microsoft::WRL::ComPtr;
namespace {
void Check(HRESULT n){if(FAILED(n))throw std::runtime_error("Glass renderer operation failed: "+std::to_string(n));}
struct Asset {const unsigned char* data{};size_t size{};};
Asset Find(const std::string& name) {
    HMODULE module{};GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,reinterpret_cast<LPCWSTR>(&Find),&module);
    auto path=std::filesystem::path(name).lexically_normal().generic_string();
    for(const auto& entry:EmbeddedAssets)if(path==entry.name){const auto resource=FindResourceW(module,MAKEINTRESOURCEW(entry.id),RT_RCDATA);if(resource)return {static_cast<const unsigned char*>(LockResource(LoadResource(module,resource))),SizeofResource(module,resource)};}
    return {};
}
struct Files : Rml::FileInterface {
    struct OpenFile {Asset asset;size_t offset{};};
    Rml::FileHandle Open(const Rml::String& path) override {const auto asset=Find(path);return asset.data?reinterpret_cast<Rml::FileHandle>(new OpenFile{asset}):0;}
    void Close(Rml::FileHandle f) override {delete reinterpret_cast<OpenFile*>(f);}
    size_t Read(void* dst,size_t size,Rml::FileHandle f) override {auto& file=*reinterpret_cast<OpenFile*>(f);const auto n=std::min(size,file.asset.size-file.offset);std::memcpy(dst,file.asset.data+file.offset,n);file.offset+=n;return n;}
    bool Seek(Rml::FileHandle f,long offset,int origin) override {auto& file=*reinterpret_cast<OpenFile*>(f);const auto at=(origin==SEEK_SET?0:origin==SEEK_END?int64_t(file.asset.size):int64_t(file.offset))+offset;if(at<0||uint64_t(at)>file.asset.size)return false;file.offset=size_t(at);return true;}
    size_t Tell(Rml::FileHandle f) override {return reinterpret_cast<OpenFile*>(f)->offset;}
    size_t Length(Rml::FileHandle f) override {return reinterpret_cast<OpenFile*>(f)->asset.size;}
};
struct System : Rml::SystemInterface {
    std::chrono::steady_clock::time_point start=std::chrono::steady_clock::now();
    double GetElapsedTime() override {return std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();}
    bool LogMessage(Rml::Log::Type,const Rml::String& message) override {OutputDebugStringA(("rtxForge overlay: "+message+"\n").c_str());return true;}
};
struct Root : Rml::Element {explicit Root(const Rml::String& tag):Rml::Element(tag){ForceLocalStackingContext();}void Paint(){Render();}};
struct Renderer : RenderInterface_DX11 {
    using RenderInterface_DX11::RenderInterface_DX11;
    Rml::TextureHandle LoadTexture(Rml::Vector2i& dimensions,const Rml::String& name) override {
        const auto asset=Find(name);if(!asset.data||asset.size>10*1024*1024)return 0;
        ComPtr<IWICImagingFactory> factory;Check(CoCreateInstance(CLSID_WICImagingFactory,nullptr,CLSCTX_INPROC_SERVER,IID_PPV_ARGS(&factory)));
        ComPtr<IWICStream> stream;Check(factory->CreateStream(&stream));Check(stream->InitializeFromMemory(const_cast<BYTE*>(asset.data),DWORD(asset.size)));
        ComPtr<IWICBitmapDecoder> decoder;Check(factory->CreateDecoderFromStream(stream.Get(),nullptr,WICDecodeMetadataCacheOnLoad,&decoder));ComPtr<IWICBitmapFrameDecode> frame;Check(decoder->GetFrame(0,&frame));
        UINT w,h;Check(frame->GetSize(&w,&h));if(w>2048||h>2048)return 0;
        ComPtr<IWICFormatConverter> converter;Check(factory->CreateFormatConverter(&converter));Check(converter->Initialize(frame.Get(),GUID_WICPixelFormat32bppPRGBA,WICBitmapDitherTypeNone,nullptr,0,WICBitmapPaletteTypeCustom));
        std::vector<Rml::byte> rgba(size_t(w)*h*4);Check(converter->CopyPixels(nullptr,w*4,UINT(rgba.size()),rgba.data()));dimensions={int(w),int(h)};return GenerateTexture(rgba,dimensions);
    }
};
// A complete context-state swap isolates initialization, compositor passes and
// readback. Restore the game's state even when setup or rendering throws.
struct StateScope {
    ComPtr<ID3D11DeviceContext1> context;ComPtr<ID3DDeviceContextState> previous,clean;
    explicit StateScope(ID3D11Device* device) {
        ComPtr<ID3D11Device1> d;Check(device->QueryInterface(IID_PPV_ARGS(&d)));ComPtr<ID3D11DeviceContext> base;device->GetImmediateContext(&base);Check(base.As(&context));
        const auto level=device->GetFeatureLevel();D3D_FEATURE_LEVEL selected;Check(d->CreateDeviceContextState(0,&level,1,D3D11_SDK_VERSION,__uuidof(ID3D11Device),&selected,&clean));context->SwapDeviceContextState(clean.Get(),&previous);
    }
    ~StateScope(){if(context&&previous)context->SwapDeviceContextState(previous.Get(),nullptr);}
};
Rml::Input::KeyIdentifier Key(int vk){if(vk>='A'&&vk<='Z')return Rml::Input::KeyIdentifier(Rml::Input::KI_A+vk-'A');if(vk>=VK_F1&&vk<=VK_F12)return Rml::Input::KeyIdentifier(Rml::Input::KI_F1+vk-VK_F1);switch(vk){case VK_TAB:return Rml::Input::KI_TAB;case VK_RETURN:return Rml::Input::KI_RETURN;case VK_SPACE:return Rml::Input::KI_SPACE;case VK_ESCAPE:return Rml::Input::KI_ESCAPE;case VK_DELETE:return Rml::Input::KI_DELETE;case VK_HOME:return Rml::Input::KI_HOME;case VK_END:return Rml::Input::KI_END;case VK_BACK:return Rml::Input::KI_BACK;case VK_LEFT:return Rml::Input::KI_LEFT;case VK_RIGHT:return Rml::Input::KI_RIGHT;case VK_UP:return Rml::Input::KI_UP;case VK_DOWN:return Rml::Input::KI_DOWN;default:return Rml::Input::KI_UNKNOWN;}}
struct Runtime {
    Files files;System system;Rml::ElementInstancerGeneric<Root> roots;
    ComPtr<ID3D11Device> device;ComPtr<ID3D11DeviceContext> immediate;
    ComPtr<ID3D11Texture2D> windowLayer;ComPtr<ID3D11RenderTargetView> windowView;ComPtr<ID3D11ShaderResourceView> windowSource;
    std::unique_ptr<Renderer> renderer;std::unique_ptr<Backdrop> backdrop;std::unique_ptr<ForgeGlass::Controller> controls;
    Rml::Context* context{};Rml::ElementDocument* document{};bool initialized=false,mouse[3]{},keys[256]{},hostVisible=false;int width{},height{};DXGI_FORMAT format{};
    ForgeWorkbench::Values lastValues;
    ForgeWorkbench::History history;double historyPaint=-1;
    double nextTelemetry=0,nextPreferences=0;std::string lastHelper;
    unsigned outputSpace=0;
    bool receivedSnapshot=false,messageInitialized=false,dx12Interop=false,systemReducedMotion=false;
    int helperRevision=-1;bool helperReady=false;std::set<std::string> supportedKeys;
    std::map<std::string,nlohmann::json> pendingSettings;
    nlohmann::json SettingsValues()const {const auto& c=*controls;return {{"overlay_helper",c.helperEnabled},{"overlay_start_with_windows",c.startWithWindows},{"overlay_live_stats",c.showStats},{"overlay_welcome",c.showWelcome},{"overlay_welcome_position",c.welcomePosition},{"overlay_renderer",c.primaryMenu},{"optiscaler_hotkey",c.optiShortcut},{"optiscaler_ui",c.menuSettings.at("opti-menu")},{"optiscaler_intro",c.menuSettings.at("opti-intro")},{"reshade_ui",c.menuSettings.at("reshade-menu")},{"reshade_intro",c.menuSettings.at("reshade-intro")}};}
    void Helper(const char* text) {
        if(!text||std::strlen(text)>65536||lastHelper==text)return;lastHelper=text;const auto data=nlohmann::json::parse(text,nullptr,false);if(!data.is_object())return;
        auto& c=*controls;helperReady=data.value("ready",false);c.Disabled("save",!helperReady||!data.value("named_supported",false)||data.value("pending",false));
        const int revision=data.value("revision",0);if(revision==helperRevision)return;helperRevision=revision;
        if(data.contains("settings")&&data["settings"].is_object()){const auto& prefs=data["settings"];
            c.helperEnabled=prefs.value("overlay_helper",c.helperEnabled);c.startWithWindows=prefs.value("overlay_start_with_windows",c.startWithWindows);
            if(prefs.contains("panel_key")){c.shortcut=Key(prefs.value("panel_key",VK_DELETE));const int mods=prefs.value("panel_modifiers",0);c.shortcutModifiers=(mods&1?Rml::Input::KM_ALT:0)|(mods&2?Rml::Input::KM_CTRL:0)|(mods&4?Rml::Input::KM_SHIFT:0);c.shortcutLabel=prefs.value("panel_hotkey",std::string("Del"));if(auto* keycap=c.Element("toast-message")->QuerySelector(".keycap"))keycap->SetInnerRML(Rml::StringUtilities::EncodeRml(c.shortcutLabel));}
            c.showStats=prefs.value("overlay_live_stats",c.showStats);c.showWelcome=prefs.value("overlay_welcome",c.showWelcome);c.welcomePosition=prefs.value("overlay_welcome_position",c.welcomePosition);c.primaryMenu=prefs.value("overlay_renderer",c.primaryMenu);c.optiShortcut=prefs.value("optiscaler_hotkey",c.optiShortcut);if(!c.showWelcome)c.Visible("welcome",false);
            for(const auto& [key,name]:std::map<std::string,std::string>{{"opti-menu","optiscaler_ui"},{"opti-intro","optiscaler_intro"},{"reshade-menu","reshade_ui"},{"reshade-intro","reshade_intro"}})c.menuSettings[key]=prefs.value(name,c.menuSettings[key]);c.SyncSettings();
        }
        if(data.contains("presets")&&data["presets"].is_array()&&data["presets"].size()<=12){
            std::map<std::string,std::string> selected;for(const auto* id:{"presets","compare-left","compare-right"})selected[id]=dynamic_cast<Rml::ElementFormControl*>(c.Element(id))->GetValue();
            if(data.value("op",std::string())=="preset-save"&&!data.value("error",false))selected["presets"]=data.value("preset_name",selected["presets"]);
            c.presets.clear();std::string options;for(const auto& preset:data["presets"]){if(!preset.is_object()||!preset.value("compatible",false))continue;const auto name=preset.value("name",std::string());if(name.empty()||name.size()>60||!preset.contains("values")||!preset["values"].is_object())continue;
                auto values=c.values;for(const auto& [key,value]:preset["values"].items())if(value.is_number()&&values.contains(key))values[key]=value.get<float>();c.presets[name]=values;const auto safe=Rml::StringUtilities::EncodeRml(name);options+="<option value=\""+safe+"\">"+safe+"</option>";
            }
            if(options.empty())options="<option value=\"\">No saved presets</option>";c.typographySync=true;for(const auto* id:{"presets","compare-left","compare-right"}){c.Element(id)->SetInnerRML(options);if(c.presets.contains(selected[id]))dynamic_cast<Rml::ElementFormControl*>(c.Element(id))->SetValue(selected[id]);}c.typographySync=false;
            if(!c.presets.empty()){c.compareLeft=dynamic_cast<Rml::ElementFormControl*>(c.Element("compare-left"))->GetValue();c.compareRight=dynamic_cast<Rml::ElementFormControl*>(c.Element("compare-right"))->GetValue();}c.Disabled("presets",c.presets.empty());c.Disabled("delete-preset",c.presets.empty()||data.value("pending",false));
        }
        if(data.contains("review")&&data["review"].is_object()){
            const auto& review=data["review"];c.reviewId=review.value("review_id",0);c.Visible("review-panel",c.reviewId>0);c.Disabled("apply-review",!review.value("ready",false)||data.value("pending",false));std::string markup;
            for(const auto& [key,label]:std::map<std::string,std::string>{{"items","READY"},{"blocked","NEEDS ATTENTION"},{"skipped","UNCHANGED"}})if(review.contains(key)&&review[key].is_array()&&!review[key].empty()){markup+="<h3>"+label+"</h3>";for(const auto& item:review[key])if(item.is_object())markup+="<p>"+Rml::StringUtilities::EncodeRml(item.value("title",std::string()))+"</p><p class=\"hint\">"+Rml::StringUtilities::EncodeRml(item.value("detail",std::string()))+"</p>";}c.Element("review-items")->SetInnerRML(markup);
        }
        for(const auto* id:{"menus-review","global-review"})c.Disabled(id,!helperReady||data.value("pending",false));
        const auto message=data.value("message",std::string());if(!message.empty()){c.Message(message);if(data.value("op",std::string())=="preset-save"&&!data.value("error",false)){c.edits.saved=c.values;c.Notify("Preset saved");}}
    }

    ~Runtime(){if(controls&&controls->prefsDirty)controls->SavePreferences();if(document&&controls)for(const auto* event:{"click","change","keydown","mouseover","mouseout","mousedown","mousemove","mouseup"})document->RemoveEventListener(event,controls.get());if(initialized)Rml::Shutdown();controls.reset();}
    void Init(const ForgeGlass::Frame& frame,const D3D11_TEXTURE2D_DESC& desc) {
        device=frame.device;device->GetImmediateContext(&immediate);width=int(desc.Width);height=int(desc.Height);format=desc.Format;outputSpace=frame.colorSpace;
        ComPtr<ID3D11On12Device> interop;dx12Interop=SUCCEEDED(device.As(&interop));
        BOOL animate=TRUE;systemReducedMotion=SystemParametersInfoW(SPI_GETCLIENTAREAANIMATION,0,&animate,0)&&!animate;
        renderer=std::make_unique<Renderer>(device.Get());renderer->SetViewport(width,height);Rml::SetSystemInterface(&system);Rml::SetFileInterface(&files);Rml::SetRenderInterface(renderer.get());ForgeGlass::Require(Rml::Initialise(),"RmlUi initialization failed");initialized=true;
        Rml::Factory::RegisterElementInstancer("paint-root",&roots);
        ForgeGlass::Require(Rml::LoadFontFace("fonts/RobotoVariable.ttf"),"Roboto failed to load");ForgeGlass::Require(Rml::LoadFontFace("fonts/BakbakOne-Regular.ttf"),"Heading font failed to load");ForgeGlass::Require(Rml::LoadFontFace("fonts/InterVariable.ttf"),"Inter failed to load");
        context=Rml::CreateContext("game-overlay",{width,height});ForgeGlass::Require(context!=nullptr,"RmlUi context failed");document=context->LoadDocument("overlay.rml");ForgeGlass::Require(document!=nullptr,"Overlay document failed");
        controls=std::make_unique<ForgeGlass::Controller>();auto& c=*controls;c.document=document;c.preview=false;c.UseTheme(3);c.LoadPreferences(true);if(c.copyFont=="aptos")c.copyFont="roboto";
        c.InstallExtraControls();c.Typography();c.Materials();c.Sync();c.SyncSettings();c.Metadata();c.Session({});c.edits.Start(c.values);
        for(const auto* event:{"click","change","keydown","mouseover","mouseout","mousedown","mousemove","mouseup"})document->AddEventListener(event,&c);
        c.Element("font-select")->SetInnerRML("<option value=\"roboto\">Roboto</option><option value=\"inter\">Inter</option>");document->QuerySelector(".prototype-toolbar")->SetProperty("display","none");c.Visible("type-panel",false);c.Visible("inspector",false);c.Visible("welcome",false);c.Visible("main-panel",frame.visible);document->Show();hostVisible=frame.visible;c.Layout(c.layout);lastValues=c.values;
        const unsigned char pixel[4]={};const float uv[4]={0,0,1,1};DXGI_FORMAT compatible=format;if(format==DXGI_FORMAT_R8G8B8A8_TYPELESS)compatible=DXGI_FORMAT_R8G8B8A8_UNORM;if(format==DXGI_FORMAT_B8G8R8A8_TYPELESS)compatible=DXGI_FORMAT_B8G8R8A8_UNORM;
        backdrop=std::make_unique<Backdrop>(device.Get(),width,height,pixel,1,1,uv,compatible,frame.colorSpace);
        D3D11_TEXTURE2D_DESC layer{};layer.Width=width;layer.Height=height;layer.MipLevels=layer.ArraySize=1;layer.Format=DXGI_FORMAT_R8G8B8A8_UNORM;layer.SampleDesc.Count=1;layer.BindFlags=D3D11_BIND_RENDER_TARGET|D3D11_BIND_SHADER_RESOURCE;Check(device->CreateTexture2D(&layer,nullptr,&windowLayer));Check(device->CreateRenderTargetView(windowLayer.Get(),nullptr,&windowView));Check(device->CreateShaderResourceView(windowLayer.Get(),nullptr,&windowSource));
        if(frame.welcome){c.Welcome();c.toastUntil=system.GetElapsedTime()+7;}
    }
    bool Draw(const ForgeGlass::Host& host,ForgeGlass::Frame& frame,ID3D11Texture2D* target) {
        auto& c=*controls;const double now=system.GetElapsedTime();
        c.requestJson=[&](const std::string& text){return host.request&&host.request(host.user,text.c_str());};
        c.deletePreset=[&](const std::string& name){const auto request=nlohmann::json{{"op","preset-delete"},{"changes",{{"name",name}}}}.dump();return host.request&&host.request(host.user,request.c_str());};
        c.savePreset=[&](const std::string& name){nlohmann::json values=nlohmann::json::object();for(const auto& key:supportedKeys)if(c.values.contains(key))values[key]=std::floor(c.values.at(key))==c.values.at(key)?nlohmann::json(int(c.values.at(key))):nlohmann::json(c.values.at(key));const auto request=nlohmann::json{{"op","preset-save"},{"changes",{{"name",name},{"values",values}}}}.dump();return host.request&&host.request(host.user,request.c_str());};
        ForgeGlass::Snapshot snapshot{};snapshot.nrGpuMs=snapshot.gameFps=snapshot.displayedFps=snapshot.measuredRatio=-1;
        if(host.read&&host.read(host.user,&snapshot)){
            ForgeSession::Snapshot live;live.nrKnown=snapshot.nrKnown;live.nrRunning=snapshot.nrRunning;live.nrWarming=snapshot.nrWarming;live.fgKnown=snapshot.fgKnown;live.fgRunning=snapshot.fgRunning;live.framesKnown=snapshot.framesKnown;live.nrGpuMs=snapshot.nrGpuMs;live.gameFps=snapshot.gameFps;live.displayedFps=snapshot.displayedFps;live.measuredRatio=snapshot.measuredRatio;if(now>=nextTelemetry){c.Session(live);nextTelemetry=now+.2;}
            ForgeWorkbench::Values current;for(uint32_t i=0;i<std::min(snapshot.count,128u);i++)if(snapshot.values&&snapshot.values[i].key&&std::isfinite(snapshot.values[i].value))current[snapshot.values[i].key]=snapshot.values[i].value;
            const auto beforeValues=c.values;for(const auto& [key,value]:current)if(c.values.contains(key))c.values[key]=value;
            for(const auto& [key,value]:c.values)if(!current.contains(key))c.defaults[key]=value;
            for(uint32_t i=0;i<std::min(snapshot.defaultCount,128u);i++)if(snapshot.defaults&&snapshot.defaults[i].key&&current.contains(snapshot.defaults[i].key)&&std::isfinite(snapshot.defaults[i].value))c.defaults[snapshot.defaults[i].key]=snapshot.defaults[i].value;
            supportedKeys.clear();for(const auto& [key,value]:current)supportedKeys.insert(key);
            c.values["mfg_enabled"]=current.contains("multiplier")&&current["multiplier"]!=0;
            if(receivedSnapshot&&current.contains("enabled")&&beforeValues.at("enabled")!=current.at("enabled"))c.Notify(current.at("enabled")?"Neural rendering enabled":"Neural rendering disabled");receivedSnapshot=true;
            if(c.values!=beforeValues)c.Sync();c.Visible("frame-section",snapshot.fgAvailable);c.Visible("neural-section",snapshot.nrAvailable);
            if(snapshot.title)document->QuerySelector("h1")->SetInnerRML(Rml::StringUtilities::EncodeRml(snapshot.title));
            if(snapshot.accent){const std::string color=snapshot.accent;if(color.size()==7&&color[0]=='#'&&color.find_first_not_of("0123456789abcdefABCDEF",1)==std::string::npos){const auto rgb=std::stoul(color.substr(1),nullptr,16);c.accent={float((rgb>>16)&255)/255,float((rgb>>8)&255)/255,float(rgb&255)/255};}}
            for(const auto* id:{"compact-api","overview-api","popup-api"})c.Element(id)->SetInnerRML(dx12Interop?"DirectX 12":"DirectX 11");for(const auto* id:{"compact-output","overview-output","popup-output"})c.Element(id)->SetInnerRML(outputSpace==1?"HDR · scRGB":outputSpace==2?"HDR10":"SDR");c.Element("open-session")->QuerySelector(".session-name")->SetInnerRML("Live session");c.Element("open-session")->QuerySelector(".status-note")->SetInnerRML("Live");
            for(int ratio=2;ratio<=6;ratio++)c.Disabled(("ratio-"+std::to_string(ratio)).c_str(),current.contains("__multiplier_max")&&ratio>current.at("__multiplier_max"));c.Disabled("mode-dynamic",current.contains("__dynamic_supported")&&current.at("__dynamic_supported")==0);
            for(const auto& [id,control]:c.extraFields)c.Disabled(id.c_str(),!current.contains(control->key));
            for(const auto& [id,key]:std::map<std::string,std::string>{{"strength","intensity"},{"pass-count","passes"},{"model-preset","preset"},{"detail","detail"},{"colour","colour"},{"tone","tone"}})c.Disabled(id.c_str(),!current.contains(key));
            for(const auto* key:{"strength","tone","structure","skin"})c.Disabled((std::string("pass-")+key).c_str(),!current.contains("pass"+std::to_string(c.pass)+"_"+key)||c.values["pass"+std::to_string(c.pass)+"_inherit"]!=0);
            c.Disabled("open-passes",!current.contains("pass2_strength"));if(!messageInitialized){c.Message(snapshot.liveTuning?"Live tuning":"Model changes apply after restarting the game.");messageInitialized=true;}
            Helper(snapshot.helperJson);
            for(const auto* id:{"overview-metadata","popup-metadata"}){auto* metadata=c.Element(id);metadata->QuerySelector(".preview-badge")->SetProperty("display","none");metadata->QuerySelector(".session-heading")->GetChild(1)->SetInnerRML("Live session");}
            c.Element("status-sr")->SetProperty("display","none");c.Element("status-rr")->SetProperty("display","none");
            c.Element("status-nr")->SetClass("active",snapshot.nrKnown&&snapshot.nrRunning);c.Element("status-nr")->SetClass("unavailable",!snapshot.nrAvailable);c.Element("status-fg")->SetClass("active",snapshot.fgKnown&&snapshot.fgRunning);c.Element("status-fg")->SetClass("waiting",snapshot.fgAvailable&&!snapshot.fgKnown);
            history.Add(now,snapshot.nrRunning?snapshot.nrGpuMs:-1,snapshot.gameFps,snapshot.framesKnown?snapshot.displayedFps:-1);
            if(now-historyPaint>=.5){historyPaint=now;double ceiling=1;for(const auto& sample:history.samples)ceiling=std::max(ceiling,sample.nr);std::string graph;for(size_t i=1;i<history.samples.size();i++){const auto& a=history.samples[i-1];const auto& b=history.samples[i];if(a.nr<0||b.nr<0||b.time-a.time>1)continue;const float x1=float((a.time-now+30)/30*100),x2=float((b.time-now+30)/30*100),y1=float(128-112*a.nr/ceiling),y2=float(128-112*b.nr/ceiling);const float dx=(x2-x1)*5,dy=y2-y1;graph+="<div style=\"position: absolute; left: "+std::to_string(x1)+"%; top: "+std::to_string(y1)+"dp; width: "+std::to_string(std::sqrt(dx*dx+dy*dy))+"dp; height: 2dp; background-color: var(--accent); transform-origin: 0% 50%; transform: rotate("+std::to_string(std::atan2(dy,dx)*180/3.14159265)+"deg);\"/>";}
                for(const auto* id:{"overview-metadata","popup-metadata"}){auto* chart=c.Element(id)->QuerySelector(".history-empty");chart->SetInnerRML(graph.empty()?"<p>No NR timing samples available.</p>":graph);}
            }
            lastValues=c.values;
        }
        if(hostVisible!=frame.visible){hostVisible=frame.visible;c.Visible("main-panel",hostVisible);if(hostVisible)c.Enter("main-panel");else{c.Visible("inspector",false);c.Visible("type-panel",false);}}
        const auto beforeSettings=SettingsValues();const int oldShortcut=c.shortcut,oldModifiers=c.shortcutModifiers;
        const bool focused=GetForegroundWindow()==frame.window;const int modifiers=focused?((frame.keys[VK_CONTROL]?Rml::Input::KM_CTRL:0)|(frame.keys[VK_SHIFT]?Rml::Input::KM_SHIFT:0)|(frame.keys[VK_MENU]?Rml::Input::KM_ALT:0)):0;
        context->ProcessMouseMove(focused?int(frame.mouseX):-1,focused?int(frame.mouseY):-1,modifiers);
        for(int i=0;i<3;i++){const bool down=focused&&frame.mouse[i];if(down!=mouse[i]){if(down)context->ProcessMouseButtonDown(i,modifiers);else context->ProcessMouseButtonUp(i,modifiers);mouse[i]=down;}}
        if(focused&&frame.wheel)context->ProcessMouseWheel(-frame.wheel,modifiers);
        for(int vk=0;vk<256;vk++){const bool down=focused&&frame.keys[vk];if(down!=keys[vk]){const auto key=Key(vk);if(key!=Rml::Input::KI_UNKNOWN){if(down){const auto shortcut=c.shortcut;if(!c.bindingShortcut)c.shortcut=Rml::Input::KI_UNKNOWN;context->ProcessKeyDown(key,modifiers);if(!c.bindingShortcut&&c.shortcut==Rml::Input::KI_UNKNOWN)c.shortcut=shortcut;}else context->ProcessKeyUp(key,modifiers);}if(down&&vk>=VK_SPACE&&!(modifiers&(Rml::Input::KM_CTRL|Rml::Input::KM_ALT))){BYTE state[256]{};GetKeyboardState(state);WCHAR text[8]{};const auto layout=GetKeyboardLayout(0);const int count=ToUnicodeEx(vk,MapVirtualKeyExW(vk,MAPVK_VK_TO_VSC,layout),state,text,8,4,layout);for(int i=0;i<count;i++)if(text[i]>=32)context->ProcessTextInput(Rml::Character(text[i]));}keys[vk]=down;}}
        const auto afterSettings=SettingsValues();for(const auto& [key,value]:afterSettings.items())if(beforeSettings.at(key)!=value)pendingSettings[key]=value;
        if(oldShortcut!=c.shortcut||oldModifiers!=c.shortcutModifiers){const auto key=c.shortcut;const int vk=key==Rml::Input::KI_DELETE?VK_DELETE:key>=Rml::Input::KI_A&&key<=Rml::Input::KI_Z?'A'+key-Rml::Input::KI_A:key>=Rml::Input::KI_F1&&key<=Rml::Input::KI_F12?VK_F1+key-Rml::Input::KI_F1:0;if(vk)pendingSettings["panel_binding"]={{"key",vk},{"modifiers",(c.shortcutModifiers&Rml::Input::KM_ALT?1:0)|(c.shortcutModifiers&Rml::Input::KM_CTRL?2:0)|(c.shortcutModifiers&Rml::Input::KM_SHIFT?4:0)}};}
        if(helperReady&&host.request&&!pendingSettings.empty()){auto it=pendingSettings.begin();const auto request=nlohmann::json{{"op","set-setting"},{"key",it->first},{"value",it->second}}.dump();if(host.request(host.user,request.c_str()))pendingSettings.erase(it);}
        ForgeWorkbench::Values changed;for(const auto& [key,value]:c.values)if(lastValues.contains(key)&&lastValues.at(key)!=value&&key!="mfg_enabled")changed[key]=value;
        if(c.values["mfg_enabled"]!=lastValues["mfg_enabled"]){changed["multiplier"]=c.values["mfg_enabled"]?2:0;changed["dynamic_mfg"]=0;}
        if(!changed.empty()){std::vector<ForgeGlass::Value> updates;for(const auto& [key,value]:changed)updates.push_back({key.c_str(),value});if(!host.apply||!host.apply(host.user,updates.data(),uint32_t(updates.size()))){c.values=lastValues;c.Message("This change is unavailable in the current rendering route.");}c.Sync();}
        c.reducedMotion=systemReducedMotion||!c.motionEnabled;document->SetClass("reduce-motion",c.reducedMotion);c.Animate(now);c.Adapt(backdrop->measured,now);context->Update();c.AdaptiveForeground(*backdrop,now);context->Update();
        // Display changes resolve during Update. Reading the previous computed
        // visibility would immediately close a panel reopened by the host.
        frame.visible=c.Element("main-panel")->IsVisible();hostVisible=frame.visible;
        if(c.toastUntil>0&&now>c.toastUntil){c.Visible("welcome",false);c.toastUntil=0;}
        if(c.prefsDirty&&now>=nextPreferences){c.SavePreferences();nextPreferences=now+.5;}c.savePreset={};c.deletePreset={};c.requestJson={};
            std::vector<Backdrop::Panel> panels;
            for(const auto* id : {"main-panel","inspector","welcome","type-panel"}) {
                auto* e=document->GetElementById(id);
                if(e->IsVisible()) {
                    const auto at=e->GetAbsoluteOffset(Rml::BoxArea::Border);const auto size=e->GetBox().GetSize(Rml::BoxArea::Border);
                    Backdrop::Panel panel{at.x,at.y,size.x,size.y,24*context->GetDensityIndependentPixelRatio()};panel.sampleIndex=std::string(id)=="main-panel"?0:std::string(id)=="inspector"?1:std::string(id)=="welcome"?2:3;panel.scale=context->GetDensityIndependentPixelRatio();if(std::string(id)=="inspector" && c.inspectorAnchored){panel.arrow=1;panel.anchorX=std::clamp(c.inspectorAnchorX,at.x+24,at.x+size.x-24);}
                    const auto variable=[e](const char* name,float fallback){const auto* p=e->GetProperty(name);if(!p)return fallback;try{return std::stof(p->Get<Rml::String>());}catch(...){return fallback;}};
                    panel.blur=c.blurRadius;panel.radius=std::clamp(variable("--corner-radius",24.f),0.f,100.f)*panel.scale;panel.saturation=std::clamp(variable("--material-saturation",1.12f),0.f,2.f);panel.grain=std::clamp(variable("--material-texture",.028f),0.f,.08f);panel.luminosity=std::clamp(variable("--material-luminosity",.04f),0.f,.25f);
                    panel.shadowOpacity=std::clamp(variable("--shadow-opacity",.30f),0.f,.5f);panel.shadowRadius=std::clamp(variable("--shadow-radius",28.f),8.f,60.f);panel.shadowOffset=std::clamp(variable("--shadow-offset",12.f),0.f,24.f);
                    panel.opacity=std::clamp(variable("--window-opacity",1.f),0.f,1.f);panel.tone=std::clamp(variable("--surface-tone",.96f),0.f,1.f);panel.grounding=std::clamp(variable("--surface-grounding",.52f),0.f,1.f);panel.blendAmount=std::clamp(variable("--material-blend-opacity",.3f),0.f,1.f);
                    if(const auto* blend=e->GetProperty("--material-blend")) {const auto name=blend->Get<Rml::String>();panel.blendMode=float(MaterialColor::Mode(name));}
                    if(const auto* blend=e->GetProperty("--shadow-blend")) {const auto name=blend->Get<Rml::String>();panel.shadowBlend=name=="overlay"?1.f:name=="soft-light"?2.f:0.f;}
                    panels.push_back(panel);
                }
            }
            // Compose each window and its UI as a unit. A front window must
            // frost the already composited lower windows, not leave their text on top.
            backdrop->Draw(target,frame.target,{},false,false);
            backdrop->Sample(panels,now);
            std::map<std::string,Backdrop::Panel> byId;size_t panelIndex=0;
            for(const auto* id:{"main-panel","inspector","welcome","type-panel"})if(c.Element(id)->IsVisible())byId[id]=panels.at(panelIndex++);
            const auto renderUi=[&](Rml::Element* root,ID3D11RenderTargetView* destination=nullptr) {if(!destination)destination=frame.target;immediate->OMSetRenderTargets(1,&destination,nullptr);D3D11_VIEWPORT viewport{0,0,float(width),float(height),0,1};immediate->RSSetViewports(1,&viewport);renderer->BeginFrame();auto& manager=context->GetRenderManager();manager.PrepareRender({width,height});static_cast<Root*>(root)->Paint();manager.ResetState();renderer->EndFrame(destination);};
            for(const auto& id:c.stacking)if(byId.contains(id)) {
                const float clearLayer[4]={};immediate->ClearRenderTargetView(windowView.Get(),clearLayer);backdrop->Draw(target,windowView.Get(),{byId.at(id)},true,false);
                renderUi(c.Element(id.c_str()),windowView.Get());const auto velocity=c.windowVelocity[id];backdrop->ComposeLayer(frame.target,windowSource.Get(),velocity.x,velocity.y,c.reducedMotion);
            }

            if(c.Element("tooltip")->IsVisible()){
                if(outputSpace){backdrop->Draw(target,frame.target,{},false,false);const float clear[4]={};immediate->ClearRenderTargetView(windowView.Get(),clear);renderUi(c.Element("tooltip"),windowView.Get());backdrop->ComposeLayer(frame.target,windowSource.Get(),0,0,true);}
                else renderUi(c.Element("tooltip"));
            }
        return true;
    }
};
std::unique_ptr<Runtime> runtime;std::mutex mutex;bool logged=false;
}
extern "C" __declspec(dllexport) bool __cdecl ForgeGlassDraw(const ForgeGlass::Host* host,ForgeGlass::Frame* frame) {
    if(!host||!frame||host->size!=sizeof(*host)||host->abi!=ForgeGlass::Abi||frame->size!=sizeof(*frame)||frame->abi!=ForgeGlass::Abi||!frame->device||!frame->target||frame->colorSpace>2)return false;
    std::unique_lock guard(mutex,std::try_to_lock);if(!guard.owns_lock())return true;
    const HRESULT apartment=CoInitializeEx(nullptr,COINIT_MULTITHREADED);const bool uninitialize=SUCCEEDED(apartment);
    bool drawn=false;
    try {
        StateScope isolated(frame->device);ComPtr<ID3D11Resource> resource;frame->target->GetResource(&resource);ComPtr<ID3D11Texture2D> target;Check(resource.As(&target));D3D11_TEXTURE2D_DESC desc{};target->GetDesc(&desc);
        if(desc.SampleDesc.Count!=1||desc.Width<640||desc.Height<480||desc.Width>7680||desc.Height>4320)throw std::runtime_error("Unsupported glass viewport");
        const bool sdr=desc.Format==DXGI_FORMAT_R8G8B8A8_UNORM||desc.Format==DXGI_FORMAT_R8G8B8A8_UNORM_SRGB||desc.Format==DXGI_FORMAT_R8G8B8A8_TYPELESS||desc.Format==DXGI_FORMAT_B8G8R8A8_UNORM||desc.Format==DXGI_FORMAT_B8G8R8A8_UNORM_SRGB||desc.Format==DXGI_FORMAT_B8G8R8A8_TYPELESS;
        const bool supported=frame->colorSpace==0?sdr:frame->colorSpace==1?desc.Format==DXGI_FORMAT_R16G16B16A16_FLOAT:desc.Format==DXGI_FORMAT_R10G10B10A2_UNORM;
        if(!supported)throw std::runtime_error("Unsupported glass format and transfer-function pair");
        if(runtime&&(runtime->device.Get()!=frame->device||runtime->width!=int(desc.Width)||runtime->height!=int(desc.Height)||runtime->format!=desc.Format||runtime->outputSpace!=frame->colorSpace))runtime.reset();
        if(!runtime){if(host->log)host->log(host->user,"Initializing glass overlay");runtime=std::make_unique<Runtime>();runtime->Init(*frame,desc);if(host->log)host->log(host->user,runtime->dx12Interop?"Glass overlay ready: DirectX 12":"Glass overlay ready: DirectX 11");}drawn=runtime->Draw(*host,*frame,target.Get());
    }catch(const std::exception& error){runtime.reset();if(!logged&&host->log){host->log(host->user,error.what());logged=true;}}
    if(uninitialize)CoUninitialize();return drawn;
}
void ReleaseGlassBridge12();
extern "C" __declspec(dllexport) void __cdecl ForgeGlassRelease(){std::lock_guard guard(mutex);runtime.reset();ReleaseGlassBridge12();logged=false;}
