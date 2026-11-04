#pragma once
// The parts of OptiScaler that ForgePanel.h uses, for the Feeder NR panel.
// Settings are RenoDX keys in the game's ReShade.ini; input and the NR toggle
// come from ReShade (feeder_panel::Host, set by rtxforge-panel.cpp).
#include <windows.h>
#include <dxgi1_6.h>
#include <cmath>
#include <cstdint>
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

    // A RenoDX build with rtxForge's live interface (providers/renodx-dlss5)
    // reads and applies settings in the running game. Stock RenoDX loads them
    // only when the game starts, so values are saved for the next launch.
    float Get(const char *key, float fallback)
    {
        float value = 0;
        if (Live() && live.get(key, &value, nullptr) && std::isfinite(value)) return value;
        return feeder_panel::host.get(key, fallback);
    }
    void Set(const char *key, float value, bool integer)
    {
        if (!Live()) { feeder_panel::host.set(key, value, integer); return; }
        float applied = 0;
        uint64_t generation = 0;
        const int result = live.set(key, value, &applied, &generation);
        if (result == 1) { feeder_panel::host.set(key, value, integer); return; }  // Not live in this build.
        if (result != 0)
        {
            feeder_panel::host.log("RenoDX refused a live setting change");
            unconfirmedAt = GetTickCount64();
            return;
        }
        if (generation > rebuildTarget) { rebuildTarget = generation; rebuildSent = GetTickCount64(); }
    }
    // Whether the running RenoDX applies settings live (version 1 interface).
    bool Live()
    {
        if (live.version) return live.version == 1;
        if (GetTickCount64() < nextLookup) return false;
        nextLookup = GetTickCount64() + 2000;
        const HMODULE module = GetModuleHandleW(L"renodx-dlss5.addon64");
        if (!module) return false;
        const auto version = reinterpret_cast<uint32_t(__cdecl *)()>(GetProcAddress(module, "RenoDXNrApiVersion"));
        live.get = reinterpret_cast<decltype(live.get)>(GetProcAddress(module, "RenoDXNrGetV1"));
        live.set = reinterpret_cast<decltype(live.set)>(GetProcAddress(module, "RenoDXNrSetV1"));
        live.applied = reinterpret_cast<decltype(live.applied)>(GetProcAddress(module, "RenoDXNrAppliedGenerationV1"));
        live.version = version && live.get && live.set && live.applied ? version() : UINT32_MAX;
        feeder_panel::host.log(live.version == 1 ? "RenoDX live settings interface found" : "RenoDX has no supported live settings interface");
        return live.version == 1;
    }
    // Neural rendering switches live through RenoDX's own toggle key. RenoDX
    // writes NeuralUplift back when it handles the key, which is the only
    // confirmation this route has. Until that readback arrives (or times out)
    // a second press would toggle RenoDX back, so further requests are refused.
    void SetNeuralRendering(float value)
    {
        const int wanted = value != 0;
        if (Pending())
        {
            feeder_panel::host.log("Neural rendering change refused: the previous toggle is still unconfirmed");
            return;
        }
        feeder_panel::host.log(wanted ? "Neural rendering requested on" : "Neural rendering requested off");
        if ((Get("NeuralUplift", 0) != 0) == (wanted != 0)) return;
        feeder_panel::host.toggle_nr();
        toggleTarget = wanted;
        toggleSent = GetTickCount64();
    }
    // 0 idle or confirmed, 1 waiting for RenoDX, 2 recently unconfirmed.
    int LiveState()
    {
        Pending();
        if (toggleTarget >= 0 || Rebuilding()) return 1;
        return unconfirmedAt && GetTickCount64() - unconfirmedAt < 4000 ? 2 : 0;
    }

private:
    static constexpr ULONGLONG ConfirmTimeout = 2000, RebuildTimeout = 8000;
    int toggleTarget = -1;
    ULONGLONG toggleSent = 0, unconfirmedAt = 0, nextLookup = 0, rebuildSent = 0;
    uint64_t rebuildTarget = 0;
    struct
    {
        uint32_t version = 0;
        bool(__cdecl *get)(const char *, float *, uint64_t *) = nullptr;
        int(__cdecl *set)(const char *, float, float *, uint64_t *) = nullptr;
        uint64_t(__cdecl *applied)() = nullptr;
    } live;
    // A preset, pass or resolution change rebuilds the NR feature. It has
    // applied once every live feature reports the requested generation; with
    // no feature yet (NR off), the next one is built with it.
    bool Rebuilding()
    {
        if (!rebuildTarget || !Live()) return false;
        const uint64_t built = live.applied();
        if (built == 0 || built >= rebuildTarget) { rebuildTarget = 0; return false; }
        if (GetTickCount64() - rebuildSent < RebuildTimeout) return true;
        feeder_panel::host.log("RenoDX did not finish rebuilding NR for a setting change");
        rebuildTarget = 0;
        unconfirmedAt = GetTickCount64();
        return false;
    }
    bool Pending()
    {
        if (toggleTarget < 0) return false;
        if ((Get("NeuralUplift", 0) != 0) == (toggleTarget != 0)) { toggleTarget = -1; return false; }
        if (GetTickCount64() - toggleSent < ConfirmTimeout) return true;
        feeder_panel::host.log("RenoDX did not confirm the neural rendering toggle");
        toggleTarget = -1;
        unconfirmedAt = GetTickCount64();
        return false;
    }
};
