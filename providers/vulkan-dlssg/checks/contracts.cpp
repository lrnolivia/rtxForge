#include "feature_registry.h"
#include "profile.h"
#include "extension_filter.h"
#include <cassert>
namespace {
bool legacyOnly{};
VkResult nativeFailure = VK_SUCCESS;
VkResult VKAPI_CALL Enumerate(VkPhysicalDevice, const char*, uint32_t* count, VkExtensionProperties* output) {
    if (nativeFailure != VK_SUCCESS) return nativeFailure;
    const char* names[] = {VK_EXT_BUFFER_DEVICE_ADDRESS_EXTENSION_NAME, VK_KHR_BUFFER_DEVICE_ADDRESS_EXTENSION_NAME};
    uint32_t available = legacyOnly ? 1 : 2;
    if (!output) { *count = available; return VK_SUCCESS; }
    const auto capacity = *count; *count = capacity < available ? capacity : available;
    for (uint32_t i = 0; i < *count; ++i) std::strcpy(output[i].extensionName, names[i]);
    return capacity < available ? VK_INCOMPLETE : VK_SUCCESS;
}
}
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
    uint32_t count{};
    assert(fgvk::EnumerateCoreBufferAddress(Enumerate, {}, nullptr, &count, nullptr) == VK_SUCCESS && count == 1);
    VkExtensionProperties output[2]{}; count = 0;
    assert(fgvk::EnumerateCoreBufferAddress(Enumerate, {}, nullptr, &count, output) == VK_INCOMPLETE && count == 0);
    count = 2;
    assert(fgvk::EnumerateCoreBufferAddress(Enumerate, {}, nullptr, &count, output) == VK_SUCCESS && count == 1);
    assert(!std::strcmp(output[0].extensionName, VK_KHR_BUFFER_DEVICE_ADDRESS_EXTENSION_NAME));
    legacyOnly = true; count = 2;
    assert(fgvk::EnumerateCoreBufferAddress(Enumerate, {}, nullptr, &count, output) == VK_SUCCESS && count == 1);
    assert(!std::strcmp(output[0].extensionName, VK_EXT_BUFFER_DEVICE_ADDRESS_EXTENSION_NAME));
    nativeFailure = VK_ERROR_DEVICE_LOST;
    assert(fgvk::EnumerateCoreBufferAddress(Enumerate, {}, nullptr, &count, output) == VK_ERROR_DEVICE_LOST);
}
