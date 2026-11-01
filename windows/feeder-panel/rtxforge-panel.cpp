// rtxForge panel for Feeder NR games, as a ReShade add-on.
//
// RenoDX DLSS5 reads [RenoDX.DLSS5] from ReShade.ini once, when it loads, and
// keeps its live state in memory. Its NR toggle key is the only live control,
// and RenoDX writes NeuralUplift back to ReShade.ini when it toggles. So
// Neural rendering is live here (the panel presses RenoDX's own toggle key),
// and tuning is saved to the same keys rtxForge's Presets page writes, for
// RenoDX to load on the next launch.
//
// This file includes ReShade's headers but not Dear ImGui: the panel keeps
// its own ImGui context (panel.cpp), separate from ReShade's.
#include "Config.h"
#include "reshade.hpp"
#include "EffectBridge.h"
#include "panel.h"
#include <cmath>
#include <cstdio>
#include <cstdlib>

#ifdef RTXFORGE_STANDALONE_RESHADE
extern "C" __declspec(dllexport) const char *NAME = "rtxForge ReShade controls";
#else
extern "C" __declspec(dllexport) const char *NAME = "rtxForge Overlay";
#endif
extern "C" __declspec(dllexport) const char *DESCRIPTION = "The rtxForge Overlay.";

namespace
{
constexpr const char *Section = "RenoDX.DLSS5";
reshade::api::effect_runtime *current = nullptr;
HWND current_window = nullptr;
reshade::api::swapchain *current_swapchain = nullptr;
reshade::api::color_space space = reshade::api::color_space::srgb_nonlinear;
ULONGLONG toggle_sent = 0;

float get(const char *key, float fallback)
{
    char text[64] = "";
    size_t size = sizeof(text);
    if (!reshade::get_config_value(nullptr, Section, key, text, &size) || !text[0]) return fallback;
    char *end = nullptr;
    const float value = std::strtof(text, &end);
    return end != text && std::isfinite(value) ? value : fallback;
}

void set(const char *key, float value, bool integer)
{
    char text[32];
    if (integer) std::snprintf(text, sizeof(text), "%ld", std::lround(value));
    else std::snprintf(text, sizeof(text), "%.2f", value);
    reshade::set_config_value(nullptr, Section, key, static_cast<const char *>(text));
}

WORD toggle_key = 0;

void send_key(WORD key, bool up)
{
    INPUT input = {};
    input.type = INPUT_KEYBOARD;
    input.ki.wVk = key;
    input.ki.wScan = static_cast<WORD>(MapVirtualKeyW(key, MAPVK_VK_TO_VSC));
    input.ki.dwFlags = up ? KEYEVENTF_KEYUP : 0;
    SendInput(1, &input, sizeof(INPUT));
}

// RenoDX listens for its own toggle key in gameplay; press it for the player.
// The key is held for a few frames, as a person would, so ReShade sees the press.
void toggle_nr()
{
    toggle_key = static_cast<WORD>(get("NRToggleKey", VK_F6));
    send_key(toggle_key, false);
    toggle_sent = GetTickCount64();
}

void release_toggle()
{
    if (toggle_key && GetTickCount64() - toggle_sent > 120)
    {
        send_key(toggle_key, true);
        toggle_key = 0;
    }
}

const feeder_panel::Host host = {
    [] { return current_window && GetForegroundWindow() == current_window; },
    [](int vk) { return current && current->is_key_down(vk); },
    [](int vk) { return current && current->is_key_pressed(vk); },
    [](int vk) { return current && current->is_key_released(vk); },
    [] { return current ? int(current->last_key_pressed()) : 0; },
    get, set, toggle_nr,
    [](const char *text) { reshade::log::message(reshade::log::level::info, text); },
};

void on_init(reshade::api::effect_runtime *runtime)
{
    ForgeReShade::Attach(runtime);
#ifdef RTXFORGE_STANDALONE_RESHADE
    // Provider hosts already own presentation and input. Keep reflection active
    // while letting their existing overlay render it exactly once.
    if (GetModuleHandleW(L"rtxforge-panel.addon64")) return;
    wchar_t executable[32768]{};
    if (GetModuleFileNameW(nullptr,executable,std::size(executable)) &&
        std::filesystem::exists(std::filesystem::path(executable).parent_path()/L"OptiScaler.ini")) return;
#endif
    if (runtime->get_device()->get_api() != reshade::api::device_api::d3d11) return;
    current = runtime;
    current_window = static_cast<HWND>(runtime->get_hwnd());
    current_swapchain = nullptr;
    feeder_panel::Init(reinterpret_cast<ID3D11Device *>(runtime->get_device()->get_native()), current_window,
#ifdef RTXFORGE_STANDALONE_RESHADE
        false
#else
        true
#endif
    );
}

void on_destroy(reshade::api::effect_runtime *runtime)
{
    ForgeReShade::Detach(runtime);
    if (runtime != current) return;
    feeder_panel::Release();
    current = nullptr;
    current_window = nullptr;current_swapchain = nullptr;
}

// HDR games present PQ or scRGB; the panel encodes its colours to match.
void on_present(reshade::api::command_queue *, reshade::api::swapchain *swapchain, const reshade::api::rect *, const reshade::api::rect *, uint32_t, const reshade::api::rect *)
{
    if(!current)return;
    if(!current_swapchain && swapchain->get_hwnd()==current_window)current_swapchain=swapchain;
    if(swapchain==current_swapchain)space=swapchain->get_color_space();
}

void on_finish_effects(reshade::api::effect_runtime *runtime, reshade::api::command_list *, reshade::api::resource_view target, reshade::api::resource_view)
{
    ForgeReShade::Update(runtime);
    if (runtime != current) return;
    release_toggle();
    uint32_t width = 0, height = 0, x = 0, y = 0;
    int16_t wheel = 0;
    runtime->get_screenshot_width_and_height(&width, &height);
    runtime->get_mouse_cursor_position(&x, &y, &wheel);
    RECT client {};
    // The runtime HWND query may enter DXGI and synchronously wait for the
    // window thread during fullscreen transitions. Keep the HWND obtained at
    // initialization instead of querying it from the render callback.
    GetClientRect(current_window, &client);
    const float sx = client.right > 0 ? float(width) / float(client.right) : 1.0f;
    const float sy = client.bottom > 0 ? float(height) / float(client.bottom) : 1.0f;
    feeder_panel::Frame frame {
        reinterpret_cast<ID3D11RenderTargetView *>(target.handle), float(width), float(height), x * sx, y * sy, wheel / 120.0f,
        {runtime->is_mouse_button_down(0), runtime->is_mouse_button_down(1), runtime->is_mouse_button_down(2)},
        space == reshade::api::color_space::extended_srgb_linear ? feeder_panel::Output::scrgb
            : space == reshade::api::color_space::hdr10_st2084 ? feeder_panel::Output::hdr10 : feeder_panel::Output::sdr};
    // RenoDX doesn't see its toggle key while game input is blocked, so let the
    // press through for a moment after the panel sends it.
    if (feeder_panel::Draw(frame) && GetTickCount64() - toggle_sent > 400) runtime->block_input_next_frame();
}
}

