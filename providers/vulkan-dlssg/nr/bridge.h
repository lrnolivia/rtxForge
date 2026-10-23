#pragma once
#include <windows.h>
#include <vulkan/vulkan.h>
#include <cstdint>
namespace fgvk {
struct NrGetters {
    int (__cdecl* pointer)(void*, const char*, void**);
    int (__cdecl* scalar)(void*, const char*, float*);
    int (__cdecl* integer)(void*, const char*, unsigned*);
    int (__cdecl* signedInteger)(void*, const char*, int*);
};
struct NrStatus { bool requested, running; uint64_t frames; double gpuMs; bool warming; };
void NrConfigure(const char* ini);
bool NrRequested();
void NrRequest(bool enabled);
void NrWithSettings(void (*draw)());
NrStatus NrReadStatus();
void NrSetNgxModule(HMODULE module);
bool NrSetDevice(PFN_vkGetInstanceProcAddr, PFN_vkGetDeviceProcAddr, VkInstance, VkPhysicalDevice, VkDevice);
void NrEvaluate(VkCommandBuffer, void* parameters, const NrGetters&, int createFlags);
void NrPresented(bool success);
void NrShutdown(bool deviceAlive);
}
