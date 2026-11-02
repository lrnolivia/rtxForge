// Hides ReShade's startup banner in Feeder NR games unless rtxForge's ReShade
// welcome option is on ([rtxForge.UI] QuietStartup=0). Its own add-on because
// it draws with ReShade's Dear ImGui, which the panel add-on must not share.
#include <windows.h>
#define ImTextureID ImU64
#include "imgui.h"
#include "reshade.hpp"

extern "C" __declspec(dllexport) const char *NAME = "rtxForge quiet startup";
extern "C" __declspec(dllexport) const char *DESCRIPTION = "Hides ReShade's startup banner; the ReShade menu and its shortcut are unchanged.";

namespace
{
bool quiet = true, read = false;

void on_overlay(reshade::api::effect_runtime *)
{
    if (!read)
    {
        char text[8] = "";
        size_t size = sizeof(text);
        quiet = !(reshade::get_config_value(nullptr, "rtxForge.UI", "QuietStartup", text, &size) && text[0] == '0');
        read = true;
    }
    // RenoDX 8.5 rc10 uses this window for its transient status card. When
    // the glass renderer owns notifications, suppress that duplicate card.
    // Its separate ##issue_notice diagnostic window is deliberately untouched.
    const auto glass=GetModuleHandleW(L"rtxforge-glass.dll");
    const auto ownsNotifications=glass?reinterpret_cast<bool (__cdecl*)()>(GetProcAddress(glass,"ForgeGlassNotificationsActive")):nullptr;
    if (ownsNotifications && ownsNotifications())
    {
        ImGui::Begin("##nr_status_card", nullptr, ImGuiWindowFlags_NoDecoration | ImGuiWindowFlags_NoNav | ImGuiWindowFlags_NoMove |
            ImGuiWindowFlags_NoInputs | ImGuiWindowFlags_NoSavedSettings);
        ImDrawList *status = ImGui::GetWindowDrawList();
        for (int i = 0; i < status->CmdBuffer.Size; ++i) status->CmdBuffer[i].ElemCount = 0;
        ImGui::End();
    }
    if (!quiet) return;
    // ReShade creates this window before the add-on overlay event.
    ImGui::Begin("Splash Window", nullptr, ImGuiWindowFlags_NoDecoration | ImGuiWindowFlags_NoNav | ImGuiWindowFlags_NoMove |
        ImGuiWindowFlags_NoInputs | ImGuiWindowFlags_NoSavedSettings);
    ImDrawList *draw = ImGui::GetWindowDrawList();
    for (int i = 0; i < draw->CmdBuffer.Size; ++i) draw->CmdBuffer[i].ElemCount = 0;
    ImGui::End();
}
}

BOOL APIENTRY DllMain(HMODULE module, DWORD reason, LPVOID)
{
    if (reason == DLL_PROCESS_ATTACH)
    {
        DisableThreadLibraryCalls(module);
        if (!reshade::register_addon(module)) return FALSE;
        reshade::register_event<reshade::addon_event::reshade_overlay>(on_overlay);
    }
    else if (reason == DLL_PROCESS_DETACH)
    {
        reshade::unregister_event<reshade::addon_event::reshade_overlay>(on_overlay);
        reshade::unregister_addon(module);
    }
    return TRUE;
}
