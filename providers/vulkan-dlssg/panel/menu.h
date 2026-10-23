#pragma once
#include <cstdint>
#include <vulkan/vulkan.h>
namespace fgvk {
bool MenuInitializeUI();
bool MenuHasDrawing();
void MenuBuildUI();
void MenuResetUI();
void MenuRendererAvailable(bool);
void MenuError(const char*);
bool MenuApplyRequest();
void MenuGenerationState(bool);
void MenuTelemetry(uint32_t displayed, uint32_t maximum, uint32_t status);
bool MenuColorSpace(VkColorSpaceKHR, VkFormat);
void MenuRegisterSwapchain(VkDevice,VkPhysicalDevice,VkInstance,uint32_t,VkSwapchainKHR,const VkSwapchainCreateInfoKHR*,PFN_vkGetDeviceProcAddr,PFN_vkGetSwapchainImagesKHR);
void MenuDestroySwapchain(VkDevice,VkSwapchainKHR);
void MenuCaptureImages(VkDevice,VkSwapchainKHR,uint32_t,const VkImage*);
void MenuPresentCompleted(bool,VkResult);
bool MenuRender(VkQueue,const VkPresentInfoKHR*,VkPresentInfoKHR&);
}
