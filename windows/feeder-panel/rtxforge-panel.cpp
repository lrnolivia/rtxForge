// rtxForge panel for Feeder NR games, as a ReShade add-on.
//
// RenoDX DLSS5 reads [RenoDX.DLSS5] from ReShade.ini once, when it loads, and
// keeps its live state in memory. Its NR toggle key is the only live control,
// and RenoDX writes NeuralUplift back to ReShade.ini when it toggles. So NR
// on/off is live here (the panel presses RenoDX's own toggle key), and the
// tuning below is saved to the same keys rtxForge's Presets page writes, for
// RenoDX to load on the next launch.
#include <windows.h>
#define ImTextureID ImU64
#include "imgui.h"
#include "reshade.hpp"
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>

extern "C" __declspec(dllexport) const char *NAME = "rtxForge panel";
extern "C" __declspec(dllexport) const char *DESCRIPTION = "rtxForge's in-game panel for Feeder NR. Also hides ReShade's startup banner.";

namespace
{
constexpr const char *Section = "RenoDX.DLSS5";
constexpr const char *Ui = "rtxForge.UI";

enum Kind { Strength, Passes, Resolution, Preset };

struct Tuning
{
    Kind kind;
    const char *key, *label;
    float min, max, fallback;
    bool integer;
    float launch = 0, wanted = 0;
    bool owned = false; // set by this panel this session; re-saved if RenoDX writes its loaded value back
};

Tuning tunings[] = {
    {Strength, "NRIntensity", "Model strength", 0.0f, 2.0f, 1.0f, false},
    {Passes, "NRPasses", "Model passes", 1.0f, 4.0f, 1.0f, true},
    {Resolution, "NRResolutionScale", "Model resolution", 0.25f, 1.0f, 0.65f, false},
    {Preset, "NRPreset", "Model preset", 0.0f, 3.0f, 0.0f, true},
};
const char *const presets[] = {"Automatic", "Preset 1", "Preset 2", "Preset 3"};
const char *const passes[] = {"1 pass", "2 passes", "3 passes", "4 passes"};

bool open = false, quiet = true, enabled_in_game = true, captured = false;
UINT panel_key = VK_OEM_3, panel_mods = 0;
ImU32 accent = IM_COL32(118, 185, 0, 255);
char title[160] = "rtxForge";
ULONGLONG toggle_sent = 0, last_check = 0;
int toggle_from = -1;
char notice[160] = "";

float config_float(const char *key, float fallback)
{
    char text[64] = "";
    size_t size = sizeof(text);
    if (!reshade::get_config_value(nullptr, Section, key, text, &size) || !text[0])
        return fallback;
    char *end = nullptr;
    const float value = std::strtof(text, &end);
    return end != text && std::isfinite(value) ? value : fallback;
}

void save(Tuning &item, float value)
{
    char text[32];
    if (item.integer) std::snprintf(text, sizeof(text), "%d", static_cast<int>(std::lround(value)));
    else std::snprintf(text, sizeof(text), "%.2f", value);
    reshade::set_config_value(nullptr, Section, item.key, static_cast<const char *>(text));
}

int neural_uplift()
{
    return config_float("NeuralUplift", 0) != 0 ? 1 : 0;
}

DWORD registry_dword(HKEY key, const char *name, DWORD fallback)
{
    DWORD value = 0, size = sizeof(value), type = 0;
    return RegQueryValueExA(key, name, nullptr, &type, reinterpret_cast<BYTE *>(&value), &size) == ERROR_SUCCESS && type == REG_DWORD ? value : fallback;
}

// The rtxForge app publishes the panel shortcut and each game's accent and name.
void load_preferences()
{
    HKEY key;
    if (RegOpenKeyExA(HKEY_CURRENT_USER, "Software\\rtxForge\\Overlay", 0, KEY_READ, &key) == ERROR_SUCCESS)
    {
        panel_key = registry_dword(key, "PanelKey", VK_OEM_3);
        panel_mods = registry_dword(key, "PanelModifiers", 0);
        enabled_in_game = registry_dword(key, "InGamePanel", 1) != 0;
        RegCloseKey(key);
    }
    wchar_t exe[MAX_PATH] = L"";
    if (!GetModuleFileNameW(nullptr, exe, MAX_PATH)) return;
    wchar_t value[256] = L"";
    DWORD size = sizeof(value);
    if (RegGetValueW(HKEY_CURRENT_USER, L"Software\\rtxForge\\Overlay\\Games", exe, RRF_RT_REG_SZ, nullptr, value, &size) != ERROR_SUCCESS) return;
    unsigned r, g, b;
    if (swscanf_s(value, L"#%02x%02x%02x", &r, &g, &b) == 3) accent = IM_COL32(r, g, b, 255);
    if (const wchar_t *name = wcschr(value, L'|'))
    {
        // ReShade's font has no trademark glyphs.
        wchar_t plain[128] = L"";
        size_t length = 0;
        for (const wchar_t *c = name + 1; *c && length + 1 < 128; ++c)
            if (*c != L'™' && *c != L'®' && *c != L'©') plain[length++] = *c;
        char utf8[128] = "";
        WideCharToMultiByte(CP_UTF8, 0, plain, -1, utf8, sizeof(utf8), nullptr, nullptr);
        std::snprintf(title, sizeof(title), "%s", utf8);
    }
}

bool shortcut_pressed(reshade::api::effect_runtime *runtime)
{
    if (!panel_key || !runtime->is_key_pressed(panel_key)) return false;
    const bool ctrl = runtime->is_key_down(VK_CONTROL), shift = runtime->is_key_down(VK_SHIFT), alt = runtime->is_key_down(VK_MENU);
    return ctrl == ((panel_mods & MOD_CONTROL) != 0) && shift == ((panel_mods & MOD_SHIFT) != 0) && alt == ((panel_mods & MOD_ALT) != 0);
}

// RenoDX listens for its own toggle key in gameplay; press it for the player.
void press_toggle()
{
    const WORD key = static_cast<WORD>(config_float("NRToggleKey", VK_F6));
    INPUT input[2] = {};
    input[0].type = input[1].type = INPUT_KEYBOARD;
    input[0].ki.wVk = input[1].ki.wVk = key;
    input[1].ki.dwFlags = KEYEVENTF_KEYUP;
    SendInput(2, input, sizeof(INPUT));
    toggle_from = neural_uplift();
    toggle_sent = GetTickCount64();
    notice[0] = '\0';
}

void capture_launch_values()
{
    for (Tuning &item : tunings)
        item.launch = item.wanted = config_float(item.key, item.fallback);
    char text[8] = "";
    size_t size = sizeof(text);
    quiet = !(reshade::get_config_value(nullptr, Ui, "QuietStartup", text, &size) && text[0] == '0');
    captured = true;
}

// RenoDX saves its loaded values when the player changes something in its own
// window. Keep this panel's next-launch choice unless the player picked another.
void keep_choices()
{
    const ULONGLONG now = GetTickCount64();
    if (now - last_check < 1000) return;
    last_check = now;
    for (Tuning &item : tunings)
    {
        if (!item.owned) continue;
        const float saved = config_float(item.key, item.fallback);
        if (std::fabs(saved - item.wanted) < 0.001f) continue;
        if (std::fabs(saved - item.launch) < 0.001f) save(item, item.wanted);
        else { item.wanted = saved; item.owned = false; }
    }
}

void hide_splash()
{
    // ReShade creates this window before the add-on overlay event.
    ImGui::Begin("Splash Window", nullptr, ImGuiWindowFlags_NoDecoration | ImGuiWindowFlags_NoNav | ImGuiWindowFlags_NoMove |
        ImGuiWindowFlags_NoInputs | ImGuiWindowFlags_NoSavedSettings);
    ImDrawList *draw = ImGui::GetWindowDrawList();
    for (int i = 0; i < draw->CmdBuffer.Size; ++i) draw->CmdBuffer[i].ElemCount = 0;
    ImGui::End();
}

void caption(const char *text)
{
    ImGui::PushStyleColor(ImGuiCol_Text, IM_COL32(200, 205, 214, 255));
    ImGui::TextUnformatted(text);
    ImGui::PopStyleColor();
}

void hint(const char *text)
{
    ImGui::PushStyleColor(ImGuiCol_Text, IM_COL32(150, 156, 168, 255));
    ImGui::PushTextWrapPos(0.0f);
    ImGui::TextUnformatted(text);
    ImGui::PopTextWrapPos();
    ImGui::PopStyleColor();
}

void draw_neural_rendering()
{
    const int state = neural_uplift();
    const ULONGLONG now = GetTickCount64();
    const bool waiting = toggle_sent && state == toggle_from && now - toggle_sent < 2000;
    if (toggle_sent && !waiting)
    {
        if (state == toggle_from) std::snprintf(notice, sizeof(notice), "RenoDX didn't respond. Try again in gameplay.");
        toggle_sent = 0;
    }
    caption("Neural rendering");
    bool on = state != 0;
    if (waiting) ImGui::BeginDisabled();
    if (ImGui::Checkbox(waiting ? "Switching..." : on ? "On" : "Off", &on)) press_toggle();
    if (waiting) ImGui::EndDisabled();
    ImGui::SameLine();
    hint("Live");
    if (notice[0]) hint(notice);
}

void draw_tuning(Tuning &item)
{
    float value = item.wanted;
    bool changed = false;
    ImGui::PushID(item.key);
    caption(item.label);
    ImGui::SetNextItemWidth(-1.0f);
    if (item.kind == Passes || item.kind == Preset)
    {
        const char *const *names = item.kind == Passes ? passes : presets;
        int index = static_cast<int>(std::lround(value - item.min));
        if (ImGui::Combo("##value", &index, names, 4)) { value = item.min + index; changed = true; }
    }
    else if (item.kind == Resolution)
    {
        float percent = value * 100.0f;
        if (ImGui::SliderFloat("##value", &percent, 25.0f, 100.0f, "%.0f%%", ImGuiSliderFlags_AlwaysClamp)) { value = std::round(percent) / 100.0f; changed = true; }
    }
    else if (ImGui::SliderFloat("##value", &value, item.min, item.max, "%.2f", ImGuiSliderFlags_AlwaysClamp)) changed = true;
    if (changed)
    {
        item.wanted = value;
        item.owned = true;
        save(item, value);
    }
    if (std::fabs(item.wanted - item.launch) >= 0.001f)
    {
        char text[64];
        const int now = static_cast<int>(std::lround(item.launch - item.min));
        if (item.integer) std::snprintf(text, sizeof(text), "Next launch. Now %s.", now < 0 || now > 3 ? "custom" : item.kind == Passes ? passes[now] : presets[now]);
        else if (item.kind == Resolution) std::snprintf(text, sizeof(text), "Next launch. Now %.0f%%.", item.launch * 100.0f);
        else std::snprintf(text, sizeof(text), "Next launch. Now %.2f.", item.launch);
        hint(text);
    }
    ImGui::PopID();
}

void draw_panel(reshade::api::effect_runtime *runtime)
{
    // RenoDX doesn't see its toggle key while game input is blocked, so let
    // the key press through for a moment after the panel sends it.
    if (!toggle_sent || GetTickCount64() - toggle_sent > 250) runtime->block_input_next_frame();
    ImGuiIO &io = ImGui::GetIO();
    io.MouseDrawCursor = true;
    const float scale = io.DisplaySize.y > 0 ? io.DisplaySize.y / 1080.0f : 1.0f;
    ImGui::SetNextWindowPos(ImVec2(32.0f * scale, 32.0f * scale), ImGuiCond_FirstUseEver, ImVec2(0, 0));
    ImGui::SetNextWindowSize(ImVec2(380.0f * scale, 0.0f), ImGuiCond_Always);
    ImGui::PushStyleVar(ImGuiStyleVar_WindowRounding, 14.0f * scale);
    ImGui::PushStyleVar(ImGuiStyleVar_FrameRounding, 8.0f * scale);
    ImGui::PushStyleVar(ImGuiStyleVar_GrabRounding, 8.0f * scale);
    ImGui::PushStyleVar(ImGuiStyleVar_WindowPadding, ImVec2(18.0f * scale, 16.0f * scale));
    ImGui::PushStyleVar(ImGuiStyleVar_ItemSpacing, ImVec2(10.0f * scale, 8.0f * scale));
    ImGui::PushStyleColor(ImGuiCol_WindowBg, IM_COL32(18, 20, 24, 236));
    ImGui::PushStyleColor(ImGuiCol_Border, (accent & 0x00FFFFFF) | 0x99000000);
    ImGui::PushStyleColor(ImGuiCol_FrameBg, IM_COL32(40, 44, 52, 255));
    ImGui::PushStyleColor(ImGuiCol_FrameBgHovered, IM_COL32(52, 57, 67, 255));
    ImGui::PushStyleColor(ImGuiCol_FrameBgActive, IM_COL32(60, 66, 78, 255));
    ImGui::PushStyleColor(ImGuiCol_CheckMark, accent);
    ImGui::PushStyleColor(ImGuiCol_SliderGrab, accent);
    ImGui::PushStyleColor(ImGuiCol_SliderGrabActive, accent);
    ImGui::PushStyleColor(ImGuiCol_Header, (accent & 0x00FFFFFF) | 0x66000000);
    ImGui::PushStyleColor(ImGuiCol_HeaderHovered, (accent & 0x00FFFFFF) | 0x99000000);
    ImGui::PushStyleColor(ImGuiCol_Separator, IM_COL32(255, 255, 255, 28));
    ImGui::PushStyleColor(ImGuiCol_Button, IM_COL32(52, 57, 67, 255));
    ImGui::PushStyleColor(ImGuiCol_ButtonHovered, (accent & 0x00FFFFFF) | 0x99000000);
    ImGui::PushStyleColor(ImGuiCol_ButtonActive, accent);
    if (ImGui::Begin("rtxForge##feeder-panel", nullptr, ImGuiWindowFlags_NoTitleBar | ImGuiWindowFlags_NoCollapse |
        ImGuiWindowFlags_AlwaysAutoResize | ImGuiWindowFlags_NoSavedSettings))
    {
        ImGui::GetWindowDrawList()->AddRectFilled(ImGui::GetWindowPos(), ImVec2(ImGui::GetWindowPos().x + ImGui::GetWindowWidth(), ImGui::GetWindowPos().y + 4.0f * scale), accent, 14.0f * scale, ImDrawFlags_RoundCornersTop);
        ImGui::TextUnformatted(title);
        hint("Feeder NR");
        ImGui::Separator();
        draw_neural_rendering();
        ImGui::Separator();
        caption("Tuning");
        hint("Saved to ReShade.ini, the same settings as rtxForge Presets. RenoDX loads them the next time the game starts.");
        for (Tuning &item : tunings) draw_tuning(item);
        bool pending = false;
        for (const Tuning &item : tunings) pending |= std::fabs(item.wanted - item.launch) >= 0.001f;
        if (pending && ImGui::Button("Keep current values"))
            for (Tuning &item : tunings) { item.wanted = item.launch; item.owned = true; save(item, item.launch); }
        ImGui::Separator();
        hint("Close with the panel shortcut or Esc.");
    }
    ImGui::End();
    ImGui::PopStyleColor(14);
    ImGui::PopStyleVar(5);
    if (runtime->is_key_pressed(VK_ESCAPE)) open = false;
}

void on_overlay(reshade::api::effect_runtime *runtime)
{
    if (!captured) capture_launch_values();
    if (quiet) hide_splash();
    keep_choices();
    if (enabled_in_game && shortcut_pressed(runtime)) open = !open;
    if (open) draw_panel(runtime);
}
}

BOOL APIENTRY DllMain(HMODULE module, DWORD reason, LPVOID)
{
    if (reason == DLL_PROCESS_ATTACH)
    {
        DisableThreadLibraryCalls(module);
        if (!reshade::register_addon(module)) return FALSE;
        load_preferences();
        reshade::register_event<reshade::addon_event::reshade_overlay>(on_overlay);
    }
    else if (reason == DLL_PROCESS_DETACH)
    {
        reshade::unregister_event<reshade::addon_event::reshade_overlay>(on_overlay);
        reshade::unregister_addon(module);
    }
    return TRUE;
}
