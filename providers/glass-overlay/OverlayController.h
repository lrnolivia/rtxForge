#pragma once
#include <windows.h>
#include <RmlUi/Core.h>
#include <RmlUi/Core/Elements/ElementFormControl.h>
#include <ForgeWorkbench.h>
#include "../../prototypes/overlay-rmlui/Backdrop.h"
#include "../../prototypes/overlay-rmlui/MaterialColor.h"
#include "../../prototypes/overlay-rmlui/Motion.h"
#include "../../prototypes/overlay-rmlui/ThemeDefaults.h"
#include "../../prototypes/overlay-rmlui/SessionData.h"
#include <PrototypeControls.generated.h>
#include <filesystem>
#include <map>
#include <functional>
#include <unordered_set>
#include <stdexcept>
namespace ForgeGlass {
namespace fs=std::filesystem;
inline void Require(bool ok,const char* message) {if(!ok)throw std::runtime_error(message);}
inline std::string Utf8(const std::wstring& value) {return fs::path(value).generic_string();}
struct Controller : Rml::EventListener
{
    Rml::ElementDocument* document{};
    ForgeWorkbench::Values values{{"intensity",1},{"style",1},{"multiplier",-1},{"dynamic_mfg",0},{"passes",3},{"preset",0},
        {"detail",1},{"colour",1},{"tone",1},{"pass2_strength",.65f},{"pass2_tone",.8f},{"pass2_structure",1},{"pass2_skin",.5f},{"pass2_inherit",0},{"pass2_style",0},
        {"pass3_strength",1},{"pass3_tone",1},{"pass3_structure",1},{"pass3_skin",-1},{"pass3_inherit",1},{"pass3_style",0},{"enabled",1},{"mfg_enabled",1}};
    ForgeWorkbench::Values defaults=values;
    ForgeWorkbench::Edits edits;
    std::map<std::string,ForgeWorkbench::Values> presets;
    bool preview=true;std::function<bool(const std::string&)> savePreset,deletePreset,requestJson;int reviewId=0;bool helperEnabled=true,startWithWindows=false;
    std::string compareMode="toggle",compareLeft="natural",compareRight="cinematic";
    std::map<std::string,const ExtraControl*> extraFields;
    void InstallExtraControls() {
        for(const auto& control:ExtraControls)if(!values.contains(control.key))values[control.key]=control.initial;defaults=values;
        const auto install=[&](const char* container,const char* page,const std::string& prefix) {
            std::vector<std::string> groups;for(const auto& c:ExtraControls)if(std::string(c.page)==page && std::find(groups.begin(),groups.end(),c.section)==groups.end())groups.push_back(c.section);
            std::string markup;int index=0;
            for(const auto& group:groups){const auto body=prefix+"body-"+std::to_string(index);std::string title=group;for(auto& ch:title)ch=char(std::toupper(static_cast<unsigned char>(ch)));
                markup+="<div class=\"option-group\"><button id=\"group-toggle-"+body+"\" class=\"group-heading\"><img class=\"glyph\" src=\"icons/sliders-horizontal-light.png\"/>"+title+"<span class=\"chevron\"/></button><div id=\""+body+"\" class=\"group-body\""+(index==0 && std::string(page)!="look"?"":" style=\"display: none\"")+">";
                for(const auto& c:ExtraControls)if(std::string(c.page)==page && c.section==group){const auto id=prefix+c.key;extraFields[id]=&c;const auto label=Rml::StringUtilities::EncodeRml(c.label);const auto reset="<button id=\"reset-"+id+"\" class=\"reset-value\" title=\"Reset value\"><img class=\"glyph\" src=\"icons/arrow-counter-clockwise-light.png\"/></button>";
                    if(std::string(c.kind)=="toggle")markup+="<div class=\"inherit-row option-toggle\"><label>"+label+"</label><button id=\""+id+"\" class=\"switch\"><span/></button>"+reset+"</div>";
                    else if(std::string(c.kind)=="choice")markup+="<div class=\"slider-field\"><div class=\"field-heading\"><label>"+label+"</label>"+reset+"</div><select id=\""+id+"\">"+c.options+"</select></div>";
                    else markup+="<div class=\"slider-field\"><div class=\"field-heading\"><label>"+label+"</label><span id=\""+id+"-value\"/>"+reset+"</div><input id=\""+id+"\" class=\"range\" type=\"range\" min=\""+std::to_string(c.minimum)+"\" max=\""+std::to_string(c.maximum)+"\" step=\""+std::to_string(c.step)+"\" value=\""+std::to_string(values.at(c.key))+"\"/></div>";
                }if(group=="Area")markup+="<p class=\"hint\">Uses distance, not character recognition.</p>";markup+="</div></div>";++index;
            }Element(container)->SetInnerRML(markup);
        };
        install("extra-neural","neural","extra-main-");install("extra-frame","frame","extra-frame-");install("extra-look","look","extra-look-");install("extra-processing","neural","extra-popup-");install("extra-frame-popup","frame","extra-fgpopup-");
    }
    void PrepareComparison() {if(compareMode=="presets"&&(!presets.contains(compareLeft)||!presets.contains(compareRight))){compareMode="toggle";Message("Save two compatible presets to compare them.");}edits.EndComparison(values);edits.a=compareMode=="presets"?presets.at(compareLeft):values;edits.b=compareMode=="presets"?presets.at(compareRight):values;if(compareMode=="toggle"){edits.a["enabled"]=0;edits.b["enabled"]=1;}edits.comparing=true;edits.side=1;values=edits.b;}
    int pass=2;
    int appearance=3;
    std::array<float,3> accent{.19f,.46f,.80f};
    std::array<Backdrop::SceneColor,4> filtered;
    std::array<bool,4> panelDark{};
    double lastAdapt=-1;
    bool dark=false, syncing=false;
    std::string inspectorPanel="passes";
    std::string layout="floating";
    Rml::Element* dragged=nullptr;
    Rml::Vector2f dragStart{},dragOrigin{};
    std::vector<std::string> stacking{"main-panel","inspector","welcome","type-panel"};
    std::string copyFont="roboto",headingFont="bakbak";
    int copySize=22,copyWeight=500,headingSize=36,headingWeight=400,overlayScale=100;
    float lightOpacity=100,darkOpacity=80,clearOpacity=20,blurRadius=48,grainAmount=4.f,blendStrength=50;
    std::string surfaceBlend="soft-light";
    bool inspectorAnchored=false,prefsDirty=false,customTheme=false,moreOpen=false,textDepth=true,invertDark=false,toastPill=false,motionEnabled=true;
    int sceneRequest=-1;
    bool showStats=true,showWelcome=true,showNotifications=true,bindingShortcut=false,settingsOpen=false;
    int shortcut=Rml::Input::KI_DELETE,shortcutModifiers=0;
    std::string shortcutLabel="Del",welcomePosition="top-right",primaryMenu="game",optiShortcut="Insert";
    std::map<std::string,bool> menuSettings{{"opti-menu",true},{"opti-intro",false},{"reshade-menu",true},{"reshade-intro",false}};
    ForgeSession::Snapshot session;
    void Welcome() {if(!showWelcome)return;Element("toast-message")->SetInnerRML("Press <span class=\"keycap\">"+Rml::StringUtilities::EncodeRml(shortcutLabel)+"</span> for controls");Element("welcome")->SetProperty("width","500dp");Visible("welcome",true);Raise("welcome");Enter("welcome");toastUntil=0;}
    void ToggleOverlay() {const bool show=!Element("main-panel")->IsVisible();Visible("main-panel",show);if(show){Raise("main-panel");Enter("main-panel");}else{Visible("inspector",false);Visible("type-panel",false);Welcome();}}
    void Settings(bool show) {
        if(layout=="bar"){entrances.erase("main-panel");pendingEntrance.erase("main-panel");coasting.erase("main-panel");for(const auto* prop:{"left","top","margin-left","margin-top"})Element("main-panel")->RemoveProperty(prop);}
        settingsOpen=show;document->SetClass("settings-page",show);Visible("settings-screen",show);Visible("overview",!show);Visible("inspector",false);Element("settings-screen")->SetScrollTop(0);SyncSettings();}
    void SyncSettings() {const bool was=typographySync;typographySync=true;for(const auto& [id,on]:menuSettings)Element(("setting-"+id).c_str())->SetClass("on",on);Element("setting-helper")->SetClass("on",helperEnabled);Element("setting-startup")->SetClass("on",startWithWindows);Element("setting-stats")->SetClass("on",showStats);Element("setting-welcome")->SetClass("on",showWelcome);Element("setting-notifications")->SetClass("on",showNotifications);Element("shortcut-key")->SetInnerRML(bindingShortcut?"…":Rml::StringUtilities::EncodeRml(shortcutLabel));dynamic_cast<Rml::ElementFormControl*>(Element("welcome-position"))->SetValue(welcomePosition);dynamic_cast<Rml::ElementFormControl*>(Element("primary-menu"))->SetValue(primaryMenu);dynamic_cast<Rml::ElementFormControl*>(Element("opti-shortcut"))->SetValue(optiShortcut);PositionWelcome();typographySync=was;}
    void Session(const ForgeSession::Snapshot& snapshot) {session=snapshot;Element("compact-frames")->SetInnerRML(ForgeSession::Frames(snapshot));Element("compact-neural")->SetInnerRML(ForgeSession::Neural(snapshot));Element("compact-ratio")->SetInnerRML(snapshot.framesKnown&&snapshot.measuredRatio>=1&&snapshot.measuredRatio<=8?ForgeSession::Number(snapshot.measuredRatio,1)+"×":"");for(const auto* p:{"overview","popup"}){const std::string prefix=p;Element((prefix+"-nr").c_str())->SetInnerRML(ForgeSession::Neural(snapshot));Element((prefix+"-frame").c_str())->SetInnerRML(ForgeSession::Available(snapshot.gameFps)&&snapshot.gameFps>0?ForgeSession::Number(1000/snapshot.gameFps,2)+" ms":"—");Element((prefix+"-rendered").c_str())->SetInnerRML(ForgeSession::Number(snapshot.gameFps));Element((prefix+"-displayed").c_str())->SetInnerRML(snapshot.framesKnown?ForgeSession::Number(snapshot.displayedFps):"—");}if(showStats)Element("compact-live")->RemoveProperty("display");else Element("compact-live")->SetProperty("display","none");}
    void PositionWelcome() {
        if(welcomePosition!="top-right"&&welcomePosition!="top-left"&&welcomePosition!="top-center"&&welcomePosition!="bottom-right"&&welcomePosition!="bottom-left")welcomePosition="top-right";
        entrances.erase("welcome");pendingEntrance.erase("welcome");coasting.erase("welcome");
        for(const auto* prop:{"left","right","top","bottom","margin-left","margin-top"})Element("welcome")->RemoveProperty(prop);
        const bool bottom=welcomePosition.rfind("bottom",0)==0;Element("welcome")->SetProperty(bottom?"bottom":"top","32dp");Element("welcome")->SetProperty(bottom?"top":"bottom","auto");
        Element("welcome")->SetProperty("left",welcomePosition.find("left")!=std::string::npos?"32dp":welcomePosition=="top-center"?"50vw":"auto");Element("welcome")->SetProperty("right",welcomePosition.find("right")!=std::string::npos?"32dp":"auto");if(welcomePosition=="top-center")Element("welcome")->SetProperty("margin-left","-250dp");
    }
    void Metadata() {const auto view=document->GetContext()->GetDimensions();const auto size=std::to_string(view.x)+" × "+std::to_string(view.y);for(const auto* id:{"compact-size","overview-size","popup-size"})Element(id)->SetInnerRML(size);}
    double toastUntil=0;
    void Notify(const std::string& text) {if(!showNotifications)return;Element("toast-message")->SetInnerRML(Rml::StringUtilities::EncodeRml(text));Element("welcome")->SetProperty("width",std::to_string(std::clamp(234+int(text.size())*8,420,760))+"dp");Visible("welcome",true);Raise("welcome");Enter("welcome");toastUntil=Rml::GetSystemInterface()->GetElapsedTime()+3.;}
    bool reducedMotion=false;
    float inspectorAnchorX=0;
    struct Entrance {double start;Rml::Vector2f target;float previous;};
    struct Coast {Rml::Vector2f position,velocity;std::string follower;Rml::Vector2f offset;};
    std::map<std::string,Entrance> entrances;
    std::map<std::string,Coast> coasting;
    std::map<std::string,Rml::Vector2f> windowVelocity;
    std::unordered_set<std::string> pendingEntrance;
    double lastAnimation=-1,dragTime=0;
    Rml::Vector2f dragLast{},dragVelocity{};
    void Enter(const std::string& id) {pendingEntrance.insert(id);coasting.erase(id);}
    void Animate(double now) {
        const float dt=lastAnimation<0?1.f/60:std::clamp(float(now-lastAnimation),.001f,.05f);lastAnimation=now;
        if(!pendingEntrance.empty()){document->GetContext()->Update();for(const auto& id:pendingEntrance){auto* e=Element(id.c_str());const auto at=e->GetAbsoluteOffset(Rml::BoxArea::Border);e->SetProperty("margin-left","0px");e->SetProperty("margin-top","0px");e->SetProperty("left",std::to_string(at.x)+"px");e->SetProperty("top",std::to_string(at.y)+"px");entrances[id]={now,at,0};}pendingEntrance.clear();}
        for(auto it=entrances.begin();it!=entrances.end();) {const float t=reducedMotion?1.f:std::clamp(float((now-it->second.start)/.38),0.f,1.f);const float lift=(it->first=="welcome"?-14.f:24.f)*document->GetContext()->GetDensityIndependentPixelRatio()*(1-Motion::Spring(t));auto* e=Element(it->first.c_str());const float opacity=std::min(1.f,t*2.2f);e->SetProperty("opacity",std::to_string(opacity));e->SetProperty("--window-opacity",std::to_string(opacity));e->SetProperty("top",std::to_string(it->second.target.y+lift)+"px");windowVelocity[it->first]={0,(lift-it->second.previous)/dt};it->second.previous=lift;if(t>=1){windowVelocity[it->first]={};it=entrances.erase(it);}else ++it;}
        for(auto it=coasting.begin();it!=coasting.end();){auto* e=Element(it->first.c_str());auto& m=it->second;const auto view=document->GetContext()->GetDimensions();const auto size=e->GetBox().GetSize(Rml::BoxArea::Border);if(reducedMotion)m.velocity={};else{Motion::Coast(m.position.x,m.velocity.x,view.x-size.x-8,dt);Motion::Coast(m.position.y,m.velocity.y,view.y-size.y-8,dt);}e->SetProperty("left",std::to_string(m.position.x)+"px");e->SetProperty("top",std::to_string(m.position.y)+"px");windowVelocity[it->first]=m.velocity;if(!m.follower.empty()){auto* f=Element(m.follower.c_str());f->SetProperty("left",std::to_string(m.position.x+m.offset.x)+"px");f->SetProperty("top",std::to_string(m.position.y+m.offset.y)+"px");windowVelocity[m.follower]=m.velocity;}if(m.velocity.x==0 && m.velocity.y==0)it=coasting.erase(it);else ++it;}
    }
    Rml::Element* dragFollower=nullptr;
    Rml::Vector2f followerOrigin{};
    float followerAnchorOrigin=0;
    fs::path preferences;
    bool typographySync=false;
    std::map<Rml::Element*,MaterialColor::Foreground> foreground;
    double lastForeground=-1;
    void AdaptiveForeground(const Backdrop& backdrop,double now) {
        const float dt=lastForeground<0?.1f:float(now-lastForeground);lastForeground=now;
        if(appearance!=3){Rml::ElementList current;document->QuerySelectorAll(current,"h1,h2,label,.hint,.brand,.welcome-wordmark,.welcome-message,.preview-note,button,select,.field-heading span,.status-note,.glyph");for(auto* e:current){if(foreground.contains(e)){e->RemoveProperty("color");e->RemoveProperty("image-color");e->RemoveProperty("font-effect");}}foreground.clear();return;}
        Rml::ElementList elements;document->QuerySelectorAll(elements,"h1,h2,label,.hint,.brand,.welcome-wordmark,.welcome-message,.preview-note,button,select,.field-heading span,.status-note,.glyph");
        const std::unordered_set<Rml::Element*> alive(elements.begin(),elements.end());std::erase_if(foreground,[&](const auto& pair){return !alive.contains(pair.first);});
        for(auto* e:elements){if(!e->IsVisible())continue;bool panel=false,menu=false;for(auto* p=e;p;p=p->GetParentNode()){if(p->IsClassSet("glass"))panel=true;if(p->GetId()=="settings-menu"||p->GetTagName()=="selectbox")menu=true;}if(!panel||menu)continue;
            const auto at=e->GetAbsoluteOffset(Rml::BoxArea::Border),size=e->GetBox().GetSize(Rml::BoxArea::Border);const auto c=backdrop.Background(at.x,at.y,size.x,size.y);if(!c.valid)continue;
            const auto surface=MaterialColor::ClearSurface({c.r,c.g,c.b},clearOpacity/100.f,MaterialColor::Mode(surfaceBlend),blendStrength/100.f);
            const float mix=foreground[e].Update(MaterialColor::LinearLuma(surface),dt,reducedMotion,textDepth);std::string color;
            if(e->GetTagName()=="h1"||e->GetTagName()=="h2")color=Hex(accent[0]*(.55f-.15f*mix)+.60f*mix,accent[1]*(.55f-.15f*mix)+.60f*mix,accent[2]*(.55f-.15f*mix)+.60f*mix);
            else color=Hex(.12f+.84f*mix,.11f+.84f*mix,.10f+.84f*mix);
            auto& state=foreground[e];if(state.lastColor!=color){e->SetProperty(e->IsClassSet("glyph")?"image-color":"color",color);state.lastColor=color;}
            const int bucket=int(std::round(mix*4));const float shade=1-bucket*.25f;const std::string effect=textDepth && !e->IsClassSet("glyph")?"glow(0dp 2dp 0dp "+std::string(bucket>=2?"1dp ":"0dp ")+Hex(shade,shade,shade,.40f)+")":"none";
            if(state.lastEffect!=effect){e->SetProperty("font-effect",effect);state.lastEffect=effect;}
        }
    }
    void Raise(const std::string& id) {
        std::erase(stacking,id);stacking.push_back(id);
        if(layout=="centered" && id=="main-panel" && Element("inspector")->IsVisible()) {std::erase(stacking,std::string("inspector"));stacking.push_back("inspector");}
        for(size_t i=0;i<stacking.size();++i)Element(stacking[i].c_str())->SetProperty("z-index",std::to_string(i+1));
    }
    void UseTheme(int mode) {
        const auto theme=ForgeAppearance::Get(mode);appearance=mode;customTheme=false;
        lightOpacity=ForgeAppearance::Light.tint;darkOpacity=ForgeAppearance::Dark.tint;clearOpacity=ForgeAppearance::Clear.tint;
        blurRadius=theme.blur;grainAmount=theme.grain;surfaceBlend=theme.blend;blendStrength=theme.strength;invertDark=false;textDepth=true;Materials();
    }
    void ShowAppearance() {
        Visible("type-panel",true);Raise("type-panel");document->GetContext()->Update();
        const auto at=Element("main-panel")->GetAbsoluteOffset(Rml::BoxArea::Border),main=Element("main-panel")->GetBox().GetSize(Rml::BoxArea::Border),size=Element("type-panel")->GetBox().GetSize(Rml::BoxArea::Border);const auto view=document->GetContext()->GetDimensions();
        Element("type-panel")->SetProperty("left",std::to_string(std::clamp(at.x+main.x+24,12.f,std::max(12.f,view.x-size.x-12)))+"px");Element("type-panel")->SetProperty("top",std::to_string(std::clamp(layout=="bar"?at.y-size.y-20:at.y,12.f,std::max(12.f,view.y-size.y-12)))+"px");Enter("type-panel");
    }
    void Materials() {
        if(typographySync)return;typographySync=true;
        const float opacity=appearance==1?lightOpacity:appearance==3?clearOpacity:darkOpacity;
        dynamic_cast<Rml::ElementFormControl*>(Element("tint-opacity"))->SetValue(std::to_string(opacity));
        Element("tint-opacity-value")->SetInnerRML(std::to_string(int(opacity))+"%");
        dynamic_cast<Rml::ElementFormControl*>(Element("surface-blend"))->SetValue(surfaceBlend);
        dynamic_cast<Rml::ElementFormControl*>(Element("blur-radius"))->SetValue(std::to_string(blurRadius));Element("blur-radius-value")->SetInnerRML(std::to_string(int(blurRadius))+" px");
        dynamic_cast<Rml::ElementFormControl*>(Element("grain-amount"))->SetValue(std::to_string(grainAmount));char grain[24];std::snprintf(grain,sizeof(grain),"%.1f%%",grainAmount);Element("grain-amount-value")->SetInnerRML(grain);
        dynamic_cast<Rml::ElementFormControl*>(Element("blend-strength"))->SetValue(std::to_string(blendStrength));Element("blend-strength-value")->SetInnerRML(std::to_string(int(blendStrength))+"%");dynamic_cast<Rml::ElementFormControl*>(Element("blend-strength"))->SetDisabled(surfaceBlend=="normal");
        Element("text-depth")->SetClass("on",textDepth);Element("dark-inverted")->SetClass("on",invertDark);Element("motion-effects")->SetClass("on",motionEnabled);
        Visible("dark-inversion-row",appearance==2);Visible("appearance-details",moreOpen);Element("appearance-more")->SetClass("expanded",moreOpen);
        Element("toast-pill")->SetClass("selected",toastPill);Element("toast-rounded")->SetClass("selected",!toastPill);
        Element("theme-label")->SetInnerRML(customTheme?"Custom":appearance==1?"Light":appearance==2?"Dark":"Clear");Element("theme-description")->SetInnerRML(customTheme?(appearance==1?"Custom · based on Light":appearance==2?"Custom · based on Dark":"Custom · based on Clear"):"Select a theme to restore its defaults.");
        document->SetClass("dark-inverted",appearance==2 && invertDark);Element("welcome")->SetProperty("--corner-radius",toastPill?"28":"14");Element("welcome")->SetProperty("border-radius",toastPill?"28dp":"14dp");
        typographySync=false;prefsDirty=true;
    }
    void LoadPreferences(bool runtime=false) {
        wchar_t folder[32768]{};if(!GetEnvironmentVariableW(L"LOCALAPPDATA",folder,32768))return;
        preferences=fs::path(folder)/(runtime?L"rtxForge/overlay-appearance.ini":L"rtxForge/prototypes/overlay-rmlui.ini");
        const auto number=[&](const wchar_t* key,int fallback,int low,int high){return std::clamp(int(GetPrivateProfileIntW(L"Appearance",key,fallback,preferences.c_str())),low,high);};
        copySize=number(L"TextSize",22,16,26);copyWeight=number(L"TextWeight",500,100,900);headingSize=36;headingWeight=400;overlayScale=number(L"ScaleBaseline",0,0,120)==120?number(L"Scale",100,70,150):100;
        const bool current=number(L"ThemeVersion",0,0,ForgeAppearance::Version)==ForgeAppearance::Version;
        appearance=current?number(L"Theme",3,1,3):3;
        const auto theme=ForgeAppearance::Get(appearance);
        lightOpacity=current?float(number(L"LightTint",100,0,100)):100;darkOpacity=current?float(number(L"DarkTint",80,0,100)):80;clearOpacity=current?float(number(L"ClearTint",20,0,100)):20;
        blurRadius=current?float(number(L"Blur",int(theme.blur),16,48)):theme.blur;grainAmount=current?number(L"Grain",40,0,80)/10.f:4;
        customTheme=current&&number(L"Custom",0,0,1)!=0;textDepth=number(L"TextDepth",1,0,1)!=0;invertDark=number(L"InvertDark",0,0,1)!=0;toastPill=number(L"ToastPill",0,0,1)!=0;motionEnabled=number(L"Motion",1,0,1)!=0;
        blendStrength=current?float(number(L"BlendStrength",int(theme.strength),0,100)):theme.strength;surfaceBlend=theme.blend;
        showStats=number(L"ShowStats",1,0,1)!=0;showWelcome=number(L"ShowWelcome",1,0,1)!=0;showNotifications=number(L"ShowNotifications",1,0,1)!=0;
        shortcut=number(L"Shortcut",Rml::Input::KI_DELETE,0,255);shortcutModifiers=number(L"ShortcutModifiers",0,0,7);
        for(auto& [key,on]:menuSettings)on=number(fs::path("Menu-"+key).c_str(),on,0,1)!=0;
        wchar_t text[80]{};GetPrivateProfileStringW(L"Appearance",L"HeadingFont",L"bakbak",text,80,preferences.c_str());const auto heading=Utf8(text);if(heading=="bakbak"||heading=="roboto"||heading=="inter"||heading=="aptos")headingFont=heading;
        GetPrivateProfileStringW(L"Appearance",L"TextFont",L"roboto",text,80,preferences.c_str());const auto copy=Utf8(text);if(copy=="roboto"||copy=="inter"||copy=="aptos")copyFont=copy;
        if(current){GetPrivateProfileStringW(L"Appearance",L"SurfaceBlend",fs::path(theme.blend).c_str(),text,80,preferences.c_str());const auto blend=Utf8(text);if(MaterialColor::Valid(blend))surfaceBlend=blend;}
        GetPrivateProfileStringW(L"Appearance",L"ShortcutLabel",L"Del",text,80,preferences.c_str());shortcutLabel=Utf8(text);
        GetPrivateProfileStringW(L"Appearance",L"WelcomePosition",L"top-right",text,80,preferences.c_str());welcomePosition=Utf8(text);
        GetPrivateProfileStringW(L"Appearance",L"PrimaryMenu",L"game",text,80,preferences.c_str());primaryMenu=Utf8(text)=="optiscaler"?"optiscaler":"game";
        GetPrivateProfileStringW(L"Appearance",L"OptiShortcut",L"Insert",text,80,preferences.c_str());optiShortcut=Utf8(text)=="F8"?"F8":Utf8(text)=="Disabled"?"Disabled":"Insert";
        GetPrivateProfileStringW(L"Appearance",L"Layout",L"floating",text,80,preferences.c_str());const auto savedLayout=Utf8(text);if(savedLayout=="floating"||savedLayout=="centered"||savedLayout=="bar")layout=savedLayout;
    }
    void SavePreferences() {
        if(preferences.empty())return;fs::create_directories(preferences.parent_path());
        const auto put=[&](const wchar_t* key,int value){const auto text=std::to_wstring(value);WritePrivateProfileStringW(L"Appearance",key,text.c_str(),preferences.c_str());};
        put(L"TextSize",copySize);put(L"TextWeight",copyWeight);put(L"HeadingSize",headingSize);put(L"HeadingWeight",headingWeight);put(L"Scale",overlayScale);put(L"Theme",appearance);put(L"LightTint",int(lightOpacity));put(L"DarkTint",int(darkOpacity));
        put(L"ThemeVersion",ForgeAppearance::Version);put(L"ScaleBaseline",120);put(L"Custom",customTheme);put(L"TextDepth",textDepth);put(L"InvertDark",invertDark);put(L"ToastPill",toastPill);put(L"Motion",motionEnabled);put(L"Grain",int(grainAmount*10));put(L"BlendStrength",int(blendStrength));put(L"ClearTint",int(clearOpacity));put(L"Blur",int(blurRadius));
        WritePrivateProfileStringW(L"Appearance",L"HeadingFont",fs::path(headingFont).c_str(),preferences.c_str());WritePrivateProfileStringW(L"Appearance",L"SurfaceBlend",fs::path(surfaceBlend).c_str(),preferences.c_str());prefsDirty=false;
        WritePrivateProfileStringW(L"Appearance",L"TextFont",fs::path(copyFont).c_str(),preferences.c_str());
        put(L"ShowStats",showStats);put(L"ShowWelcome",showWelcome);put(L"ShowNotifications",showNotifications);put(L"Shortcut",shortcut);put(L"ShortcutModifiers",shortcutModifiers);
        for(const auto& [key,on]:menuSettings)put(fs::path("Menu-"+key).c_str(),on);
        for(const auto& [key,value]:std::map<std::wstring,std::string>{{L"ShortcutLabel",shortcutLabel},{L"WelcomePosition",welcomePosition},{L"PrimaryMenu",primaryMenu},{L"OptiShortcut",optiShortcut},{L"Layout",layout}})WritePrivateProfileStringW(L"Appearance",key.c_str(),fs::path(value).c_str(),preferences.c_str());
    }
    void Typography() {
        if(typographySync)return;typographySync=true;
        headingFont="bakbak";copyWeight=500;headingWeight=400;headingSize=copySize+14;
        document->GetContext()->SetDensityIndependentPixelRatio(1.2f*overlayScale/100.f);
        document->SetProperty("--copy-font",copyFont=="aptos"?"Overlay UI":copyFont=="inter"?"Inter Variable":"Roboto");document->SetProperty("--heading-font","Bakbak One");
        document->SetProperty("--copy-weight","500");document->SetProperty("--heading-weight","400");
        document->SetProperty("--copy-size",std::to_string(copySize)+"dp");document->SetProperty("--heading-size",std::to_string(headingSize)+"dp");document->SetProperty("--section-size",std::to_string(headingSize-10)+"dp");document->SetProperty("--hint-size",std::to_string(copySize-4)+"dp");document->SetProperty("--value-size",std::to_string(copySize-3)+"dp");
        dynamic_cast<Rml::ElementFormControl*>(Element("font-select"))->SetValue(copyFont);Element("scale-value")->SetInnerRML(std::to_string(overlayScale)+"%");
        for(const auto* id:{"text-smaller","text-default","text-larger"})Element(id)->SetClass("selected",copySize==(std::string(id)=="text-smaller"?20:std::string(id)=="text-larger"?24:22));
        typographySync=false;prefsDirty=true;
    }
    void Layout(const std::string& mode) {
        Settings(false);prefsDirty=true;
        layout=mode;document->SetClass("overview-page",mode=="centered");document->SetClass("layout-centered",mode=="centered");document->SetClass("layout-bar",mode=="bar");
        document->SetClass("frame-page",false);document->SetClass("neural-page",false);
        for(const auto* id:{"main-panel","inspector"})for(const auto* property:{"left","top","margin-left","margin-top"})Element(id)->RemoveProperty(property);
        inspectorAnchored=false;
        Visible("overview",true);Visible("inspector",false);Select("layout-switch","layout-"+mode);
        Enter("main-panel");
        document->GetContext()->Update();
    }
    static std::string Hex(float r,float g,float b,float a=1) {char text[16];std::snprintf(text,sizeof(text),"#%02x%02x%02x%02x",int(std::clamp(r,0.f,1.f)*255),int(std::clamp(g,0.f,1.f)*255),int(std::clamp(b,0.f,1.f)*255),int(std::clamp(a,0.f,1.f)*255));return text;}
    static float Luma(Backdrop::SceneColor c) {const auto linear=[](float x){return x<=.04045f?x/12.92f:std::pow((x+.055f)/1.055f,2.4f);};return .2126f*linear(c.r)+.7152f*linear(c.g)+.0722f*linear(c.b);}
    void Adapt(const std::array<Backdrop::SceneColor,4>& colors,double now)
    {
        const float amount=lastAdapt<0 ? 1.f:float(1-std::exp(-std::clamp(now-lastAdapt,0.,.1)/.65));lastAdapt=now;
        for(size_t i=0;i<4;++i) {
            auto& c=filtered[i];const bool first=!c.valid;
            if(colors[i].valid) {if(first)c=colors[i];else{c.r+=(colors[i].r-c.r)*amount;c.g+=(colors[i].g-c.g)*amount;c.b+=(colors[i].b-c.b)*amount;}}
            const float light=c.valid?Luma(c):.4f;
            const bool isDark=appearance==2 || (appearance==3 && (first?light<.18f:panelDark[i]?light<.20f:light<.16f));
            panelDark[i]=isDark;auto* e=Element(i==0?"main-panel":i==1?"inspector":i==2?"welcome":"type-panel");e->SetClass("dark",isDark);
            // Constrain the neutral base. Scene chroma comes through the blurred
            // layer; the material's tone does not add a blue cast of its own.
            e->SetProperty("--surface-tone",std::to_string(appearance==3?.96f:isDark?(invertDark?.13f:.07f):.96f));
            e->SetProperty("--surface-grounding",std::to_string((appearance==3?clearOpacity:isDark?darkOpacity:lightOpacity)/100.f));
            e->SetProperty("--material-blur",std::to_string(blurRadius));e->SetClass("clear",appearance==3);
            e->SetProperty("--material-blend",surfaceBlend);e->SetProperty("--material-blend-opacity",std::to_string(blendStrength/100.f));e->SetProperty("--material-texture",std::to_string(grainAmount/100.f));
            const auto variant=[&](float white,float black){return Hex(accent[0]*(1-white-black)+white,accent[1]*(1-white-black)+white,accent[2]*(1-white-black)+white);};
            e->SetProperty("--accent",isDark?variant(.24f,0):variant(0,.06f));
            e->SetProperty("--accent-ink",isDark?variant(.60f,0):variant(0,.40f));
            e->SetProperty("--accent-soft",Hex(accent[0],accent[1],accent[2],.14f));
            e->SetProperty("--shadow-opacity",std::to_string(i==2?.10f:.26f));
        }
        Select("theme-menu",customTheme?"":appearance==1?"theme-light":appearance==3?"theme-clear":"theme-dark");
    }
    Rml::Element* Element(const char* id) { auto* e=document->GetElementById(id);Require(e!=nullptr,id);return e; }
    void Disabled(const char* id,bool disabled) {auto* e=Element(id);if(disabled)e->SetAttribute("disabled","");else e->RemoveAttribute("disabled");e->SetPseudoClass("disabled",disabled);e->SetProperty("focus",disabled?"none":"auto");}
    void Visible(const char* id,bool visible) { Element(id)->SetProperty("display",visible ? (std::string(id)=="welcome"?"flex":"block"):"none"); }
    void Message(const std::string& text) { Element("feedback")->SetInnerRML(text); }
    void Put(const std::string& key,float value) { auto before=values;values[key]=value;edits.Record(before,values); }
    void Select(const char* container,const std::string& id) {
        auto* parent=Element(container);
        for(int i=0;i<parent->GetNumChildren();++i) parent->GetChild(i)->SetClass("selected",parent->GetChild(i)->GetId()==id);
    }
    void Sync()
    {
        if(syncing || typographySync)return;
        syncing=true;
        auto range=[&](const char* id,const std::string& key) {
            const auto value=values.at(key);auto* field=dynamic_cast<Rml::ElementFormControl*>(Element(id));Require(field!=nullptr,"Expected range control");
            field->SetValue(std::to_string(value));char text[32];std::snprintf(text,sizeof(text),"%.2f",value);
            Element((std::string(id)+"-value").c_str())->SetInnerRML(text);
        };
        range("strength","intensity");range("detail","detail");range("colour","colour");range("tone","tone");
        const auto prefix="pass"+std::to_string(pass)+"_";
        for(const auto* key : {"strength","tone","structure","skin"})range((std::string("pass-")+key).c_str(),prefix+key);
        Element("inherit")->SetClass("on",values[prefix+"inherit"]!=0);Element("pass-fields")->SetProperty("opacity",values[prefix+"inherit"] ? ".35":"1");
        for(const auto* key : {"strength","tone","structure","skin"})dynamic_cast<Rml::ElementFormControl*>(Element((std::string("pass-")+key).c_str()))->SetDisabled(values[prefix+"inherit"]!=0);
        for(const auto* id : {"pass-style-default","pass-style-natural","pass-style-cinematic"})Disabled(id,values[prefix+"inherit"]!=0);
        Select("pass-style",values[prefix+"style"]==0 ? "pass-style-default":values[prefix+"style"]==1 ? "pass-style-natural":"pass-style-cinematic");
        Element("pass-2")->SetClass("selected",pass==2);Element("pass-3")->SetClass("selected",pass==3);
        Disabled("pass-3",values["passes"]<3);Disabled("open-passes",values["passes"]<2);
        Element("nr-toggle")->SetClass("on",values["enabled"]!=0);Visible("nr-body",values["enabled"]!=0);
        Element("mfg-toggle")->SetClass("on",values["mfg_enabled"]!=0);Visible("mfg-body",values["mfg_enabled"]!=0);
        Element("ratios")->SetProperty("display",values["multiplier"]>=2 ? "flex":"none");
        Select("nr-style",values["style"]==0 ? "style-default":values["style"]==1 ? "style-natural":"style-cinematic");
        Select("mfg-mode",values["dynamic_mfg"]!=0 ? "mode-dynamic":values["multiplier"]<0 ? "mode-auto":"mode-custom");
        Element("mfg-hint")->SetInnerRML(values["dynamic_mfg"]!=0 ? "Adjusts frame generation up to the selected limit.":values["multiplier"]<0 ? "Follows the game’s frame generation setting.":"Uses the selected frame generation multiplier.");
        Select("ratios","ratio-"+std::to_string(int(values["multiplier"])));
        Element("compare-a")->SetClass("selected",edits.comparing && edits.side==0);Element("compare-b")->SetClass("selected",!edits.comparing || edits.side==1);
        Element("compare-a")->SetInnerRML(compareMode=="presets"?compareLeft:"Off");Element("compare-b")->SetInnerRML(compareMode=="presets"?compareRight:"On");
        Element("compare-preset-pair")->SetProperty("display",compareMode=="presets"?"flex":"none");
        Disabled("undo",edits.past.empty());Disabled("redo",edits.future.empty());
        for(const auto& [id,key] : std::map<std::string,std::string>{{"pass-count","passes"},{"model-preset","preset"}})
            if(values.contains(key))dynamic_cast<Rml::ElementFormControl*>(Element(id.c_str()))->SetValue(std::to_string(int(values[key])));
        for(const auto& [id,control]:extraFields) {const float value=values.at(control->key);auto* e=Element(id.c_str());if(std::string(control->kind)=="toggle")e->SetClass("on",value!=0);else {dynamic_cast<Rml::ElementFormControl*>(e)->SetValue(std::string(control->kind)=="choice"?std::to_string(int(value)):std::to_string(value));if(std::string(control->kind)!="choice"){char text[48];std::snprintf(text,sizeof(text),control->step>=1?"%.0f":"%.2f",value);Element((id+"-value").c_str())->SetInnerRML(text);}}}
        syncing=false;
    }
    void Open(const std::string& panel) {
        inspectorPanel=panel;
        Element("inspector")->SetClass("opening",true);
        Visible("inspector",true);Visible("pass-inspector",panel=="passes");Visible("look-inspector",panel=="look");Visible("extra-processing",panel=="processing");Visible("extra-frame-popup",panel=="frame");Visible("popup-metadata",panel=="overview");Element("inspector")->SetClass("session-inspector",panel=="overview");
        const auto icon=panel=="overview"?"gauge":panel=="passes"?"stack":panel=="look"?"sliders-horizontal":panel=="frame"?"film-strip":"cpu";
        const auto title=panel=="overview"?"SESSION":panel=="processing"?"NEURAL RENDERING":panel=="passes"?"PASS TUNING":panel=="look"?"LOOK &amp; DETAIL":panel=="frame"?"FRAME GENERATION":"PROCESSING";
        Element("inspector-title")->SetInnerRML(std::string("<img class=\"glyph\" src=\"icons/")+icon+"-light.png\"/>"+title);
        if(layout=="centered")Visible("overview",false);
        Raise("inspector");Enter("inspector");inspectorAnchored=layout=="bar";
        if(inspectorAnchored) {auto* source=Element(panel=="overview"?"open-session":panel=="passes"?"open-passes":panel=="frame"?"open-frame-options":panel=="processing"?"open-processing":"open-look");document->GetContext()->Update();const auto at=source->GetAbsoluteOffset(Rml::BoxArea::Border);const auto bounds=source->GetBox().GetSize(Rml::BoxArea::Border);const auto size=Element("inspector")->GetBox().GetSize(Rml::BoxArea::Border);const auto viewport=document->GetContext()->GetDimensions();inspectorAnchorX=at.x+bounds.x*.5f;Element("inspector")->SetProperty("left",std::to_string(std::clamp(inspectorAnchorX-size.x*.5f,12.f,std::max(12.f,viewport.x-size.x-12)))+"px");Element("inspector")->SetProperty("top",std::to_string(std::max(12.f,at.y-size.y-20))+"px");}
    }
    void ProcessEvent(Rml::Event& event) override
    {
        if(syncing || typographySync)return;
        auto* target=event.GetTargetElement();
        if(event.GetType()=="keydown") {
            const int key=event.GetParameter<int>("key_identifier",0);const int mods=event.GetParameter<int>("key_modifier_state",0)&7;
            if(bindingShortcut){
                if(key==Rml::Input::KI_ESCAPE){bindingShortcut=false;SyncSettings();event.StopPropagation();return;}
                if(key==Rml::Input::KI_DELETE||(key>=Rml::Input::KI_A&&key<=Rml::Input::KI_Z)||(key>=Rml::Input::KI_F1&&key<=Rml::Input::KI_F12)){
                    shortcut=key;shortcutModifiers=mods;shortcutLabel=(mods&Rml::Input::KM_CTRL?"Ctrl + ":"") + std::string(mods&Rml::Input::KM_ALT?"Alt + ":"") + (mods&Rml::Input::KM_SHIFT?"Shift + ":"");
                    shortcutLabel+=key==Rml::Input::KI_DELETE?"Del":key>=Rml::Input::KI_F1&&key<=Rml::Input::KI_F12?"F"+std::to_string(key-Rml::Input::KI_F1+1):std::string(1,char('A'+key-Rml::Input::KI_A));
                    bindingShortcut=false;prefsDirty=true;SyncSettings();event.StopPropagation();return;
                }
                event.StopPropagation();return;
            }
            if(key==shortcut&&mods==shortcutModifiers){ToggleOverlay();event.StopPropagation();return;}
        }
        if(event.GetType()=="mousemove" && dragged) {
            const Rml::Vector2f delta{event.GetParameter<float>("mouse_x",0)-dragStart.x,event.GetParameter<float>("mouse_y",0)-dragStart.y};
            const auto viewport=document->GetContext()->GetDimensions();const auto size=dragged->GetBox().GetSize(Rml::BoxArea::Border);
            const Rml::Vector2f position{std::clamp(dragOrigin.x+delta.x,8.f,std::max(8.f,viewport.x-size.x-8)),std::clamp(dragOrigin.y+delta.y,8.f,std::max(8.f,viewport.y-size.y-8))};
            const double now=Rml::GetSystemInterface()->GetElapsedTime();const float elapsed=std::max(.004f,float(now-dragTime));const auto raw=(position-dragLast)/elapsed;dragVelocity={std::clamp(dragVelocity.x*.6f+raw.x*.4f,-2200.f,2200.f),std::clamp(dragVelocity.y*.6f+raw.y*.4f,-2200.f,2200.f)};dragLast=position;dragTime=now;windowVelocity[dragged->GetId()]=dragVelocity;
            dragged->SetProperty("left",std::to_string(position.x)+"px");dragged->SetProperty("top",std::to_string(position.y)+"px");
            if(dragged==Element("inspector") && std::fabs(delta.x)+std::fabs(delta.y)>3)inspectorAnchored=false;
            if(dragFollower){dragFollower->SetProperty("left",std::to_string(followerOrigin.x+position.x-dragOrigin.x)+"px");dragFollower->SetProperty("top",std::to_string(followerOrigin.y+position.y-dragOrigin.y)+"px");if(layout=="bar")inspectorAnchorX=followerAnchorOrigin+position.x-dragOrigin.x;}return;
        }
        if(event.GetType()=="mouseup") {if(dragged){const auto id=dragged->GetId();if(!reducedMotion && std::fabs(dragVelocity.x)+std::fabs(dragVelocity.y)>50)coasting[id]={dragLast,dragVelocity,dragFollower?dragFollower->GetId():"",dragFollower?followerOrigin-dragOrigin:Rml::Vector2f{}};else windowVelocity[id]={};}dragged=nullptr;dragFollower=nullptr;return;}
        if(event.GetType()=="mousedown") {
            auto* glass=target;bool interactive=false;
            while(glass && !glass->IsClassSet("glass")) {const auto tag=glass->GetTagName();if(tag=="button"||tag=="input"||tag=="select"||tag=="option"||tag.find("slider")!=std::string::npos||tag.find("scrollbar")!=std::string::npos)interactive=true;glass=glass->GetParentNode();}
            if(glass) {const auto id=glass->GetId();Raise(id);
                if(!interactive) {dragged=layout=="centered" && (id=="main-panel"||id=="inspector")?Element("main-panel"):glass;coasting.erase(dragged->GetId());entrances.erase(dragged->GetId());dragStart={event.GetParameter<float>("mouse_x",0),event.GetParameter<float>("mouse_y",0)};dragOrigin=dragged->GetAbsoluteOffset(Rml::BoxArea::Border);dragLast=dragOrigin;dragVelocity={};dragTime=Rml::GetSystemInterface()->GetElapsedTime();dragged->SetProperty("margin-left","0px");dragged->SetProperty("margin-top","0px");dragged->SetProperty("left",std::to_string(dragOrigin.x)+"px");dragged->SetProperty("top",std::to_string(dragOrigin.y)+"px");
                    if((layout=="centered" || (layout=="bar" && inspectorAnchored)) && dragged==Element("main-panel") && Element("inspector")->IsVisible()){dragFollower=Element("inspector");followerOrigin=dragFollower->GetAbsoluteOffset(Rml::BoxArea::Border);followerAnchorOrigin=inspectorAnchorX;dragFollower->SetProperty("margin-left","0px");dragFollower->SetProperty("margin-top","0px");}}
            }
            return;
        }
        auto* button=target;while(button && button->GetTagName()!="button")button=button->GetParentNode();
        if(button)target=button;
        while(target && target->GetId().empty())target=target->GetParentNode();
        if(!target)return;const auto id=target->GetId();
        if(event.GetType()=="mouseover") {
            const auto title=target->GetAttribute<Rml::String>("title","");if(!title.empty()) {const auto at=target->GetAbsoluteOffset(Rml::BoxArea::Border);Element("tooltip")->SetInnerRML(Rml::StringUtilities::EncodeRml(title));Element("tooltip")->SetProperty("left",std::to_string(at.x-60)+"px");Element("tooltip")->SetProperty("top",std::to_string(at.y+38)+"px");Visible("tooltip",true);}
            return;
        }
        if(event.GetType()=="mouseout") {Visible("tooltip",false);return;}
        if(target->IsPseudoClassSet("disabled"))return;
        if(event.GetType()=="keydown") {
            const auto key=event.GetParameter<int>("key_identifier",0);
            if(target->GetTagName()=="button" && (key==Rml::Input::KI_RETURN || key==Rml::Input::KI_SPACE)) {event.StopPropagation();target->DispatchEvent("click",{});}
            return;
        }
        if(event.GetType()=="change") {
            auto* field=dynamic_cast<Rml::ElementFormControl*>(target);if(!field)return;
            if(id=="scene-select") {sceneRequest=std::stoi(field->GetValue());return;}
            if(id=="welcome-position"){welcomePosition=field->GetValue();prefsDirty=true;PositionWelcome();return;}
            if(id=="primary-menu"){primaryMenu=field->GetValue();prefsDirty=true;return;}
            if(id=="opti-shortcut"){optiShortcut=field->GetValue();prefsDirty=true;return;}
            if(extraFields.contains(id)) {Put(extraFields.at(id)->key,std::stof(field->GetValue()));Sync();return;}
            if(id=="tint-opacity") {customTheme=true;if(appearance==1)lightOpacity=std::stof(field->GetValue());else if(appearance==3)clearOpacity=std::stof(field->GetValue());else darkOpacity=std::stof(field->GetValue());Materials();return;}
            if(id=="blur-radius") {customTheme=true;blurRadius=std::stof(field->GetValue());Materials();return;} if(id=="grain-amount"){customTheme=true;grainAmount=std::stof(field->GetValue());Materials();return;} if(id=="blend-strength"){customTheme=true;blendStrength=std::stof(field->GetValue());Materials();return;}
            if(id=="surface-blend") {customTheme=true;surfaceBlend=field->GetValue();Materials();return;}
            if(id=="overlay-scale") {overlayScale=std::stoi(field->GetValue());Typography();return;}
            if(id=="compare-mode"||id=="compare-left"||id=="compare-right") {if(id=="compare-mode")compareMode=field->GetValue();else if(id=="compare-left")compareLeft=field->GetValue();else compareRight=field->GetValue();PrepareComparison();Sync();return;}
            if(id=="font-select") {copyFont=field->GetValue();Typography();return;}
            if(id=="copy-size"||id=="copy-weight"||id=="heading-size"||id=="heading-weight") {const int value=std::stoi(field->GetValue());if(id=="copy-size")copySize=value;else if(id=="copy-weight")copyWeight=value;else if(id=="heading-size")headingSize=value;else headingWeight=value;Typography();return;}
            const auto mapping=std::map<std::string,std::string>{{"strength","intensity"},{"detail","detail"},{"colour","colour"},{"tone","tone"},{"pass-count","passes"},{"model-preset","preset"}};
            if(const auto found=mapping.find(id);found!=mapping.end())Put(found->second,std::stof(field->GetValue()));
            else if(id.rfind("pass-",0)==0)Put("pass"+std::to_string(pass)+"_"+id.substr(5),std::stof(field->GetValue()));
            else if(id=="presets") {
                const auto name=field->GetValue();auto before=values;
                if(presets.contains(name))values=presets.at(name);
                else {values["style"]=name=="natural" ? 1.f:2.f;values["intensity"]=name=="natural" ? 1.f:.8f;}
                edits.Record(before,values);edits.saved=values;Message(preview?"Preset loaded into this preview":"Preset selected");Notify(name+std::string(preview?" preset · Preview":" preset"));
            }
        } else if(event.GetType()=="click") {
            if(id=="close")ToggleOverlay();
            else if(id.rfind("group-toggle-",0)==0){auto* group=Element(id.substr(13).c_str());group->SetProperty("display",group->IsVisible()?"none":"block");target->SetClass("expanded",group->IsVisible());}
            else if(id.rfind("reset-extra-",0)==0 && extraFields.contains(id.substr(6)))Put(extraFields.at(id.substr(6))->key,defaults.at(extraFields.at(id.substr(6))->key));
            else if(extraFields.contains(id)) {const auto* control=extraFields.at(id);if(std::string(control->kind)=="toggle")Put(control->key,values.at(control->key)==0?1.f:0.f);}
            else if(id=="open-settings"||id=="nav-settings")Settings(!settingsOpen);
            else if(id=="settings-back")Settings(false);
            else if(id=="shortcut-bind") {bindingShortcut=true;SyncSettings();document->Focus();}
            else if(id=="setting-stats") {showStats=!showStats;prefsDirty=true;Session(session);SyncSettings();}
            else if(id=="setting-welcome") {showWelcome=!showWelcome;prefsDirty=true;if(!showWelcome)Visible("welcome",false);SyncSettings();}
            else if(id=="setting-notifications") {showNotifications=!showNotifications;prefsDirty=true;SyncSettings();}
            else if(id=="welcome-test")Welcome();
            else if(id=="setting-helper"||id=="setting-startup"){if(id=="setting-helper")helperEnabled=!helperEnabled;else startWithWindows=!startWithWindows;prefsDirty=true;SyncSettings();}
            else if(id=="menus-review"){if(!requestJson||!requestJson("{\"op\":\"menus-review\"}"))Message("Connect the background helper to review installed games.");}
            else if(id=="discard-review"){if(requestJson)requestJson("{\"op\":\"discard-review\"}");Visible("review-panel",false);reviewId=0;}
            else if(id=="apply-review"){if(reviewId>0&&requestJson)requestJson("{\"op\":\"apply-review\",\"review_id\":"+std::to_string(reviewId)+"}");}
            else if(id=="global-review"){
                const auto nr=dynamic_cast<Rml::ElementFormControl*>(Element("global-neural"))->GetValue(),fg=dynamic_cast<Rml::ElementFormControl*>(Element("global-frame"))->GetValue();
                if(nr=="leave"&&fg=="leave")Message("Choose a library change to review.");else {std::string changes;if(nr!="leave")changes="\"nr\":"+std::string(nr=="1"?"true":"false");if(fg!="leave")changes+=(changes.empty()?"":",")+std::string("\"mfg\":")+std::to_string(std::stoi(fg));if(!requestJson||!requestJson("{\"op\":\"global-review\",\"changes\":{"+changes+"}}"))Message("Connect the background helper to review installed games.");}
            }
            else if(id.rfind("setting-",0)==0&&menuSettings.contains(id.substr(8))) {menuSettings[id.substr(8)]=!menuSettings[id.substr(8)];prefsDirty=true;SyncSettings();}
            else if(id=="open-appearance")ShowAppearance();
            else if(id=="appearance-more") {moreOpen=!moreOpen;Materials();}
            else if(id=="theme-reset")UseTheme(appearance);
            else if(id=="text-smaller"||id=="text-default"||id=="text-larger") {copySize=id=="text-smaller"?20:id=="text-larger"?24:22;Typography();}
            else if(id=="scale-minus"||id=="scale-plus") {overlayScale=std::clamp(overlayScale+(id=="scale-plus"?10:-10),70,150);Typography();}
            else if(id=="text-depth") {textDepth=!textDepth;customTheme=true;Materials();}
            else if(id=="dark-inverted") {invertDark=!invertDark;customTheme=true;Materials();}
            else if(id=="toast-pill"||id=="toast-rounded") {toastPill=id=="toast-pill";Materials();}
            else if(id=="motion-effects") {motionEnabled=!motionEnabled;Materials();}
            else if(id=="type-close")Visible("type-panel",false);
            else if(id=="type-reset") {copyFont="roboto";headingFont="bakbak";copySize=22;copyWeight=500;headingSize=36;headingWeight=400;Typography();}
            else if(id.rfind("layout-",0)==0)Layout(id.substr(7));
            else if(id=="nav-overview"||id=="nav-frame"||id=="nav-neural") {Settings(false);Visible("overview",true);Visible("inspector",false);document->SetClass("overview-page",id=="nav-overview");document->SetClass("frame-page",id=="nav-frame");document->SetClass("neural-page",id=="nav-neural");}
            else if(id=="nav-look")Open("look");else if(id=="nav-passes")Open("passes");
            else if(id=="welcome-close")Visible("welcome",false);
            else if(id=="theme")Visible("theme-menu",!Element("theme-menu")->IsVisible());
            else if(id=="theme-light"||id=="theme-dark"||id=="theme-clear")UseTheme(id=="theme-light"?1:id=="theme-dark"?2:3);
            else if(id=="open-passes")Open("passes");else if(id=="open-look")Open("look");
            else if(id=="open-session")Open("overview");
            else if(id=="open-processing")Open("processing");else if(id=="open-frame-options")Open("frame");
            else if(id=="inspector-close") {Visible("inspector",false);Visible("overview",true);Element("inspector")->SetClass("opening",false);}
            else if(id=="pass-2" || id=="pass-3")pass=id=="pass-2" ? 2:3;
            else if(id=="inherit")Put("pass"+std::to_string(pass)+"_inherit",values["pass"+std::to_string(pass)+"_inherit"] ? 0.f:1.f);
            else if(id=="nr-toggle") {Put("enabled",values["enabled"] ? 0.f:1.f);Notify(values["enabled"]?(preview?"Neural rendering on · Preview":"Neural rendering on"):(preview?"Neural rendering off · Preview":"Neural rendering off"));}
            else if(id=="mfg-toggle")Put("mfg_enabled",values["mfg_enabled"] ? 0.f:1.f);
            else if(id=="undo")values=edits.Undo(values);else if(id=="redo")values=edits.Redo(values);
            else if(id=="defaults") {edits.Record(values,defaults);values=defaults;}
            else if(id=="compare-a" || id=="compare-b") {if(!edits.comparing)PrepareComparison();values=edits.Compare(id=="compare-b",values);}
            else if(id=="save"&&!preview){Visible("save-sheet",!Element("save-sheet")->IsVisible());}
            else if(id=="delete-preset"&&deletePreset){const auto name=dynamic_cast<Rml::ElementFormControl*>(Element("presets"))->GetValue();if(!name.empty()&&deletePreset(name)){Visible("save-sheet",false);Message("Deleting preset…");}}
            else if(id=="save-cancel")Visible("save-sheet",false);
            else if(id=="save-confirm"&&savePreset){const auto name=dynamic_cast<Rml::ElementFormControl*>(Element("preset-name"))->GetValue();if(name.empty()||name.size()>60)Message(name.empty()?"Name your preset.":"Use a shorter preset name.");else if(savePreset(name)){Visible("save-sheet",false);Message("Saving preset…");}else Message("The helper is busy. Try saving again.");}
            else if(id=="save") {const auto name=dynamic_cast<Rml::ElementFormControl*>(Element("presets"))->GetValue();presets[name]=values;edits.saved=values;Message("Session preset saved in memory · game settings unchanged");Notify("Preset saved · Preview");}
            else if(id=="reset-inspector") {auto before=values;for(auto& [key,value]:values){bool reset=inspectorPanel=="look"?(key=="detail"||key=="colour"||key=="tone"):inspectorPanel=="passes" && key.rfind("pass"+std::to_string(pass)+"_",0)==0;for(const auto& control:ExtraControls)if(key==control.key && std::string(control.page)==(inspectorPanel=="processing"?"neural":inspectorPanel=="frame"?"frame":inspectorPanel=="look"?"look":""))reset=true;if(reset)value=defaults.at(key);}edits.Record(before,values);}
            else if(id.rfind("style-",0)==0)Put("style",id=="style-default" ? 0.f:id=="style-natural" ? 1.f:2.f);
            else if(id.rfind("pass-style-",0)==0)Put("pass"+std::to_string(pass)+"_style",id=="pass-style-default" ? 0.f:id=="pass-style-natural" ? 1.f:2.f);
            else if(id.rfind("ratio-",0)==0)Put("multiplier",float(std::stoi(id.substr(6))));
            else if(id.rfind("status-",0)==0)Message("Sample status indicators · no live game telemetry");
            else if(id.rfind("mode-",0)==0) {auto before=values;values["multiplier"]=id=="mode-auto" ? -1.f:2.f;values["dynamic_mfg"]=id=="mode-dynamic" ? 1.f:0.f;edits.Record(before,values);}
        }
        if(event.GetType()=="click" || event.GetType()=="change")Sync();
    }
};
}
