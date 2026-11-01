#pragma once
#include "GlassLoader.h"
// Include after ForgePanel.h. Reuse its validated runtime bindings and mailbox;
// the glass renderer owns presentation, never a second copy of game tuning.
namespace ForgeGlassPanel {
inline ForgeGlass::Loader loader;
inline HWND window{};
inline void (*logSink)(const char*)=nullptr;
inline bool (*readModelDimensions)(unsigned&,unsigned&)=nullptr;
inline int runtimeKind=0;
inline bool Read(void*,ForgeGlass::Snapshot* out) {
    static ForgeWorkbench::Values values;static std::vector<ForgeGlass::Value> fields;
    auto& cfg=*Config::Instance();values=ForgePanel::Values(cfg);fields.clear();for(const auto& [key,value]:values)fields.push_back({key.c_str(),value});if(ForgePanel::mfgAllowed){fields.push_back({"__multiplier_max",float(State::Instance().dlssgMfgMax.value_or(0)+1)});fields.push_back({"__dynamic_supported",State::Instance().dlssgGameDMFGSupported?1.f:0.f});}
    ForgePanel::LiveStats stats;if(ForgePanel::readLiveStats)stats=ForgePanel::readLiveStats();
    fields.push_back({"__runtime_kind",float(runtimeKind)});
    unsigned width=0,height=0;if(stats.nrRunning&&readModelDimensions&&readModelDimensions(width,height)&&width>0&&height>0&&width<=32768&&height<=32768){fields.push_back({"__nr_width",float(width)});fields.push_back({"__nr_height",float(height)});}
    auto prefs=ForgePanelChannel::settings;if(!prefs.contains("panel_key")){prefs["panel_key"]=ForgePanel::ShortcutKey();prefs["panel_modifiers"]=ForgePanel::modifiers;prefs["panel_hotkey"]=ForgePanel::ShortcutLabel();}
    static std::string title,accent;title=prefs.value("game_title",ForgePanel::title);char cachedAccent[8]{};std::snprintf(cachedAccent,sizeof(cachedAccent),"#%02X%02X%02X",unsigned(std::clamp(ForgePanel::accent.x,0.f,1.f)*255+.5f),unsigned(std::clamp(ForgePanel::accent.y,0.f,1.f)*255+.5f),unsigned(std::clamp(ForgePanel::accent.z,0.f,1.f)*255+.5f));accent=prefs.value("game_accent",std::string(cachedAccent));
    static LONG lastRevision=-1;static bool lastPending=false;static std::string lastMessage,helper;if(lastRevision!=ForgePanelChannel::lastRevision||lastPending!=ForgePanelChannel::pending||lastMessage!=ForgePanelChannel::message){lastRevision=ForgePanelChannel::lastRevision;lastPending=ForgePanelChannel::pending;lastMessage=ForgePanelChannel::message;helper=nlohmann::json{{"revision",ForgePanelChannel::lastRevision},{"ready",ForgePanelChannel::helperReady},{"pending",ForgePanelChannel::pending},{"error",ForgePanelChannel::responseError},{"message",ForgePanelChannel::message},{"op",ForgePanelChannel::lastOperation},{"preset_name",ForgePanelChannel::savedPresetName},{"settings",prefs},{"hdr",ForgePanelChannel::hdr},{"review",ForgePanelChannel::review},{"presets",ForgePanelChannel::namedPresets},{"named_supported",ForgePanelChannel::namedSupported}}.dump();}
    *out={title.c_str(),accent.c_str(),fields.data(),uint32_t(fields.size()),stats.nrKnown,stats.nrRunning,stats.nrWarming,stats.fgKnown,stats.fgRunning,stats.framesKnown,stats.nrGpuMs,stats.gameFps,stats.displayedFps,stats.measuredRatio,ForgePanel::nrAllowed,ForgePanel::mfgAllowed,ForgePanel::liveTuning,helper.c_str()};
    static std::vector<ForgeGlass::Value> defaults;defaults.clear();for(const auto& field:ForgePanel::controls)if(ForgePanel::Available(field))defaults.push_back({field.key,field.defaultValue});if(ForgePanel::mfgAllowed)defaults.push_back({"dynamic_mfg",0});out->defaults=defaults.data();out->defaultCount=uint32_t(defaults.size());return true;
}
inline bool Apply(void*,const ForgeGlass::Value* fields,uint32_t count) {
    if(!fields||count>128)return false;ForgeWorkbench::Values values;
    for(uint32_t i=0;i<count;i++){if(!fields[i].key||!std::isfinite(fields[i].value))return false;values[fields[i].key]=fields[i].value;}
    return ForgePanel::ApplyValues(*Config::Instance(),values);
}
inline bool Request(void*,const char* text) {if(!text)return false;const auto message=nlohmann::json::parse(text,nullptr,false);return message.is_object()&&ForgePanelChannel::Send(message);}
inline void Log(void*,const char* text) {if(logSink)logSink(text);else {LOG_WARN("rtxForge glass: {}",text);}OutputDebugStringA((std::string("rtxForge glass: ")+text+"\n").c_str());}
inline bool Prepare(HWND hwnd) {window=hwnd;const auto path=Util::DllPath().wstring();return ForgePanel::enabled&&loader.Load(path.c_str());}
inline uint32_t OutputSpace(){const auto& state=State::Instance();if(!state.hdrOutputActive)return 0;const auto& color=state.outputColorSpace;if(!color.valid||color.model!=ColorModel::RGB||color.range!=ColorRange::Full)return 255;if(color.transfer==ColorTransfer::Linear&&color.primaries==ColorPrimaries::Rec709)return 1;if(color.transfer==ColorTransfer::PQ&&color.primaries==ColorPrimaries::Rec2020)return 2;return 255;}
inline bool Draw(ID3D11Device* device,ID3D11RenderTargetView* target,bool& visible) {
    if(!loader.Ready()||!ForgePanel::selected)return false;
    ForgePanel::PollHelper();ForgePanel::Flush(*Config::Instance());
    const auto& io=ImGui::GetIO();
    ForgeGlass::Frame frame{};frame.size=sizeof(frame);frame.abi=ForgeGlass::Abi;frame.device=device;frame.target=target;frame.window=window;
    frame.mouseX=io.MousePos.x;frame.mouseY=io.MousePos.y;frame.wheel=io.MouseWheel;for(int i=0;i<3;i++)frame.mouse[i]=io.MouseDown[i];for(int vk=0;vk<256;vk++)frame.keys[vk]=OptiInput::IsKeyDown(vk);
    frame.visible=visible;frame.welcome=ForgePanel::WelcomePending();frame.colorSpace=OutputSpace();
    const ForgeGlass::Host host{sizeof(ForgeGlass::Host),ForgeGlass::Abi,nullptr,Read,Apply,Request,Log};
    const bool rendered=loader.Render(host,frame);if(rendered)visible=frame.visible;ForgePanelChannel::Visible(visible);return rendered;
}
inline bool Draw12(ID3D12Device* device,ID3D12CommandQueue* queue,ID3D12Resource* target,bool& visible) {
    if(!loader.Ready()||!ForgePanel::selected)return false;
    ForgePanel::PollHelper();ForgePanel::Flush(*Config::Instance());const auto& io=ImGui::GetIO();
    ForgeGlass::Frame12 frame{};frame.size=sizeof(frame);frame.abi=ForgeGlass::Abi;frame.device=device;frame.queue=queue;frame.target=target;frame.before=frame.after=D3D12_RESOURCE_STATE_PRESENT;
    frame.input.size=sizeof(frame.input);frame.input.abi=ForgeGlass::Abi;frame.input.window=window;frame.input.mouseX=io.MousePos.x;frame.input.mouseY=io.MousePos.y;frame.input.wheel=io.MouseWheel;
    for(int i=0;i<3;i++)frame.input.mouse[i]=io.MouseDown[i];for(int vk=0;vk<256;vk++)frame.input.keys[vk]=OptiInput::IsKeyDown(vk);
    frame.input.visible=visible;frame.input.welcome=ForgePanel::WelcomePending();frame.input.colorSpace=OutputSpace();
    const ForgeGlass::Host host{sizeof(ForgeGlass::Host),ForgeGlass::Abi,nullptr,Read,Apply,Request,Log};
    const bool rendered=loader.Render(host,frame);if(rendered)visible=frame.input.visible;ForgePanelChannel::Visible(visible);return rendered;
}
inline void Shutdown(){loader.Shutdown();}
}
