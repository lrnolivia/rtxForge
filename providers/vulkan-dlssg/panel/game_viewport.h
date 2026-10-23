#pragma once
#include "imgui.h"
namespace fgvk {
// The overlay borrows the game's surface; it owns no OS windows or Vulkan
// surface factory. Win32 advertises viewports even with ConfigFlags disabled,
// so constrain its capabilities after platform initialization as well.
inline void UseGameViewport() {
    auto& io = ImGui::GetIO();
    io.ConfigFlags &= ~ImGuiConfigFlags_ViewportsEnable;
    io.BackendFlags &= ~(ImGuiBackendFlags_PlatformHasViewports | ImGuiBackendFlags_RendererHasViewports);
}
}