BOOL APIENTRY DllMain(HMODULE module, DWORD reason, LPVOID)
{
    if (reason == DLL_PROCESS_ATTACH)
    {
        DisableThreadLibraryCalls(module);
        if (!reshade::register_addon(module)) return FALSE;
        GetModuleFileNameW(module, feeder_panel::module_path, MAX_PATH);
        feeder_panel::host = host;
        reshade::register_event<reshade::addon_event::init_effect_runtime>(on_init);
        reshade::register_event<reshade::addon_event::destroy_effect_runtime>(on_destroy);
        reshade::register_event<reshade::addon_event::reshade_finish_effects>(on_finish_effects);
        reshade::register_event<reshade::addon_event::present>(on_present);
        reshade::register_event<reshade::addon_event::reshade_reloaded_effects>(ForgeReShade::Reload);
    }
    else if (reason == DLL_PROCESS_DETACH)
    {
        reshade::unregister_event<reshade::addon_event::reshade_reloaded_effects>(ForgeReShade::Reload);
        reshade::unregister_event<reshade::addon_event::present>(on_present);
        reshade::unregister_event<reshade::addon_event::reshade_finish_effects>(on_finish_effects);
        reshade::unregister_event<reshade::addon_event::destroy_effect_runtime>(on_destroy);
        reshade::unregister_event<reshade::addon_event::init_effect_runtime>(on_init);
        reshade::unregister_addon(module);
    }
    return TRUE;
}
