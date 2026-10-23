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
        l.put({30, 0}, {first, 0, 256, 1});
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
        require(quote("a\"\\\n\x01") == "\"a\\\"\\\\\\u000a\\u0001\"", "JSON control/path escaping failed");
        std::cout << "PASS: lifetime reuse, stale views, descriptor overlap, missing sources, bounds, JSON escaping\n";
        return 0;
    } catch (const std::exception &e) { std::cerr << e.what() << '\n'; return 1; }
}
