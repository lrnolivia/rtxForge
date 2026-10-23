#include "menu.h"
#include "state.h"
#include "ForgePanel.h"
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
#include <array>

extern IMGUI_IMPL_API LRESULT ImGui_ImplWin32_WndProcHandler(HWND, UINT, WPARAM, LPARAM);
namespace fgvk {
namespace {
std::atomic<bool> opened{false}, available{false};
std::atomic<int> shortcut{VK_DELETE}, shortcutModifiers{0};
std::array<bool,256> pressed{}, released{};
int lastPressed{};
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
    const auto key = shortcut.load();
    const int mods = ((GetKeyState(VK_MENU)&0x8000) ? 1:0) | ((GetKeyState(VK_CONTROL)&0x8000) ? 2:0) | ((GetKeyState(VK_SHIFT)&0x8000) ? 4:0);
    if (message == WM_KEYUP && key > 0 && w == key && mods == shortcutModifiers && available) {
        opened = !opened; return 0;
    }
    if (message == WM_KEYDOWN && key > 0 && w == key && mods == shortcutModifiers && available) return 0;
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
    ForgePanel::Init(game);
    ForgePanel::selected = ForgePanel::enabled;
    ForgePanel::nrAllowed = true; ForgePanel::mfgAllowed = true;
    ForgePanel::title = Profile().title;
    ForgePanel::controlSupported = [](const ForgePanel::Control& field) {
        for(const auto* key : {"multiplier","enabled","style","intensity","preset","detail","colour","structure","tone","skin","auto_mask","work_scale"})
            if(!strcmp(key,field.key)) return true;
        return false;
    };
    shortcut = ForgePanel::ShortcutKey(); shortcutModifiers = ForgePanel::modifiers;
    ::Config::Instance()->FGDLSSGOverrideInterpolationCount = int(Rt().frames);
    io.ConfigFlags |= ImGuiConfigFlags_NavEnableKeyboard;
    io.ConfigFlags &= ~ImGuiConfigFlags_ViewportsEnable;
    ForgePanel::readLiveStats = [] {
        const auto nr = NrReadStatus();
        ForgePanel::LiveStats stats;
        stats.nrKnown = true; stats.nrRunning = nr.running; stats.nrFramesKnown = true; stats.nrFrames = nr.frames;
        stats.nrGpuMs = nr.gpuMs; stats.fgKnown = true; stats.fgRunning = active;
        stats.framesKnown = meter.valid;
        if(meter.valid) { stats.gameFps=meter.gameFPS; stats.displayedFps=meter.outputFPS; stats.measuredRatio=meter.ratio; }
        return stats;
    };
    if (!ImGui_ImplWin32_Init(game)) { ImGui::DestroyContext(); return false; }
    SetLastError(0);
    original = reinterpret_cast<WNDPROC>(SetWindowLongPtrW(game, GWLP_WNDPROC, reinterpret_cast<LONG_PTR>(WindowProc)));
    if (!original) {
        ImGui_ImplWin32_Shutdown(); ImGui::DestroyContext(); game = nullptr; return false;
    }
    Log("rtxForge canonical ForgePanel initialized: window=%p shortcut=%x", game, shortcut.load());
    return true;
}
void MenuResetUI() {
    opened = false;
    if (game && original && reinterpret_cast<WNDPROC>(GetWindowLongPtrW(game, GWLP_WNDPROC)) == WindowProc)
        SetWindowLongPtrW(game, GWLP_WNDPROC, reinterpret_cast<LONG_PTR>(original));
    if (ImGui::GetCurrentContext()) { ImGui_ImplWin32_Shutdown(); ImGui::DestroyContext(); }
    ForgePanelChannel::Shutdown();
    ForgePanel::font = ForgePanel::bold = nullptr; ForgePanel::animation = 0;
    game = nullptr; original = nullptr;
    std::lock_guard<std::mutex> guard(inputMutex); messages.clear();
}
bool MenuHasDrawing() { return ForgePanel::selected && (opened.load() || ForgePanel::Animating()); }
void MenuBuildUI(uint32_t width, uint32_t height) {
    std::vector<Message> pending;
    { std::lock_guard<std::mutex> guard(inputMutex); pending.swap(messages); }
    pressed.fill(false); released.fill(false);
    for(auto message : pending) {
        if(message.w < 256 && (message.id == WM_KEYDOWN || message.id == WM_SYSKEYDOWN)) {
            pressed[message.w] = true; lastPressed = int(message.w);
        }
        if(message.w < 256 && (message.id == WM_KEYUP || message.id == WM_SYSKEYUP)) released[message.w] = true;
        // MFG queues mouse events too: no cross-thread SetCapture from present.
        const int button = message.id == WM_LBUTTONDOWN || message.id == WM_LBUTTONUP ? 0 :
            message.id == WM_RBUTTONDOWN || message.id == WM_RBUTTONUP ? 1 :
            message.id == WM_MBUTTONDOWN || message.id == WM_MBUTTONUP ? 2 : -1;
        if(button >= 0) ImGui::GetIO().AddMouseButtonEvent(button, message.id == WM_LBUTTONDOWN || message.id == WM_RBUTTONDOWN || message.id == WM_MBUTTONDOWN);
        else ImGui_ImplWin32_WndProcHandler(game, message.id, message.w, message.l);
    }
    ImGui_ImplWin32_NewFrame();
    auto& io = ImGui::GetIO();
    if(io.DisplaySize.x > 0 && io.DisplaySize.y > 0)
        io.DisplayFramebufferScale = {width/io.DisplaySize.x, height/io.DisplaySize.y};
    io.MouseDrawCursor = opened;
    State::Instance().outputColorSpace = hdr10 ? OutputColorSpace{ColorTransfer::PQ, ColorPrimaries::Rec2020, ColorModel::RGB, true} : OutputColorSpace{};
    State::Instance().hdrOutputActive = hdr10;
    State::Instance().dlssgMfgMax = std::min(int(maximum), 3);
    ImGui::NewFrame();
    NrWithSettings([] {
        bool visible = opened.load();
        ForgePanel::Draw(visible, 1.f);
        opened = visible;
        // Preserve the shared panel's save/review protocol; an unconnected
        // helper leaves those buttons disabled rather than saving elsewhere.
    });
    shortcut = ForgePanel::ShortcutKey(); shortcutModifiers = ForgePanel::modifiers;
    const auto& cfg = *::Config::Instance();
    const int count = cfg.FGDLSSGOverrideInterpolationCount.has_value() ? cfg.FGDLSSGOverrideInterpolationCount.value() : int(Cfg().dlssgFrames);
    if((count == 0) != Rt().fgUserOff) request.Set(count != 0);
    if(count > 0 && count != int(Rt().frames)) frameRequest = std::clamp(count,1,3);
    ImGui::Render();
}
}
namespace OptiInput {
bool IsFocused() { return GetForegroundWindow() == fgvk::game; }
bool IsKeyDown(int key) { return key > 0 && key < 256 && (GetAsyncKeyState(key)&0x8000); }
bool IsKeyPressed(int key) { return key > 0 && key < 256 && fgvk::pressed[key]; }
bool IsKeyReleased(int key) { return key > 0 && key < 256 && fgvk::released[key]; }
int GetLastPressedKey() { return fgvk::lastPressed; }
}
