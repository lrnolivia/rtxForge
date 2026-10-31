#pragma once
#include <json.hpp>
#include <atomic>
#include <cstring>
#include <cmath>

namespace ForgePanelChannel
{
constexpr LONG Magic = 0x50465852;
constexpr size_t Capacity = 32768;
struct Header
{
    LONG magic, version, pid, request, response, visible, requestLength, responseLength, revision, ownsShortcut;
    char reserved[24];
    char requestData[Capacity], responseData[Capacity];
};
static_assert(offsetof(Header,requestData) == 64);
static_assert(offsetof(Header,responseData) == 64+Capacity);
static_assert(sizeof(Header) == 64+Capacity*2);
inline Header* channel = nullptr;
inline HANDLE mapping = nullptr, file = nullptr;
inline LONG lastRevision = 0;
inline bool pending = false, helperReady = false, needsHello = true;
    inline nlohmann::json settings = nlohmann::json::object(), status = nlohmann::json::object(), review = nlohmann::json::object(), hdr = nlohmann::json::object();
inline nlohmann::json namedPresets = nlohmann::json::array();
inline bool namedSupported = false, responseError = false;
inline std::string lastOperation, savedPresetName;
inline std::string message;
inline ULONGLONG requestedAt = 0;

inline bool OnWine()
{
    const auto ntdll = GetModuleHandleW(L"ntdll.dll");
    return ntdll && GetProcAddress(ntdll,"wine_get_version");
}
// A native Linux host cannot open a Wine named section, so under Wine the same
// header lives in %LOCALAPPDATA%\rtxForge\panel.<pid>.map (C:\users\steamuser\...
// in the prefix), which the host maps too. Exclusive creation never adopts a stale
// or planted file; delete-on-close removes it when the game exits.
inline HANDLE CreateWineMapping()
{
    wchar_t base[MAX_PATH];
    const auto length = GetEnvironmentVariableW(L"LOCALAPPDATA",base,MAX_PATH);
    if(length == 0 || length >= MAX_PATH) return nullptr;
    const auto folder = std::wstring(base,length) + L"\\rtxForge";
    if(!CreateDirectoryW(folder.c_str(),nullptr) && GetLastError() != ERROR_ALREADY_EXISTS) return nullptr;
    const auto path = folder + L"\\panel." + std::to_wstring(GetCurrentProcessId()) + L".map";
    file = CreateFileW(path.c_str(),GENERIC_READ|GENERIC_WRITE,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,nullptr,
                       CREATE_NEW,FILE_ATTRIBUTE_TEMPORARY|FILE_FLAG_DELETE_ON_CLOSE,nullptr);
    if(file == INVALID_HANDLE_VALUE) { file = nullptr; return nullptr; }
    const auto section = CreateFileMappingW(file,nullptr,PAGE_READWRITE,0,sizeof(Header),nullptr);
    if(!section) { CloseHandle(file); file = nullptr; }
    return section;
}
inline void Init()
{
    // Device/ImGui resets must not replace a mapping the helper still holds.
    if(channel) { InterlockedExchange(&channel->visible,0); needsHello = true; return; }
    if(OnWine()) mapping = CreateWineMapping();
    else
    {
        const auto name = L"Local\\rtxForge.panel." + std::to_wstring(GetCurrentProcessId());
        mapping = CreateFileMappingW(INVALID_HANDLE_VALUE,nullptr,PAGE_READWRITE,0,sizeof(Header),name.c_str());
        if(mapping && GetLastError() == ERROR_ALREADY_EXISTS) { CloseHandle(mapping); mapping = nullptr; }
    }
    if(mapping) channel = static_cast<Header*>(MapViewOfFile(mapping,FILE_MAP_ALL_ACCESS,0,0,sizeof(Header)));
    if(!channel)
    {
        if(mapping) CloseHandle(mapping);
        if(file) CloseHandle(file);
        mapping = nullptr; file = nullptr; return;
    }
    *channel = {}; channel->version = 1; channel->pid = GetCurrentProcessId(); channel->ownsShortcut = 1;
    MemoryBarrier(); InterlockedExchange(&channel->magic,Magic);
}
inline void Visible(bool visible)
{
    if(!channel || channel->visible == int(visible)) return;
    InterlockedExchange(&channel->visible,visible ? 1 : 0);
    if(visible) needsHello = true;
}
inline bool Send(nlohmann::json request)
{
    if(!channel || pending) return false;
    const auto body = request.dump();
    if(body.empty() || body.size() > Capacity) { message = "This request is too large. Use rtxForge."; return false; }
    const LONG next = channel->request < 0x7fffff00 ? channel->request+2 : 2;
    InterlockedExchange(&channel->request,next|1);
    std::memcpy(channel->requestData,body.data(),body.size()); channel->requestLength = LONG(body.size());
    MemoryBarrier(); InterlockedExchange(&channel->request,next);
    pending = true; requestedAt = GetTickCount64();
    const auto op = request.value("op",std::string());
    if(op != "hello" && op != "status" && op != "discard-review") message = op == "save" ? "Saving preset..." : op == "apply-review" ? "Applying changes..." : "Working...";
    return true;
}
inline void Validate(const nlohmann::json& response)
{
    const auto check=[](bool valid) { if(!valid) throw std::runtime_error("Invalid panel response"); };
    check(response.is_object());
    for(const auto* name : {"op","message"}) if(response.contains(name)) check(response[name].is_string());
    for(const auto* name : {"busy","ready","error"}) if(response.contains(name)) check(response[name].is_boolean());
    if(response.contains("named_supported")) check(response["named_supported"].is_boolean());
    if(response.contains("preset_name")) check(response["preset_name"].is_string());
    if(response.contains("named_presets")) {
        check(response["named_presets"].is_array() && response["named_presets"].size() <= 12);
        for(const auto& entry : response["named_presets"]) {
            check(entry.is_object() && entry.contains("name") && entry["name"].is_string()
                && entry["name"].get<std::string>().size() <= 60 && entry.contains("compatible")
                && entry["compatible"].is_boolean() && entry.contains("values")
                && entry["values"].is_object() && entry["values"].size() <= 64);
            for(const auto& value : entry["values"]) check(value.is_number() && std::isfinite(value.get<double>()));
        }
    }
    if(response.contains("hdr")) {
        const auto& data=response["hdr"];check(data.is_object());
        for(const auto* name:{"available","installed","pending"})if(data.contains(name))check(data[name].is_boolean());
        if(data.contains("message"))check(data["message"].is_string()&&data["message"].get<std::string>().size()<=1000);
        if(data.contains("controls"))check(data["controls"].is_array()&&data["controls"].size()<=64);
        if(data.contains("values"))check(data["values"].is_object()&&data["values"].size()<=64);
    }
    if(response.contains("review_id")) check(response["review_id"].is_number_integer() && response["review_id"].get<int>()>0);
    if(response.contains("settings"))
    {
        const auto& prefs=response["settings"]; check(prefs.is_object());
        for(const auto* name : {"overlay_controls","overlay_renderer","panel_hotkey","optiscaler_hotkey"}) if(prefs.contains(name)) check(prefs[name].is_string());
        for(const auto* name : {"panel_key","panel_modifiers"}) if(prefs.contains(name)) check(prefs[name].is_number_integer());
        for(const auto* name : {"overlay_helper","overlay_start_with_windows","optiscaler_ui","optiscaler_intro","reshade_ui","reshade_intro"}) if(prefs.contains(name)) check(prefs[name].is_boolean());
    }
    if(response.contains("status"))
    {
        check(response["status"].is_object());
        if(response["status"].contains("pipelines"))
        {
            const auto& pipes=response["status"]["pipelines"]; check(pipes.is_object());
            for(const auto* name : {"SR","RR","NR","FG"}) if(pipes.contains(name))
            { check(pipes[name].is_object()); for(const auto* field : {"state","detail"}) if(pipes[name].contains(field)) check(pipes[name][field].is_string()); }
        }
    }
    for(const auto* name : {"items","blocked","skipped"}) if(response.contains(name))
    {
        check(response[name].is_array() && response[name].size()<=1000);
        for(const auto& entry : response[name])
        { check(entry.is_object()); for(const auto* field : {"title","detail"}) if(entry.contains(field)) check(entry[field].is_string()); }
    }
}
inline void Poll()
{
    if(!channel) return;
    const auto revision = InterlockedCompareExchange(&channel->revision,0,0);
    if(revision == 0 || (revision&1) || revision == lastRevision || channel->response != channel->request)
    { if(pending && GetTickCount64()-requestedAt > 10000) message = "Waiting for the background helper. Start it from rtxForge if needed."; return; }
    const auto length = channel->responseLength;
    if(length <= 0 || length > Capacity) return;
    std::string body(channel->responseData,size_t(length)); MemoryBarrier();
    if(revision != InterlockedCompareExchange(&channel->revision,0,0)) return;
    try
    {
        auto response = nlohmann::json::parse(body,[](int depth,nlohmann::json::parse_event_t,nlohmann::json&) { if(depth>16) throw std::runtime_error("Panel response is too deeply nested"); return true; });
        Validate(response);
        pending = response.value("busy",false); helperReady = true;
        if(response.contains("message")) message = response.value("message",std::string());
        else if(message.rfind("Waiting for the background helper",0) == 0) message.clear();
        if(response.contains("settings")) settings = response["settings"];
        if(response.contains("status")) status = response["status"];
        if(response.contains("hdr") && response["hdr"].is_object()) hdr = response["hdr"];
        const auto op = response.value("op",std::string());
        lastOperation = op; responseError = response.value("error",false);
        if(response.contains("named_supported")) namedSupported = response["named_supported"].get<bool>();
        else if(op == "hello") namedSupported = false;
        if(response.contains("named_presets")) namedPresets = response["named_presets"];
        if(response.contains("preset_name")) savedPresetName = response["preset_name"].get<std::string>();
        if(response.contains("review_id")) review = response;
        if(op == "apply-review" || op == "discard-review") review = nlohmann::json::object();
        lastRevision = revision;
    }
    catch(...) { pending = false; helperReady = false; lastRevision = revision; message = "The helper response was invalid. Close and reopen the panel."; }
}
inline void DiscardReview()
{ review = nlohmann::json::object(); if(!pending) Send({{"op","discard-review"}}); }
inline void Shutdown()
{
    // MenuCommon calls this during graphics-context resets, not only process exit.
    Visible(false); needsHello = true;
}
struct Lifetime
{
    ~Lifetime()
    {
        if(channel) { InterlockedExchange(&channel->visible,0); InterlockedExchange(&channel->magic,0); UnmapViewOfFile(channel); }
        if(mapping) CloseHandle(mapping);
        if(file) CloseHandle(file);
        channel = nullptr; mapping = nullptr; file = nullptr;
    }
};
inline Lifetime lifetime;
}
