#pragma once
#include <array>
#include <algorithm>
#include <cmath>
#include <string>
#include <vector>

namespace MaterialColor {
using Color=std::array<float,3>;
inline const std::vector<std::string> Modes={"normal","overlay","soft-light","reserved","multiply","screen","hard-light","darken","lighten","color","luminosity","difference"};
inline int Mode(const std::string& name) {for(size_t i=0;i<Modes.size();++i)if(name==Modes[i] && i!=3)return int(i);return 0;}
inline bool Valid(const std::string& name) {return name!="reserved" && std::find(Modes.begin(),Modes.end(),name)!=Modes.end();}
inline float Luma(Color c) {return .3f*c[0]+.59f*c[1]+.11f*c[2];}
inline Color SetLuma(Color c,float l) {
    const float delta=l-Luma(c);for(auto& v:c)v+=delta;
    const float n=*std::min_element(c.begin(),c.end()),x=*std::max_element(c.begin(),c.end());
    if(n<0)for(auto& v:c)v=l+(v-l)*l/std::max(l-n,.00001f);
    if(x>1)for(auto& v:c)v=l+(v-l)*(1-l)/std::max(x-l,.00001f);
    for(auto& v:c)v=std::clamp(v,0.f,1.f);return c;
}
inline Color Blend(Color d,Color s,int mode) {
    if(mode==9)return SetLuma(s,Luma(d));
    if(mode==10)return SetLuma(d,Luma(s));
    Color out{};
    for(int i=0;i<3;i++){
        const float a=d[i],b=s[i];float v=b;
        switch(mode){
            case 1:v=a<.5f?2*a*b:1-2*(1-a)*(1-b);break;
            case 2:{const float D=a<=.25f?((16*a-12)*a+4)*a:std::sqrt(a);v=b<=.5f?a-(1-2*b)*a*(1-a):a+(2*b-1)*(D-a);break;}
            case 4:v=a*b;break;case 5:v=1-(1-a)*(1-b);break;
            case 6:v=b<.5f?2*a*b:1-2*(1-a)*(1-b);break;
            case 7:v=std::min(a,b);break;case 8:v=std::max(a,b);break;case 11:v=std::fabs(a-b);break;
        }out[i]=v;
    }return out;
}
inline Color ClearSurface(Color backdrop,float tint,int mode,float strength) {
    Color source=backdrop;const float l=.2126f*source[0]+.7152f*source[1]+.0722f*source[2];
    for(auto& v:source){v=l+(v-l)*.65f;v=v*.96f+((l+.5f)*.5f)*.04f;v=v*(1-tint)+.96f*tint;}
    const auto blended=Blend(backdrop,source,mode);
    for(int i=0;i<3;i++)source[i]+= (blended[i]-source[i])*strength;
    return source;
}
inline float LinearLuma(Color c) {for(auto& v:c)v=v<=.04045f?v/12.92f:std::pow((v+.055f)/1.055f,2.4f);return .2126f*c[0]+.7152f*c[1]+.0722f*c[2];}
}
