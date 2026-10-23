#include "state.h"
#include "color.h"
#include <cassert>
#include <cstdio>
#include <thread>
int main() {
    using namespace fgvk::panel;
    Request request; bool off = false;
    assert(!request.Consume(off));
    std::thread writer([&]{ request.Set(false); }); writer.join();
    assert(request.Consume(off) && off); assert(!request.Consume(off));
    request.Set(false); request.Set(true); assert(request.Consume(off) && !off);
    Meter meter;
    for (int n = 0; n < 120; ++n) meter.Observe(1. + n / 60., 2);
    assert(meter.valid && std::abs(meter.ratio - 2) < .00001);
    assert(meter.gameFPS > 59 && meter.gameFPS < 61);
    meter.Reset(); assert(!meter.valid);
    for (int n = 0; n < 120; ++n) meter.Observe(5. + n / 60., 1);
    assert(meter.valid && std::abs(meter.ratio - 1) < .00001);
    meter.Observe(20, 2); assert(!meter.valid); // a focus/stall gap invalidates old telemetry
    assert((HDR10(0x7fffffff) >> 24) == 0x7f);
    assert((HDR10(0xff000000) & 0xffffff) == 0);
    const auto white = HDR10(0xffffffff);
    assert((white & 255) >= 147 && (white & 255) <= 149);
    assert(std::abs(int(white & 255) - int((white >> 8) & 255)) <= 1);
    assert(PQ(100) < PQ(203) && PQ(203) < PQ(1000));
    puts("Panel requests, observed frame telemetry, focus gaps and HDR10 colour checks: PASS");
}
