#pragma once
#include <vulkan/vulkan.h>
namespace fgvk {
// Streamline 2.12 intercepts acquire1 only. Passing acquire2 straight to the
// driver selects from its six backing images while the game owns three proxy
// images. Bridge the equivalent single-device, extension-free operation.
inline VkResult AcquireGameImage(PFN_vkAcquireNextImageKHR proxy,
    PFN_vkAcquireNextImage2KHR native, VkDevice device,
    const VkAcquireNextImageInfoKHR* info, uint32_t* index) {
    if (proxy && info && info->deviceMask == 1 && !info->pNext)
        return proxy(device, info->swapchain, info->timeout, info->semaphore, info->fence, index);
    return native ? native(device, info, index) : VK_ERROR_INITIALIZATION_FAILED;
}
}
