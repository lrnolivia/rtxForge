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
