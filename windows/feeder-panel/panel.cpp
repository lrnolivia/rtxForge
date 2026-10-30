// The same rtxForge panel OptiScaler shows, hosted for Feeder NR games.
#include "Config.h"
#include <imgui/imgui.h>
#include <imgui/imgui_impl_dx11.h>
#include "ForgePanel.h"
#include "../../providers/glass-overlay/ForgeGlassPanel.h"
#include "panel.h"

namespace feeder_panel
{
namespace
{
ImGuiContext *context = nullptr;
ID3D11Device *device = nullptr;
ID3D11DeviceContext *immediate = nullptr;
bool visible = false, backend = false;
LARGE_INTEGER frequency {}, last {};
ForgePanel::LiveStats statistics;
double measuredSeconds{}; unsigned measuredPresents{};
// RenoDX loads tuning at launch; say so in the panel's own message line.
constexpr const char *NextLaunch = "Saved. Model changes apply the next time the game starts. Neural rendering switches now.";
const char *const Keys[] = {"NRIntensity", "NRPasses", "NRResolutionScale", "NRPreset", "NRStyle", "NRLocalStructure"};
float launch[std::size(Keys)] {};

void feed_keys(ImGuiIO &io)
{
    static const std::pair<int, ImGuiKey> keys[] = {
        {VK_ESCAPE, ImGuiKey_Escape}, {VK_RETURN, ImGuiKey_Enter}, {VK_SPACE, ImGuiKey_Space}, {VK_TAB, ImGuiKey_Tab},
        {VK_BACK, ImGuiKey_Backspace}, {VK_DELETE, ImGuiKey_Delete}, {VK_HOME, ImGuiKey_Home}, {VK_END, ImGuiKey_End},
        {'A', ImGuiKey_A}, {'C', ImGuiKey_C}, {'V', ImGuiKey_V}, {'X', ImGuiKey_X}, {'Y', ImGuiKey_Y}, {'Z', ImGuiKey_Z},
        {VK_UP, ImGuiKey_UpArrow}, {VK_DOWN, ImGuiKey_DownArrow}, {VK_LEFT, ImGuiKey_LeftArrow}, {VK_RIGHT, ImGuiKey_RightArrow}};
    for (const auto &[vk, key] : keys) io.AddKeyEvent(key, host.key_down(vk));
    io.AddKeyEvent(ImGuiMod_Ctrl,host.key_down(VK_CONTROL));
    io.AddKeyEvent(ImGuiMod_Shift,host.key_down(VK_SHIFT));
    io.AddKeyEvent(ImGuiMod_Alt,host.key_down(VK_MENU));
    if(io.WantTextInput) {
        const auto vk=host.last_pressed();
        if(vk>0 && vk<256 && host.key_pressed(vk)) {
            BYTE keyboard[256]{}; GetKeyboardState(keyboard);
            for(int key=0;key<256;++key) keyboard[key]=BYTE((keyboard[key]&1) | (host.key_down(key) ? 0x80 : 0));
            WCHAR text[8]{}; const auto layout=GetKeyboardLayout(0);
            const int count=ToUnicodeEx(vk,MapVirtualKeyExW(vk,MAPVK_VK_TO_VSC,layout),keyboard,text,8,4,layout);
            for(int i=0;i<count;++i) if(text[i]>=32) io.AddInputCharacterUTF16(text[i]);
        }
    }
}

void colour_space(Output output)
{
    auto &state = State::Instance();
    state.outputColorSpace = {};
    state.hdrOutputActive = output != Output::sdr;
    if (output == Output::scrgb) state.outputColorSpace = {ColorTransfer::Linear, ColorPrimaries::Rec709, ColorModel::RGB, true};
    else if (output == Output::hdr10) state.outputColorSpace = {ColorTransfer::PQ, ColorPrimaries::Rec2020, ColorModel::RGB, true};
}

// The footer names the panel shortcut. The helper sends it when it connects;
// until then use the name rtxForge saved with the shortcut.
void seed_shortcut_name()
{
    wchar_t local[MAX_PATH] {};
    if (!GetEnvironmentVariableW(L"LOCALAPPDATA", local, MAX_PATH)) return;
    try
    {
        std::ifstream input(std::filesystem::path(local) / L"rtxForge" / L"settings.json");
        const auto settings = nlohmann::json::parse(input, nullptr, false);
        if (settings.is_object() && settings.value("panel_hotkey", nlohmann::json()).is_string())
            ForgePanelChannel::settings["panel_hotkey"] = settings["panel_hotkey"];
    }
    catch (...) {}
}

void next_launch_message()
{
    bool pending = false;
    for (size_t i = 0; i < std::size(Keys); ++i) pending |= std::fabs(host.get(Keys[i], launch[i]) - launch[i]) > 0.001f;
    auto &message = ForgePanelChannel::message;
    if (pending && message.empty()) message = NextLaunch;
    else if (!pending && message == NextLaunch) message.clear();
}
}

bool Init(ID3D11Device *game, HWND window)
{
    if (context) return backend;
    context = ImGui::CreateContext();
    ImGui::SetCurrentContext(context);
    auto &io = ImGui::GetIO();
    io.IniFilename = nullptr;
    io.LogFilename = nullptr;
    io.ConfigFlags |= ImGuiConfigFlags_NavEnableKeyboard;
    ForgePanel::Init(window);
    ForgePanel::readLiveStats = [] { return statistics; };
    // Feeder installs are NR only, so the panel never offers frame generation.
    ForgePanel::selected = ForgePanel::enabled;
    ForgePanel::nrAllowed = true;
    ForgePanel::liveTuning = false;
    ForgePanel::mfgAllowed = false;
    for (size_t i = 0; i < std::size(Keys); ++i) launch[i] = host.get(Keys[i], 0);
    seed_shortcut_name();
    ForgeGlassPanel::logSink=host.log;
    ForgeGlassPanel::Prepare(window);
    device = game;
    device->AddRef();
    device->GetImmediateContext(&immediate);
    backend = ForgePanel::enabled && ImGui_ImplDX11_Init(device, immediate);
    QueryPerformanceFrequency(&frequency);
    QueryPerformanceCounter(&last);
    return backend;
}

bool Draw(const Frame &frame)
{
    if (!backend || !ForgePanel::selected) return false;
    ImGui::SetCurrentContext(context);
    if (!ForgePanel::CapturingShortcut() && ForgePanel::ShortcutReleased()) visible = !visible;
    ForgePanelChannel::Visible(visible);
    LARGE_INTEGER now;
    QueryPerformanceCounter(&now);
    auto &io = ImGui::GetIO();
    const double delta = double(now.QuadPart - last.QuadPart)/double(frequency.QuadPart);
    io.DeltaTime = std::clamp(float(delta), 1.0f / 1000.0f, 0.1f);
    if(delta <= 0 || delta > .5) { measuredSeconds=0; measuredPresents=0; statistics.gameFps=-1; }
    else if((measuredSeconds += delta) >= .5) {
        statistics.gameFps = (++measuredPresents)/measuredSeconds; measuredSeconds=0; measuredPresents=0;
    } else ++measuredPresents;
    last = now;
    if (!visible && !ForgePanel::Animating() && !ForgePanel::WelcomePending()) return false;

    io.DisplaySize = ImVec2(frame.width, frame.height);
    io.AddMousePosEvent(frame.mouse_x, frame.mouse_y);
    for (int button = 0; button < 3; ++button) io.AddMouseButtonEvent(button, frame.mouse[button]);
    if (frame.wheel != 0) io.AddMouseWheelEvent(0, frame.wheel);
    feed_keys(io);
    io.MouseDrawCursor = visible;
    colour_space(frame.output);

    ImGui_ImplDX11_NewFrame();
    ImGui::NewFrame();
    next_launch_message();
    if(ForgeGlassPanel::loader.Ready()) {
        next_launch_message();
        if(ForgePanelChannel::needsHello&&!ForgePanelChannel::pending&&ForgePanelChannel::Send({{"op","hello"}}))ForgePanelChannel::needsHello=false;
        const bool drawn=ForgeGlassPanel::Draw(device,frame.target,visible);
        if(drawn){
            ImGui::Render();ID3D11RenderTargetView* previous=nullptr;ID3D11DepthStencilView* depth=nullptr;immediate->OMGetRenderTargets(1,&previous,&depth);immediate->OMSetRenderTargets(1,&frame.target,nullptr);ImGui_ImplDX11_RenderDrawData(ImGui::GetDrawData());immediate->OMSetRenderTargets(1,&previous,depth);if(previous)previous->Release();if(depth)depth->Release();return visible;
        }
        ImGui::EndFrame();ImGui::NewFrame();
    }
    ForgePanel::Welcome(visible);
    ForgePanel::Draw(visible, frame.height / 1080.0f);
    ImGui::Render();

    ID3D11RenderTargetView *previous = nullptr;
    ID3D11DepthStencilView *depth = nullptr;
    immediate->OMGetRenderTargets(1, &previous, &depth);
    immediate->OMSetRenderTargets(1, &frame.target, nullptr);
    ImGui_ImplDX11_RenderDrawData(ImGui::GetDrawData());
    immediate->OMSetRenderTargets(1, &previous, depth);
    if (previous) previous->Release();
    if (depth) depth->Release();
    return visible;
}

void Release()
{
    if (!context) return;
    ImGui::SetCurrentContext(context);
    ForgeGlassPanel::Shutdown();
    if (backend) ImGui_ImplDX11_Shutdown();
    backend = false;
    if (immediate) immediate->Release();
    if (device) device->Release();
    immediate = nullptr;
    device = nullptr;
    ForgePanelChannel::Shutdown();
    ImGui::DestroyContext(context);
    context = nullptr;
}

void Shutdown() { Release(); }
}
