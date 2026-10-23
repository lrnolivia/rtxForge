#pragma once
#include <atomic>
#include <cstdint>
#include <algorithm>

namespace fgvk::panel {
// Requests cross the window/render boundary; only the present owner changes FG.
class Request {
    std::atomic<int> enabled{-1};
public:
    void Set(bool value) { enabled.store(value ? 1 : 0); }
    bool Consume(bool& off) {
        const int value = enabled.exchange(-1);
        if (value < 0) return false;
        off = value == 0;
        return true;
    }
};

class Meter {
    double started = 0;
    uint64_t presents = 0, displayed = 0;
public:
    double gameFPS = 0, outputFPS = 0, ratio = 0;
    bool valid = false;
    void Reset() { started = 0; presents = displayed = 0; valid = false; }
    void Observe(double seconds, uint32_t frames) {
        if (!started || seconds <= started || seconds - started > 5) {
            started = seconds; presents = displayed = 0; valid = false; return;
        }
        ++presents; displayed += frames;
        if (seconds - started < .5) return;
        const double elapsed = seconds - started;
        gameFPS = presents / elapsed; outputFPS = displayed / elapsed;
        ratio = double(displayed) / presents; valid = true;
        started = seconds; presents = displayed = 0;
    }
};
}
