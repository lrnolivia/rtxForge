#include "menu.h"
#include "state.h"
#include "color.h"
#include "config.h"
#include "profile.h"
#include "bridge.h"
#include "component.h"
#include "log.h"
#include "imgui.h"
#include "imgui_impl_win32.h"
#include <windows.h>
#include <atomic>
#include <mutex>
#include <vector>
#include <string>

extern IMGUI_IMPL_API LRESULT ImGui_ImplWin32_WndProcHandler(HWND, UINT, WPARAM, LPARAM);
namespace fgvk {
namespace {
std::atomic<bool> opened{false}, available{false};
panel::Request request;
std::atomic<int> frameRequest{0};
panel::Meter meter;
bool active = false, hdr10 = false;
uint32_t maximum = 0, status = 0;
HWND game = nullptr;
WNDPROC original = nullptr;
std::mutex inputMutex, errorMutex;
std::string lastError;
struct Message { UINT id; WPARAM w; LPARAM l; };
std::vector<Message> messages;

double Seconds() {
    LARGE_INTEGER frequency{}, now{};
    QueryPerformanceFrequency(&frequency); QueryPerformanceCounter(&now);
    return double(now.QuadPart) / double(frequency.QuadPart);
}
LRESULT CALLBACK WindowProc(HWND window, UINT message, WPARAM w, LPARAM l) {
    if (message == WM_KILLFOCUS) opened = false;
    if (message == WM_KEYDOWN && w == VK_DELETE && !(l & (1ll << 30)) && available) {
        opened = !opened; return 0;
    }
    if (message == WM_KEYUP && w == VK_DELETE) return 0;
    if (opened && message == WM_KEYDOWN && w == VK_ESCAPE) { opened = false; return 0; }
    const bool input = message == WM_MOUSEMOVE || (message >= WM_LBUTTONDOWN && message <= WM_MOUSEHWHEEL)
        || message == WM_KEYDOWN || message == WM_KEYUP || message == WM_CHAR
        || message == WM_SYSKEYDOWN || message == WM_SYSKEYUP;
    if (opened && input) {
        std::lock_guard<std::mutex> guard(inputMutex);
        if (message == WM_MOUSEMOVE && !messages.empty() && messages.back().id == WM_MOUSEMOVE)
            messages.back() = {message, w, l};
        else if (messages.size() < 256) messages.push_back({message, w, l});
        return 0;
    }
    if (opened && message == WM_INPUT) { DefWindowProcW(window, message, w, l); return 0; }
    return CallWindowProcW(original, window, message, w, l);
}
BOOL CALLBACK FindWindow(HWND window, LPARAM out) {
    DWORD pid{}; GetWindowThreadProcessId(window, &pid);
    if (pid != GetCurrentProcessId() || !IsWindowVisible(window) || GetWindow(window, GW_OWNER)) return TRUE;
    RECT size{}, previous{}; GetClientRect(window, &size);
    auto& best = *reinterpret_cast<HWND*>(out);
    if (best) GetClientRect(best, &previous);
    if (size.right >= 640 && size.bottom >= 360 && int64_t(size.right)*size.bottom > int64_t(previous.right)*previous.bottom)
        best = window;
    return TRUE;
}
}

void MenuError(const char* value) { std::lock_guard<std::mutex> guard(errorMutex); lastError = value; }
void MenuRendererAvailable(bool value) { available = value; if (!value) opened = false; }
bool MenuApplyRequest() {
    bool off{};
    bool changed = request.Consume(off);
    if (changed) { Rt().fgUserOff = off; Log("panel: FG requested %s", off ? "OFF" : "ON"); }
    const int frames = frameRequest.exchange(0);
    if (frames >= 1 && frames <= 3) { Rt().frames = static_cast<uint32_t>(frames); changed = true; Log("panel: requested %dx output", frames + 1); }
    return changed;
}
void MenuGenerationState(bool value) { if (active != value) meter.Reset(); active = value; }
void MenuTelemetry(uint32_t displayed, uint32_t maxFrames, uint32_t result) {
    maximum = maxFrames; status = result; meter.Observe(Seconds(), displayed);
}
bool MenuColorSpace(VkColorSpaceKHR space, VkFormat format) {
    hdr10 = space == VK_COLOR_SPACE_HDR10_ST2084_EXT;
    if (hdr10) return format == VK_FORMAT_A2B10G10R10_UNORM_PACK32 || format == VK_FORMAT_A2R10G10B10_UNORM_PACK32;
    return space == VK_COLOR_SPACE_SRGB_NONLINEAR_KHR
        && (format == VK_FORMAT_B8G8R8A8_UNORM || format == VK_FORMAT_R8G8B8A8_UNORM);
}
bool MenuInitializeUI() {
    if (ImGui::GetCurrentContext()) return true;
    HWND selected{}; EnumWindows(FindWindow, reinterpret_cast<LPARAM>(&selected));
    if (!selected) return false;
    game = selected;
    ImGui::CreateContext();
    auto& io = ImGui::GetIO(); io.IniFilename = nullptr; io.LogFilename = nullptr;
    const float scale = float(GetDpiForWindow(game)) / 96.f;
    ImFontConfig font{}; font.SizePixels = 18.f * (scale < 1 ? 1 : scale);
    io.Fonts->AddFontDefault(&font);
    ImGui::StyleColorsDark();
    auto& style = ImGui::GetStyle(); style.WindowRounding = 14; style.FrameRounding = 6;
    style.WindowPadding = {20, 18}; style.ItemSpacing = {10, 12};
    style.Colors[ImGuiCol_CheckMark] = {0.64f, .88f, .06f, 1};
    style.Colors[ImGuiCol_Button] = {.25f, .31f, .10f, 1};
    style.Colors[ImGuiCol_ButtonHovered] = {.37f, .47f, .12f, 1};
    style.ScaleAllSizes(scale < 1 ? 1 : scale);
    if (!ImGui_ImplWin32_Init(game)) { ImGui::DestroyContext(); return false; }
    SetLastError(0);
    original = reinterpret_cast<WNDPROC>(SetWindowLongPtrW(game, GWLP_WNDPROC, reinterpret_cast<LONG_PTR>(WindowProc)));
    if (!original) {
        ImGui_ImplWin32_Shutdown(); ImGui::DestroyContext(); game = nullptr; return false;
    }
    Log("rtxForge Vulkan panel initialized: window=%p Delete opens panel", game);
    return true;
}
void MenuResetUI() {
    opened = false;
    if (game && original && reinterpret_cast<WNDPROC>(GetWindowLongPtrW(game, GWLP_WNDPROC)) == WindowProc)
        SetWindowLongPtrW(game, GWLP_WNDPROC, reinterpret_cast<LONG_PTR>(original));
    if (ImGui::GetCurrentContext()) { ImGui_ImplWin32_Shutdown(); ImGui::DestroyContext(); }
    game = nullptr; original = nullptr;
    std::lock_guard<std::mutex> guard(inputMutex); messages.clear();
}
bool MenuHasDrawing() { return opened.load(); }
void MenuBuildUI() {
    std::vector<Message> pending;
    { std::lock_guard<std::mutex> guard(inputMutex); pending.swap(messages); }
    for (auto message : pending) ImGui_ImplWin32_WndProcHandler(game, message.id, message.w, message.l);
    ImGui_ImplWin32_NewFrame(); ImGui::GetIO().MouseDrawCursor = opened;
    ImGui::NewFrame();
    if (opened) {
        ImGui::SetNextWindowSize({560, 0}, ImGuiCond_FirstUseEver);
        ImGui::SetNextWindowPos({130, 100}, ImGuiCond_FirstUseEver);
        bool visible = true;
        ImGui::Begin("rtxForge", &visible, ImGuiWindowFlags_AlwaysAutoResize | ImGuiWindowFlags_NoCollapse);
        ImGui::Text("%s / Vulkan", Profile().title);
        ImGui::TextDisabled("Universal Experimental"); ImGui::Separator();
        bool enabled = !Rt().fgUserOff;
        if (ImGui::Checkbox("NVIDIA Frame Generation", &enabled)) request.Set(enabled);
        ImGui::Text("Requested: %s   Active: %s", enabled ? "On" : "Off", active ? "On" : "Off");
        int multiplier = static_cast<int>(Rt().frames) - 1;
        if (ImGui::Combo("Output multiplier", &multiplier, "2x\0" "3x\0" "4x\0")) frameRequest.store(multiplier + 1);
        ImGui::Text("Universal MFG Unlocker: %s", UniversalMfgLoaded() ? "Loaded" : "Unavailable");
        ImGui::TextDisabled("Requested %ux; measured output appears below.", Rt().frames + 1);
        const auto nr = NrReadStatus();
        bool nrEnabled = nr.requested;
        if (ImGui::Checkbox("Neural Rendering", &nrEnabled)) NrRequest(nrEnabled);
        ImGui::Text("NR %s / %llu evaluations composed", nr.running ? "Running" : "Idle", static_cast<unsigned long long>(nr.frames));
        if (nr.gpuMs >= 0) ImGui::Text("NR GPU %.2f ms", nr.gpuMs);
        ImGui::Separator();
        if (meter.valid) {
            ImGui::Text("Game %.1f FPS   Displayed %.1f FPS", meter.gameFPS, meter.outputFPS);
            ImGui::Text("Measured output %.2fx", meter.ratio);
        } else ImGui::TextUnformatted("Waiting for presented-frame telemetry...");
        ImGui::Text("NVIDIA status %u   Runtime capacity %u generated", status, maximum);
        ImGui::TextDisabled("%s / session-only controls", hdr10 ? "HDR10, 203 nit panel white" : "SDR");
        std::string error;
        { std::lock_guard<std::mutex> guard(errorMutex); error = lastError; }
        if (!error.empty()) ImGui::TextWrapped("Panel diagnostic: %s", error.c_str());
        ImGui::Separator(); ImGui::TextDisabled("Delete closes the panel");
        ImGui::End(); if (!visible) opened = false;
    }
    ImGui::Render();
    if (hdr10) {
        auto* draw = ImGui::GetDrawData();
        for (int n = 0; draw && n < draw->CmdListsCount; ++n)
            for (auto& vertex : draw->CmdLists[n]->VtxBuffer) vertex.col = panel::HDR10(vertex.col);
    }
}
}
