#pragma once
#include <cstdint>
#include <cstring>
#include <vulkan/vulkan.h>
namespace fgvk {
struct GameProfile {
    const char* executable;
    const char* title;
    uint32_t applicationId;
    float fov, nearPlane, farPlane;
    VkImageLayout depthLayout, motionLayout;
};
inline constexpr GameProfile profiles[] = {
    {"bg3.exe", "Baldur's Gate 3", 0x0E658703, .84f, .05f, 10000.f,
     VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL, VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL},
    {"RDR2.exe", "Red Dead Redemption 2", 0x060E8AB7, 1.0471975512f, .05f, 10000.f,
     VK_IMAGE_LAYOUT_UNDEFINED, VK_IMAGE_LAYOUT_UNDEFINED},
};
inline const GameProfile* FindProfile(const char* executable) {
    for (const auto& profile : profiles)
        if (_stricmp(profile.executable, executable) == 0) return &profile;
    return nullptr;
}
bool SelectProfile();
const GameProfile& Profile();
}
