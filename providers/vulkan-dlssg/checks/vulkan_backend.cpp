// Exercise the actual Win32 + Vulkan backend startup without a game or visible
// window. --regression preserves Win32's advertised secondary-window support
// and reproduces the missing CreateVkSurface assertion on the pinned backend.
#include <windows.h>
#include <cstdlib>
#include <cstdio>
#include <cstring>
#include <vector>
#include <vulkan/vulkan.h>
#include "imgui.h"
#include "imgui_impl_win32.h"
#include "imgui_impl_vulkan.h"
#include "game_viewport.h"
namespace {
PFN_vkGetInstanceProcAddr gipa{};
PFN_vkGetDeviceProcAddr gdpa{};
VkInstance instance{};
VkDevice device{};
void Require(bool okay, const char* operation) {
    if (!okay) { std::fprintf(stderr, "Vulkan backend fixture failed: %s\n", operation); std::exit(1); }
}
PFN_vkVoidFunction Load(const char* name, void*) {
    const auto fn = gdpa ? gdpa(device, name) : nullptr;
    return fn ? fn : gipa(instance, name);
}
void Check(VkResult result) { Require(result >= 0, "ImGui Vulkan operation"); }
}
int main(int argc, char** argv) {
    _set_error_mode(_OUT_TO_STDERR);
    _set_abort_behavior(0, _WRITE_ABORT_MSG | _CALL_REPORTFAULT);
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
    const auto library = LoadLibraryW(L"vulkan-1.dll");
    if (!library) { puts("Win32/Vulkan backend startup: SKIP (Vulkan loader unavailable)"); return 0; }
    gipa = reinterpret_cast<PFN_vkGetInstanceProcAddr>(GetProcAddress(library, "vkGetInstanceProcAddr"));
    Require(gipa != nullptr, "instance procedure resolver");
    const auto createInstance = reinterpret_cast<PFN_vkCreateInstance>(gipa({}, "vkCreateInstance"));
    VkApplicationInfo app{VK_STRUCTURE_TYPE_APPLICATION_INFO}; app.apiVersion = VK_API_VERSION_1_1;
    const char* extensions[] = {VK_KHR_SURFACE_EXTENSION_NAME, "VK_KHR_win32_surface"};
    VkInstanceCreateInfo ci{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};
    ci.pApplicationInfo = &app; ci.enabledExtensionCount = 2; ci.ppEnabledExtensionNames = extensions;
    Require(createInstance && createInstance(&ci, nullptr, &instance) == VK_SUCCESS, "create native instance");
    const auto enumerate = reinterpret_cast<PFN_vkEnumeratePhysicalDevices>(gipa(instance, "vkEnumeratePhysicalDevices"));
    uint32_t count{}; Require(enumerate(instance, &count, nullptr) == VK_SUCCESS, "enumerate device count");
    if (!count) { puts("Win32/Vulkan backend startup: SKIP (no Vulkan physical device)"); return 0; }
    std::vector<VkPhysicalDevice> devices(count);
    Require(enumerate(instance, &count, devices.data()) == VK_SUCCESS, "enumerate native devices");
    const auto physical = devices[0];
    const auto queues = reinterpret_cast<PFN_vkGetPhysicalDeviceQueueFamilyProperties>(gipa(instance, "vkGetPhysicalDeviceQueueFamilyProperties"));
    queues(physical, &count, nullptr); std::vector<VkQueueFamilyProperties> families(count); queues(physical, &count, families.data());
    uint32_t family = UINT32_MAX;
    for (uint32_t i = 0; i < count; ++i) if (families[i].queueFlags & VK_QUEUE_GRAPHICS_BIT) { family = i; break; }
    Require(family != UINT32_MAX, "graphics queue family");
    float priority = 1.f; VkDeviceQueueCreateInfo qi{VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO};
    qi.queueFamilyIndex = family; qi.queueCount = 1; qi.pQueuePriorities = &priority;
    const char* swapchain = VK_KHR_SWAPCHAIN_EXTENSION_NAME;
    VkDeviceCreateInfo dc{VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO}; dc.queueCreateInfoCount = 1; dc.pQueueCreateInfos = &qi;
    dc.enabledExtensionCount = 1; dc.ppEnabledExtensionNames = &swapchain;
    const auto createDevice = reinterpret_cast<PFN_vkCreateDevice>(gipa(instance, "vkCreateDevice"));
    Require(createDevice(physical, &dc, nullptr, &device) == VK_SUCCESS, "create native device");
    gdpa = reinterpret_cast<PFN_vkGetDeviceProcAddr>(gipa(instance, "vkGetDeviceProcAddr"));
    VkQueue queue{}; reinterpret_cast<PFN_vkGetDeviceQueue>(gdpa(device, "vkGetDeviceQueue"))(device, family, 0, &queue);
    VkAttachmentDescription attachment{}; attachment.format = VK_FORMAT_B8G8R8A8_UNORM; attachment.samples = VK_SAMPLE_COUNT_1_BIT;
    attachment.loadOp = VK_ATTACHMENT_LOAD_OP_LOAD; attachment.storeOp = VK_ATTACHMENT_STORE_OP_STORE;
    attachment.initialLayout = attachment.finalLayout = VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL;
    VkAttachmentReference reference{0, VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL};
    VkSubpassDescription subpass{}; subpass.pipelineBindPoint = VK_PIPELINE_BIND_POINT_GRAPHICS; subpass.colorAttachmentCount = 1; subpass.pColorAttachments = &reference;
    VkRenderPassCreateInfo rp{VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO}; rp.attachmentCount = 1; rp.pAttachments = &attachment; rp.subpassCount = 1; rp.pSubpasses = &subpass;
    VkRenderPass renderPass{};
    Require(reinterpret_cast<PFN_vkCreateRenderPass>(gdpa(device, "vkCreateRenderPass"))(device, &rp, nullptr, &renderPass) == VK_SUCCESS, "create native render pass");
    const auto window = CreateWindowExW(0, L"STATIC", L"Vulkan backend fixture", WS_OVERLAPPED, 0, 0, 640, 480, nullptr, nullptr, GetModuleHandleW(nullptr), nullptr);
    Require(window != nullptr, "create hidden fixture window");
    ImGui::CreateContext(); ImGui::GetIO().IniFilename = nullptr; ImGui::GetIO().LogFilename = nullptr;
    Require(ImGui_ImplWin32_Init(window), "initialize real Win32 backend");
    Require((ImGui::GetIO().BackendFlags & ImGuiBackendFlags_PlatformHasViewports) != 0, "Win32 advertises secondary windows");
    Require(ImGui::GetPlatformIO().Platform_CreateVkSurface == nullptr, "host owns its Vulkan surface");
    const bool regression = argc > 1 && !std::strcmp(argv[1], "--regression");
    if (!regression) fgvk::UseGameViewport();
    Require(ImGui_ImplVulkan_LoadFunctions(VK_API_VERSION_1_1, Load), "load real Vulkan backend procedures");
    ImGui_ImplVulkan_InitInfo info{}; info.ApiVersion = VK_API_VERSION_1_1; info.Instance = instance;
    info.PhysicalDevice = physical; info.Device = device; info.QueueFamily = family; info.Queue = queue;
    info.PipelineInfoMain.RenderPass = renderPass; info.PipelineInfoMain.MSAASamples = VK_SAMPLE_COUNT_1_BIT;
    info.MinImageCount = info.ImageCount = 3; info.DescriptorPoolSize = 32; info.CheckVkResultFn = Check;
    Require(ImGui_ImplVulkan_Init(&info), "initialize actual Vulkan renderer");
    fgvk::UseGameViewport();
    ImGui_ImplVulkan_Shutdown(); ImGui_ImplWin32_Shutdown(); ImGui::DestroyContext(); DestroyWindow(window);
    reinterpret_cast<PFN_vkDestroyRenderPass>(gdpa(device, "vkDestroyRenderPass"))(device, renderPass, nullptr);
    reinterpret_cast<PFN_vkDestroyDevice>(gdpa(device, "vkDestroyDevice"))(device, nullptr);
    reinterpret_cast<PFN_vkDestroyInstance>(gipa(instance, "vkDestroyInstance"))(instance, nullptr);
    FreeLibrary(library);
    puts("Actual Win32/Vulkan backend startup and shutdown on the game-surface policy: PASS");
}
