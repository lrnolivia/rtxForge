#pragma once
#include <algorithm>
#include <cmath>

namespace Motion {
inline float Spring(float t) {t=std::clamp(t,0.f,1.f);return t>=1?1.f:1-std::exp(-7*t)*(std::cos(9*t)+.78f*std::sin(9*t));}
inline void Coast(float& position,float& velocity,float limit,float elapsed) {
    const int steps=std::max(1,int(std::ceil(elapsed/.008f)));const float dt=std::min(elapsed,.05f)/steps;
    for(int i=0;i<steps;i++) {
        if(position<8 || position>limit) {const float edge=std::clamp(position,8.f,std::max(8.f,limit));velocity+=(-180*(position-edge)-26.8f*velocity)*dt;}
        else velocity*=std::exp(-6.5f*dt);
        position+=velocity*dt;position=std::clamp(position,0.f,std::max(8.f,limit)+8);
    }
    if(std::fabs(velocity)<3){position=std::clamp(position,8.f,std::max(8.f,limit));velocity=0;}
}
}
