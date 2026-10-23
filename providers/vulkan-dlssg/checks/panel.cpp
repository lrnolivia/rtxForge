// Render the real shared panel without a game, window or graphics device.
#include "ForgePanel.h"
#include <cassert>
#include <cstdarg>
#include <cstdio>
namespace fgvk { void Log(const char*, ...) {} }
namespace OptiInput {
bool IsFocused() { return true; }
bool IsKeyDown(int) { return false; }
bool IsKeyPressed(int) { return false; }
bool IsKeyReleased(int) { return false; }
int GetLastPressedKey() { return 0; }
}
int main() {
    ImGui::CreateContext();
    auto& io = ImGui::GetIO();
    io.IniFilename = nullptr; io.LogFilename = nullptr;
    io.BackendFlags |= ImGuiBackendFlags_RendererHasTextures;
    ForgePanel::initialized = ForgePanel::enabled = true;
    ForgePanel::Init(nullptr);
    ForgePanel::selected = ForgePanel::nrAllowed = ForgePanel::mfgAllowed = true;
    State::Instance().dlssgMfgMax = 3;
    ForgePanel::readLiveStats = [] {
        ForgePanel::LiveStats stats;
        stats.nrKnown=stats.nrRunning=stats.nrFramesKnown=stats.fgKnown=stats.fgRunning=stats.framesKnown=true;
        stats.nrFrames=1200; stats.nrGpuMs=10.5; stats.gameFps=30; stats.displayedFps=120; stats.measuredRatio=4;
        return stats;
    };
    assert(ForgePanel::font && ForgePanel::bold && ForgePanel::font != ForgePanel::bold);
    assert(ForgePanel::brandFont && ForgePanel::brandFont != ForgePanel::font);
    assert(!strcmp(ForgePanel::PanelFontLoader()->Name,"stb_truetype"));
    for(int test=0;test<3;++test) {
        io.DisplaySize = test==0 ? ImVec2(1920,1080) : test==1 ? ImVec2(3840,2160) : ImVec2(1920,1080);
        io.DisplayFramebufferScale = test==2 ? ImVec2(2,2) : ImVec2(1,1);
        ForgePanel::dpiScale = 1;
        const float expected = test==1 ? 2.f : 1.f;
        assert(std::abs(ForgePanel::PanelScale()-expected)<.001f);
        State::Instance().outputColorSpace = test==1 ? OutputColorSpace{ColorTransfer::PQ,ColorPrimaries::Rec2020,ColorModel::RGB,true} : OutputColorSpace{};
        bool visible=true;
        for(int frame=0;frame<20;++frame) {
            io.DeltaTime=1.f/60;
            ImGui::NewFrame();
            for(auto* texture : io.Fonts->TexList) { texture->SetTexID(1); texture->SetStatus(ImTextureStatus_OK); }
            assert(ForgePanel::Draw(visible,1));
            ImGui::Render();
            const auto draw=ImGui::GetDrawData();
            assert(draw && draw->TotalVtxCount>0 && draw->TotalIdxCount>0);
        }
    }
    // Welcome uses its own shared preference and measured top-center layout;
    // it never needs a fabricated helper connection to draw the saved shortcut.
    ForgePanel::welcomeStarted=0; ForgePanel::welcomeDismissed=false;
    ForgePanel::key=VK_OEM_3; ForgePanel::modifiers=2;
    ForgePanelChannel::settings["overlay_welcome"]=true;
    io.DisplaySize=ImVec2(1920,1080); io.DisplayFramebufferScale=ImVec2(1,1);
    State::Instance().outputColorSpace={};
    for(int frame=0;frame<4;++frame) {
        ImGui::NewFrame();
        for(auto* texture:io.Fonts->TexList) {texture->SetTexID(1);texture->SetStatus(ImTextureStatus_OK);}
        ForgePanel::Welcome(false); ImGui::Render();
        auto window=ImGui::FindWindowByName("rtxForge##welcome");
        assert(window && std::abs(window->Pos.x+window->Size.x*.5f-960)<2 && window->Pos.y>=55);
        assert(ImGui::GetDrawData()->TotalVtxCount>0);
    }
    ForgePanelChannel::settings["overlay_welcome"]=false; assert(!ForgePanel::WelcomePending());
    ForgePanelChannel::settings["overlay_welcome"]=true;
    ForgePanel::Welcome(true); assert(!ForgePanel::WelcomePending());
    ForgePanelChannel::Shutdown();
    ImGui::DestroyContext();
    puts("Canonical panel, Inter fonts, live-stat callback, SDR/HDR and framebuffer/DPI scaling: PASS");
}
