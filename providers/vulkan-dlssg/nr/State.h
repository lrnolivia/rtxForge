#pragma once
#include <string>
#include <optional>
#include <cstdint>
enum class ColorTransfer : uint32_t { Unknown, SRGB, Linear, PQ, HLG };
enum class ColorPrimaries : uint32_t { Unknown, Rec709, Rec2020 };
enum class ColorModel : uint32_t { Unknown, RGB, YCbCr };
struct OutputColorSpace {
    ColorTransfer transfer{ColorTransfer::SRGB};
    ColorPrimaries primaries{ColorPrimaries::Rec709};
    ColorModel model{ColorModel::RGB};
    bool valid{};
};
class State {
public:
    std::wstring NVNGX_ApplicationDataPath;
    OutputColorSpace outputColorSpace;
    bool hdrOutputActive{};
    std::optional<int> dlssgMfgMax;
    bool dlssgGameDMFGSupported{};
    static State& Instance() { static State state; return state; }
};
