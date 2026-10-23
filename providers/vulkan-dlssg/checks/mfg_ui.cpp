// Exercise the pinned release's real guard and ownership ABI in a disposable
// fixture process; no graphics device, game or input automation.
#include "quiet_ui.h"
#include <cassert>
#include <cstdio>
struct Status {
    unsigned size{64},version{1},owner{},duplicate{},dxgi{},vulkan{},visible{},failures{},key{},binding{};
    unsigned long long dxgiFrames{},vulkanFrames{},rendered{};
};
int wmain(int argc,wchar_t** argv) {
    assert(argc==2);
    assert(!fgvk::mfg_ui::Matches(GetModuleHandleW(nullptr)));
    auto module=LoadLibraryExW(argv[1],nullptr,LOAD_WITH_ALTERED_SEARCH_PATH);
    assert(module && fgvk::mfg_ui::Matches(module));
    auto query=reinterpret_cast<BOOL(WINAPI*)(Status*)>(GetProcAddress(module,"MfgUnlockSingleModuleQuery"));
    Status before{}; assert(query && query(&before) && before.owner && !before.duplicate);
    auto guard=reinterpret_cast<bool(*)()>(reinterpret_cast<unsigned char*>(module)+fgvk::mfg_ui::GuardRva);
    assert(guard());
    assert(fgvk::mfg_ui::Install(module));
    assert(!guard());
    Status after{}; assert(query(&after) && after.owner && !after.duplicate && !after.visible);
    fgvk::mfg_ui::nativeMenu=true; assert(guard());
    fgvk::mfg_ui::nativeMenu=false; assert(!guard());
    puts("Pinned MFG UI suppression/re-enable preserves independent backend ownership: PASS");
}
