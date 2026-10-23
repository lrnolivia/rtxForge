#include "pch.h"
#include "bridge.h"
#include "Util.h"
#include <dlssnr/DlssNrFeature_Vk.h>
#include <nvsdk_ngx_vk.h>
#include <atomic>
#include <mutex>

namespace {
std::mutex evaluation;
std::atomic<bool> requested{false};
std::atomic<uint64_t> composed{0};
std::atomic<bool> running{false};
std::atomic<double> gpuMs{-1};
bool dispatchReady = false, resetNext = true;
using Allocate = NVSDK_NGX_Result(__cdecl*)(NVSDK_NGX_Parameter**);
using Destroy = NVSDK_NGX_Result(__cdecl*)(NVSDK_NGX_Parameter*);
Allocate allocateParameters{};
Destroy destroyParameters{};

// Read through the NGX core's C getters. The native parameter object's virtual
// overload order is not assumed to match this compiler's C++ ABI.
class FrameParameters final : public NVSDK_NGX_Parameter {
    void* native;
    const fgvk::NrGetters& getters;
    int flags;
    bool reset;
public:
    FrameParameters(void* p, const fgvk::NrGetters& g, int f, bool r) : native(p), getters(g), flags(f), reset(r) {}
    void Set(const char*, unsigned long long) override {}
    void Set(const char*, float) override {}
    void Set(const char*, double) override {}
    void Set(const char*, unsigned) override {}
    void Set(const char*, int) override {}
    void Set(const char*, ID3D11Resource*) override {}
    void Set(const char*, ID3D12Resource*) override {}
    void Set(const char*, void*) override {}
    NVSDK_NGX_Result Get(const char*, unsigned long long*) const override { return NVSDK_NGX_Result_FAIL_UnsupportedParameter; }
    NVSDK_NGX_Result Get(const char* name, float* value) const override {
        return getters.scalar ? static_cast<NVSDK_NGX_Result>(getters.scalar(native, name, value)) : NVSDK_NGX_Result_FAIL_UnsupportedParameter;
    }
    NVSDK_NGX_Result Get(const char*, double*) const override { return NVSDK_NGX_Result_FAIL_UnsupportedParameter; }
    NVSDK_NGX_Result Get(const char* name, unsigned* value) const override {
        if (!strcmp(name, NVSDK_NGX_Parameter_DLSS_Feature_Create_Flags)) {
            *value = static_cast<unsigned>(flags); return NVSDK_NGX_Result_Success;
        }
        if (reset && !strcmp(name, NVSDK_NGX_Parameter_Reset)) { *value = 1; return NVSDK_NGX_Result_Success; }
        return getters.integer ? static_cast<NVSDK_NGX_Result>(getters.integer(native, name, value)) : NVSDK_NGX_Result_FAIL_UnsupportedParameter;
    }
    NVSDK_NGX_Result Get(const char* name, int* value) const override {
        return getters.signedInteger ? static_cast<NVSDK_NGX_Result>(getters.signedInteger(native, name, value)) : NVSDK_NGX_Result_FAIL_UnsupportedParameter;
    }
    NVSDK_NGX_Result Get(const char*, ID3D11Resource**) const override { return NVSDK_NGX_Result_FAIL_UnsupportedParameter; }
    NVSDK_NGX_Result Get(const char*, ID3D12Resource**) const override { return NVSDK_NGX_Result_FAIL_UnsupportedParameter; }
    NVSDK_NGX_Result Get(const char* name, void** value) const override {
        return getters.pointer ? static_cast<NVSDK_NGX_Result>(getters.pointer(native, name, value)) : NVSDK_NGX_Result_FAIL_UnsupportedParameter;
    }
    void Reset() override {}
};
}

NVSDK_NGX_Result NVSDK_CONV NVSDK_NGX_VULKAN_AllocateParameters(NVSDK_NGX_Parameter** out) {
    if (out) *out = nullptr;
    return allocateParameters ? allocateParameters(out) : NVSDK_NGX_Result_FAIL_NotInitialized;
}
NVSDK_NGX_Result NVSDK_CONV NVSDK_NGX_VULKAN_DestroyParameters(NVSDK_NGX_Parameter* parameters) {
    return destroyParameters ? destroyParameters(parameters) : NVSDK_NGX_Result_FAIL_NotInitialized;
}

