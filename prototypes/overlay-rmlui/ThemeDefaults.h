#pragma once
namespace ForgeAppearance {
struct Theme {float tint,blur,grain,strength;const char* blend;};
// Lauren's selected material presets. Clear remains the initial appearance.
inline constexpr int Version=4;
inline constexpr Theme Light{100,44,4,35,"overlay"};
inline constexpr Theme Dark{80,48,4,15,"overlay"};
inline constexpr Theme Clear{20,48,4,50,"soft-light"};
inline constexpr Theme Accent{67,48,4,0,"normal"};
inline constexpr Theme Get(int mode) {return mode==1?Light:mode==2?Dark:mode==4?Accent:Clear;}
}
