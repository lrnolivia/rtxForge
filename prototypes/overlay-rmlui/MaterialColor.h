#pragma once
#include <array>
#include <algorithm>
#include <cmath>
#include <string>
#include <vector>

namespace MaterialColor {
using Color=std::array<float,3>;
// Small reusable atlas, created only when the color spectrum is first shown.
inline constexpr int SpectrumSize=32,SpectrumHues=180;
inline Color Hsv(float hue,float saturation,float value) {
    hue=(hue-std::floor(hue))*6;const int sector=int(hue);const float f=hue-sector,p=value*(1-saturation),q=value*(1-saturation*f),t=value*(1-saturation*(1-f));
    switch(sector){case 0:return {value,t,p};case 1:return {q,value,p};case 2:return {p,value,t};case 3:return {p,q,value};case 4:return {t,p,value};default:return {value,p,q};}
}
inline Color ToHsv(Color color) {
    const float high=*std::max_element(color.begin(),color.end()),low=*std::min_element(color.begin(),color.end()),chroma=high-low;float hue=0;
    if(chroma>0){hue=high==color[0]?(color[1]-color[2])/chroma:high==color[1]?2+(color[2]-color[0])/chroma:4+(color[0]-color[1])/chroma;hue/=6;if(hue<0)hue+=1;}
    return {hue,high>0?chroma/high:0,high};
}
inline std::vector<unsigned char> SpectrumTexture(bool hueStrip) {
    const int width=hueStrip?360:SpectrumSize*SpectrumHues,height=hueStrip?1:SpectrumSize;std::vector<unsigned char> pixels(size_t(width)*height*4);
    for(int y=0;y<height;++y)for(int x=0;x<width;++x){const auto color=hueStrip?Hsv(float(x)/(width-1),1,1):Hsv(float(x/SpectrumSize)/SpectrumHues,float(x%SpectrumSize)/(SpectrumSize-1),1-float(y)/(height-1));const size_t at=(size_t(y)*width+x)*4;for(int c=0;c<3;++c)pixels[at+c]=static_cast<unsigned char>(color[c]*255+.5f);pixels[at+3]=255;}
    return pixels;
}
inline bool YellowFamily(Color color);
inline float Smooth(float t){t=std::clamp(t,0.f,1.f);return t*t*(3-2*t);}
inline Color Saturation(Color color,float percent) {
    const float low=*std::min_element(color.begin(),color.end()),high=*std::max_element(color.begin(),color.end());
    const float chroma=high-low,light=(high+low)*.5f;if(chroma<.00001f)return color;
    const float scale=std::min(std::clamp(percent,0.f,200.f)/100.f,std::min(2*light,2-2*light)/chroma);
    for(auto& value:color)value=std::clamp(light+(value-light)*scale,0.f,1.f);return color;
}
inline Color AccentTone(Color color,float lightness) {
    for(auto& v:color)v=v<=.04045f?v/12.92f:std::pow((v+.055f)/1.055f,2.4f);
    const float l=std::cbrt(.4122214708f*color[0]+.5363325363f*color[1]+.0514459929f*color[2]);
    const float m=std::cbrt(.2119034982f*color[0]+.6806995451f*color[1]+.1073969566f*color[2]);
    const float s=std::cbrt(.0883024619f*color[0]+.2817188376f*color[1]+.6299787005f*color[2]);
    const float a=1.9779984951f*l-2.4285922050f*m+.4505937099f*s,b=.0259040371f*l+.7827717662f*m-.8086757660f*s;
    const auto linear=[&](float chroma){const float L=lightness+.3963377774f*a*chroma+.2158037573f*b*chroma,M=lightness-.1055613458f*a*chroma-.0638541728f*b*chroma,S=lightness-.0894841775f*a*chroma-1.2914855480f*b*chroma;return Color{4.0767416621f*L*L*L-3.3077115913f*M*M*M+.2309699292f*S*S*S,-1.2684380046f*L*L*L+2.6097574011f*M*M*M-.3413193965f*S*S*S,-.0041960863f*L*L*L-.7034186147f*M*M*M+1.7076147010f*S*S*S};};
    const auto inGamut=[](Color c){return std::all_of(c.begin(),c.end(),[](float v){return v>=0&&v<=1;});};
    float low=0,high=1;if(!inGamut(linear(1)))for(int i=0;i<14;++i){const float mid=(low+high)*.5f;if(inGamut(linear(mid)))low=mid;else high=mid;}else low=1;
    auto result=linear(low);for(auto& v:result)v=std::clamp(v<=.0031308f?12.92f*v:1.055f*std::pow(v,1.f/2.4f)-.055f,0.f,1.f);return result;
}
inline Color AccentSurface(Color accent,float character,float saturation=100) {
    const float light=Smooth(character/50.f),dark=Smooth((character-50.f)/50.f);
    Color result{};
    // Move perceptual lightness while retaining hue/chroma, rather than diluting
    // both ends with white or gray. Keep vivid yellow out of an olive dark shade.
    const float top=*std::max_element(accent.begin(),accent.end()),bottom=*std::min_element(accent.begin(),accent.end());
    const bool yellow=YellowFamily(accent)&&top>.9f&&top-bottom>.6f;
    const auto deep=AccentTone(accent,.30f);
    for(size_t i=0;i<3;++i){const float clear=.10f+.80f*accent[i],pale=.72f+.25f*accent[i],shade=yellow?.16f+.05f*accent[i]:deep[i];result[i]=(clear+(pale-clear)*light)*(1-dark)+shade*dark;}
    return Saturation(result,saturation);
}
inline float AccentOpacity(float character){return .20f+.60f*Smooth(character/50.f);}
inline bool YellowFamily(Color color) {
    const float top=*std::max_element(color.begin(),color.end()),bottom=*std::min_element(color.begin(),color.end()),delta=top-bottom;
    if(top<=0||delta/top<=.25f)return false;
    float hue=top==color[0]?std::fmod((color[1]-color[2])/delta+6.f,6.f):top==color[1]?(color[2]-color[0])/delta+2.f:(color[0]-color[1])/delta+4.f;
    hue*=60;return hue>=30&&hue<=100;
}
inline bool MuddyShade(Color color){const auto top=*std::max_element(color.begin(),color.end()),bottom=*std::min_element(color.begin(),color.end());return YellowFamily(color)&&top>0&&(top-bottom)/top>.40f&&top<.90f;}
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
inline float Contrast(Color a,Color b) {const float x=LinearLuma(a),y=LinearLuma(b);return (std::max(x,y)+.05f)/(std::min(x,y)+.05f);}
inline Color ClearHeading(Color accent) {
    // Soft, bright ink shared by every heading, never individually sampled.
    return Blend({.58f,.58f,.58f},accent,Mode("screen"));
}
inline bool ValidAccent(const std::string& color) {return color.empty()||(color.size()==7&&color[0]=='#'&&color.find_first_not_of("0123456789abcdefABCDEF",1)==std::string::npos);}
inline Color ParseAccent(const std::string& color,Color fallback) {if(color.empty()||!ValidAccent(color))return fallback;const auto rgb=std::stoul(color.substr(1),nullptr,16);return {float((rgb>>16)&255)/255,float((rgb>>8)&255)/255,float(rgb&255)/255};}
inline Color SceneAccent(Color color) {
    // Keep sampled color recognizable without deriving olive/brown highlights.
    const float top=*std::max_element(color.begin(),color.end());
    if(top>.001f){const float target=YellowFamily(color)?.96f:std::clamp(top,.62f,.94f);for(auto& v:color)v=std::clamp(v*target/top,0.f,1.f);}
    return color;
}
}
