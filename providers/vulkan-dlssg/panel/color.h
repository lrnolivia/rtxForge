#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>

namespace fgvk::panel {
inline double Linear(double x) { return x <= .04045 ? x / 12.92 : std::pow((x + .055) / 1.055, 2.4); }
inline double PQ(double nits) {
    const double p = std::pow(std::clamp(nits / 10000., 0., 1.), 2610. / 16384.);
    return std::pow((3424. / 4096. + 2413. / 128. * p) / (1. + 2392. / 128. * p), 2523. / 32.);
}
// The panel contains solid colours and the white font atlas. Preserve coverage
// alpha; encode its sRGB colours for the host's post-tonemap HDR10 attachment.
inline uint32_t HDR10(uint32_t color) {
    const double r = Linear((color & 255) / 255.);
    const double g = Linear(((color >> 8) & 255) / 255.);
    const double b = Linear(((color >> 16) & 255) / 255.);
    const auto channel = [](double value) { return uint32_t(std::lround(PQ(value * 203.) * 255.)); };
    return (color & 0xff000000u) | channel(.627404*r + .329283*g + .043313*b)
        | channel(.069097*r + .91954*g + .011362*b) << 8
        | channel(.016391*r + .088013*g + .895595*b) << 16;
}
}
