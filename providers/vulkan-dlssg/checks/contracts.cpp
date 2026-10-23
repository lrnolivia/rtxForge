#include "feature_registry.h"
#include "profile.h"
#include <cassert>
int main() {
    fgvk::FeatureRegistry registry;
    int handle;
    assert(registry.Find(&handle).id == 0);
    registry.Created(&handle, 1, 0x6b);
    assert(registry.Find(&handle).id == 1 && registry.Find(&handle).flags == 0x6b);
    registry.Released(&handle);
    assert(registry.Find(&handle).id == 0);
    registry.Created(&handle, 18, 0);
    assert(registry.Find(&handle).id != 1); // NR cannot recursively enter the SR path.
    registry.Created(&handle, 13, 0);
    assert(registry.Find(&handle).id != 1); // Neither can frame generation.
    const auto bg3 = fgvk::FindProfile("BG3.EXE"), rdr2 = fgvk::FindProfile("rdr2.exe");
    assert(bg3 && rdr2 && bg3->applicationId != rdr2->applicationId);
    assert(!fgvk::FindProfile("bg3_dx11.exe") && !fgvk::FindProfile("unreviewed.exe"));
    assert(rdr2->depthLayout == VK_IMAGE_LAYOUT_UNDEFINED); // Requires observed input layouts.
}
