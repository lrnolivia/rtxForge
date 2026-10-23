#include "feature_registry.h"
#include "profile.h"
#include "extension_filter.h"
#include "startup.h"
#include "acquire_bridge.h"
#include <cassert>
namespace {
bool legacyOnly{};
VkResult nativeFailure = VK_SUCCESS;
unsigned proxyAcquires{}, nativeAcquires{};
VkDevice acquiredDevice{};
VkAcquireNextImageInfoKHR acquired{};
VkResult VKAPI_CALL ProxyAcquire(VkDevice device, VkSwapchainKHR sc, uint64_t timeout, VkSemaphore semaphore, VkFence fence, uint32_t* index) {
    acquiredDevice = device; acquired.swapchain = sc; acquired.timeout = timeout; acquired.semaphore = semaphore; acquired.fence = fence;
    *index = proxyAcquires++ % 3; return VK_SUBOPTIMAL_KHR;
}
VkResult VKAPI_CALL NativeAcquire(VkDevice, const VkAcquireNextImageInfoKHR*, uint32_t* index) {
    *index = nativeAcquires++ % 6; return VK_SUCCESS;
}
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
    fgvk::NrStartup startup;
    // Frame count alone at high FPS cannot start NR during an initial burst.
    for (uint32_t i = 0; i < 200; ++i) startup.Presented(true, true, i / 240.);
    assert(!startup.ready);
    startup.Presented(true, true, 3.); assert(startup.ready);
    for (uint32_t i = 0; i < 29; ++i) startup.Presented(false, true, 4. + i / 60.);
    assert(startup.ready);
    startup.Presented(false, true, 5.); assert(!startup.ready);
    // A warm-up cannot accumulate across loading screens or failed presents.
    for (uint32_t i = 0; i < 100; ++i) startup.Presented(true, true, 6. + i / 30.);
    assert(!startup.ready);
    startup.Presented(false, true, 10.); assert(startup.frames == 0);
    for (uint32_t i = 0; i < 120; ++i) startup.Presented(true, true, 11. + i / 30.);
    assert(startup.ready);
    startup.Presented(true, false, 16.); assert(!startup.ready);
    VkAcquireNextImageInfoKHR acquire{VK_STRUCTURE_TYPE_ACQUIRE_NEXT_IMAGE_INFO_KHR};
    acquire.deviceMask = 1; acquire.swapchain = reinterpret_cast<VkSwapchainKHR>(0x20);
    acquire.timeout = 123; acquire.semaphore = reinterpret_cast<VkSemaphore>(0x30); acquire.fence = reinterpret_cast<VkFence>(0x40);
    const auto device = reinterpret_cast<VkDevice>(0x10);
    // Cross more than one backing-buffer rotation: only proxy image indices
    // may reach the three-image game view, with all sync fields preserved.
    for (uint32_t i = 0; i < 18; ++i) {
        uint32_t index = UINT32_MAX;
        assert(fgvk::AcquireGameImage(ProxyAcquire, NativeAcquire, device, &acquire, &index) == VK_SUBOPTIMAL_KHR);
        assert(index == i % 3);
    }
    assert(proxyAcquires == 18 && nativeAcquires == 0 && acquiredDevice == device);
    assert(acquired.swapchain == acquire.swapchain && acquired.timeout == 123 && acquired.semaphore == acquire.semaphore && acquired.fence == acquire.fence);
    uint32_t index{}; acquire.deviceMask = 2;
    assert(fgvk::AcquireGameImage(ProxyAcquire, NativeAcquire, device, &acquire, &index) == VK_SUCCESS && nativeAcquires == 1);
}
