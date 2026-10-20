#pragma once
#include <Config.h>
#include <imgui/imgui.h>
#include <json.hpp>
#include <fstream>
#include <array>
#include <type_traits>
#include <cmath>
#include <chrono>
#include <cstring>

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
inline ImFont* font = nullptr;
inline bool selected = false, settings = false, advanced = false, nrAllowed = false, mfgAllowed = false;
inline int key = VK_END, modifiers = 0;
inline float animation = 0, cpuMs = 0;
inline ImVec4 accent(.82f, .82f, .82f, 1);
inline std::string title = "Game", feedback;
inline std::array<float, std::size(controls)> installed {};
inline DWORD Preference(const wchar_t* name, DWORD fallback)
{
    DWORD value = fallback, bytes = sizeof(value);
    RegGetValueW(HKEY_CURRENT_USER, L"Software\\rtxForge\\Overlay", name, RRF_RT_REG_DWORD, nullptr, &value, &bytes);
    return value;
}
inline void WritePreference(const wchar_t* name, DWORD value)
{
    HKEY target = nullptr;
    if (RegCreateKeyExW(HKEY_CURRENT_USER, L"Software\\rtxForge\\Overlay", 0, nullptr, 0, KEY_SET_VALUE, nullptr, &target, nullptr) == ERROR_SUCCESS)
    { RegSetValueExW(target, name, 0, REG_DWORD, reinterpret_cast<BYTE*>(&value), sizeof(value)); RegCloseKey(target); }
}
inline void Init(HWND window)
{
    ImFontConfig options; options.FontDataOwnedByAtlas = false;
    font = ImGui::GetIO().Fonts->AddFontFromMemoryTTF(forgeInter, sizeof(forgeInter), 18.f, &options);
    key = int(Preference(L"PanelKey", VK_END)); modifiers = int(Preference(L"PanelModifiers", 0));
    advanced = Preference(L"Advanced", 0) != 0;
    wchar_t caption[256] {}; GetWindowTextW(window, caption, 256);
    title = wstring_to_string(caption);
    try
    {
        const auto folder = std::filesystem::path(Config::Instance()->MainDllPath.value());
        const auto path = folder / ".rtxforge-install.json";
        if (std::filesystem::file_size(path) < 2 * 1024 * 1024)
        {
            std::ifstream input(path); const auto metadata = nlohmann::json::parse(input);
            const auto mode = metadata.value("feature_mode", std::string());
            nrAllowed = mode == "nr-mfg" || mode == "nr-only";
            mfgAllowed = mode == "nr-mfg" || mode == "mfg-only";
            if (metadata.contains("name")) title = metadata.value("name", title);
        }
    }
    catch (...) { nrAllowed = mfgAllowed = false; }
    // Identity is cached by the helper/manager before launch. Never load artwork
    // or walk a library from the game's render thread.
    wchar_t exe[32768] {}, identity[1024] {}; GetModuleFileNameW(nullptr, exe, 32768);
    DWORD bytes = sizeof(identity);
    if (RegGetValueW(HKEY_CURRENT_USER, L"Software\\rtxForge\\Overlay\\Games", exe, RRF_RT_REG_SZ,
                    nullptr, identity, &bytes) == ERROR_SUCCESS)
    {
        const auto text = wstring_to_string(identity);
        if(text.size() > 8 && text[0] == '#' && text[7] == '|')
        {
            try { const auto rgb = std::stoul(text.substr(1,6), nullptr, 16);
                accent = ImVec4(float((rgb >> 16) & 255)/255, float((rgb >> 8) & 255)/255, float(rgb & 255)/255, 1);
                title = text.substr(8); } catch (...) { }
        }
    }
    for(size_t i = 0; i < std::size(controls); ++i) installed[i] = controls[i].get(*Config::Instance());
}
inline bool ShortcutReleased()
{
    if (!OptiInput::IsFocused() || key <= 0 || key >= 256 || key == VK_INSERT || key == VK_F12) return false;
    const int held = (OptiInput::IsKeyDown(VK_MENU) ? 1 : 0) | (OptiInput::IsKeyDown(VK_CONTROL) ? 2 : 0) | (OptiInput::IsKeyDown(VK_SHIFT) ? 4 : 0);
    return OptiInput::IsKeyReleased(key) && held == modifiers;
}
inline bool Animating() { return selected && animation > 0; }
inline ImVec4 Mix(ImVec4 a, ImVec4 b, float amount)
{ return ImVec4(a.x*amount+b.x*(1-amount), a.y*amount+b.y*(1-amount), a.z*amount+b.z*(1-amount), 1); }
inline bool Available(const Control& field)
{
    if (std::strcmp(field.key,"multiplier") == 0) return mfgAllowed;
    return std::strcmp(field.group,"Sharpening") == 0 || std::strcmp(field.group,"Motion sharpening") == 0 || nrAllowed;
}
inline bool IconButton(const char* id, bool gear, float scale)
{
    const auto position = ImGui::GetCursorScreenPos();
    const bool pressed = ImGui::InvisibleButton(id,ImVec2(30.f*scale,30.f*scale));
    auto* draw = ImGui::GetWindowDrawList();
    const auto center = ImVec2(position.x+15.f*scale,position.y+15.f*scale);
    const auto ink = ImGui::GetColorU32(ImVec4(.77f,.77f,.77f,1));
    if(ImGui::IsItemHovered()) draw->AddRectFilled(position,ImVec2(position.x+30*scale,position.y+30*scale),ImGui::GetColorU32(ImVec4(1,1,1,.09f)),8*scale);
    if(gear)
    {
        draw->AddCircle(center,6*scale,ink,24,1.5f*scale); draw->AddCircle(center,2*scale,ink,16,1.5f*scale);
        for(int i=0;i<8;++i) { const float angle=i*3.14159265f/4;
            draw->AddLine(ImVec2(center.x+std::cos(angle)*6*scale,center.y+std::sin(angle)*6*scale),
                ImVec2(center.x+std::cos(angle)*9*scale,center.y+std::sin(angle)*9*scale),ink,1.5f*scale); }
    }
    else
    {
        draw->AddLine(ImVec2(center.x-5*scale,center.y-5*scale),ImVec2(center.x+5*scale,center.y+5*scale),ink,1.5f*scale);
        draw->AddLine(ImVec2(center.x+5*scale,center.y-5*scale),ImVec2(center.x-5*scale,center.y+5*scale),ink,1.5f*scale);
    }
    return pressed;
}
inline void Field(const Control& field, Config& cfg)
{
    ImGui::PushID(field.key);
    ImGui::BeginDisabled(!Available(field));
    auto value = field.get(cfg); bool changed = false;
    const auto label = advanced ? field.advanced : field.label;
    if (field.kind == Kind::toggle)
    { bool on = value != 0; changed = ImGui::Checkbox(label, &on); value = on ? 1.f : 0.f; }
    else
    {
        ImGui::TextUnformatted(label); ImGui::SetNextItemWidth(-1);
        if(field.kind == Kind::choice)
        {
            const char* preview = "Automatic";
            for(size_t i=0; i<field.count; ++i) if(field.choices[i].value == value) preview = field.choices[i].label;
            if(ImGui::BeginCombo("##value", preview))
            {
                for(size_t i=0; i<field.count; ++i)
                {
                    const auto& choice = field.choices[i];
                    const bool unavailable = std::strcmp(field.key,"multiplier") == 0 && choice.value > 0
                        && choice.value - 1 > State::Instance().dlssgMfgMax.value_or(0);
                    ImGui::BeginDisabled(unavailable);
                    if(ImGui::Selectable(choice.label, value == choice.value)) { value = choice.value; changed = true; }
                    ImGui::EndDisabled();
                }
                ImGui::EndCombo();
            }
        }
        else if(field.kind == Kind::number)
        { int n = int(value); changed = ImGui::SliderInt("##value", &n, int(field.low), int(field.high)); value = float(n); }
        else
        {
            const bool percent = !advanced || std::strcmp(field.key,"work_scale") == 0;
            const auto format = percent ? "%.0f%%" : "%.2f";
            auto shown = percent ? value * 100.f : value;
            changed = ImGui::SliderFloat("##value", &shown, percent ? field.low*100 : field.low, percent ? field.high*100 : field.high, format, ImGuiSliderFlags_AlwaysClamp);
            value = percent ? shown/100.f : shown;
            if(std::strcmp(field.key,"skin") == 0 && value < 0) ImGui::TextDisabled("-1 follows local structure");
        }
    }
    if(changed && std::isfinite(value)) field.set(cfg, std::clamp(value, field.low, field.high), false);
    ImGui::EndDisabled(); ImGui::PopID(); ImGui::Spacing();
}
inline bool Draw(bool& visible, float scale)
{
    if (!selected) return false;
    if (!OptiInput::IsFocused()) { visible = false; animation = 0; return false; }
    const auto start = std::chrono::steady_clock::now();
    const auto dt = std::min(ImGui::GetIO().DeltaTime, .05f);
    animation = std::clamp(animation + dt / (visible ? .16f : -.11f), 0.f, 1.f);
    if(animation <= 0) return false;
    const auto eased = 1 - std::pow(1-animation, 3.f), sizeScale = .97f + .03f*eased;
    const auto display = ImGui::GetIO().DisplaySize;
    const auto edge = 24.f*scale, width = std::min(420.f*scale, display.x-edge*2);
    const auto height = display.y-edge*2;
    // A few translucent rounded quads give a soft offset shadow. No texture,
    // backdrop sampling, render target or shader pass is allocated for it.
    auto* shadow = ImGui::GetBackgroundDrawList();
    for(int layer=6;layer>0;--layer)
    {
        const auto spread=float(layer)*2*scale;
        shadow->AddRectFilled(ImVec2(edge-spread,edge-spread+6*scale),
            ImVec2(edge+width*sizeScale+spread,edge+height*sizeScale+spread+6*scale),
            IM_COL32(0,0,0,int(5*eased)),(20*scale)+spread);
    }
    ImGui::SetNextWindowPos(ImVec2(edge,edge + height*(1-sizeScale)*.5f), ImGuiCond_Always);
    ImGui::SetNextWindowSize(ImVec2(width*sizeScale,height*sizeScale), ImGuiCond_Always);
    ImGui::PushFont(font, 15.f*scale);
    ImGui::PushStyleVar(ImGuiStyleVar_Alpha,eased);
    ImGui::PushStyleVar(ImGuiStyleVar_WindowRounding,20.f*scale);
    ImGui::PushStyleVar(ImGuiStyleVar_WindowPadding,ImVec2(26.f*scale,22.f*scale));
    ImGui::PushStyleVar(ImGuiStyleVar_FrameRounding,8.f*scale);
    ImGui::PushStyleVar(ImGuiStyleVar_FramePadding,ImVec2(10.f*scale,9.f*scale));
    ImGui::PushStyleVar(ImGuiStyleVar_ItemSpacing,ImVec2(10.f*scale,12.f*scale));
    ImGui::PushStyleVar(ImGuiStyleVar_WindowBorderSize,0);
    const ImVec4 neutral(.91f,.91f,.91f,1), dark(.12f,.12f,.12f,1);
    ImGui::PushStyleColor(ImGuiCol_WindowBg,ImVec4(.045f,.045f,.045f,.94f));
    ImGui::PushStyleColor(ImGuiCol_Text,neutral);
    ImGui::PushStyleColor(ImGuiCol_Button,Mix(accent,dark,.20f));
    ImGui::PushStyleColor(ImGuiCol_ButtonHovered,Mix(accent,dark,.32f));
    ImGui::PushStyleColor(ImGuiCol_ButtonActive,Mix(accent,dark,.15f));
    ImGui::PushStyleColor(ImGuiCol_FrameBg,ImVec4(.16f,.16f,.16f,.8f));
    ImGui::PushStyleColor(ImGuiCol_CheckMark,Mix(accent,neutral,.45f));
    ImGui::PushStyleColor(ImGuiCol_SliderGrab,Mix(accent,neutral,.45f));
    ImGui::PushStyleColor(ImGuiCol_Header,Mix(accent,dark,.18f));
    ImGui::PushStyleColor(ImGuiCol_HeaderHovered,Mix(accent,dark,.26f));
    ImGui::Begin("rtxForge##ingame",nullptr,ImGuiWindowFlags_NoDecoration|ImGuiWindowFlags_NoMove|ImGuiWindowFlags_NoSavedSettings|ImGuiWindowFlags_NoScrollWithMouse|ImGuiWindowFlags_NoScrollbar);
    ImGui::TextUnformatted("rtxForge"); ImGui::SameLine(ImGui::GetWindowContentRegionMax().x-68.f*scale);
    if(IconButton("Overlay settings",true,scale)) settings = !settings;
    ImGui::SameLine(); if(IconButton("Close panel",false,scale)) visible = false;
    ImGui::PushFontSize(24.f*scale); ImGui::PushStyleColor(ImGuiCol_Text,Mix(accent,neutral,.8f));
    ImGui::TextWrapped("%s",title.c_str()); ImGui::PopStyleColor(); ImGui::PopFontSize();
    ImGui::TextDisabled("NR + MFG controls"); ImGui::Spacing();
    const auto footer = 96.f*scale;
    ImGui::BeginChild("controls",ImVec2(0,-footer),ImGuiChildFlags_None,ImGuiWindowFlags_NoBackground);
    auto& cfg = *Config::Instance();
    if(settings)
    {
        ImGui::SeparatorText("Overlay settings");
        if(ImGui::Checkbox("Advanced controls", &advanced)) WritePreference(L"Advanced",advanced);
        ImGui::TextWrapped("Advanced keeps OptiScaler's original units. Insert opens the original menu when enabled.");
        ImGui::Text("Panel CPU submit: %.3f ms",cpuMs);
        ImGui::TextWrapped("No extra rendering pass while closed. Acrylic blur is not used inside the game.");
    }
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
                if(primary) { ImGui::SeparatorText(group); open = true; }
                else open = ImGui::CollapsingHeader(group);
            }
            if(open) Field(field,cfg);
        }
    }
    ImGui::EndChild();
    if(!feedback.empty()) ImGui::TextWrapped("%s",feedback.c_str());
    const auto available = ImGui::GetContentRegionAvail().x, gap = 10.f*scale;
    ImGui::PushStyleColor(ImGuiCol_Button,Mix(accent,dark,.45f));
    if(ImGui::Button("Save preset",ImVec2((available-gap)*.66f,42.f*scale)))
    {
        for(const auto& field : controls) if(Available(field)) field.set(cfg,field.get(cfg),true);
        feedback = cfg.SaveIni() ? "Preset saved for this game" : "Could not save. Check folder access.";
    }
    ImGui::PopStyleColor(); ImGui::SameLine();
    ImGui::PushStyleColor(ImGuiCol_Button,ImVec4(.55f,.15f,.18f,1));
    if(ImGui::Button("Reset",ImVec2(-1,42.f*scale)))
    { for(size_t i=0; i<std::size(controls); ++i) if(Available(controls[i])) controls[i].set(cfg,installed[i],false); feedback = "Restored this session's starting settings"; }
    ImGui::PopStyleColor(); ImGui::TextDisabled("End / your custom shortcut to close");
    if(ImGui::IsKeyPressed(ImGuiKey_Escape,false)) visible = false;
    ImGui::End(); ImGui::PopStyleColor(10); ImGui::PopStyleVar(7); ImGui::PopFont();
    cpuMs = std::chrono::duration<float,std::milli>(std::chrono::steady_clock::now()-start).count();
    return true;
}
}
