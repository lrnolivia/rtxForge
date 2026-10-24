#include "trace_model.hpp"
#include <iostream>
#include <stdexcept>
using namespace forge::trace;
static void require(bool result, const char *message) { if (!result) throw std::runtime_error(message); }
int main() {
    try {
        Ledger l;
        const auto first = l.create(10, 1920, 1080, 34, 8);
        l.view(20, 10);
        l.view(21, 10);
        l.put({30, 0}, {first, 0, 256, 1});
        l.put({30, 4}, {first, 0, 256, 1});
        l.destroy(10);
        const auto second = l.create(10, 1280, 720, 34, 8);
        require(first != second && !l.alive(first) && l.alive(second), "Native handle reuse aliased resource lifetimes");
        require(l.resolve_view(20) == first, "An old view was rebound to a new resource");
        require(l.get({30, 0}).resource_id == first, "An old descriptor was rebound to a new resource");
        l.put({30, 1}, {second, 64, 256, 1});
        l.put({30, 2}, {second, 128, 256, 1});
        l.copy({30, 0}, {30, 1}, 3);
        require(l.get({30, 2}).offset == 64 && l.get({30, 3}).offset == 128, "Overlapping descriptor copy did not snapshot inputs");
        l.copy({99, 0}, {30, 1}, 1);
        require(l.get({30, 1}).resource_id == 0, "Missing source retained a stale destination");
        l.copy({30, UINT32_MAX}, {30, 0}, 2);
        require(l.dropped == 1, "Overflowing descriptor range was not refused");
        require(l.copy_drops == 1, "Copy range drop reason was lost");
        l.view(20, 0);
        require(l.resolve_view(20) == 0, "A null view retained a stale resource");
        l.put({30, 0}, {});
        require(l.get({30, 0}).resource_id == 0, "A null update retained a stale descriptor");
        l.collect({first});
        require(l.resources.contains(first) && !l.alive(first), "Collection lost pinned capture metadata");
        require(l.get({30, 4}).resource_id == 0 && l.resolve_view(21) == 0, "Collection retained dead bindings");
        l.collect({});
        require(!l.resources.contains(first) && l.alive(second), "Collection lost live metadata or retained dead history");
        l.destroy(10);
        l.collect({});
        const auto third = l.create(10, 640, 360, 34, 8);
        require(third > second && l.resolve_view(20) == 0, "Collection aliased a recycled resource handle");
        Ledger pressure;
        for (std::uint32_t i = 0; i < Ledger::descriptor_limit + 1; ++i) {
            pressure.view(1000 + i, 0);
            pressure.put({1, i}, {});
        }
        require(pressure.views.empty() && pressure.descriptors.empty() && pressure.dropped == 0,
                "Null descriptor initialization exhausted the live catalog");
        const auto scene = pressure.create(10, 320, 180, 10, 8);
        for (std::uint32_t i = 0; i < Ledger::view_limit; ++i) pressure.view(1000 + i, 10);
        pressure.view(1000, 10);
        require(pressure.dropped == 0, "A view replacement was refused at capacity");
        pressure.view(999, 10);
        require(pressure.view_drops == 1, "A view capacity drop was not classified");
        for (std::uint32_t i = 0; i < Ledger::descriptor_limit; ++i) pressure.put({1, i}, {scene, 0, 0, 2});
        pressure.put({1, 0}, {scene, 128, 0, 2});
        require(pressure.get({1, 0}).offset == 128 && pressure.descriptor_drops == 0,
                "A descriptor replacement was refused at capacity");
        pressure.put({1, static_cast<std::uint32_t>(Ledger::descriptor_limit)}, {scene, 0, 0, 2});
        require(pressure.descriptor_drops == 1, "A descriptor capacity drop was not classified");
        require(quote("a\"\\\n\x01") == "\"a\\\"\\\\\\u000a\\u0001\"", "JSON control/path escaping failed");
        std::cout << "PASS: lifetime reuse, stale views, descriptor overlap, null pressure, capacity replacement, bounds, JSON escaping\n";
        return 0;
    } catch (const std::exception &e) { std::cerr << e.what() << '\n'; return 1; }
}
