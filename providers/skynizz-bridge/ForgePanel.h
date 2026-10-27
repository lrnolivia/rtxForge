#pragma once
#include <Config.h>
#include <Logger.h>
#include <Util.h>
#include <imgui/imgui.h>
#include <imgui/imgui_internal.h>
#include <json.hpp>
#include <fstream>
#include <array>
#include <type_traits>
#include <cmath>
#include <chrono>
#include <cstring>
#include <unordered_map>
#include <cstdio>
#include "ForgePanelChannel.h"
#include "ForgePanelIcon.h"

// Runs inside the already-installed menu hook. No HWND, secondary swapchain,
// screen copy, blur pass, process polling, network or per-frame disk access.
namespace ForgePanel
{
enum class Kind { toggle, choice, slider, number };
struct Choice { float value; const char* label; };
struct Control
{
    const char *key, *label, *advanced, *group;
    Kind kind; float low, high;
    float (*get)(Config&); void (*set)(Config&, float, bool);
    const Choice* choices; size_t count;
};
#include "ForgePanelBindings.h"
#include "ForgePanelFont.h"
inline ImFont* font = nullptr; inline ImFont* bold = nullptr; inline ImFont* brandFont = nullptr;
inline bool selected = false, settings = false, global = false, advanced = false, nrAllowed = false, mfgAllowed = false, enabled = false, binding = false, initialized = false;
inline int key = VK_DELETE, modifiers = 0, bindingRelease = 0;
inline float animation = 0, cpuMs = 0;
inline ImVec4 accent(.82f, .82f, .82f, 1);
inline std::string title = "Game";
// HKEY_CURRENT_USER is a process-wide cached handle another module can
// redirect; RegOpenCurrentUser opens the caller's own hive. Init only.
inline LSTATUS ReadUser(const wchar_t* path, const wchar_t* name, DWORD type, void* data, DWORD bytes)
{
    DWORD size = bytes;
    const auto cached = RegGetValueW(HKEY_CURRENT_USER, path, name, type, nullptr, data, &size);
    if(cached == ERROR_SUCCESS) return cached;
    HKEY parent = nullptr; const auto root = RegOpenKeyExW(HKEY_CURRENT_USER, L"Software\\rtxForge", 0, KEY_READ, &parent);
    if(root == ERROR_SUCCESS) RegCloseKey(parent);
    HANDLE token = nullptr; const bool impersonating = OpenThreadToken(GetCurrentThread(), TOKEN_QUERY, TRUE, &token) != FALSE;
    if(impersonating) CloseHandle(token);
    HKEY user = nullptr; auto direct = RegOpenCurrentUser(KEY_READ, &user);
    if(direct == ERROR_SUCCESS) { size = bytes; direct = RegGetValueW(user, path, name, type, nullptr, data, &size); RegCloseKey(user); }
    LOG_WARN("rtxForge preference {}: cached HKCU {}, Software\\rtxForge open {}, impersonating {}, current-user hive {}",
             wstring_to_string(name), cached, root, impersonating, direct);
    // Once per launch, record what this process can actually see.
    static bool listed = false;
    if(!listed && root == ERROR_SUCCESS)
    {
        listed = true; std::string seen;
        if(RegOpenKeyExW(HKEY_CURRENT_USER, L"Software\\rtxForge", 0, KEY_READ, &parent) == ERROR_SUCCESS)
        {
            wchar_t item[256]; DWORD length = 256;
            for(DWORD i = 0; i < 32 && RegEnumKeyExW(parent, i, item, &length, nullptr, nullptr, nullptr, nullptr) == ERROR_SUCCESS; ++i, length = 256)
                seen += " key:" + wstring_to_string(item);
            RegCloseKey(parent);
        }
        HKEY overlay = nullptr; const auto open = RegOpenKeyExW(HKEY_CURRENT_USER, L"Software\\rtxForge\\Overlay", 0, KEY_READ, &overlay);
        if(open == ERROR_SUCCESS)
        {
            wchar_t item[256]; DWORD length = 256, kind = 0;
            for(DWORD i = 0; i < 32 && RegEnumValueW(overlay, i, item, &length, nullptr, &kind, nullptr, nullptr) == ERROR_SUCCESS; ++i, length = 256)
                seen += " value:" + wstring_to_string(item) + "/" + std::to_string(kind);
            RegCloseKey(overlay);
        }
        LOG_WARN("rtxForge registry view: Overlay open {}{}", open, seen);
    }
    return direct;
}
inline DWORD Preference(const wchar_t* name, DWORD fallback)
{
    DWORD value = fallback;
    const auto result = ReadUser(L"Software\\rtxForge\\Overlay", name, RRF_RT_REG_DWORD, &value, sizeof(value));
    if(result != ERROR_SUCCESS) LOG_WARN("rtxForge panel preference read failed: {}, using default {}", result, fallback);
    return result == ERROR_SUCCESS ? value : fallback;
}
// Use the same stb_truetype grayscale rasterizer and dynamic font textures as
// Universal MFG. Keep the real panel's Inter faces and weights.
inline const ImFontLoader* PanelFontLoader() { return ImFontAtlasGetFontLoaderForStbTruetype(); }
inline float dpiScale = 1.f;
inline bool showLiveStats = true;
inline bool lightTheme = false;
inline ImVec4 Tone(float dark, float light, float alpha = 1)
{ const float value = lightTheme ? light : dark; return ImVec4(value,value,value,alpha); }
inline bool showWelcome = true, welcomeDismissed = false;
inline DWORD welcomePosition = 0;
inline const std::array<const char*,5> welcomePositions = {"top-center","top-left","top-right","bottom-left","bottom-right"};
inline ULONGLONG welcomeStarted = 0;
inline bool nativeMfgMenuSupported = false;
struct LiveStats {
    bool nrKnown{}, nrRunning{}, nrFramesKnown{}, fgKnown{}, fgRunning{}, framesKnown{}, nrWarming{};
    unsigned long long nrFrames{};
    double nrGpuMs{-1}, gameFps{-1}, displayedFps{-1}, measuredRatio{-1};
};
inline LiveStats (*readLiveStats)() = nullptr;
inline bool (*controlSupported)(const Control&) = nullptr;
// Render at output pixel density. Never enlarge a low-resolution font atlas.
// This follows MFG's DPI/output/client relationship without double scaling.
inline float PanelScale() {
    const auto& io = ImGui::GetIO();
    const auto fb = io.DisplayFramebufferScale;
    const float sx = std::clamp(fb.x, .125f, 8.f), sy = std::clamp(fb.y, .125f, 8.f);
    const float resolution = std::min(io.DisplaySize.x*sx/1920.f, io.DisplaySize.y*sy/1080.f);
    return std::clamp(std::max(dpiScale, resolution), 1.f, 4.f)/sy;
}
inline void LoadGameIdentity()
{
    const auto& prefs = ForgePanelChannel::settings;
    if(prefs.contains("game_title") && prefs["game_title"].is_string()
        && prefs.contains("game_accent") && prefs["game_accent"].is_string()) {
        const auto color = prefs["game_accent"].get<std::string>();
        if(color.size()==7 && color[0]=='#' && color.substr(1).find_first_not_of("0123456789abcdefABCDEF")==std::string::npos) {
            const auto rgb = std::stoul(color.substr(1),nullptr,16);
            accent = ImVec4(float((rgb>>16)&255)/255,float((rgb>>8)&255)/255,float(rgb&255)/255,1);
            title = prefs["game_title"].get<std::string>();
            return;
        }
    }
    // The helper refreshes this cache outside the game. Read only at startup
    // and after a helper reply, never on each rendered frame.
    wchar_t exe[32768] {}, identity[1024] {}; GetModuleFileNameW(nullptr, exe, 32768);
    if (ReadUser(L"Software\\rtxForge\\Overlay\\Games", exe, RRF_RT_REG_SZ, identity, sizeof(identity)) != ERROR_SUCCESS) return;
    const auto text = wstring_to_string(identity);
    if(text.size() <= 8 || text[0] != '#' || text[7] != '|') return;
    if(text.substr(1,6).find_first_not_of("0123456789abcdefABCDEF") != std::string::npos) return;
    const auto rgb = std::stoul(text.substr(1,6), nullptr, 16);
    accent = ImVec4(float((rgb >> 16) & 255)/255, float((rgb >> 8) & 255)/255, float(rgb & 255)/255, 1);
    title = text.substr(8);
}
inline void PollHelper()
{
    const auto previous=ForgePanelChannel::lastRevision;
    ForgePanelChannel::Poll();
    if(ForgePanelChannel::helperReady && ForgePanelChannel::lastRevision!=previous) LoadGameIdentity();
    const auto& prefs=ForgePanelChannel::settings;
    if(prefs.contains("overlay_controls")) advanced=prefs.value("overlay_controls",std::string())=="classic";
    const auto theme=prefs.value("overlay_theme",std::string());
    if(theme=="light" || theme=="dark") lightTheme=theme=="light";
    else if(prefs.contains("overlay_light")) lightTheme=prefs.value("overlay_light",false);
    if(prefs.contains("panel_key")) key=prefs.value("panel_key",int(VK_DELETE));
    if(prefs.contains("panel_modifiers")) modifiers=prefs.value("panel_modifiers",0);
}
inline void Init(HWND window)
{
    if(!initialized)
    {
        enabled = Preference(L"InGamePanel",0) != 0; initialized = true;
        LOG_INFO("rtxForge panel startup: enabled {}", enabled);
    }
    if(!enabled) return;
    ForgePanelChannel::Init();
    LOG_INFO("rtxForge panel channel: ready {}", ForgePanelChannel::channel != nullptr);
    ImFontConfig options; options.FontDataOwnedByAtlas = false;
    options.FontLoader = PanelFontLoader();
    dpiScale = std::clamp(float(GetDpiForWindow(window))/96.f, .75f, 3.f);
    font = ImGui::GetIO().Fonts->AddFontFromMemoryTTF(forgeInter, sizeof(forgeInter), 18.f, &options);
    bold = ImGui::GetIO().Fonts->AddFontFromMemoryTTF(forgeInterSemiBold, sizeof(forgeInterSemiBold), 18.f, &options);
    brandFont = ImGui::GetIO().Fonts->AddFontFromMemoryTTF(forgeBakbak, sizeof(forgeBakbak), 24.f, &options);
    LOG_INFO("rtxForge panel fonts: {}", font != nullptr && bold != nullptr);
    key = int(Preference(L"PanelKey", VK_DELETE)); modifiers = int(Preference(L"PanelModifiers", 0));
    advanced = Preference(L"Advanced", 0) != 0;
    lightTheme = Preference(L"LightTheme", 0) != 0;
    showLiveStats = Preference(L"ShowLiveStats", 1) != 0;
    showWelcome = Preference(L"ShowWelcome", 1) != 0;
    welcomePosition = Preference(L"WelcomePosition", 0);
    // Init runs on the render thread. GetWindowTextW sends WM_GETTEXT to the
    // window's own thread and waits; games whose window thread waits on the
    // render thread (Starfield) then deadlock. Read the caption directly.
    wchar_t caption[256] {}; InternalGetWindowText(window, caption, 256);
    title = wstring_to_string(caption);
    LOG_INFO("rtxForge panel caption read");
    try
    {
        // MainDllPath is the configurable DLSS search directory (often the
        // OptiScaler subfolder), not the installed bridge's directory.
        const auto folder = Util::DllPath().parent_path();
        const auto path = folder / ".rtxforge-install.json";
        if (std::filesystem::file_size(path) < 2 * 1024 * 1024)
        {
            std::ifstream input(path); const auto metadata = nlohmann::json::parse(input);
            const auto mode = metadata.value("feature_mode", std::string());
            nrAllowed = mode == "nr-mfg" || mode == "nr-only";
            mfgAllowed = mode == "nr-mfg" || mode == "mfg-only";
            if(metadata.contains("mfg_provider") && metadata["mfg_provider"].is_object()
                && metadata["mfg_provider"].value("ownership",std::string()) == "managed-addon") mfgAllowed = false;
            if (metadata.contains("name")) title = metadata.value("name", title);
        }
    }
    catch (...) { nrAllowed = mfgAllowed = false; }
    LOG_INFO("rtxForge panel features: NR {}, MFG {}", nrAllowed, mfgAllowed);
    // Identity is cached by the helper/manager before launch. Never load artwork
    // or walk a library from the game's render thread.
    LoadGameIdentity();
    // The game can see an older HKCU view than its launcher. Fetch saved
    // welcome/shortcut preferences without requiring the panel to be opened.
    if(ForgePanelChannel::Send({{"op","hello"}})) ForgePanelChannel::needsHello=false;
}
inline bool CapturingShortcut()
{
    if(binding) return true;
    if(bindingRelease == 0) return false;
    if(OptiInput::IsKeyReleased(bindingRelease) || !OptiInput::IsKeyDown(bindingRelease)) bindingRelease = 0;
    return true;
}
// The key the panel opens on, or 0. OptiScaler keeps it from the game.
inline int ShortcutKey()
{
    return enabled && key > 0 && key < 256 && key != VK_INSERT && key != VK_END && key != VK_F12 ? key : 0;
}
inline bool ShortcutReleased()
{
    if (ShortcutKey() == 0 || !OptiInput::IsFocused()) return false;
    const int held = (OptiInput::IsKeyDown(VK_MENU) ? 1 : 0) | (OptiInput::IsKeyDown(VK_CONTROL) ? 2 : 0) | (OptiInput::IsKeyDown(VK_SHIFT) ? 4 : 0);
    // Pause keyboards can omit key-up. Use its existing input press event;
    // all other keys retain release behavior. No native shortcut is consumed.
    return (key == VK_PAUSE ? OptiInput::IsKeyPressed(key) : OptiInput::IsKeyReleased(key)) && held == modifiers;
}
// HDR games give OptiScaler a PQ (HDR10) or scRGB swapchain and it draws
// ImGui straight into it. Panel colours are sRGB, so encode them for the
// output at a 203-nit UI white; otherwise white text lands near 5,000 nits
// and dark greys near black. Mirrors OptiScaler's own target detection.
inline ImVec4 Output(ImVec4 c)
{
    const auto& output = State::Instance().outputColorSpace;
    if(!output.valid || output.model != ColorModel::RGB) return c;
    const auto linear = [](float x) { x = std::clamp(x, 0.f, 1.f); return x <= .04045f ? x/12.92f : std::pow((x+.055f)/1.055f, 2.4f); };
    const float r = linear(c.x), g = linear(c.y), b = linear(c.z);
    if(output.transfer == ColorTransfer::Linear && output.primaries == ColorPrimaries::Rec709)
    {
        const float scale = State::Instance().hdrOutputActive ? 203.f/80.f : 1.f;
        return ImVec4(r*scale, g*scale, b*scale, c.w);
    }
    if(output.transfer == ColorTransfer::PQ && output.primaries == ColorPrimaries::Rec2020)
    {
        const auto pq = [](float value)
        {
            const float y = std::pow(std::clamp(value*203.f/10000.f, 0.f, 1.f), 2610.f/16384.f);
            return std::pow((3424.f/4096.f + 2413.f/128.f*y)/(1.f + 2392.f/128.f*y), 2523.f/32.f);
        };
        return ImVec4(pq(.6274040f*r + .3292820f*g + .0433136f*b), pq(.0690970f*r + .9195400f*g + .0113612f*b),
                      pq(.0163916f*r + .0880132f*g + .8955950f*b), c.w);
    }
    return c;
}
inline void PushColor(ImGuiCol slot, ImVec4 colour) { ImGui::PushStyleColor(slot, Output(colour)); }
inline ImU32 Colour(ImVec4 colour) { return ImGui::GetColorU32(Output(colour)); }
inline ImU32 Colour(ImU32 colour) { return ImGui::GetColorU32(Output(ImGui::ColorConvertU32ToFloat4(colour))); }
inline ImU32 Colour(ImGuiCol slot) { return ImGui::GetColorU32(slot); }
inline bool Animating() { return selected && animation > 0; }
inline ImVec4 Mix(ImVec4 a, ImVec4 b, float amount)
{ return ImVec4(a.x*amount+b.x*(1-amount), a.y*amount+b.y*(1-amount), a.z*amount+b.z*(1-amount), 1); }
inline float Luminance(ImVec4 color)
{
    const auto linear=[](float n) { return n<=.04045f ? n/12.92f : std::pow((n+.055f)/1.055f,2.4f); };
    return .2126f*linear(color.x)+.7152f*linear(color.y)+.0722f*linear(color.z);
}
inline ImVec4 OnColor(ImVec4 background)
{
    const float lum=Luminance(background);
    return (1.05f/(lum+.05f)) >= ((lum+.05f)/.05f) ? ImVec4(1,1,1,1) : ImVec4(0,0,0,1);
}
inline ImVec4 TitleColor()
{
    const auto neutral=Tone(.91f,.12f), surface=Tone(.045f,.96f);
    for(float amount=.85f;amount>=0;amount-=.05f)
    { const auto color=Mix(accent,neutral,amount); const auto a=Luminance(color), b=Luminance(surface);
        if((std::max(a,b)+.05f)/(std::min(a,b)+.05f)>=4.5f) return color; }
    return neutral;
}
inline bool Available(const Control& field)
{
    if(controlSupported && !controlSupported(field)) return false;
    if (std::strcmp(field.key,"multiplier") == 0) return mfgAllowed;
    return std::strcmp(field.group,"Upscaling") == 0 || std::strcmp(field.group,"Sharpening") == 0 || std::strcmp(field.group,"Motion sharpening") == 0 || nrAllowed;
}
inline bool IconButton(const char* id, int kind, float scale)
{
    const auto position = ImGui::GetCursorScreenPos();
    const bool pressed = ImGui::InvisibleButton(id,ImVec2(30.f*scale,30.f*scale));
    auto* draw = ImGui::GetWindowDrawList();
    const auto center = ImVec2(position.x+15.f*scale,position.y+15.f*scale);
    const auto ink = Colour(Tone(.77f,.26f));
    if(ImGui::IsItemHovered()) draw->AddRectFilled(position,ImVec2(position.x+30*scale,position.y+30*scale),Colour(Tone(1,0,.09f)),8*scale);
    if(kind == 1)
    {
        draw->AddCircle(center,6*scale,ink,24,1.5f*scale); draw->AddCircle(center,2*scale,ink,16,1.5f*scale);
        for(int i=0;i<8;++i) { const float angle=i*3.14159265f/4;
            draw->AddLine(ImVec2(center.x+std::cos(angle)*6*scale,center.y+std::sin(angle)*6*scale),
                ImVec2(center.x+std::cos(angle)*9*scale,center.y+std::sin(angle)*9*scale),ink,1.5f*scale); }
    }
    else if(kind == 2)
    {
        const float r=7*scale;
        draw->AddCircle(center,r,ink,24,1.5f*scale);
        draw->AddLine(ImVec2(center.x-r,center.y),ImVec2(center.x+r,center.y),ink,1.5f*scale);
        draw->AddBezierCubic(ImVec2(center.x,center.y-r),ImVec2(center.x-r*.7f,center.y-r),ImVec2(center.x-r*.7f,center.y+r),ImVec2(center.x,center.y+r),ink,1.5f*scale,16);
        draw->AddBezierCubic(ImVec2(center.x,center.y-r),ImVec2(center.x+r*.7f,center.y-r),ImVec2(center.x+r*.7f,center.y+r),ImVec2(center.x,center.y+r),ink,1.5f*scale,16);
    }
    else
    {
        draw->AddLine(ImVec2(center.x-5*scale,center.y-5*scale),ImVec2(center.x+5*scale,center.y+5*scale),ink,1.5f*scale);
        draw->AddLine(ImVec2(center.x+5*scale,center.y-5*scale),ImVec2(center.x-5*scale,center.y+5*scale),ink,1.5f*scale);
    }
    return pressed;
}
// NR tuning is baked into the model, so every commit rebuilds it, and
// creation frames are where upstream saw GPU hangs. Sliders commit on
// release; commits are spaced and applied together as one rebuild.
inline std::unordered_map<std::string, float> dragging;
inline std::unordered_map<const Control*, float> queued;
inline std::chrono::steady_clock::time_point lastCommit {};
inline void Flush(Config& cfg, bool force = false)
{
    const auto now = std::chrono::steady_clock::now();
    if(queued.empty() || (!force && now - lastCommit < std::chrono::milliseconds(400))) return;
    for(const auto& [field, value] : queued) field->set(cfg, std::clamp(value, field->low, field->high), false);
    queued.clear(); lastCommit = now;
}
inline void Commit(const Control& field, Config& cfg, float value)
{
    if(!std::isfinite(value)) return;
    queued[&field] = value; Flush(cfg);
}
// The rtxForge sidebar's slider: a thin track with a subtle fill and a small
// vertical thumb, its value right-aligned on the label line. Drawn over an
// invisible ImGui slider, so mouse, keyboard and gamepad input are unchanged.
inline void SliderBegin(const char* text)
{
    const auto label = ImGui::GetItemRectMin();
    const float right = ImGui::GetCursorScreenPos().x + ImGui::GetContentRegionAvail().x;
    ImGui::GetWindowDrawList()->AddText(ImVec2(right - ImGui::CalcTextSize(text).x, label.y), Colour(Tone(.90f,.15f)), text);
    ImGui::SetNextItemWidth(-1);
    for(const auto slot : {ImGuiCol_FrameBg, ImGuiCol_FrameBgHovered, ImGuiCol_FrameBgActive, ImGuiCol_SliderGrab, ImGuiCol_SliderGrabActive})
        PushColor(slot, ImVec4(0,0,0,0));
}
inline void SliderEnd(float fraction, float scale)
{
    ImGui::PopStyleColor(5);
    const auto min = ImGui::GetItemRectMin(), max = ImGui::GetItemRectMax();
    const bool hot = ImGui::IsItemHovered() || ImGui::IsItemActive();
    auto* draw = ImGui::GetWindowDrawList();
    const float thumb = 3.f*scale, half = (hot ? 10.f : 9.f)*scale, line = 1.f*scale, y = (min.y+max.y)*.5f;
    const float left = min.x+thumb, right = max.x-thumb, at = left+std::clamp(fraction,0.f,1.f)*(right-left);
    const auto control = lightTheme ? TitleColor() : Mix(accent, ImVec4(.93f,.93f,.93f,1), .45f);
    draw->AddRectFilled(ImVec2(min.x,y-line), ImVec2(max.x,y+line), Colour(Tone(1,0,hot ? .31f : .22f)), line);
    draw->AddRectFilled(ImVec2(min.x,y-line), ImVec2(at,y+line), Colour(control), line);
    draw->AddRectFilled(ImVec2(at-thumb,y-half), ImVec2(at+thumb,y+half), Colour(hot ? Mix(control, ImVec4(1,1,1,1), .7f) : control), thumb);
}
// The rtxForge mark, generated from gui/icons/rtxforge-mark.svg.
inline void Brand(float scale)
{
    const float height = 18.f*scale, unit = height/forgeIconHeight;
    const auto origin = ImGui::GetCursorScreenPos(); auto* draw = ImGui::GetWindowDrawList();
    ImVec2 points[256];
    for(const auto& shape : forgeIconShapes)
    {
        const int count = std::min(shape.count, 256);
        for(int i=0;i<count;++i) points[i] = ImVec2(origin.x+forgeIconPoints[2*(shape.start+i)]*unit, origin.y+forgeIconPoints[2*(shape.start+i)+1]*unit);
        draw->AddConcavePolyFilled(points, count, Colour(shape.hole ? IM_COL32(12,12,12,255) : shape.colour));
    }
    ImGui::Dummy(ImVec2(unit*forgeIconWidth, height)); ImGui::SameLine(0, 8.f*scale);
}
// The sidebar's dropdown: flat fill, hairline border and a small chevron.
// The frame is measured first because an open combo makes its popup current.
inline bool Dropdown(const char* preview)
{
    const float scale = ImGui::GetFontSize()/14.f;
    const auto position = ImGui::GetCursorScreenPos();
    const auto size = ImVec2(ImGui::CalcItemWidth(), ImGui::GetFrameHeight());
    auto* draw = ImGui::GetWindowDrawList();
    ImGui::PushStyleVar(ImGuiStyleVar_FrameBorderSize, 1.f*scale);
    ImGui::PushStyleVar(ImGuiStyleVar_FrameRounding, 8.f*scale);
    PushColor(ImGuiCol_Border, Tone(1,0,.16f));
    PushColor(ImGuiCol_FrameBg, Tone(.20f,.88f));
    PushColor(ImGuiCol_FrameBgHovered, Tone(.25f,.82f));
    ImGui::PushStyleVar(ImGuiStyleVar_WindowPadding, ImVec2(6.f*scale, 6.f*scale));
    const bool open = ImGui::BeginCombo("##value", preview, ImGuiComboFlags_NoArrowButton);
    ImGui::PopStyleVar();
    ImGui::PopStyleColor(3); ImGui::PopStyleVar(2);
    const float x = position.x+size.x-16.f*scale, y = position.y+size.y*.5f, arm = 4.f*scale;
    const auto ink = Colour(Tone(.77f,.26f));
    draw->AddLine(ImVec2(x-arm,y-arm*.5f), ImVec2(x,y+arm*.5f), ink, 1.5f*scale);
    draw->AddLine(ImVec2(x,y+arm*.5f), ImVec2(x+arm,y-arm*.5f), ink, 1.5f*scale);
    if(open)
    {
        ImGui::PushStyleVar(ImGuiStyleVar_ItemSpacing, ImVec2(ImGui::GetStyle().ItemSpacing.x, 2.f*scale));
        ImGui::PushStyleVar(ImGuiStyleVar_SelectableTextAlign, ImVec2(0, .5f));
    }
    return open;
}
inline bool DropdownItem(const char* label, bool selected)
{ return ImGui::Selectable(label, selected, 0, ImVec2(0, 32.f*ImGui::GetFontSize()/14.f)); }
inline void DropdownEnd() { ImGui::PopStyleVar(2); ImGui::EndCombo(); }
// Smaller labels and emphasis retain Inter SemiBold.
inline void BoldWrapped(const char* text, ImVec4 colour, float scale)
{
    const float wrap = ImGui::GetContentRegionAvail().x;
    const auto size = ImGui::CalcTextSize(text, nullptr, false, wrap);
    const auto position = ImGui::GetCursorScreenPos(); auto* draw = ImGui::GetWindowDrawList();
    const auto col = Colour(colour);
    ImGui::PushFont(bold ? bold : font, ImGui::GetFontSize());
    const auto weighted = ImGui::CalcTextSize(text, nullptr, false, wrap);
    draw->AddText(nullptr, 0.f, position, col, text, nullptr, wrap);
    ImGui::PopFont();
    ImGui::Dummy(ImVec2(std::max(size.x, weighted.x), std::max(size.y, weighted.y)));
}
// Main feature and Settings headings share the official brand typeface.
inline void Hero(const char* text, float size, ImVec4 color)
{
    ImGui::PushFont(brandFont ? brandFont : bold,size);
    PushColor(ImGuiCol_Text,color);
    ImGui::PushTextWrapPos(0); ImGui::TextUnformatted(text); ImGui::PopTextWrapPos();
    ImGui::PopStyleColor(); ImGui::PopFont();
}
inline void Section(const char* text)
{
    const float size = ImGui::GetFontSize()*18.f/14.f;
    ImGui::Spacing(); Hero(text, size, ImVec4(.90f,.90f,.90f,1));
}
// The sidebar's ToggleSwitch: a pill track filled with the accent when on.
inline bool Switch(const char* id, bool* on)
{
    const float scale = ImGui::GetFontSize()/14.f, width = 40.f*scale, height = 20.f*scale;
    const auto position = ImGui::GetCursorScreenPos();
    const bool pressed = ImGui::InvisibleButton(id, ImVec2(width, height));
    if(pressed) *on = !*on;
    const bool hot = ImGui::IsItemHovered();
    const auto control = lightTheme ? TitleColor() : Mix(accent, ImVec4(.93f,.93f,.93f,1), .45f);
    const auto track = *on ? (hot ? Mix(control, Tone(1,0), .8f) : control) : Tone(1,0, hot ? .26f : .18f);
    auto* draw = ImGui::GetWindowDrawList();
    draw->AddRectFilled(position, ImVec2(position.x+width, position.y+height), Colour(track), height*.5f);
    const float x = *on ? position.x+width-height*.5f : position.x+height*.5f;
    draw->AddCircleFilled(ImVec2(x, position.y+height*.5f), height*.5f-4.f*scale, Colour(*on ? OnColor(control) : ImVec4(.86f,.86f,.86f,1)), 20);
    return pressed;
}
// A label with its switch right-aligned on the same line.
inline bool SwitchRow(const char* label, bool* on)
{
    const float scale = ImGui::GetFontSize()/14.f, width = 40.f*scale, height = 20.f*scale;
    const float left = ImGui::GetCursorPosX(), available = ImGui::GetContentRegionAvail().x, top = ImGui::GetCursorPosY();
    const char* end = std::strstr(label, "##");
    ImGui::SetCursorPosY(top + (height - ImGui::GetFontSize())*.5f); ImGui::TextUnformatted(label, end);
    ImGui::SameLine(left + available - width); ImGui::SetCursorPosY(top);
    ImGui::PushID(label); const bool changed = Switch("##switch", on); ImGui::PopID();
    return changed;
}
// A section heading with a feature switch inline, like the sidebar's Neural rendering.
inline bool HeaderToggle(const char* text, bool* on, bool enabled)
{
    const float scale = ImGui::GetFontSize()/14.f, size = 18.f*scale, width = 40.f*scale, height = 20.f*scale;
    ImGui::Spacing();
    const float left = ImGui::GetCursorPosX(), available = ImGui::GetContentRegionAvail().x, top = ImGui::GetCursorPosY();
    Hero(text, size, ImVec4(.90f,.90f,.90f,1));
    ImGui::SameLine(left + available - width); ImGui::SetCursorPosY(top + (size - height)*.5f);
    ImGui::BeginDisabled(!enabled); ImGui::PushID(text);
    const bool changed = Switch("##header", on);
    ImGui::PopID(); ImGui::EndDisabled();
    return changed;
}
inline void HeaderSwitch(const char* text, const char* key, Config& cfg)
{
    for(const auto& field : controls)
    {
        if(std::strcmp(field.key, key) != 0) continue;
        const auto pending = queued.find(&field);
        bool on = (pending != queued.end() ? pending->second : field.get(cfg)) != 0;
        if(HeaderToggle(text, &on, Available(field))) Commit(field, cfg, on ? 1.f : 0.f);
    }
}// A sidebar-style segmented button: accent fill when selected.
inline bool Segment(const char* label, bool selected, float width, bool enabled = true)
{
    const auto dark=Tone(.21f,.88f);
    ImGui::BeginDisabled(!enabled);
    PushColor(ImGuiCol_Button, Mix(accent, dark, selected ? .45f : .06f));
    PushColor(ImGuiCol_ButtonHovered, Mix(accent, dark, selected ? .55f : .16f));
    ImGui::PushFont(selected && bold ? bold : font, ImGui::GetFontSize());
    const bool pressed = ImGui::Button(label, ImVec2(width, 0));
    ImGui::PopFont(); ImGui::PopStyleColor(2); ImGui::EndDisabled();
    return pressed;
}
inline float lastFrameGeneration = -1.f;
// Multi-Frame Generation: an on/off switch on the heading, Auto/Custom/Dynamic
// tabs, and 2x to 6x as the fixed ratio (Custom) or the ceiling (Dynamic).
inline void FrameGeneration(Config& cfg)
{
    const Control* field = nullptr;
    for(const auto& control : controls) if(std::strcmp(control.key, "multiplier") == 0) field = &control;
    if(!field) return;
    const auto pending = queued.find(field);
    const float value = pending != queued.end() ? pending->second : field->get(cfg);
    const bool dynamic = cfg.FGDLSSGOverrideForceDMFG.value_or_default();
    const int ceiling = std::clamp(State::Instance().dlssgMfgMax.value_or(0) + 1, 2, 6);
    bool on = value != 0;
    if(HeaderToggle("Multi-Frame Generation", &on, mfgAllowed))
    {
        if(on) Commit(*field, cfg, lastFrameGeneration != 0 ? lastFrameGeneration : -1.f);
        else { lastFrameGeneration = value; cfg.FGDLSSGOverrideForceDMFG.set_volatile_value(false); Commit(*field, cfg, 0.f); }
    }
    if(!on) { ImGui::TextDisabled("Multi-Frame Generation is off."); ImGui::Spacing(); return; }
    ImGui::BeginDisabled(!mfgAllowed);
    const int mode = dynamic ? 2 : value < 0 ? 0 : 1;
    const char* tabs[] = { "Auto", "Custom", "Dynamic" };
    const float gap = ImGui::GetStyle().ItemSpacing.x, third = (ImGui::GetContentRegionAvail().x - gap*2)/3;
    const bool dynamicReady = State::Instance().dlssgGameDMFGSupported;
    for(int i = 0; i < 3; ++i)
    {
        if(i) ImGui::SameLine();
        if(!Segment(tabs[i], mode == i, third, i != 2 || dynamicReady || dynamic)) continue;
        const float ratio = value >= 2 ? value : float(i == 2 ? ceiling : 2);
        cfg.FGDLSSGOverrideForceDMFG.set_volatile_value(i == 2);
        Commit(*field, cfg, i == 0 ? -1.f : ratio);
    }
    if(mode == 0) ImGui::TextDisabled("Follows the game's frame generation setting.");
    else
    {
        ImGui::TextUnformatted(mode == 2 ? "Maximum generated frames" : "Multiplier");
        const char* ratios[] = { "2\xC3\x97", "3\xC3\x97", "4\xC3\x97", "5\xC3\x97", "6\xC3\x97" };
        const float fifth = (ImGui::GetContentRegionAvail().x - gap*4)/5;
        for(int r = 2; r <= 6; ++r)
        {
            if(r > 2) ImGui::SameLine();
            ImGui::PushID(r);
            if(Segment(ratios[r-2], int(value) == r, fifth, r <= ceiling)) Commit(*field, cfg, float(r));
            ImGui::PopID();
        }
        if(mode == 2) ImGui::TextDisabled("Generates up to this many frames to reach your display's refresh rate.");
    }
    if(!dynamicReady && !dynamic) ImGui::TextDisabled("Dynamic needs a game and driver that support it.");
    ImGui::EndDisabled(); ImGui::Spacing();
}

// The sidebar's labelled dropdown for plain lists.
inline bool ChoiceList(const char* label, int* current, const char* const items[], int count)
{
    ImGui::PushID(label);
    ImGui::PushStyleVar(ImGuiStyleVar_ItemSpacing, ImVec2(ImGui::GetStyle().ItemSpacing.x, 3.f*ImGui::GetFontSize()/14.f));
    ImGui::TextUnformatted(label); ImGui::PopStyleVar(); ImGui::SetNextItemWidth(-1);
    bool changed = false;
    if(Dropdown(items[std::clamp(*current, 0, count-1)]))
    {
        for(int i=0;i<count;++i) if(DropdownItem(items[i], i == *current)) { *current = i; changed = true; }
        DropdownEnd();
    }
    ImGui::PopID(); return changed;
}inline void Field(const Control& field, Config& cfg)
{
    ImGui::PushID(field.key);
    ImGui::BeginDisabled(!Available(field));
    auto value = field.get(cfg); bool changed = false;
    if(const auto pending = queued.find(&field); pending != queued.end()) value = pending->second;
    if(const auto held = dragging.find(field.key); held != dragging.end()) value = held->second;
    const auto label = advanced ? field.advanced : field.label;
    if(std::strcmp(field.key,"multiplier") == 0 || std::strcmp(field.key,"style") == 0)
    {
        const auto count=std::strcmp(field.key,"style")==0 ? 3u : 5u;
        const auto width=(ImGui::GetContentRegionAvail().x-ImGui::GetStyle().ItemSpacing.x*(count-1))/count;
        for(unsigned i=0;i<count;++i)
        {
            if(i) ImGui::SameLine();
            const auto& option=field.choices[i];
            const bool selectedOption=value==option.value;
            const bool unavailable=std::strcmp(field.key,"multiplier")==0 && option.value>0 && option.value-1>State::Instance().dlssgMfgMax.value_or(0);
            ImGui::BeginDisabled(unavailable);
            PushColor(ImGuiCol_Button,Mix(accent,Tone(.21f,.88f),selectedOption ? .45f : .06f));
            if(ImGui::Button(option.label,ImVec2(width,0))) { value=option.value; changed=true; }
            ImGui::PopStyleColor(); ImGui::EndDisabled();
        }
    }
    else if (field.kind == Kind::toggle)
    { bool on = value != 0; changed = SwitchRow(label, &on); value = on ? 1.f : 0.f; }
    else
    {
        // Labels sit close to their control, as in the rtxForge sidebar.
        ImGui::PushStyleVar(ImGuiStyleVar_ItemSpacing,ImVec2(ImGui::GetStyle().ItemSpacing.x,3.f*ImGui::GetFontSize()/14.f));
        ImGui::TextUnformatted(label); ImGui::PopStyleVar(); ImGui::SetNextItemWidth(-1);
        if(field.kind == Kind::choice)
        {
            const char* preview = "Automatic";
            for(size_t i=0; i<field.count; ++i) if(field.choices[i].value == value) preview = field.choices[i].label;
            if(Dropdown(preview))
            {
                for(size_t i=0; i<field.count; ++i)
                {
                    const auto& choice = field.choices[i];
                    const bool unavailable = std::strcmp(field.key,"multiplier") == 0 && choice.value > 0
                        && choice.value - 1 > State::Instance().dlssgMfgMax.value_or(0);
                    ImGui::BeginDisabled(unavailable);
                    if(DropdownItem(choice.label, value == choice.value)) { value = choice.value; changed = true; }
                    ImGui::EndDisabled();
                }
                DropdownEnd();
            }
        }
        else
        {
            // Checked straight after the slider, before any hint text becomes the last item.
            const auto released = [&] {
                if(!ImGui::IsItemDeactivatedAfterEdit()) return;
                if(const auto held = dragging.find(field.key); held != dragging.end()) { value = held->second; dragging.erase(held); changed = true; }
            };
            const float scale = ImGui::GetFontSize()/14.f;
            const float fraction = field.high > field.low ? (value - field.low) / (field.high - field.low) : 0.f;
            char text[32];
            if(field.kind == Kind::number)
            {
                int n = int(value); std::snprintf(text, sizeof(text), "%d", n); SliderBegin(text);
                if(ImGui::SliderInt("##value", &n, int(field.low), int(field.high), "")) dragging[field.key] = float(n);
                released(); SliderEnd(fraction, scale);
            }
            else
            {
                // Strengths read 0.00-2.00 as in Presets; only model resolution is a percentage.
                const bool percent = std::strcmp(field.key,"work_scale") == 0;
                auto shown = percent ? value * 100.f : value;
                std::snprintf(text, sizeof(text), percent ? "%.0f%%" : "%.2f", shown); SliderBegin(text);
                if(ImGui::SliderFloat("##value", &shown, percent ? field.low*100 : field.low, percent ? field.high*100 : field.high, "", ImGuiSliderFlags_AlwaysClamp))
                    dragging[field.key] = percent ? shown/100.f : shown;
                released(); SliderEnd(fraction, scale);
                if(std::strcmp(field.key,"skin") == 0 && value < 0) ImGui::TextDisabled("-1 follows local structure");
            }
        }
    }
    if(changed) Commit(field, cfg, value);
    ImGui::EndDisabled(); ImGui::PopID(); ImGui::Spacing();
}
inline void Pipelines(float scale)
{
    const auto& status = ForgePanelChannel::status;
    // The label is drawn centred on the 22 px pill row without moving the line.
    ImGui::PushFont(ImGui::GetFont(), 11.f*scale);
    const auto start = ImGui::GetCursorScreenPos(); const auto label = ImGui::CalcTextSize("DLSS files");
    ImGui::GetWindowDrawList()->AddText(ImVec2(start.x, start.y + (22.f*scale - label.y)*.5f), Colour(Tone(1,0,.75f)), "DLSS files");
    ImGui::Dummy(ImVec2(label.x, 22.f*scale)); ImGui::SameLine();
    for(const auto* name : {"SR","RR","NR","FG"})
    {
        const auto info = status.contains("pipelines") && status["pipelines"].contains(name) ? status["pipelines"][name] : nlohmann::json::object();
        const auto state = info.value("state",std::string());
        auto color = state == "managed" ? ImVec4(.59f,.84f,.41f,1) : state == "other" ? ImVec4(.76f,.91f,.62f,1)
            : state == "changed" ? ImVec4(.96f,.78f,.38f,1) : state == "absent" ? ImVec4(.48f,.50f,.53f,1) : ImVec4(.67f,.67f,.67f,1);
        if(lightTheme) color=Mix(color,ImVec4(0,0,0,1),.53f);
        const auto pos = ImGui::GetCursorScreenPos(); const auto size = ImVec2(42.f*scale,22.f*scale);
        ImGui::InvisibleButton(name,size); auto* draw=ImGui::GetWindowDrawList();
        draw->AddRectFilled(pos,ImVec2(pos.x+size.x,pos.y+size.y),Colour(ImVec4(color.x,color.y,color.z,.10f)),11*scale);
        draw->AddCircleFilled(ImVec2(pos.x+10*scale,pos.y+11*scale),2.5f*scale,Colour(color),12);
        draw->AddText(bold ? bold : font,11.f*scale,ImVec2(pos.x+17*scale,pos.y+5*scale),Colour(color),name);
        if(ImGui::IsItemHovered()) ImGui::SetTooltip("%s",info.value("detail",std::string("File ownership is unavailable. This does not indicate live activity.")).c_str());
        if(std::strcmp(name,"FG") != 0) ImGui::SameLine();
    }
    ImGui::PopFont();
}
inline bool Preference(const char* name, nlohmann::json value)
{
    if(!ForgePanelChannel::Send({{"op","set-setting"},{"key",name},{"value",value}})) return false;
    ForgePanelChannel::settings[name] = std::move(value); return true;
}
inline void PreferenceToggle(const char* label, const char* name, bool fallback)
{
    auto value = ForgePanelChannel::settings.value(name,fallback);
    if(SwitchRow(label,&value)) Preference(name,value);
}
inline void ReviewEntries(const char* label, const char* key)
{
    const auto& review = ForgePanelChannel::review;
    if(!review.contains(key) || review[key].empty()) return;
    if(ImGui::CollapsingHeader((std::string(label)+" ("+std::to_string(review[key].size())+")").c_str(),std::strcmp(key,"items")==0 ? ImGuiTreeNodeFlags_DefaultOpen : 0))
    {
        for(const auto& entry : review[key])
        { ImGui::TextWrapped("%s",entry.value("title",std::string()).c_str()); PushColor(ImGuiCol_Text,Tone(.7f,.35f)); ImGui::TextWrapped("%s",entry.value("detail",std::string()).c_str()); ImGui::PopStyleColor(); ImGui::Spacing(); }
    }
}
inline void ReviewedChanges()
{
    using namespace ForgePanelChannel;
    if(review.empty()) return;
    ReviewEntries("Ready","items"); ReviewEntries("Needs attention","blocked"); ReviewEntries("Unchanged or unavailable","skipped");
    ImGui::BeginDisabled(pending || !review.value("ready",false));
    if(ImGui::Button("Apply to games",ImVec2(-1,0))) Send({{"op","apply-review"},{"review_id",review.value("review_id",0)}});
    ImGui::EndDisabled();
}
inline void GlobalControls()
{
    static int nr=0,mfg=0;
    const char* nrItems[]={"Leave as is","Off","On"};
    const char* mfgItems[]={"Leave as is","Off","2x","3x","4x","5x","6x","Follow game"};
    ImGui::TextWrapped("One-time changes. Review the games before applying. Running games are skipped.");
    ImGui::BeginDisabled(ForgePanelChannel::pending || !ForgePanelChannel::helperReady);
    ImGui::SetNextItemWidth(-1);
    if(ChoiceList("Neural rendering",&nr,nrItems,3)) ForgePanelChannel::DiscardReview();
    ImGui::SetNextItemWidth(-1);
    if(ChoiceList("Frame generation",&mfg,mfgItems,8)) ForgePanelChannel::DiscardReview();
    ImGui::BeginDisabled(nr==0 && mfg==0);
    if(ImGui::Button("Review games",ImVec2(-1,0)))
    {
        nlohmann::json changes = nlohmann::json::object();
        if(nr) changes["nr"] = nr==2;
        if(mfg) changes["mfg"] = mfg==1 ? 0 : mfg==7 ? -1 : mfg;
        ForgePanelChannel::review = nlohmann::json::object();
        ForgePanelChannel::Send({{"op","global-review"},{"changes",changes}});
    }
    ImGui::EndDisabled(); ImGui::EndDisabled();
    ReviewedChanges();
}
// The shortcut's name as the app writes it (OverlayShortcut.cs), for when the helper has not
// sent panel_hotkey: the panel then names the key it read from the registry, not a default.
inline std::string ShortcutLabel()
{
    if(ForgePanelChannel::settings.contains("panel_hotkey")) return ForgePanelChannel::settings.value("panel_hotkey",std::string());
    static const std::pair<int,const char*> names[]={{0x23,"End"},{0x24,"Home"},{0x21,"PageUp"},{0x22,"PageDown"},{0x25,"Left"},{0x26,"Up"},
        {0x27,"Right"},{0x28,"Down"},{0x13,"Pause"},{0x91,"ScrollLock"},{0x2E,"Delete"},{0x2D,"Insert"},{8,"Backspace"},{13,"Enter"},{0x20,"Space"},
        {0x6A,"NumMultiply"},{0x6B,"NumAdd"},{0x6D,"NumSubtract"},{0x6E,"NumDecimal"},{0x6F,"NumDivide"},{0xBA,"Semicolon"},{0xBB,"Equals"},
        {0xBC,"Comma"},{0xBD,"Minus"},{0xBE,"Period"},{0xBF,"Slash"},{0xC0,"Backtick"},{0xDB,"LeftBracket"},{0xDC,"Backslash"},
        {0xDD,"RightBracket"},{0xDE,"Quote"}};
    if(key == 0) return "Disabled";
    std::string name;
    for(const auto& [code,text] : names) if(code == key) name = text;
    if(name.empty() && ((key >= 0x30 && key <= 0x39) || (key >= 0x41 && key <= 0x5A))) name = std::string(1,char(key));
    if(name.empty() && key >= 0x60 && key <= 0x69) name = "Num" + std::to_string(key - 0x60);
    if(name.empty() && key >= 0x70 && key <= 0x87) name = "F" + std::to_string(key - 0x6F);
    if(name.empty()) name = "Key " + std::to_string(key);
    return std::string((modifiers & 2) ? "Ctrl+" : "") + ((modifiers & 1) ? "Alt+" : "") + ((modifiers & 4) ? "Shift+" : "") + name;
}
inline bool WelcomeSyncing()
{
    return !ForgePanelChannel::helperReady && ForgePanelChannel::pending
        && GetTickCount64()-ForgePanelChannel::requestedAt<1500;
}
inline bool WelcomePending()
{
    const auto& prefs = ForgePanelChannel::settings;
    const bool show = prefs.contains("overlay_welcome") && prefs["overlay_welcome"].is_boolean()
        ? prefs["overlay_welcome"].get<bool>() : showWelcome;
    if(!enabled || !show || welcomeDismissed || !ShortcutKey()) return false;
    if(WelcomeSyncing()) return true;
    if(!welcomeStarted) welcomeStarted=GetTickCount64();
    return GetTickCount64()-welcomeStarted < 7000;
}
inline int WelcomePosition()
{
    const auto& prefs=ForgePanelChannel::settings;
    if(prefs.contains("overlay_welcome_position") && prefs["overlay_welcome_position"].is_string())
        for(int i=0;i<int(welcomePositions.size());++i)
            if(prefs["overlay_welcome_position"]==welcomePositions[i]) return i;
    return welcomePosition<welcomePositions.size() ? int(welcomePosition) : 0;
}
inline std::string KeyFace()
{
    std::string face;
    if(key==VK_OEM_3) face="`";
    else if(key==VK_DELETE) face="Del";
    else if(key==VK_INSERT) face="Ins";
    else if(key==VK_BACK) face="<";
    else if(key==VK_RETURN) face="Enter";
    else if(key>=0x70 && key<=0x87) face="F"+std::to_string(key-0x6f);
    else if((key>=0x30 && key<=0x39)||(key>=0x41 && key<=0x5a)) face=char(key);
    else face="Key";
    return face;
}
inline void KeyGlyph(float scale)
{
    const auto face=KeyFace();
    const auto origin=ImGui::GetCursorScreenPos();
    const float height=20.f*scale;
    ImGui::PushFont(font,11.f*scale);
    const auto text=ImGui::CalcTextSize(face.c_str());
    const float width=std::max(22.f*scale,text.x+10.f*scale);
    auto* draw=ImGui::GetWindowDrawList();
    draw->AddRectFilled(origin,ImVec2(origin.x+width,origin.y+height),Colour(Tone(.19f,.88f)),4.f*scale);
    draw->AddRect(origin,ImVec2(origin.x+width,origin.y+height),Colour(Tone(.65f,.48f)),4.f*scale);
    draw->AddLine(ImVec2(origin.x+4.f*scale,origin.y+height-3.f*scale),ImVec2(origin.x+width-4.f*scale,origin.y+height-3.f*scale),Colour(Tone(.4f,.62f)),scale);
    draw->AddText(ImVec2(origin.x+(width-text.x)*.5f,origin.y+(height-text.y)*.5f-scale),Colour(Tone(.94f,.12f)),face.c_str());
    ImGui::PopFont(); ImGui::Dummy(ImVec2(width,height));
}
inline void Welcome(bool panelVisible)
{
    PollHelper();
    if(panelVisible) welcomeDismissed=true;
    if(WelcomeSyncing()) return;
    if(!WelcomePending() || !OptiInput::IsFocused()) return;
    const float scale=PanelScale();
    const auto display=ImGui::GetIO().DisplaySize;
    const auto label=ShortcutLabel()+" to open the overlay";
    ImGui::PushFont(font,14.f*scale);
    const float words=ImGui::CalcTextSize("Press").x+ImGui::CalcTextSize(label.c_str()).x+14.f*scale;
    ImGui::PopFont(); ImGui::PushFont(font,11.f*scale);
    const float cap=std::max(22.f*scale,ImGui::CalcTextSize(KeyFace().c_str()).x+10.f*scale);
    ImGui::PopFont(); ImGui::PushFont(brandFont ? brandFont : bold,20.f*scale);
    const float wordmark=ImGui::CalcTextSize("rtxForge").x;
    ImGui::PopFont();
    const float width=40.f*scale+24.f*scale*forgeIconWidth/forgeIconHeight+10.f*scale+wordmark+16.f*scale+words+cap;
    const int placement=WelcomePosition();
    const bool bottom=placement>=3, right=placement==2 || placement==4;
    const float x=placement==0 ? display.x*.5f : right ? display.x-24.f*scale : 24.f*scale;
    ImGui::SetNextWindowPos(ImVec2(x,bottom ? display.y-24.f*scale : 56.f*scale),ImGuiCond_Always,
        ImVec2(placement==0 ? .5f : right ? 1.f : 0.f,bottom ? 1.f : 0.f));
    ImGui::SetNextWindowSize(ImVec2(width,48.f*scale),ImGuiCond_Always);
    ImGui::PushStyleVar(ImGuiStyleVar_WindowPadding,ImVec2(20.f*scale,12.f*scale));
    ImGui::PushStyleVar(ImGuiStyleVar_WindowRounding,12.f*scale);
    ImGui::PushStyleVar(ImGuiStyleVar_WindowBorderSize,scale);
    ImGui::PushStyleVar(ImGuiStyleVar_ItemSpacing,ImVec2(8.f*scale,6.f*scale));
    PushColor(ImGuiCol_WindowBg,Tone(.045f,.96f,.94f));
    PushColor(ImGuiCol_Border,Tone(1,0,.14f));
    PushColor(ImGuiCol_Text,Tone(.9f,.12f));
    ImGui::Begin("rtxForge##welcome",nullptr,ImGuiWindowFlags_NoDecoration
        |ImGuiWindowFlags_NoInputs|ImGuiWindowFlags_NoNav|ImGuiWindowFlags_NoSavedSettings);
    const float rowTop=ImGui::GetCursorPosY();
    Brand(scale*4.f/3.f); ImGui::SameLine(0,10.f*scale);
    ImGui::SetCursorPosY(rowTop+2.f*scale); Hero("rtxForge",20.f*scale,Tone(.94f,.12f));
    ImGui::SameLine(0,16.f*scale); ImGui::SetCursorPosY(rowTop+5.f*scale);
    ImGui::PushFont(font,14.f*scale);
    ImGui::TextUnformatted("Press"); ImGui::SameLine(0,7.f*scale);
    ImGui::SetCursorPosY(rowTop+2.f*scale); KeyGlyph(scale); ImGui::SameLine(0,7.f*scale);
    ImGui::SetCursorPosY(rowTop+5.f*scale);
    ImGui::Text("%s to open the overlay",ShortcutLabel().c_str());
    ImGui::PopFont();
    ImGui::End(); ImGui::PopStyleColor(3); ImGui::PopStyleVar(4);
}
inline void SettingsControls()
{
    using ForgePanelChannel::pending; using ForgePanelChannel::helperReady; using ForgePanelChannel::Send;
    auto& prefs = ForgePanelChannel::settings;
    Section("Overlay settings");
    ImGui::BeginDisabled(pending || !helperReady);
    const char* themeItems[]={"Dark","Light","Follow app"};
    const char* themeKeys[]={"dark","light","app"};
    const auto theme=prefs.value("overlay_theme",std::string("dark"));
    int selectedTheme=theme=="light" ? 1 : theme=="app" ? 2 : 0;
    ImGui::SetNextItemWidth(-1);
    if(ChoiceList("Appearance",&selectedTheme,themeItems,3)) Preference("overlay_theme",themeKeys[selectedTheme]);
    bool advancedChoice=advanced;
    if(SwitchRow("Advanced controls", &advancedChoice))
    { if(Preference("overlay_controls",advancedChoice)) prefs["overlay_controls"] = advancedChoice ? "classic" : "unified"; }
    PreferenceToggle("Show live statistics","overlay_live_stats",showLiveStats);
    PreferenceToggle("Welcome message","overlay_welcome",showWelcome);
    const char* welcomeItems[]={"Top center","Top left","Top right","Bottom left","Bottom right"};
    int selectedWelcome=WelcomePosition();
    ImGui::SetNextItemWidth(-1);
    if(ChoiceList("Welcome position",&selectedWelcome,welcomeItems,5)) Preference("overlay_welcome_position",welcomePositions[selectedWelcome]);
    if(nativeMfgMenuSupported) PreferenceToggle("Native MFG menu and hint","vulkan_mfg_native_menu",false);
    const char* rendererItems[]={"rtxForge","Native"};
    const auto renderer=prefs.value("overlay_renderer",std::string("game"));
    int selectedRenderer=renderer=="optiscaler" ? 1 : 0;
    ImGui::SetNextItemWidth(-1);
    if(ChoiceList("Primary overlay",&selectedRenderer,rendererItems,2)) Preference("overlay_renderer",selectedRenderer==1 ? "optiscaler" : "game");
    const auto shortcut=ShortcutLabel();
    if(ImGui::Button(binding ? "Press a key..." : ("Shortcut: "+shortcut).c_str(),ImVec2(-1,0))) binding=true;
    if(binding)
    {
        const auto code=OptiInput::GetLastPressedKey();
        if(code==VK_ESCAPE && OptiInput::IsKeyPressed(code)) { bindingRelease=code; binding=false; }
        else if(code>0 && OptiInput::IsKeyPressed(code) && code!=VK_CONTROL && code!=VK_SHIFT && code!=VK_MENU
                && !(code>=VK_LSHIFT && code<=VK_RMENU))
        {
            const int mods=(OptiInput::IsKeyDown(VK_MENU)?1:0)|(OptiInput::IsKeyDown(VK_CONTROL)?2:0)|(OptiInput::IsKeyDown(VK_SHIFT)?4:0);
            if(Send({{"op","set-setting"},{"key","panel_binding"},{"value",{{"key",code},{"modifiers",mods}}}})) { bindingRelease=code; binding=false; }
        }
        ImGui::TextWrapped("Optional Ctrl, Alt or Shift. Insert stays with OptiScaler.");
    }
    if(ImGui::Button("Disable shortcut",ImVec2(-1,ImGui::GetFrameHeight()))) Send({{"op","set-setting"},{"key","panel_binding"},{"value",{{"key",0},{"modifiers",0}}}});
    Section("OptiScaler");
    PreferenceToggle("In-game menu##opti","optiscaler_ui",true);
    PreferenceToggle("Intro message##opti","optiscaler_intro",false);
    const char* nativeItems[]={"Insert","F8","Disabled"};
    const auto native=prefs.value("optiscaler_hotkey",std::string("Insert")); int selectedNative=native=="F8" ? 1 : native=="Disabled" ? 2 : 0;
    ImGui::SetNextItemWidth(-1);
    if(ChoiceList("Original menu shortcut",&selectedNative,nativeItems,3)) Preference("optiscaler_hotkey",nativeItems[selectedNative]);
    Section("ReShade");
    PreferenceToggle("In-game menu##reshade","reshade_ui",true);
    PreferenceToggle("Welcome messages##reshade","reshade_intro",false);
    ImGui::TextWrapped("Menu access and welcome messages are separate. NR, MFG and effects stay installed.");
    if(ImGui::Button("Review installed game menus",ImVec2(-1,0)))
    { ForgePanelChannel::review=nlohmann::json::object(); Send({{"op","menus-review"}}); }
    ImGui::TextWrapped("Menu, intro and primary overlay changes take effect after restarting the game.");
    ReviewedChanges();
    Section("Background helper");
    PreferenceToggle("Start with Windows","overlay_start_with_windows",true);
    ImGui::TextWrapped("The helper saves presets and handles reviews. The main rtxForge window can stay closed.");
    PreferenceToggle("Enable helper","overlay_helper",true);
    ImGui::EndDisabled();
    if(ImGui::CollapsingHeader("Performance"))
    { ImGui::Text("Panel CPU submit: %.3f ms",cpuMs); ImGui::TextWrapped("Translucent surface. No additional blur pass. Live controls work without the helper; saving and reviews need it."); }
}
// Keep each digit in an equal-width Inter cell and reserve the whole numeric
// field. Crossing 9.99/10.00 never moves its decimal point or the following label.
inline void MetricNumber(double value, int integers, int decimals)
{
    char text[64]; std::snprintf(text,sizeof(text),"%*.*f",integers+(decimals ? decimals+1 : 0),decimals,value);
    float cell=0;
    for(char digit='0';digit<='9';++digit) { const char glyph[]={digit,0}; cell=std::max(cell,ImGui::CalcTextSize(glyph).x); }
    const auto origin=ImGui::GetCursorScreenPos(); float x=origin.x;
    auto* draw=ImGui::GetWindowDrawList();
    for(const char* at=text;*at;++at) {
        const char glyph[]={*at,0}; const auto size=ImGui::CalcTextSize(glyph);
        const float width=*at=='.' ? size.x : cell;
        if(*at!=' ') draw->AddText(ImVec2(x+(width-size.x)*.5f,origin.y),ImGui::GetColorU32(ImGuiCol_Text),glyph);
        x+=width;
    }
    ImGui::Dummy(ImVec2(x-origin.x,ImGui::GetFontSize()));
}
inline void FeatureStatistics(bool neural, float scale) {
    if(!readLiveStats || !ForgePanelChannel::settings.value("overlay_live_stats",showLiveStats)) return;
    const auto stats = readLiveStats();
    ImGui::PushFont(font,12.f*scale);
    if(neural) {
        if(!stats.nrKnown) ImGui::TextDisabled("Activity unavailable from this injector");
        else {
            const bool timed = stats.nrRunning && stats.nrGpuMs >= 0 && std::isfinite(stats.nrGpuMs);
            const char* state = stats.nrWarming ? "Warming up" : stats.nrRunning ? "Active" : "Idle";
            if(timed) {
                ImGui::BeginGroup(); PushColor(ImGuiCol_Text,TitleColor()); MetricNumber(stats.nrGpuMs,4,2);
                ImGui::SameLine(0,3.f*scale); ImGui::TextUnformatted("ms"); ImGui::PopStyleColor();
                ImGui::SameLine(0,10.f*scale); ImGui::TextDisabled("GPU  /  %s",state); ImGui::EndGroup();
            } else ImGui::TextDisabled("%s",state);
            if(ImGui::IsItemHovered()) {
                if(stats.nrFramesKnown) ImGui::SetTooltip("%llu model frames composed",stats.nrFrames);
                else ImGui::SetTooltip("Model-frame count unavailable from this injector");
            }
        }
    } else if(stats.framesKnown && stats.gameFps >= 0 && stats.displayedFps >= 0 && stats.measuredRatio >= 0
              && std::isfinite(stats.gameFps) && std::isfinite(stats.displayedFps) && std::isfinite(stats.measuredRatio)) {
        ImGui::BeginGroup(); PushColor(ImGuiCol_Text,TitleColor()); MetricNumber(stats.gameFps,4,0);
        ImGui::SameLine(0,5.f*scale); ImGui::TextUnformatted(">"); ImGui::SameLine(0,5.f*scale); MetricNumber(stats.displayedFps,4,0);
        ImGui::SameLine(0,3.f*scale); ImGui::TextUnformatted("FPS"); ImGui::PopStyleColor();
        ImGui::SameLine(0,10.f*scale); ImGui::TextDisabled("/"); ImGui::SameLine(0,5.f*scale);
        ImGui::PushStyleColor(ImGuiCol_Text,ImGui::GetStyleColorVec4(ImGuiCol_TextDisabled)); MetricNumber(stats.measuredRatio,2,2); ImGui::PopStyleColor();
        ImGui::SameLine(0,2.f*scale); ImGui::TextDisabled("x"); ImGui::EndGroup();
        if(ImGui::IsItemHovered()) ImGui::SetTooltip("Measured rendered and displayed frames; independent of the requested multiplier");
    } else if(stats.gameFps >= 0 && std::isfinite(stats.gameFps)) {
        ImGui::TextDisabled("%.0f FPS rendered / output unavailable",stats.gameFps);
    } else ImGui::TextDisabled("Waiting for displayed-frame data");
    ImGui::PopFont();
}
inline bool Draw(bool& visible, float scale)
{
    if (!selected) return false;
    scale = std::max(scale, PanelScale());
    Flush(*Config::Instance());
    if (!OptiInput::IsFocused()) { visible = false; animation = 0; ForgePanelChannel::Visible(false); return false; }
    const auto start = std::chrono::steady_clock::now();
    const auto dt = std::min(ImGui::GetIO().DeltaTime, .05f);
    animation = std::clamp(animation + dt / (visible ? .16f : -.11f), 0.f, 1.f);
    if(animation <= 0) return false;
    const auto eased = 1 - std::pow(1-animation, 3.f), sizeScale = .97f + .03f*eased;
    const auto display = ImGui::GetIO().DisplaySize;
    using ForgePanelChannel::Send; using ForgePanelChannel::Poll; using ForgePanelChannel::pending;
    using ForgePanelChannel::needsHello; using ForgePanelChannel::helperReady; using ForgePanelChannel::message;
    PollHelper();
    if(!pending && needsHello && Send({{"op","hello"}})) needsHello = false;
    const auto edge = 24.f*scale, width = std::min(420.f*scale, display.x-edge*2);
    const auto height = display.y-edge*2;
    // Translucent surface with a hairline edge. No shadow quads, texture,
    // backdrop sampling, render target or shader pass.
    ImGui::SetNextWindowPos(ImVec2(edge,edge + height*(1-sizeScale)*.5f), ImGuiCond_Always);
    ImGui::SetNextWindowSize(ImVec2(width*sizeScale,height*sizeScale), ImGuiCond_Always);
    ImGui::PushFont(font, 14.f*scale);
    ImGui::PushStyleVar(ImGuiStyleVar_Alpha,eased);
    ImGui::PushStyleVar(ImGuiStyleVar_WindowRounding,20.f*scale);
    ImGui::PushStyleVar(ImGuiStyleVar_WindowPadding,ImVec2(26.f*scale,22.f*scale));
    ImGui::PushStyleVar(ImGuiStyleVar_FrameRounding,10.f*scale);
    ImGui::PushStyleVar(ImGuiStyleVar_FramePadding,ImVec2(10.f*scale,8.f*scale));
    ImGui::PushStyleVar(ImGuiStyleVar_ItemSpacing,ImVec2(10.f*scale,8.f*scale));
    ImGui::PushStyleVar(ImGuiStyleVar_WindowBorderSize,1.f*scale);
    ImGui::PushStyleVar(ImGuiStyleVar_GrabMinSize,16.f*scale);
    ImGui::PushStyleVar(ImGuiStyleVar_GrabRounding,8.f*scale);
    ImGui::PushStyleVar(ImGuiStyleVar_PopupRounding,12.f*scale);
    ImGui::PushStyleVar(ImGuiStyleVar_ChildRounding,12.f*scale);
    ImGui::PushStyleVar(ImGuiStyleVar_ScrollbarRounding,12.f*scale);
    ImGui::PushStyleVar(ImGuiStyleVar_ScrollbarSize,8.f*scale);
    const auto neutral=Tone(.91f,.12f), dark=Tone(.20f,.88f), well=Tone(.22f,.86f);
    const auto ink = TitleColor();
    const auto alpha = [](ImVec4 color, float a) { color.w = a; return color; };
    PushColor(ImGuiCol_WindowBg,Tone(.06f,.96f,.92f));
    PushColor(ImGuiCol_TextDisabled,Tone(.62f,.40f));
    PushColor(ImGuiCol_Border,Tone(1,0,.08f));
    PushColor(ImGuiCol_Text,neutral);
    PushColor(ImGuiCol_Button,Mix(accent,dark,.20f));
    PushColor(ImGuiCol_ButtonHovered,Mix(accent,dark,.32f));
    PushColor(ImGuiCol_ButtonActive,Mix(accent,dark,.45f));
    PushColor(ImGuiCol_FrameBg,well);
    PushColor(ImGuiCol_FrameBgHovered,Mix(accent,well,.18f));
    PushColor(ImGuiCol_FrameBgActive,Mix(accent,well,.28f));
    PushColor(ImGuiCol_CheckMark,ink);
    PushColor(ImGuiCol_SliderGrab,ink);
    PushColor(ImGuiCol_SliderGrabActive,Mix(ink,neutral,.6f));
    PushColor(ImGuiCol_Header,Tone(.20f,.88f));
    PushColor(ImGuiCol_HeaderHovered,Tone(.26f,.82f));
    PushColor(ImGuiCol_HeaderActive,Tone(.31f,.77f));
    PushColor(ImGuiCol_PopupBg,Tone(.07f,.97f));
    PushColor(ImGuiCol_ScrollbarBg,ImVec4(0,0,0,0));
    PushColor(ImGuiCol_ScrollbarGrab,Tone(.32f,.68f));
    PushColor(ImGuiCol_ScrollbarGrabHovered,Tone(.42f,.58f));
    PushColor(ImGuiCol_ScrollbarGrabActive,Tone(.52f,.48f));
    PushColor(ImGuiCol_Separator,Tone(1,0,.10f));
    PushColor(ImGuiCol_NavCursor,ink);
    PushColor(ImGuiCol_TextSelectedBg,alpha(Mix(accent,dark,.4f),.5f));
    ImGui::Begin("rtxForge##ingame",nullptr,ImGuiWindowFlags_NoDecoration|ImGuiWindowFlags_NoMove|ImGuiWindowFlags_NoSavedSettings|ImGuiWindowFlags_NoScrollWithMouse|ImGuiWindowFlags_NoScrollbar);
    Brand(scale); Hero("rtxForge",19.f*scale,neutral); ImGui::SameLine(ImGui::GetWindowWidth()-ImGui::GetStyle().WindowPadding.x-110.f*scale);
    if(IconButton("Global controls",2,scale)) { global = !global; settings = false; ForgePanelChannel::DiscardReview(); }
    ImGui::SameLine(); if(IconButton("Overlay settings",1,scale)) { settings = !settings; global = false; ForgePanelChannel::DiscardReview(); }
    ImGui::SameLine(); if(IconButton("Close panel",0,scale)) visible = false;
    Hero(global ? "All installed games" : title.c_str(),25.f*scale,global ? neutral : TitleColor());
    if(global) ImGui::TextDisabled("One-time changes - review before applying");
    else Pipelines(scale);
    ImGui::Spacing();
    const auto feedbackHeight=message.empty() ? 0.f : std::min(60.f*scale,ImGui::CalcTextSize(message.c_str(),nullptr,false,ImGui::GetContentRegionAvail().x).y);
    const float spacing = ImGui::GetStyle().ItemSpacing.y, hint = ImGui::GetTextLineHeight();
    const auto footer = (settings || global ? hint : 42.f*scale + spacing + hint) + spacing + (message.empty() ? 0.f : feedbackHeight + spacing);
    ImGui::BeginChild("controls",ImVec2(0,-footer),ImGuiChildFlags_None,ImGuiWindowFlags_NoBackground);
    // A narrower inner region keeps content clear of the scrollbar.
    ImGui::BeginChild("content",ImVec2(ImGui::GetContentRegionAvail().x-12.f*scale,0),ImGuiChildFlags_AutoResizeY|ImGuiChildFlags_NavFlattened,ImGuiWindowFlags_NoBackground|ImGuiWindowFlags_NoScrollbar|ImGuiWindowFlags_NoScrollWithMouse);
    auto& cfg = *Config::Instance();
    // Settings and Global use the main page's looser rhythm.
    if(settings || global) ImGui::PushStyleVar(ImGuiStyleVar_ItemSpacing, ImVec2(10.f*scale, 14.f*scale));
    if(settings) SettingsControls();
    else if(global) GlobalControls();
    else
    {
        const char* group = "";
        bool open = true;
        for(const auto& field : controls)
        {
            if(std::strcmp(group,field.group) != 0)
            {
                group = field.group; ImGui::Spacing();
                const bool primary = std::strcmp(group,"Frame generation") == 0 || std::strcmp(group,"Neural rendering") == 0 || std::strcmp(group,"Image tuning") == 0;
                if(primary) {
                    if(std::strcmp(group,"Neural rendering") == 0) { HeaderSwitch(group,"enabled",cfg); FeatureStatistics(true,scale); }
                    else if(std::strcmp(group,"Frame generation") == 0) { FrameGeneration(cfg); FeatureStatistics(false,scale); }
                    else Section(group);
                    open = true;
                }
                else open = ImGui::CollapsingHeader(group);
            }
            if(!open) continue;
            if(std::strcmp(field.key,"passes")==0 || std::strcmp(field.key,"enabled")==0 || std::strcmp(field.key,"multiplier")==0) continue;
            if(std::strcmp(field.key,"preset")==0 && ImGui::BeginTable("model choices",2,ImGuiTableFlags_SizingStretchSame))
            {
                ImGui::TableNextColumn(); Field(field,cfg); ImGui::TableNextColumn();
                for(const auto& other : controls) if(std::strcmp(other.key,"passes")==0) Field(other,cfg);
                ImGui::EndTable();
            }
            else Field(field,cfg);
        }
    }
    if(settings || global) ImGui::PopStyleVar();
    ImGui::EndChild(); ImGui::EndChild();
    if(!message.empty())
    { ImGui::BeginChild("feedback",ImVec2(0,feedbackHeight),ImGuiChildFlags_None,ImGuiWindowFlags_NoBackground); ImGui::TextWrapped("%s",message.c_str()); ImGui::EndChild(); }
    const auto available = ImGui::GetContentRegionAvail().x, gap = 10.f*scale;
    if(!settings && !global)
    {
    const auto saveColor=Mix(accent,dark,.45f);
    PushColor(ImGuiCol_Button,saveColor); PushColor(ImGuiCol_Text,OnColor(saveColor));
    ImGui::BeginDisabled(pending || !helperReady || !ForgePanelChannel::settings.value("overlay_helper",true)
        || !ForgePanelChannel::status.value("can_save",true));
    ImGui::PushFont(bold ? bold : font, ImGui::GetFontSize());
    const bool saveClicked = ImGui::Button("Save preset",ImVec2((available-gap)*.66f,42.f*scale));
    ImGui::PopFont();
    if(saveClicked)
    {
        Flush(cfg, true);
        nlohmann::json changes = nlohmann::json::object();
        for(const auto& field : controls) if(Available(field))
        {
            auto n=field.get(cfg);
            // A value chosen in OptiScaler's own menu that rtxForge does not list stays out of the preset.
            if(field.kind == Kind::choice && std::none_of(field.choices,field.choices+field.count,[n](const Choice& c){ return c.value == n; })) continue;
            if(field.kind == Kind::slider) changes[field.key]=n; else changes[field.key]=int(n);
        }
        // Protocol 7 replays Dynamic; it lives in OptiScaler's config, not the control list.
        if(mfgAllowed) changes["dynamic_mfg"]=int(cfg.FGDLSSGOverrideForceDMFG.value_or_default());
        Send({{"op","save"},{"changes",changes}});
    }
    ImGui::PopStyleColor(2); ImGui::SameLine();
    PushColor(ImGuiCol_Button,Mix(Tone(1,0),dark,.10f));
    PushColor(ImGuiCol_Text,neutral);
    if(ImGui::Button("Reset",ImVec2(-1,42.f*scale)))
    { Send({{"op","reset"}}); }
    ImGui::PopStyleColor(2); ImGui::EndDisabled();
    }
    ImGui::TextDisabled("%s",(ShortcutLabel()+" - show or hide").c_str());
    if(ImGui::IsKeyPressed(ImGuiKey_Escape,false)) visible = false;
    ImGui::End(); ImGui::PopStyleColor(24); ImGui::PopStyleVar(13); ImGui::PopFont();
    cpuMs = std::chrono::duration<float,std::milli>(std::chrono::steady_clock::now()-start).count();
    return true;
}
}
