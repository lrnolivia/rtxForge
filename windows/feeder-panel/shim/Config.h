#pragma once
// The parts of OptiScaler that ForgePanel.h uses, for the Feeder NR panel.
// Settings are RenoDX keys in the game's ReShade.ini; input and the NR toggle
// come from ReShade (feeder_panel::Host, set by rtxforge-panel.cpp).
#include <windows.h>
#include <dxgi1_6.h>
#include <filesystem>
#include <optional>
#include <string>

#define LOG_INFO(...) ((void)0)
#define LOG_WARN(...) ((void)0)

namespace feeder_panel
{
struct Host
{
    bool (*focused)();
    bool (*key_down)(int vk);
    bool (*key_pressed)(int vk);
    bool (*key_released)(int vk);
    int (*last_pressed)();
    float (*get)(const char *key, float fallback);
    void (*set)(const char *key, float value, bool integer);
    void (*toggle_nr)();
    void (*log)(const char *text);
};
inline Host host {};
inline wchar_t module_path[MAX_PATH] {};
}

inline std::string wstring_to_string(const std::wstring &text)
{
    if (text.empty()) return {};
    const int size = WideCharToMultiByte(CP_UTF8, 0, text.data(), int(text.size()), nullptr, 0, nullptr, nullptr);
    std::string result(size, '\0');
    WideCharToMultiByte(CP_UTF8, 0, text.data(), int(text.size()), result.data(), size, nullptr, nullptr);
    return result;
}

namespace Util
{
inline std::filesystem::path DllPath() { return feeder_panel::module_path; }
}

namespace OptiInput
{
inline bool IsFocused() { return feeder_panel::host.focused(); }
inline bool IsKeyDown(int vk) { return feeder_panel::host.key_down(vk); }
inline bool IsKeyPressed(int vk) { return feeder_panel::host.key_pressed(vk); }
inline bool IsKeyReleased(int vk) { return feeder_panel::host.key_released(vk); }
inline int GetLastPressedKey() { return feeder_panel::host.last_pressed(); }
}

enum class ColorTransfer : uint32_t { Unknown, SRGB, Linear, PQ, HLG };
enum class ColorPrimaries : uint32_t { Unknown, Rec709, Rec2020 };
enum class ColorModel : uint32_t { Unknown, RGB, YCbCr };
enum class ColorRange : uint32_t { Unknown, Full, Studio };

struct OutputColorSpace
{
    ColorTransfer transfer = ColorTransfer::SRGB;
    ColorPrimaries primaries = ColorPrimaries::Rec709;
    ColorModel model = ColorModel::RGB;
    bool valid = false;
    ColorRange range = ColorRange::Full;
};

class State
{
public:
    static State &Instance() { static State state; return state; }
    OutputColorSpace outputColorSpace;
    bool hdrOutputActive = false;
    // Feeder provides NR only; frame generation stays unavailable.
    std::optional<int> dlssgMfgMax = std::nullopt;
    bool dlssgGameDMFGSupported = false;
};

// An OptiScaler-style setting with no backing store, for the panel's MFG path.
template <class T>
struct Unused
{
    using value_type = T;
    T value_or_default() const { return T {}; }
    void set_volatile_value(T) {}
};

class Config
{
public:
    static Config *Instance() { static Config config; return &config; }
    Unused<bool> FGDLSSGOverrideForceDMFG;

    float Get(const char *key, float fallback) { return feeder_panel::host.get(key, fallback); }
    // RenoDX loads these when the game starts.
    void Set(const char *key, float value, bool integer) { feeder_panel::host.set(key, value, integer); }
    // Neural rendering switches live through RenoDX's own toggle key.
    void SetNeuralRendering(float value)
    {
        feeder_panel::host.log(value != 0 ? "Neural rendering requested on" : "Neural rendering requested off");
        if ((Get("NeuralUplift", 0) != 0) != (value != 0)) feeder_panel::host.toggle_nr();
    }
};