namespace fgvk {
void NrConfigure(const char* ini) {
    std::lock_guard<std::mutex> lock(evaluation);
    auto& cfg = *::Config::Instance();
    requested.store(GetPrivateProfileIntA("nr", "Enabled", 0, ini) != 0);
    auto number = [&](const char* key, float fallback, float lo, float hi) {
        char value[64]{}; const auto def = std::to_string(fallback);
        GetPrivateProfileStringA("nr", key, def.c_str(), value, sizeof(value), ini);
        const float read = strtof(value, nullptr);
        return std::isfinite(read) ? std::clamp(read, lo, hi) : fallback;
    };
    cfg.DlssNrWorkingScale.value = number("WorkingScale", 1.f, .25f, 2.f);
    cfg.DlssNrIntensity.value = number("Intensity", 1.f, 0.f, 2.f);
    cfg.DlssNrTransferStrength.value = number("DetailStrength", 1.f, 0.f, 2.f);
    cfg.DlssNrColourStrength.value = number("ColourStrength", 1.f, 0.f, 4.f);
    cfg.DlssNrWhitePointScale.value = number("WhitePoint", 1.f, .01f, 4096.f);
    // Exposure-image access needs a measured layout for each game. The initial
    // shared route uses the explicit white point and never binds an unknown image.
    cfg.DlssNrWhitePointSource.value = 0;
    const auto directory = Util::DllPath().parent_path();
    State::Instance().NVNGX_ApplicationDataPath = directory.wstring();
    Log("NR configuration: requested=%d workingScale=%.2f native Vulkan backend", requested.load(), cfg.DlssNrWorkingScale.value);
}
bool NrRequested() { return requested.load(); }
void NrRequest(bool enabled) { requested.store(enabled); }
NrStatus NrReadStatus() { return {requested.load(), running.load(), composed.load(), gpuMs.load()}; }
void NrSetNgxModule(HMODULE module) {
    std::lock_guard<std::mutex> lock(evaluation);
    const auto allocate = reinterpret_cast<Allocate>(GetProcAddress(module, "NVSDK_NGX_VULKAN_AllocateParameters"));
    const auto destroy = reinterpret_cast<Destroy>(GetProcAddress(module, "NVSDK_NGX_VULKAN_DestroyParameters"));
    if (allocate && destroy) { allocateParameters = allocate; destroyParameters = destroy; }
}
bool NrSetDevice(PFN_vkGetInstanceProcAddr gipa, PFN_vkGetDeviceProcAddr gdpa, VkInstance instance,
                 VkPhysicalDevice, VkDevice device) {
    std::lock_guard<std::mutex> lock(evaluation);
    dispatchReady = NrBindDispatch(gipa, gdpa, instance, device);
    return dispatchReady;
}
void NrEvaluate(VkCommandBuffer command, void* native, const NrGetters& getters, int flags) {
    std::lock_guard<std::mutex> lock(evaluation);
    auto& cfg = *::Config::Instance();
    if (!requested.load()) { cfg.DlssNrEnabled.value = false; running.store(false); resetNext = true; return; }
    if (!dispatchReady || !allocateParameters || !destroyParameters || flags < 0) return;
    cfg.DlssNrEnabled.value = true;
    FrameParameters frame(native, getters, flags, resetNext);
    extern VkInstance gInstance;
    extern VkPhysicalDevice gPhysicalDevice;
    extern VkDevice gDevice;
    const auto before = DlssNr::FramesVk();
    DlssNr::EvaluateAfterUpscaleVk(command, &frame, gInstance, gPhysicalDevice, gDevice);
    const auto after = DlssNr::FramesVk();
    if (after > before) {
        resetNext = false; composed.fetch_add(after - before);
        running.store(true); gpuMs.store(DlssNr::LastGpuTimeVk().value_or(-1));
        if (composed.load() % 120 == 0) Log("NR stats: %llu native Vulkan evaluations composed, GPU %.2fms",
            static_cast<unsigned long long>(composed.load()), gpuMs.load());
    } else running.store(false);
}
void NrShutdown(bool deviceAlive) {
    std::lock_guard<std::mutex> lock(evaluation);
    DlssNr::ShutdownVk(deviceAlive);
    dispatchReady = false; running.store(false); resetNext = true;
}
}
