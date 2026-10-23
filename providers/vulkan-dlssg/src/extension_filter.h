#pragma once
#include <vulkan/vulkan.h>
#include <cstring>
#include <vector>
namespace fgvk {
// Prefer the KHR BDA contract used by Streamline when both spellings are
// advertised. Retain EXT on a legacy-only device and preserve Vulkan's count,
// capacity and VK_INCOMPLETE enumeration contract.
inline VkResult EnumerateCoreBufferAddress(PFN_vkEnumerateDeviceExtensionProperties native,
    VkPhysicalDevice device, const char* layer, uint32_t* count, VkExtensionProperties* output) {
    if (!count) return VK_ERROR_INITIALIZATION_FAILED;
    if (layer) return native(device, layer, count, output);
    uint32_t available{};
    auto result = native(device, layer, &available, nullptr);
    if (result != VK_SUCCESS) return result;
    std::vector<VkExtensionProperties> properties(available);
    if (available) {
        result = native(device, layer, &available, properties.data());
        if (result != VK_SUCCESS) return result;
        properties.resize(available);
    }
    bool khr = false;
    for (const auto& item : properties)
        if (!std::strcmp(item.extensionName, VK_KHR_BUFFER_DEVICE_ADDRESS_EXTENSION_NAME)) khr = true;
    const auto capacity = output ? *count : 0;
    uint32_t visible{};
    for (const auto& item : properties) {
        if (khr && !std::strcmp(item.extensionName, VK_EXT_BUFFER_DEVICE_ADDRESS_EXTENSION_NAME)) continue;
        if (output && visible < capacity) output[visible] = item;
        ++visible;
    }
    *count = output && visible > capacity ? capacity : visible;
    return output && visible > capacity ? VK_INCOMPLETE : VK_SUCCESS;
}
}
