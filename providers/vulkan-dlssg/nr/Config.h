#pragma once
#include <cstdint>
enum class Scaler : uint32_t { FSR1, Bicubic, CatmullRom, Lanczos2, Lanczos3, Kaiser2, Kaiser3, Magic, Count };
template<class T> struct NrOption {
    T value;
    T value_or_default() const { return value; }
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
    static Config* Instance() { static Config config; return &config; }
};
