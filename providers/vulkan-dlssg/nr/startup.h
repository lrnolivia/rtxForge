#pragma once
#include <cstdint>
namespace fgvk {
// Warm the native rendering path before the first NR model work is recorded.
// This state advances even while NR is off, so a later user toggle is immediate.
// A long loading/menu gap or failed presentation requires a fresh warm-up.
struct NrStartup {
    static constexpr uint32_t minimumFrames = 120, idleLimit = 30;
    static constexpr double minimumSeconds = 3.;
    uint32_t frames{}, idle{};
    double first{};
    bool ready{};
    void Reset() { frames = idle = 0; first = 0; ready = false; }
    void Presented(bool evaluated, bool success, double now) {
        if (!success) { Reset(); return; }
        if (!evaluated) {
            if (!ready) { frames = 0; first = 0; }
            if (++idle >= idleLimit) Reset();
            return;
        }
        idle = 0;
        if (ready) return;
        if (!frames || now < first) { frames = 0; first = now; }
        ++frames;
        ready = frames >= minimumFrames && now - first >= minimumSeconds;
    }
};
}
