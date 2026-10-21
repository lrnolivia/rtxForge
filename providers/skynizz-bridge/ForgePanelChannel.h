#pragma once
#include <Windows.h>
#include <json.hpp>
#include <atomic>
#include <cstring>

// Windows keeps its named pagefile mapping. Wine exposes the same protocol
// through a private prefix file, shared with the native Linux helper.
#include <string>
#include <vector>
#include <mutex>
namespace ForgeWineMapping
{
struct Files {
    std::vector<HANDLE> handles;
    std::mutex mutex;
    ~Files() { for(auto file : handles) CloseHandle(file); }
};
inline Files files;
inline HANDLE Create(const wchar_t* kind, DWORD size, const wchar_t* name)
{
    auto ntdll=GetModuleHandleW(L"ntdll.dll");
    if(!ntdll || !GetProcAddress(ntdll,"wine_get_version"))
        return CreateFileMappingW(INVALID_HANDLE_VALUE,nullptr,PAGE_READWRITE,0,size,name);
    wchar_t local[32768];
    auto length=GetEnvironmentVariableW(L"LOCALAPPDATA",local,32768);
    if(!length || length>=32768) return nullptr;
    const std::wstring folder=std::wstring(local)+L"\\rtxForge";
    if(!CreateDirectoryW(folder.c_str(),nullptr) && GetLastError()!=ERROR_ALREADY_EXISTS) return nullptr;
    const auto path=folder+L"\\"+kind+L"."+std::to_wstring(GetCurrentProcessId())+L".map";
    // Do not truncate a stale or concurrently held file. Clean shutdown removes
    // our file; a crash leaves cleanup to the operator if the Wine PID recurs.
    auto file=CreateFileW(path.c_str(),GENERIC_READ|GENERIC_WRITE,
                          FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,nullptr,CREATE_NEW,
                          FILE_ATTRIBUTE_TEMPORARY|FILE_FLAG_DELETE_ON_CLOSE,nullptr);
    if(file==INVALID_HANDLE_VALUE) return nullptr;
    auto result=CreateFileMappingW(file,nullptr,PAGE_READWRITE,0,size,nullptr);
    if(!result) { CloseHandle(file); return nullptr; }
    { std::lock_guard<std::mutex> lock(files.mutex); files.handles.push_back(file); }
    SetLastError(ERROR_SUCCESS);
    return result;
}
}

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
inline HANDLE mapping = nullptr;
inline LONG lastRevision = 0;
inline bool pending = false, helperReady = false, needsHello = true;
inline nlohmann::json settings = nlohmann::json::object(), status = nlohmann::json::object(), review = nlohmann::json::object();
inline std::string message;
inline ULONGLONG requestedAt = 0;

inline void Init()
{
    // Device/ImGui resets must not replace a mapping the helper still holds.
    if(channel) { InterlockedExchange(&channel->visible,0); needsHello = true; return; }
    const auto name = L"Local\\rtxForge.panel." + std::to_wstring(GetCurrentProcessId());
    mapping = ForgeWineMapping::Create(L"panel",sizeof(Header),name.c_str());
    if(mapping && GetLastError() != ERROR_ALREADY_EXISTS)
        channel = static_cast<Header*>(MapViewOfFile(mapping,FILE_MAP_ALL_ACCESS,0,0,sizeof(Header)));
    if(!channel) { if(mapping) CloseHandle(mapping); mapping = nullptr; return; }
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
        const auto op = response.value("op",std::string());
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
        channel = nullptr; mapping = nullptr;
    }
};
inline Lifetime lifetime;
}
