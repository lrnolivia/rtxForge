#include "profile.h"
#include "log.h"
#include <windows.h>
namespace fgvk {
static const GameProfile* selected;
bool SelectProfile() {
    char executable[MAX_PATH]{};
    if (!GetModuleFileNameA(nullptr, executable, MAX_PATH)) return false;
    const char* name = strrchr(executable, '\\');
    selected = FindProfile(name ? name + 1 : executable);
    if (selected) Log("rtxForge Vulkan profile: %s appId=0x%x", selected->title, selected->applicationId);
    else Log("rtxForge Vulkan: executable has no reviewed profile; hooks remain inactive");
    return selected != nullptr;
}
const GameProfile& Profile() { return *selected; }
}
