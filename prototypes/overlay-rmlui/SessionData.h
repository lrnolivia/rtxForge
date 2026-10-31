#pragma once
#include <cmath>
#include <cstdio>
#include <string>
namespace ForgeSession {
// Same evidence fields as ForgePanel::LiveStats, independent of presentation.
// A requested multiplier must never be presented as a measured multiplier.
struct Snapshot {
    bool nrKnown{},nrRunning{},nrWarming{},fgKnown{},fgRunning{},framesKnown{};
    double nrGpuMs{-1},gameFps{-1},displayedFps{-1},measuredRatio{-1};
    unsigned nrWidth{},nrHeight{};
};
inline bool Available(double value) {return std::isfinite(value)&&value>=0;}
inline std::string Number(double value,int decimals=0) {
    if(!Available(value))return "—";
    char text[48];std::snprintf(text,sizeof(text),"%.*f",decimals,value);return text;
}
inline std::string Frames(const Snapshot& s) {
    if(s.fgKnown&&!s.fgRunning)return "Off";
    if(s.framesKnown&&Available(s.gameFps)&&Available(s.displayedFps)&&s.measuredRatio>=1&&s.measuredRatio<=8)
        return Number(s.gameFps)+" → "+Number(s.displayedFps)+" FPS";
    if(Available(s.gameFps))return Number(s.gameFps)+" FPS rendered";
    return s.fgKnown?"Waiting for frames":"—";
}
inline std::string Neural(const Snapshot& s) {
    if(s.nrKnown&&!s.nrRunning)return "Off";
    if(s.nrWarming)return "Warming up";
    return Available(s.nrGpuMs)?Number(s.nrGpuMs,2)+" ms":"—";
}
}
