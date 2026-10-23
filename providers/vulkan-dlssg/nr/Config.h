#pragma once
#include <cstdint>
#include <optional>
enum class Scaler : uint32_t { FSR1, Bicubic, CatmullRom, Lanczos2, Lanczos3, Kaiser2, Kaiser3, Magic, Count };
template<class T> struct NrOption {
    using value_type = T;
    std::optional<T> stored;
    T fallback{};
    NrOption(T initial = T{}) : stored(initial), fallback(initial) {}
    NrOption(std::nullopt_t) : stored(std::nullopt) {}
    T value_or_default() const { return stored.value_or(fallback); }
    T value() const { return stored.value(); }
    bool has_value() const { return stored.has_value(); }
    NrOption& operator=(T next) { stored = next; return *this; }
    NrOption& operator=(std::nullopt_t) { stored.reset(); return *this; }
    void set_volatile_value(T next) { stored = next; }
};
// Only the native Vulkan NR settings used by the pinned backend. All mutation
// happens under the bridge's evaluation mutex; UI requests use an atomic mailbox.
class Config {
public:
    NrOption<bool> DlssNrEnabled{false}, DlssNrAutoMask{true}, DlssNrApplyModel{true};
    NrOption<uint32_t> DlssNrPreset{0}, DlssNrStyle{0}, DlssNrReversibleMode{0},
        DlssNrTransfer{1}, DlssNrWhitePointSource{0};
    NrOption<float> DlssNrWorkingScale{1.f}, DlssNrIntensity{1.f}, DlssNrLocalStructure{1.f},
        DlssNrLocalTone{1.f}, DlssNrSkinStructure{-1.f}, DlssNrWhitePointScale{1.f},
        DlssNrWhitePointTrim{1.f}, DlssNrTransferStrength{1.f}, DlssNrColourStrength{1.f},
        DlssNrMaxRatio{2.f};
    NrOption<Scaler> DlssNrScalingDownscaler{Scaler::Lanczos3}, OutputScalingDownscaler{Scaler::Lanczos3};
    // Shared-panel bindings retain every canonical control. Unsupported paths
    // are disabled by its host capability predicate, never simulated.
    NrOption<int> FGDLSSGOverrideInterpolationCount{std::nullopt}, FGDLSSGInterpolationCount{1};
    NrOption<bool> FGDLSSGOverrideForceDMFG{false}, RcasEnabled{false}, OverrideSharpness{false},
        MotionSharpnessEnabled{false}, DlssNrPreSr{false}, DlssNrPreSrReduced{false},
        DlssNrJbuUpsample{false}, DlssNrCacheEnabled{false}, RenderPresetOverride{false}, DLSSDRenderPresetOverride{false};
    NrOption<uint32_t> DlssNrPasses{1}, SharpnessShader{0}, DlssNrCacheInterval{1},
        RenderPresetForAll{0}, DLSSDRenderPresetForAll{0};
    NrOption<float> Sharpness{0}, MotionSharpness{0};
    static Config* Instance() { static Config config; return &config; }
};
