#pragma once
#include <windows.h>
#include <RmlUi/Core.h>
#include <RmlUi/Core/ElementUtilities.h>
#include <RmlUi/Core/Elements/ElementFormControl.h>
#include <ForgeWorkbench.h>
#include "../../prototypes/overlay-rmlui/Backdrop.h"
#include "../../prototypes/overlay-rmlui/MaterialColor.h"
#include "../../prototypes/overlay-rmlui/Motion.h"
#include "../../prototypes/overlay-rmlui/BalancedCards.h"
#include "../../prototypes/overlay-rmlui/ThemeDefaults.h"
#include "../../prototypes/overlay-rmlui/SessionData.h"
#include <PrototypeControls.generated.h>
#include "HdrControls.h"
#include "NrAddonControls.h"
#include "EffectControls.h"
#include "ScreenColorPicker.h"
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
    HdrControls hdr;
    NrAddonControls addons;
    EffectControls effects;
    BalancedCards balancedCards;
    ScreenColorPicker screenColorPicker;bool colorEditorOpen=false,colorPicking=false,spectrumOpen=false,posterAvailable=false;MaterialColor::Color spectrumHsv{};
    std::function<std::string(float,float)> samplePoster;
    void Poster(const std::string& path){posterAvailable=!path.empty();for(const auto* id:{"accent-poster","screen-pick-poster"}){auto* image=Element(id);if(path.empty())image->SetProperty("display","none");else{image->SetAttribute("src",path);image->SetProperty("display","block");}}}
    void ColorEditor(){const auto color=MaterialColor::ParseAccent(customAccent,accent);
        if(!colorEditorOpen)spectrumOpen=false;
        for(const auto* id:{"accent-swatch","accent-spectrum-swatch"})Element(id)->QuerySelector(".color-dot")->SetProperty("background-color",Hex(color[0],color[1],color[2]));
        Visible("accent-spectrum",spectrumOpen);Element("accent-poster")->SetProperty("display",posterAvailable&&!spectrumOpen?"block":"none");Spectrum();
        Element("accent-editor")->SetProperty("display",colorEditorOpen&&accentMode=="custom"&&Element("type-panel")->IsVisible()?"block":"none");
        dynamic_cast<Rml::ElementFormControl*>(Element("accent-color"))->SetValue(Hex(color[0],color[1],color[2]).substr(0,7));
    }
    void Spectrum() {
        const int tile=std::clamp(int(spectrumHsv[0]*MaterialColor::SpectrumHues),0,MaterialColor::SpectrumHues-1);
        Element("spectrum-texture")->SetAttribute("rect",std::to_string(tile*MaterialColor::SpectrumSize)+" 0 32 32");
        Element("spectrum-marker")->SetProperty("left",std::to_string(spectrumHsv[1]*100)+"%");Element("spectrum-marker")->SetProperty("top",std::to_string((1-spectrumHsv[2])*100)+"%");Element("hue-marker")->SetProperty("left",std::to_string(spectrumHsv[0]*100)+"%");
    }
    void ChooseSpectrum() {const auto color=MaterialColor::Hsv(spectrumHsv[0],spectrumHsv[1],spectrumHsv[2]);customAccent=Hex(color[0],color[1],color[2]).substr(0,7);colorEditorOpen=false;Materials();Element("accent-swatch")->Focus();}
    void PlaceColorEditor() {
        auto* popup=Element("accent-editor");if(!colorEditorOpen||!Element("type-panel")->IsVisible()||accentMode!="custom"){popup->SetProperty("display","none");return;}
        auto* context=document->GetContext();if(!popup->IsVisible()){popup->SetProperty("display","block");context->Update();}const auto view=context->GetDimensions();const float dp=context->GetDensityIndependentPixelRatio();
        const auto at=Element("accent-swatch")->GetAbsoluteOffset(Rml::BoxArea::Border),size=popup->GetBox().GetSize(Rml::BoxArea::Border);const auto button=Element("accent-swatch")->GetBox().GetSize(Rml::BoxArea::Border);
        const float x=at.x+(button.x-size.x)*.5f,below=at.y+button.y+18*dp,y=below+size.y<=view.y-12*dp?below:at.y-size.y-18*dp;
        popup->SetProperty("left",std::to_string(std::clamp(x,12*dp,std::max(12*dp,view.x-size.x-12*dp)))+"px");popup->SetProperty("top",std::to_string(std::clamp(y,12*dp,std::max(12*dp,view.y-size.y-12*dp)))+"px");
    }
    void PollColorPick(){if(!colorPicking||!screenColorPicker.Finished())return;const auto picked=screenColorPicker.Result();colorPicking=false;document->SetClass("color-picking",false);
        if(picked){const auto rgb=*picked;customAccent=Hex(GetRValue(rgb)/255.f,GetGValue(rgb)/255.f,GetBValue(rgb)/255.f).substr(0,7);colorEditorOpen=false;}
        Materials();
    }
    std::function<void()> closePreview;
    ForgeWorkbench::Values values{{"intensity",1},{"style",1},{"multiplier",-1},{"dynamic_mfg",0},{"passes",3},{"preset",0},
        {"detail",1},{"colour",1},{"tone",1},{"pass2_strength",.65f},{"pass2_tone",.8f},{"pass2_structure",1},{"pass2_skin",.5f},{"pass2_inherit",0},{"pass2_style",0},
        {"pass3_strength",1},{"pass3_tone",1},{"pass3_structure",1},{"pass3_skin",-1},{"pass3_inherit",1},{"pass3_style",0},
        {"pass4_strength",1},{"pass4_tone",1},{"pass4_structure",1},{"pass4_skin",-1},{"pass4_inherit",1},{"pass4_style",0},{"enabled",1},{"mfg_enabled",1}};
    ForgeWorkbench::Values defaults=values;
    ForgeWorkbench::Edits edits;
    std::map<std::string,ForgeWorkbench::Values> presets;
    bool preview=true;std::function<bool(const std::string&)> savePreset,deletePreset,requestJson;int reviewId=0;bool helperEnabled=true,startWithWindows=false;
    std::function<bool(float)> restorePreview;
    ~Controller() override {RestorePreviewForTeardown();}
    void RestorePreviewForTeardown() {if(!nrPreviewActive)return;nrPreviewActive=false;values["enabled"]=nrBeforePreview;if(restorePreview)restorePreview(nrBeforePreview);}
    bool nrPreviewActive=false,monitorPreviewFocus=false;float nrBeforePreview=1;
    Rml::Element* settingsHome=nullptr;Rml::Element* metadataHome=nullptr;
    std::map<std::string,const ExtraControl*> extraFields;
    std::string activeNavigation="nav-overview",beforeSettingsNavigation="nav-overview";
    std::vector<std::string> navigationHistory;
    bool navigatingBack=false,originalLabels=false;
    int setupStep=-1;bool setupComplete=false,setupLayoutChosen=false,nativeOverlayPending=false;double nativeOverlayDeadline=0;fs::path setupPreferences;
    struct NativeShortcut{std::string name,key;bool enabled=false;};std::vector<NativeShortcut> nativeShortcuts;
    void SetupShortcuts() {
        std::string active,available;
        const auto row=[](const std::string& name,const std::string& key){return "<div class=\"setup-shortcut\"><span class=\"setup-shortcut-name\">"+Rml::StringUtilities::EncodeRml(name)+"</span><span class=\"keycap\">"+Rml::StringUtilities::EncodeRml(key)+"</span></div>";};
        for(const auto& item:nativeShortcuts){available+=row(item.name,item.key);if(item.enabled)active+=row(item.name,item.key);}
        const bool hasNative=!active.empty();
        if(hasNative)active="<div class=\"setup-menu-heading\"><img class=\"glyph\" src=\"icons/info-light.png\"/><span>Other overlays are on</span></div><div class=\"setup-shortcut-list\">"+row("rtxForge",shortcutLabel)+active+"</div>";
        Element("setup-existing-menus")->SetInnerRML(active);Element("setup-native-shortcuts")->SetInnerRML(available.empty()?"<p class=\"hint\">Native shortcuts will appear when the game connects.</p>":available);
        Visible("setup-existing-menus",hasNative);Element("setup-native")->SetClass("after-shortcuts",hasNative);
    }
    void BeginSetup() {
        EndNrPreview();QuickLayouts(false);Visible("inspector",false);Visible("welcome",false);moreOpen=godModeOpen=false;Materials();
        Element("setup-native-global")->RemoveAttribute("checked");Element("setup-native-message")->SetInnerRML("Re-enable in Game Details, under Overlay.");
        auto markup=Element("layout-switch")->GetInnerRML();size_t at=0;while((at=markup.find("id=\"layout-",at))!=std::string::npos){markup.insert(at+4,"setup-");at+=10;}
        Element("setup-layouts")->SetInnerRML(markup);setupLayoutChosen=false;setupStep=0;UpdateSetup();Raise("type-panel");Enter("type-panel");
    }
    void UpdateSetup() {
        auto* panel=Element("type-panel");panel->SetClass("setup-flow",true);panel->SetClass("setup-theme",setupStep==1);panel->SetClass("setup-layout",setupStep==0);panel->SetClass("setup-native-confirm",setupStep==2);document->SetClass("setup-open",true);Visible("type-panel",true);Visible("main-panel",setupLayoutChosen);
        Element("settings-title")->QuerySelector("span")->SetInnerRML(setupStep==0?"FIND YOUR FIT":setupStep==1?"APPEARANCE":"USE NATIVE OVERLAYS?");
        Element("setup-intro")->SetInnerRML(setupStep==0?"Choose how your controls fit into the game.":setupStep==1?"A different look, if you like.":"Turn off rtxForge for this game and use ReShade / OptiScaler instead.");
        Element("setup-next-label")->SetInnerRML(setupStep==0?"Let’s play":"Done");
        Element("setup-skip-label")->SetInnerRML(setupStep==2?"Cancel":"Skip");SetupShortcuts();Select("setup-layouts","setup-layout-"+layout);PlaceSetup();Element(setupStep==2?"setup-skip":"setup-next")->Focus();
        Visible("appearance-more",false);Visible("appearance-god-mode",false);
    }
    void PlaceSetup() {
        if(setupStep<0)return;auto* panel=Element("type-panel");auto* context=document->GetContext();context->Update();const auto view=context->GetDimensions();const auto size=panel->GetBox().GetSize(Rml::BoxArea::Border);const float dp=context->GetDensityIndependentPixelRatio(),inset=TopInset();
        const Rml::Vector2f target{std::max(12*dp,(view.x-size.x)*.5f),std::max(inset,inset+(view.y-inset-24*dp-size.y)*.5f)};
        panel->SetProperty("left",std::to_string(target.x)+"px");panel->SetProperty("top",std::to_string(target.y)+"px");if(auto it=entrances.find("type-panel");it!=entrances.end())it->second.target=target;
    }
    void FinishSetup() {
        setupStep=-1;setupComplete=true;auto* panel=Element("type-panel");for(const auto* name:{"setup-flow","setup-theme","setup-layout","setup-native-confirm"})panel->SetClass(name,false);document->SetClass("setup-open",false);Visible("type-panel",false);Visible("main-panel",true);Element("settings-title")->QuerySelector("span")->SetInnerRML("APPEARANCE");prefsDirty=true;
        Materials();if(!setupPreferences.empty()){fs::create_directories(setupPreferences.parent_path());WritePrivateProfileStringW(L"Setup",L"Version",L"1",setupPreferences.c_str());}
    }
    void MaybeSetup(){if(setupComplete)return;if(setupStep<0)BeginSetup();else UpdateSetup();}
    void UseNativeOverlays() {
        if(nativeOverlayPending)return;
        const auto* checkbox=dynamic_cast<Rml::ElementFormControl*>(Element("setup-native-global"));
        const bool global=checkbox&&checkbox->HasAttribute("checked");
        if(!requestJson){Element("setup-native-message")->SetInnerRML("Native-overlay choices are saved by Desktop or Game Mode. This is a preview.");return;}
        const std::string request=std::string("{\"op\":\"use-native-overlays\",\"global_default\":")+(global?"true}":"false}");
        if(requestJson(request)){nativeOverlayPending=true;nativeOverlayDeadline=Rml::GetSystemInterface()->GetElapsedTime()+6;Disabled("setup-native-confirm",true);Element("setup-native-message")->SetInnerRML("Saving…");}
        else Element("setup-native-message")->SetInnerRML("Couldn’t save. Try again.");
    }
    void NativeOverlaysResult(bool error) {
        nativeOverlayPending=false;Disabled("setup-native-confirm",false);
        if(error){Element("setup-native-message")->SetInnerRML("Couldn’t save. Try again.");return;}
        primaryMenu="optiscaler";menuSettings["opti-menu"]=menuSettings["reshade-menu"]=true;if(optiShortcut=="Disabled")optiShortcut="Insert";toastUntil=0;FinishSetup();SavePreferences();for(const auto* id:{"main-panel","type-panel","inspector","welcome"})Visible(id,false);
    }
    double layoutPickerDismiss=0;
    Rml::Element* statusHome=nullptr;Rml::Element* compactLiveHome=nullptr;
    void UpdateBack() {auto* back=Element("window-back");if(settingsOpen||activeNavigation!="nav-overview"||!navigationHistory.empty())back->RemoveProperty("display");else back->SetProperty("display","none");}
    void Navigation(const std::string& selected) {if(selected!=activeNavigation&&!navigatingBack)navigationHistory.push_back(activeNavigation);activeNavigation=selected;for(const auto* id:{"nav-overview","nav-frame","nav-neural","nav-look","nav-settings","nav-passes","nav-effects","nav-hdr"})Element(id)->SetClass("selected",selected==id);UpdateBack();}
    void Back() {if(settingsOpen){Settings(false);return;}const auto previous=navigationHistory.empty()?"nav-overview":navigationHistory.back();if(!navigationHistory.empty())navigationHistory.pop_back();navigatingBack=true;Page(previous);navigatingBack=false;UpdateBack();}
    void QuickLayouts(bool show) {
        layoutPickerDismiss=0;Visible("tooltip",false);auto* picker=Element("layout-picker");if(show&&picker->IsVisible())return;document->SetClass("quick-layout-open",show);if(!show){picker->SetProperty("display","none");return;}
        picker->SetProperty("display","flex");Select("layout-picker","quick-"+layout);
        QuickLayoutTheme();
        auto* context=document->GetContext();const auto view=context->GetDimensions();const float dp=context->GetDensityIndependentPixelRatio();float width=28*dp;const std::array<const char*,3> labels{"Side Panel","Advanced","Bar"};for(int i=0;i<3;++i)width+=58*dp+Rml::ElementUtilities::GetStringWidth(picker->GetChild(i),Rml::String(labels[i]));
        picker->SetProperty("width",std::to_string(std::min(width,view.x-24*dp))+"px");document->SetProperty("--quick-layout-width",std::to_string(std::min(width,view.x-24*dp))+"px");PlaceQuickLayouts();
    }
    void PlaceQuickLayouts() {
        auto* picker=Element("layout-picker");if(!picker->IsVisible())return;auto* context=document->GetContext();const auto view=context->GetDimensions();const float dp=context->GetDensityIndependentPixelRatio();
        const auto at=Element("open-layout")->GetAbsoluteOffset(Rml::BoxArea::Border),button=Element("open-layout")->GetBox().GetSize(Rml::BoxArea::Border),size=picker->GetBox().GetSize(Rml::BoxArea::Border);
        auto* actions=document->QuerySelector(".window-actions");const float right=layout=="bar"?actions->GetAbsoluteOffset(Rml::BoxArea::Border).x+actions->GetBox().GetSize(Rml::BoxArea::Border).x:at.x+button.x;
        picker->SetProperty("left",std::to_string(std::clamp(right-size.x,12*dp,std::max(12*dp,view.x-size.x-12*dp)))+"px");picker->SetProperty("top",std::to_string(std::clamp(at.y+(button.y-size.y)*.5f,12*dp,std::max(12*dp,view.y-size.y-12*dp)))+"px");
    }
    Backdrop::Panel QuickLayoutSurface(Backdrop::Panel panel,const char* id="layout-picker") {
        auto* picker=Element(id);const auto at=picker->GetAbsoluteOffset(Rml::BoxArea::Border),size=picker->GetBox().GetSize(Rml::BoxArea::Border);panel.x=at.x;panel.y=at.y;panel.width=size.x;panel.height=size.y;panel.radius=16*document->GetContext()->GetDensityIndependentPixelRatio();panel.shadowOpacity=.14f;panel.shadowRadius=16;panel.shadowOffset=6;panel.arrow=0;
        if(std::string(id)=="accent-editor"){const auto source=Element("accent-swatch")->GetAbsoluteOffset(Rml::BoxArea::Border),button=Element("accent-swatch")->GetBox().GetSize(Rml::BoxArea::Border);panel.arrow=at.y>source.y?-1.f:1.f;panel.anchorX=std::clamp(source.x+button.x*.5f,at.x+24*panel.scale,at.x+size.x-24*panel.scale);}
        return panel;
    }
    void QuickLayoutTheme() {
        auto* picker=Element("layout-picker");const bool light=BaseAppearance()==1;
        picker->SetProperty("--accent",AccentTone(0,false));picker->SetProperty("--accent-soft",AccentTone(0,false).substr(0,7)+"55");
        picker->SetProperty("--picker-ink",light?"#403b35":"#f5f1ea");
        auto surface=appearance==4?SurfaceTint():MaterialColor::Color{light?.93f:.16f,light?.91f:.15f,light?.88f:.14f};
        picker->SetProperty("--picker-fill",Hex(surface[0],surface[1],surface[2],.96f));
    }
    std::string selectMenuOwner="main-panel",selectMenuMarkup;
    bool SelectMenu() {
        // Keep RmlUi's native select, focus, scrolling and keyboard behavior.
        // Paint only its visual surface as a transient glass layer.
        auto* mirror=Element("select-menu");Rml::Element* popup=nullptr;auto* select=document->GetContext()->GetFocusElement();while(select&&select->GetTagName()!="select")select=select->GetParentNode();
        if(select&&select->IsVisible(true))for(int i=0;i<select->GetNumChildren(true);++i){auto* child=select->GetChild(i);if(child->GetTagName()=="selectbox"&&child->IsVisible(true)){popup=child;break;}}
        if(!popup){const bool was=mirror->IsVisible();if(was)mirror->SetProperty("display","none");return was;}
        selectMenuOwner="main-panel";for(auto* e=popup;e;e=e->GetParentNode())if(e->GetId()=="main-panel"||e->GetId()=="inspector"||e->GetId()=="type-panel"){selectMenuOwner=e->GetId();break;}
        const auto at=popup->GetAbsoluteOffset(Rml::BoxArea::Border),size=popup->GetBox().GetSize(Rml::BoxArea::Border);
        mirror->SetProperty("display","block");mirror->SetProperty("left",std::to_string(at.x)+"px");mirror->SetProperty("top",std::to_string(at.y)+"px");mirror->SetProperty("width",std::to_string(size.x)+"px");mirror->SetProperty("height",std::to_string(size.y)+"px");
        for(const auto* name:{"font-family","font-size","font-weight","--accent-soft"})if(const auto* value=popup->GetProperty(name))mirror->SetProperty(name,value->ToString());
        mirror->SetProperty("color",BaseAppearance()==1?"#282624":"#faf9f7");std::string markup;
        for(int i=0;i<popup->GetNumChildren();++i){auto* option=popup->GetChild(i);if(!option->IsVisible())continue;const auto point=option->GetAbsoluteOffset(Rml::BoxArea::Border),bounds=option->GetBox().GetSize(Rml::BoxArea::Border);markup+="<div class=\"menu-option"+std::string(option->IsPseudoClassSet("checked")||option->IsPseudoClassSet("hover")?" active":"")+"\" style=\"left:"+std::to_string(point.x-at.x)+"px;top:"+std::to_string(point.y-at.y)+"px;width:"+std::to_string(bounds.x)+"px;height:"+std::to_string(bounds.y)+"px\">"+option->GetInnerRML()+"</div>";}
        const float excess=popup->GetScrollHeight()-popup->GetClientHeight();if(excess>1){const float dp=document->GetContext()->GetDensityIndependentPixelRatio(),track=std::max(1.f,size.y-24*dp),thumb=std::min(track,std::max(28*dp,track*popup->GetClientHeight()/popup->GetScrollHeight()));markup+="<div class=\"menu-scroll\" style=\"top:"+std::to_string(12*dp+(track-thumb)*popup->GetScrollTop()/excess)+"px;height:"+std::to_string(thumb)+"px\"/>";}
        if(markup!=selectMenuMarkup){selectMenuMarkup=markup;mirror->SetInnerRML(markup);}return true;
    }
    void Labels() {
        Rml::ElementList labels;document->QuerySelectorAll(labels,"[data-control]");
        for(auto* label:labels){const auto key=label->GetAttribute<Rml::String>("data-control","");for(const auto& item:ControlLabels)if(key==item.key){label->SetInnerRML(Rml::StringUtilities::EncodeRml(originalLabels?item.original:item.friendly));if(originalLabels||std::string(item.original)==item.friendly)label->RemoveAttribute("title");else label->SetAttribute("title",std::string(item.original));break;}}
        Element("setting-original-labels")->SetClass("on",originalLabels);
    }
    void Page(const std::string& id) {
        Navigation(id);Visible("overview",true);Visible("inspector",false);
        for(const auto* page:{"overview","frame","neural","hdr"})document->SetClass(std::string(page)+"-page",id=="nav-"+std::string(page));
        Element("overview")->SetScrollTop(0);
        if(id=="nav-look"||id=="nav-passes"||id=="nav-effects")Open(id=="nav-look"?"look":id=="nav-effects"?"effects":"passes");
    }
    void InstallExtraControls() {
        effects.document=document;effects.Set(nlohmann::json{{"generation",0},{"fields",nlohmann::json::array()}});
        hdr.document=document;
        hdr.Set({},false,false,"Install a supported RenoDX HDR package to configure it here.");
        addons.document=document;addons.Set({},false,"");
        for(const auto& control:ExtraControls)if(!values.contains(control.key))values[control.key]=control.initial;defaults=values;
        const auto install=[&](const char* container,const char* page,const std::string& prefix) {
            std::vector<std::string> groups;for(const auto& c:ExtraControls)if(std::string(c.page)==page && std::find(groups.begin(),groups.end(),c.section)==groups.end())groups.push_back(c.section);
            std::string markup;int index=0;
            for(const auto& group:groups){const auto body=prefix+"body-"+std::to_string(index);std::string title=group;for(auto& ch:title)ch=char(std::toupper(static_cast<unsigned char>(ch)));
                markup+="<div class=\"option-group\"><button id=\"group-toggle-"+body+"\" class=\"group-heading"+(index==0 && std::string(page)!="look"?" expanded":"")+"\"><img class=\"glyph\" src=\"icons/sliders-horizontal-light.png\"/><span class=\"button-label\">"+title+"</span><span class=\"chevron\"/></button><div id=\""+body+"\" class=\"group-body\""+(index==0 && std::string(page)!="look"?"":" style=\"display: none\"")+">";
                for(const auto& c:ExtraControls)if(std::string(c.page)==page && c.section==group){if(prefix=="extra-main-"&&(std::string(c.key)=="work_scale"||std::string(c.key)=="pre_sr"))continue;const auto id=prefix+c.key;extraFields[id]=&c;const auto label=Rml::StringUtilities::EncodeRml(c.label);const auto reset="<button id=\"reset-"+id+"\" class=\"reset-value\" title=\"Reset value\"><img class=\"glyph\" src=\"icons/arrow-counter-clockwise-light.png\"/></button>";
                    if(std::string(c.kind)=="toggle")markup+="<div class=\"inherit-row option-toggle\"><label data-control=\""+std::string(c.key)+"\">"+label+"</label><button id=\""+id+"\" class=\"switch\"><span/></button>"+reset+"</div>";
                    else if(std::string(c.kind)=="choice")markup+="<div class=\"slider-field\"><div class=\"field-heading\"><label data-control=\""+std::string(c.key)+"\">"+label+"</label>"+reset+"</div><select id=\""+id+"\">"+c.options+"</select></div>";
                    else markup+="<div class=\"slider-field\"><div class=\"field-heading\"><label data-control=\""+std::string(c.key)+"\">"+label+"</label><span id=\""+id+"-value\"/>"+reset+"</div><input id=\""+id+"\" class=\"range\" type=\"range\" min=\""+std::to_string(c.minimum)+"\" max=\""+std::to_string(c.maximum)+"\" step=\""+std::to_string(c.step)+"\" value=\""+std::to_string(values.at(c.key))+"\"/></div>";
                }markup+="<p id=\""+body+"-availability\" class=\"hint group-availability\" style=\"display: none\"/>";if(group=="Area")markup+="<p class=\"hint\">Uses distance, not character recognition.</p>";markup+="</div></div>";++index;
            }Element(container)->SetInnerRML(markup);
        };
        install("extra-neural","neural","extra-main-");install("extra-frame","frame","extra-frame-");install("extra-look","look","extra-look-");install("extra-processing","neural","extra-popup-");install("extra-frame-popup","frame","extra-fgpopup-");
    }
    void BeginNrPreview() {if(nrPreviewActive||values["enabled"]==0||Element("nr-toggle")->IsPseudoClassSet("disabled"))return;nrBeforePreview=values["enabled"];nrPreviewActive=true;values["enabled"]=0;Sync();}
    void EndNrPreview() {if(!nrPreviewActive)return;nrPreviewActive=false;values["enabled"]=nrBeforePreview;Sync();}
    void CheckPreviewFocus() {if(!nrPreviewActive||!monitorPreviewFocus)return;DWORD owner=0;GetWindowThreadProcessId(GetForegroundWindow(),&owner);if(owner!=GetCurrentProcessId())EndNrPreview();}
    bool BarSettings() const {return layout=="bar"&&settingsOpen;}
    std::string RenderResolutionText() const {
        std::string text=std::to_string(int(std::round(values.at("work_scale")*100)))+"%";
        if(session.nrKnown&&session.nrRunning&&session.nrWidth&&session.nrHeight)return text+" ("+std::to_string(session.nrWidth)+" × "+std::to_string(session.nrHeight)+")";
        if(preview){const auto view=document->GetContext()->GetDimensions();return text+" ("+std::to_string(int(std::round(view.x*values.at("work_scale"))))+" × "+std::to_string(int(std::round(view.y*values.at("work_scale"))))+")";}
        return text+" (not reported)";
    }
    void RenderResolutionLabel() {auto* reading=Element("render-resolution-value");reading->SetInnerRML(RenderResolutionText());if(preview)reading->SetAttribute("title","Preview estimate from the canvas size; no game is connected.");else reading->RemoveAttribute("title");}


    // The connected runtime reports its own pass ceiling (Feeder NR allows 4,
    // OptiScaler 3); the preview keeps OptiScaler's.
    int pass=2,passesMax=3;
    int appearance=4;
    std::array<float,3> accent{.19f,.46f,.80f};
    std::string accentMode="adaptive",customAccent;
    MaterialColor::Color adaptiveAccent{.64f,.64f,.64f},adaptiveTarget{.64f,.64f,.64f};bool adaptiveSeeded=false;
    double lastAccentUpdate=-1,nextAccentSample=0;
    std::array<Backdrop::SceneColor,4> filtered;
    std::array<bool,4> panelDark{};
    double lastAdapt=-1;
    bool dark=false, syncing=false;
    std::string inspectorPanel="passes";
    std::string layout="floating";
    std::string sidePanelSide="left",barPosition="bottom";
    bool resizing=false;std::string resizeEdge;Rml::Vector2f resizeStart{},resizeOrigin{},resizeSize{};
    std::map<std::string,Rml::Vector2f> layoutSizes;
    Rml::Element* dragged=nullptr;
    Rml::Vector2f dragStart{},dragOrigin{};
    std::vector<std::string> stacking{"main-panel","inspector","welcome","type-panel"};
    std::string copyFont="roboto",headingFont="bakbak";
    int copySize=22,copyWeight=500,headingSize=36,headingWeight=400,overlayScale=100;
    float lightOpacity=100,darkOpacity=80,clearOpacity=20,accentCharacter=10,accentOpacity=26,accentSaturation=100,blurRadius=48,grainAmount=4.f,blendStrength=0;
    std::string surfaceBlend="normal";
    std::string headingAccentBlend="screen",controlAccentBlend="screen";
    float headingAccentStrength=100,controlAccentStrength=65;
    bool inspectorAnchored=false,prefsDirty=false,customTheme=false,moreOpen=false,godModeOpen=false,textDepth=true,invertDark=false,toastPill=false,motionEnabled=true;
    int sceneRequest=-1;
    bool showStats=true,showWelcome=true,showNotifications=true,bindingShortcut=false,settingsOpen=false;
    int shortcut=Rml::Input::KI_DELETE,shortcutModifiers=0;
    std::string shortcutLabel="Del",welcomePosition="top-right",primaryMenu="game",optiShortcut="Insert";
    std::map<std::string,bool> menuSettings{{"opti-menu",true},{"opti-intro",false},{"reshade-menu",true},{"reshade-intro",false}};
    ForgeSession::Snapshot session;
    bool nrAvailable=true,fgAvailable=true;
    void Capabilities(bool nr,bool fg) {
        if(nr==nrAvailable&&fg==fgAvailable)return;nrAvailable=nr;fgAvailable=fg;
        const auto show=[&](const char* id,bool enabled){if(enabled)Element(id)->RemoveProperty("display");else Element(id)->SetProperty("display","none");};
        show("frame-section",fg);show("nav-frame",fg);
        for(const auto* id:{"neural-section","nav-neural","nav-look","nav-passes","preview-original"})show(id,nr);
        show("tuning-footer",nr||fg);
        Element("presets")->GetParentNode()->SetProperty("display",nr||fg?"flex":"none");
        for(const auto* id:{"overview-nr","popup-nr"}){auto* row=Element(id)->GetParentNode();if(nr)row->RemoveProperty("display");else row->SetProperty("display","none");}
        for(const auto* id:{"overview-displayed","popup-displayed"}){auto* row=Element(id)->GetParentNode();if(fg)row->RemoveProperty("display");else row->SetProperty("display","none");}
        document->SetClass("effects-only",!nr&&!fg);
        if((!nr&&(activeNavigation=="nav-neural"||activeNavigation=="nav-look"||activeNavigation=="nav-passes"))||(!fg&&activeNavigation=="nav-frame"))Page("nav-overview");
        Session(session);Reflow();
    }
    void Welcome() {if(!showWelcome)return;Visible("toast-icon",false);Element("welcome")->SetClass("with-icon",false);Element("toast-message")->SetInnerRML("Press <span class=\"keycap\">"+Rml::StringUtilities::EncodeRml(shortcutLabel)+"</span> for controls");Element("welcome")->SetProperty("width","500dp");Visible("welcome",true);PositionWelcome();Raise("welcome");Enter("welcome");toastUntil=0;}
    void ToggleOverlay() {if(primaryMenu=="optiscaler")return;if(setupStep>=0){if(Element("type-panel")->IsVisible()){Visible("type-panel",false);Visible("main-panel",false);}else UpdateSetup();return;}EndNrPreview();if(BarSettings())Settings(false);const bool show=!Element("main-panel")->IsVisible();Visible("main-panel",show);if(show){Raise("main-panel");Enter("main-panel");}else{Visible("inspector",false);Visible("type-panel",false);Welcome();}}
    void Settings(bool show) {
        EndNrPreview();const bool leaving=settingsOpen&&!show;if(show&&!settingsOpen)beforeSettingsNavigation=activeNavigation;
        auto* screen=Element("settings-screen");if(!settingsHome)settingsHome=screen->GetParentNode();
        settingsOpen=show;const bool modal=BarSettings();if(modal)for(const auto* id:{"pass-inspector","look-inspector","extra-processing","extra-frame-popup","popup-metadata","hdr-inspector","effects-inspector","addons-inspector"})Visible(id,false);auto* destination=modal?Element("settings-modal-host"):settingsHome;
        if(screen->GetParentNode()!=destination)destination->AppendChild(screen->GetParentNode()->RemoveChild(screen));
        document->SetClass("settings-page",show);document->SetClass("bar-settings",modal);Visible("settings-modal-host",modal);
        Visible("settings-screen",show);Visible("overview",!show||modal);Visible("inspector",modal);inspectorAnchored=false;Element("inspector")->SetClass("anchored",false);
        screen->SetScrollTop(0);Element("inspector")->SetScrollTop(0);if(show)Navigation("nav-settings");else if(leaving){if(!navigationHistory.empty()&&navigationHistory.back()==beforeSettingsNavigation)navigationHistory.pop_back();navigatingBack=true;Page(beforeSettingsNavigation);navigatingBack=false;}UpdateBack();
        fittedLayout.clear();SyncSettings();Reflow();if(modal){Raise("inspector");Enter("inspector");}if(show&&layout=="centered")Element("nav-settings")->ScrollIntoView();
    }
    void SyncSettings() {Select("side-panel-side","side-"+sidePanelSide);Select("bar-position","bar-"+barPosition);const bool was=typographySync;typographySync=true;for(const auto& [id,on]:menuSettings)Element(("setting-"+id).c_str())->SetClass("on",on);Element("setting-helper")->SetClass("on",helperEnabled);Element("setting-startup")->SetClass("on",startWithWindows);Element("setting-stats")->SetClass("on",showStats);Element("setting-welcome")->SetClass("on",showWelcome);Element("setting-notifications")->SetClass("on",showNotifications);Element("shortcut-key")->SetInnerRML(bindingShortcut?"…":Rml::StringUtilities::EncodeRml(shortcutLabel));dynamic_cast<Rml::ElementFormControl*>(Element("welcome-position"))->SetValue(welcomePosition);dynamic_cast<Rml::ElementFormControl*>(Element("primary-menu"))->SetValue(primaryMenu);dynamic_cast<Rml::ElementFormControl*>(Element("opti-shortcut"))->SetValue(optiShortcut);PositionWelcome();typographySync=was;}
    void Session(const ForgeSession::Snapshot& snapshot) {session=snapshot;RenderResolutionLabel();Element("compact-frame-time")->SetInnerRML("Frame "+(ForgeSession::Available(snapshot.gameFps)&&snapshot.gameFps>0?ForgeSession::Number(1000/snapshot.gameFps,2)+" ms":"—"));Element("compact-nr-size")->SetInnerRML(snapshot.nrRunning&&snapshot.nrWidth&&snapshot.nrHeight?std::to_string(snapshot.nrWidth)+" × "+std::to_string(snapshot.nrHeight):"Dimensions not reported");Element("compact-frames")->SetInnerRML(ForgeSession::Frames(snapshot));Element("compact-neural")->SetInnerRML(ForgeSession::Neural(snapshot));Element("compact-ratio")->SetInnerRML(snapshot.framesKnown&&snapshot.measuredRatio>=1&&snapshot.measuredRatio<=8?ForgeSession::Number(snapshot.measuredRatio,1)+"×":"");for(const auto* p:{"overview","popup"}){const std::string prefix=p;Element((prefix+"-nr").c_str())->SetInnerRML(ForgeSession::Neural(snapshot));Element((prefix+"-frame").c_str())->SetInnerRML(ForgeSession::Available(snapshot.gameFps)&&snapshot.gameFps>0?ForgeSession::Number(1000/snapshot.gameFps,2)+" ms":"—");Element((prefix+"-rendered").c_str())->SetInnerRML(ForgeSession::Number(snapshot.gameFps));Element((prefix+"-displayed").c_str())->SetInnerRML(snapshot.framesKnown?ForgeSession::Number(snapshot.displayedFps):"—");}if(showStats&&(nrAvailable||fgAvailable))Element("compact-live")->RemoveProperty("display");else Element("compact-live")->SetProperty("display","none");if(showStats)Element("bar-live")->RemoveProperty("display");else Element("bar-live")->SetProperty("display","none");}
    void PositionWelcome() {
        if(!document->IsVisible())return;
        if(welcomePosition!="top-right"&&welcomePosition!="top-left"&&welcomePosition!="top-center"&&welcomePosition!="bottom-right"&&welcomePosition!="bottom-left")welcomePosition="top-right";
        entrances.erase("welcome");pendingEntrance.erase("welcome");coasting.erase("welcome");
        for(const auto* prop:{"left","right","top","bottom","margin-left","margin-top"})Element("welcome")->RemoveProperty(prop);
        const auto view=document->GetContext()->GetDimensions();const float dp=document->GetContext()->GetDensityIndependentPixelRatio();
        document->GetContext()->Update();auto* welcome=Element("welcome");const auto size=welcome->GetBox().GetSize(Rml::BoxArea::Border);
        const bool bottom=welcomePosition.rfind("bottom",0)==0;
        float x=welcomePosition.find("left")!=std::string::npos?32*dp:welcomePosition=="top-center"?(view.x-size.x)*.5f:view.x-size.x-32*dp;
        float y=bottom?view.y-size.y-32*dp:32*dp;
        // Preview windows can have a game selector. Keep its chrome out of
        // every selected toast anchor, including variable-width notifications.
        if(!bottom)if(auto* toolbar=document->QuerySelector(".prototype-toolbar");toolbar&&toolbar->IsVisible()){const auto at=toolbar->GetAbsoluteOffset(Rml::BoxArea::Border);const auto bounds=toolbar->GetBox().GetSize(Rml::BoxArea::Border);if(x<at.x+bounds.x&&x+size.x>at.x&&y<at.y+bounds.y)y=at.y+bounds.y+12*dp;}
        welcome->SetProperty("right","auto");welcome->SetProperty("bottom","auto");
        welcome->SetProperty("left",std::to_string(std::clamp(x,12*dp,std::max(12*dp,view.x-size.x-12*dp)))+"px");welcome->SetProperty("top",std::to_string(std::clamp(y,12*dp,std::max(12*dp,view.y-size.y-12*dp)))+"px");
    }
    void Metadata() {const auto view=document->GetContext()->GetDimensions();const auto size=std::to_string(view.x)+" × "+std::to_string(view.y);for(const auto* id:{"compact-size","overview-size","popup-size"})Element(id)->SetInnerRML(size);}
    double toastUntil=0;
    void Notify(const std::string& text,const std::string& icon="info") {if(!showNotifications)return;Element("toast-icon")->SetAttribute("src","icons/"+icon+"-light.png");Visible("toast-icon",true);Element("welcome")->SetClass("with-icon",true);Element("toast-message")->SetInnerRML(Rml::StringUtilities::EncodeRml(text));Element("welcome")->SetProperty("width",std::to_string(std::clamp(234+int(text.size())*8,420,760))+"dp");Visible("welcome",true);PositionWelcome();Raise("welcome");Enter("welcome");toastUntil=Rml::GetSystemInterface()->GetElapsedTime()+3.;}
    bool reducedMotion=false;
    float inspectorAnchorX=0;std::string inspectorSource;bool dragStarted=false;float dragThreshold=0;
    struct Entrance {double start;Rml::Vector2f target;float previous;};
    struct Coast {Rml::Vector2f position,velocity;std::string follower;Rml::Vector2f offset;};
    std::map<std::string,Entrance> entrances;
    std::map<std::string,Coast> coasting;
    std::map<std::string,Rml::Vector2f> windowVelocity;
    std::unordered_set<std::string> pendingEntrance;
    double lastAnimation=-1,dragTime=0;
    Rml::Vector2f dragLast{},dragVelocity{};
    Rml::Vector2i fittedView{-1,-1};Rml::Vector2f fittedMainSize{};float fittedDensity=0;std::string fittedLayout;bool fittedSettings=false,mainMoved=false;int fittedCopy=0;
    float TopInset() {
        const float dp=document->GetContext()->GetDensityIndependentPixelRatio();
        if(document->IsClassSet("desktop-preview")){
            if(layout=="floating"||layout=="bar")return 24*dp;
            // A previous layout may still place the picker at a side or bottom edge.
            if(auto* toolbar=document->QuerySelector(".prototype-toolbar");toolbar&&toolbar->IsVisible()){const auto height=toolbar->GetBox().GetSize(Rml::BoxArea::Border).y;return height>0?30*dp+height:78*dp;}
            return 24*dp;
        }
        if(auto* toolbar=document->QuerySelector(".prototype-toolbar")){const auto size=toolbar->GetBox().GetSize(Rml::BoxArea::Border);if(toolbar->IsVisible())return size.y>0?toolbar->GetAbsoluteOffset(Rml::BoxArea::Border).y+size.y+12*dp:78*dp;}
        return 24*dp;
    }
    void Reflow() {
        if(!document->IsVisible())return;
        auto* context=document->GetContext();const auto view=context->GetDimensions();const float dp=context->GetDensityIndependentPixelRatio(),inset=TopInset(),contentTop=view.y/dp<700?112.f:184.f;
        const bool changed=view!=fittedView||dp!=fittedDensity||layout!=fittedLayout||settingsOpen!=fittedSettings||copySize!=fittedCopy;
        auto* main=Element("main-panel");
        if(changed){
            fittedView=view;fittedDensity=dp;fittedLayout=layout;fittedSettings=settingsOpen;fittedCopy=copySize;fittedMainSize={};
            const bool centered=layout=="centered",bar=layout=="bar";
            const float maxWidth=std::max(280*dp,view.x-48*dp),minimumWidth=std::min((centered?900.f:480.f)*dp,maxWidth),limitWidth=bar?maxWidth:std::min((centered?10000.f:760.f)*dp,maxWidth);
            if(!resizing){if(const auto savedWidth=ReadPositionValue(layout+".width");savedWidth>=280&&savedWidth<=10000)layoutSizes[layout].x=savedWidth;if(const auto savedHeight=ReadPositionValue(layout+".height");savedHeight>=200&&savedHeight<=10000)layoutSizes[layout].y=savedHeight;}
            const auto customSize=layoutSizes[layout];const float defaultWidth=centered?std::max(1160.f*dp,std::min(1760.f*dp,view.x*.60f*overlayScale/100.f)):660.f*dp;
            const float width=bar?maxWidth:std::clamp(customSize.x>0?customSize.x*dp:defaultWidth,minimumWidth,limitWidth);
            const float top=std::max(inset,std::min(76*dp,view.y*.08f)),available=view.y-inset-24*dp;
            const float defaultHeight=std::min(available,std::max(900*dp,available*.86f));
            main->SetProperty("width",std::to_string(width)+"px");const float maxHeight=bar?std::min(view.y*.68f,available):available;main->SetProperty("height",customSize.y>0?std::to_string(std::clamp(customSize.y*dp,std::min(280*dp,maxHeight),maxHeight))+"px":centered?std::to_string(defaultHeight)+"px":"auto");
            main->SetProperty("max-height",std::to_string(centered?available:bar?std::min(view.y*.68f,available):view.y-top-24*dp)+"px");
            main->SetProperty("margin-left","0px");main->SetProperty("margin-top","0px");
            document->SetClass("compact-bar",bar&&width/dp<1050);
            if(bar){auto* live=Element("bar-live");auto* row=live->GetParentNode();auto moved=row->RemoveChild(live);if(width/dp<1050)row->AppendChild(std::move(moved));else row->InsertBefore(std::move(moved),document->QuerySelector(".window-actions"));}
            document->SetClass("compact-height",view.y/dp<700);
            const float nav=(copySize*11.f+64)*dp,left=nav+56*dp,contentWidth=width-left-40*dp;
            document->SetClass("compact-content",(centered?contentWidth:width-132*dp)/dp<500);document->SetClass("wide-content",centered&&contentWidth/dp>=820);document->SetClass("three-columns",centered&&contentWidth/dp>=1200);
            if(centered){auto* footer=Element("tuning-footer");footer->SetProperty("left",std::to_string(left)+"px");footer->SetProperty("width",std::to_string(contentWidth)+"px");footer->SetProperty("right","auto");const float height=std::max(80*dp,std::min(900*dp,available)-(contentTop+32)*dp);
                for(const auto* id:{"overview","settings-screen"}){auto* e=Element(id);e->SetProperty("left",std::to_string(left)+"px");e->SetProperty("top",std::to_string(contentTop)+"dp");e->SetProperty("width",std::to_string(contentWidth)+"px");e->SetProperty("height",std::to_string(height)+"px");}
                auto* navElement=document->QuerySelector(".sidebar");navElement->SetProperty("width",std::to_string(nav)+"px");navElement->SetProperty("top",std::to_string(contentTop)+"dp");navElement->SetProperty("height",std::to_string(height)+"px");
                auto* editor=Element("inspector");editor->SetProperty("width",std::to_string(contentWidth)+"px");editor->SetProperty("height",std::to_string(height)+"px");editor->SetProperty("max-height",std::to_string(height)+"px");
            }else{for(const auto* property:{"left","width","right"})Element("tuning-footer")->RemoveProperty(property);for(const auto* id:{"overview","settings-screen"})for(const auto* property:{"left","top","width","height"})Element(id)->RemoveProperty(property);auto* editor=Element("inspector");editor->SetProperty("width",std::to_string(std::min((BarSettings()?660.f:560.f)*dp,view.x-48*dp))+"px");editor->SetProperty("height","auto");editor->SetProperty("max-height",std::to_string(BarSettings()?available:view.y*.76f)+"px");}
            auto* appearancePanel=Element("type-panel");appearancePanel->SetProperty("width",std::to_string(std::min(480*dp,view.x-48*dp))+"px");appearancePanel->SetProperty("max-height",std::to_string(available)+"px");
            document->QuerySelector(".appearance-body")->SetProperty("max-height",std::to_string(std::max(80*dp,available-136*dp))+"px");
            context->Update();PositionWelcome();
        }
        context->Update();
        // Put the scroll rail in the panel's outer padding, preserving the
        // same card edges as the header and footer even when scrolling starts.
        for(const auto* id:{"overview","settings-screen"}){auto* e=Element(id);const auto* margin=e->GetLocalProperty("margin-right");if(layout=="centered"){if(margin)e->RemoveProperty("margin-right");}else{const float gutter=std::max(0.f,e->GetBox().GetSize(Rml::BoxArea::Padding).x-e->GetClientWidth());if(!margin||std::abs(margin->Get<float>()+gutter)>.1f)e->SetProperty("margin-right",std::to_string(-gutter)+"px");}}
        context->Update();const auto size=main->GetBox().GetSize(Rml::BoxArea::Border);
        if(changed||size!=fittedMainSize){fittedMainSize=size;const bool centered=layout=="centered",bar=layout=="bar";const auto at=main->GetAbsoluteOffset(Rml::BoxArea::Border);
            const float edge=std::min(36*dp,view.x*.04f);
            const float x=mainMoved?std::clamp(at.x,12*dp,std::max(12*dp,view.x-size.x-12*dp)):centered?(view.x-size.x)*.5f:bar?24*dp:sidePanelSide=="right"?view.x-size.x-edge:edge;
            const float y=mainMoved?std::clamp(at.y,inset,std::max(inset,view.y-size.y-12*dp)):centered?inset+(view.y-inset-24*dp-size.y)*.5f:bar?(barPosition=="top"?inset:view.y-size.y-24*dp):std::max(inset,std::min(76*dp,view.y*.08f));
            main->SetProperty("left",std::to_string(x)+"px");main->SetProperty("top",std::to_string(y)+"px");if(auto it=entrances.find("main-panel");it!=entrances.end())it->second.target={x,y};}
        if(layout=="centered"){const auto footerHeight=Element("tuning-footer")->IsVisible()?Element("tuning-footer")->GetBox().GetSize(Rml::BoxArea::Border).y+44*dp:32*dp;const float height=std::max(48*dp,size.y-contentTop*dp-footerHeight);for(const auto* id:{"overview","settings-screen","inspector"}){auto* e=Element(id);if(std::fabs(e->GetBox().GetSize(Rml::BoxArea::Border).y-height)>.1f)e->SetProperty("height",std::to_string(height)+"px");if(std::string(id)=="inspector")e->SetProperty("max-height",std::to_string(height)+"px");}document->QuerySelector(".sidebar")->SetProperty("height",std::to_string(height)+"px");}
        if(changed)RestorePosition("main-panel");
        if(inspectorAnchored&&!inspectorSource.empty()&&Element("inspector")->IsVisible()&&!dragStarted)PlaceAnchoredInspector();
        if(BarSettings()){context->Update();auto* modal=Element("inspector");const auto bounds=modal->GetBox().GetSize(Rml::BoxArea::Border);modal->SetProperty("left",std::to_string((view.x-bounds.x)*.5f)+"px");modal->SetProperty("top",std::to_string(inset+(view.y-inset-24*dp-bounds.y)*.5f)+"px");modal->SetProperty("margin-left","0px");modal->SetProperty("margin-top","0px");}
        if(layout=="centered"){const auto at=main->GetAbsoluteOffset(Rml::BoxArea::Border);const float left=(copySize*11.f+64)*dp+56*dp;auto* editor=Element("inspector");const auto before=editor->GetAbsoluteOffset(Rml::BoxArea::Border);if(std::fabs(before.x-at.x-left)>.1f||std::fabs(before.y-at.y-contentTop*dp)>.1f){editor->SetProperty("margin-left","0px");editor->SetProperty("margin-top","0px");editor->SetProperty("left",std::to_string(at.x+left)+"px");editor->SetProperty("top",std::to_string(at.y+contentTop*dp)+"px");}}
        for(const auto* id:{"inspector","type-panel"}){auto* e=Element(id);if((std::string(id)=="inspector"&&inspectorAnchored)||!e->IsVisible()||(layout=="centered"&&std::string(id)=="inspector")||dragged==e||entrances.contains(id)||pendingEntrance.contains(id)||coasting.contains(id))continue;const auto at=e->GetAbsoluteOffset(Rml::BoxArea::Border);const auto bounds=e->GetBox().GetSize(Rml::BoxArea::Border);const float x=std::clamp(at.x,12*dp,std::max(12*dp,view.x-bounds.x-12*dp)),y=std::clamp(at.y,inset,std::max(inset,view.y-bounds.y-12*dp));if(std::fabs(x-at.x)>.1f||std::fabs(y-at.y)>.1f){e->SetProperty("margin-left","0px");e->SetProperty("margin-top","0px");e->SetProperty("left",std::to_string(x)+"px");e->SetProperty("top",std::to_string(y)+"px");}}
        if(auto* body=Element("nr-body");body->IsVisible()){const std::string display=document->IsClassSet("wide-content")?"flex":"block";const auto* local=body->GetLocalProperty("display");if(!local||local->Get<Rml::String>()!=display)body->SetProperty("display",display);}
        for(const auto* id:{"hdr-main-fields","extra-neural","extra-frame","extra-look","pass-fields","settings-cards"})balancedCards.Arrange(Element(id),document->IsClassSet("wide-content"));
        PlaceSetup();PlaceQuickLayouts();PlaceColorEditor();
    }
    void Enter(const std::string& id) {pendingEntrance.insert(id);coasting.erase(id);}
    void Animate(double now) {
        if(nativeOverlayPending&&now>=nativeOverlayDeadline)NativeOverlaysResult(true);
        CheckPreviewFocus();Reflow();if(layoutPickerDismiss>0&&now>=layoutPickerDismiss)QuickLayouts(false);
        const float dt=lastAnimation<0?1.f/60:std::clamp(float(now-lastAnimation),.001f,.05f);lastAnimation=now;
        if(!pendingEntrance.empty()){document->GetContext()->Update();for(const auto& id:pendingEntrance){auto* e=Element(id.c_str());const auto at=e->GetAbsoluteOffset(Rml::BoxArea::Border);e->SetProperty("margin-left","0px");e->SetProperty("margin-top","0px");e->SetProperty("left",std::to_string(at.x)+"px");e->SetProperty("top",std::to_string(at.y)+"px");entrances[id]={now,at,0};}pendingEntrance.clear();}
        for(auto it=entrances.begin();it!=entrances.end();) {const float t=reducedMotion?1.f:std::clamp(float((now-it->second.start)/.38),0.f,1.f);const float lift=(it->first=="welcome"?-14.f:24.f)*document->GetContext()->GetDensityIndependentPixelRatio()*(1-Motion::Spring(t));auto* e=Element(it->first.c_str());const float opacity=std::min(1.f,t*2.2f);e->SetProperty("opacity",std::to_string(opacity));e->SetProperty("--window-opacity",std::to_string(opacity));e->SetProperty("top",std::to_string(it->second.target.y+lift)+"px");windowVelocity[it->first]={0,(lift-it->second.previous)/dt};it->second.previous=lift;if(t>=1){windowVelocity[it->first]={};it=entrances.erase(it);}else ++it;}
        for(auto it=coasting.begin();it!=coasting.end();){auto* e=Element(it->first.c_str());auto& m=it->second;const auto view=document->GetContext()->GetDimensions();const auto size=e->GetBox().GetSize(Rml::BoxArea::Border);if(reducedMotion)m.velocity={};else{Motion::Coast(m.position.x,m.velocity.x,view.x-size.x-8,dt);Motion::Coast(m.position.y,m.velocity.y,view.y-size.y-8,dt);}e->SetProperty("left",std::to_string(m.position.x)+"px");e->SetProperty("top",std::to_string(m.position.y)+"px");windowVelocity[it->first]=m.velocity;if(!m.follower.empty()){auto* f=Element(m.follower.c_str());f->SetProperty("left",std::to_string(m.position.x+m.offset.x)+"px");f->SetProperty("top",std::to_string(m.position.y+m.offset.y)+"px");windowVelocity[m.follower]=m.velocity;}if(m.velocity.x==0 && m.velocity.y==0){RememberPosition(it->first);if(!m.follower.empty())RememberPosition(m.follower);it=coasting.erase(it);}else ++it;}
    }
    Rml::Element* dragFollower=nullptr;
    Rml::Vector2f followerOrigin{};
    float followerAnchorOrigin=0;
    fs::path preferences,positionPreferences;std::string positionIdentity;
    fs::path PositionPath() const {const auto base=positionPreferences.empty()?preferences:positionPreferences;if(base.empty())return {};std::string suffix;if(!positionIdentity.empty()){uint64_t hash=14695981039346656037ull;for(unsigned char c:positionIdentity){hash^=c;hash*=1099511628211ull;}suffix="-"+std::to_string(hash);}return base.parent_path()/(base.stem().wstring()+L"-positions"+fs::path(suffix).wstring()+L".ini");}
    std::string PositionKey(const std::string& id) const {return layout+"."+sidePanelSide+"."+barPosition+"."+id+(id=="inspector"?"."+inspectorPanel:"");}
    float ReadPositionValue(const std::string& key,float fallback=-1) const {const auto path=PositionPath();if(path.empty())return fallback;wchar_t text[80]{};GetPrivateProfileStringW(L"Positions",fs::path(key).c_str(),L"",text,80,path.c_str());try{const float value=std::stof(text);return std::isfinite(value)?value:fallback;}catch(...){return fallback;}}
    void RememberPosition(const std::string& id) {if(id!="main-panel"&&id!="type-panel"&&id!="inspector")return;if(id=="inspector"&&layout=="centered")return;const auto path=PositionPath();if(path.empty())return;auto* e=Element(id.c_str());auto at=e->GetAbsoluteOffset(Rml::BoxArea::Border);const auto size=e->GetBox().GetSize(Rml::BoxArea::Border);if(const auto* left=e->GetLocalProperty("left");left&&left->unit==Rml::Unit::PX)at.x=left->Get<float>();if(const auto* top=e->GetLocalProperty("top");top&&top->unit==Rml::Unit::PX)at.y=top->Get<float>();const auto view=document->GetContext()->GetDimensions();if(view.x<=0||view.y<=0)return;fs::create_directories(path.parent_path());
        const auto put=[&](const std::string& key,float value){WritePrivateProfileStringW(L"Positions",fs::path(key).c_str(),fs::path(std::to_string(value)).c_str(),path.c_str());};const auto key=PositionKey(id);put(key+".x",(at.x+size.x*.5f)/view.x);put(key+".y",(at.y+size.y*.5f)/view.y);
        if(id=="main-panel"){const auto custom=layoutSizes[layout];if(custom.x>0)put(layout+".width",custom.x);if(custom.y>0)put(layout+".height",custom.y);}}
    bool RestorePosition(const std::string& id) {if(id=="inspector"&&layout=="centered")return false;const auto key=PositionKey(id);const float x=ReadPositionValue(key+".x"),y=ReadPositionValue(key+".y");if(x<0||x>1||y<0||y>1)return false;auto* context=document->GetContext();context->Update();auto* e=Element(id.c_str());const auto size=e->GetBox().GetSize(Rml::BoxArea::Border);const auto view=context->GetDimensions();const float dp=context->GetDensityIndependentPixelRatio();
        e->SetProperty("left",std::to_string(std::clamp(x*view.x-size.x*.5f,12*dp,std::max(12*dp,view.x-size.x-12*dp)))+"px");e->SetProperty("top",std::to_string(std::clamp(y*view.y-size.y*.5f,TopInset(),std::max(TopInset(),view.y-size.y-12*dp)))+"px");e->SetProperty("margin-left","0px");e->SetProperty("margin-top","0px");if(id=="main-panel")mainMoved=true;return true;}
    Rml::Vector2f SnappedPosition(Rml::Vector2f at,Rml::Vector2f size) {const auto* context=document->GetContext();const auto view=context->GetDimensions();const float dp=context->GetDensityIndependentPixelRatio(),distance=28*dp;const auto axis=[&](float value,float low,float high){high=std::max(low,high);return std::min(std::abs(value-low),std::abs(value-high))<=distance?(std::abs(value-low)<=std::abs(value-high)?low:high):std::clamp(value,low,high);};return Rml::Vector2f{size.x>=view.x-64*dp?(view.x-size.x)*.5f:axis(at.x,12*dp,view.x-size.x-12*dp),axis(at.y,TopInset(),view.y-size.y-12*dp)};}
    bool SnapReleased(const std::string& id) {auto* e=Element(id.c_str());auto before=e->GetAbsoluteOffset(Rml::BoxArea::Border);const auto size=e->GetBox().GetSize(Rml::BoxArea::Border);if(const auto* left=e->GetLocalProperty("left");left&&left->unit==Rml::Unit::PX)before.x=left->Get<float>();if(const auto* top=e->GetLocalProperty("top");top&&top->unit==Rml::Unit::PX)before.y=top->Get<float>();const auto at=SnappedPosition(before,size);const auto view=document->GetContext()->GetDimensions();const float dp=document->GetContext()->GetDensityIndependentPixelRatio();const bool horizontal=size.x<view.x-64*dp&&(std::abs(at.x-12*dp)<1||std::abs(at.x-(view.x-size.x-12*dp))<1),vertical=std::abs(at.y-TopInset())<1||std::abs(at.y-(view.y-size.y-12*dp))<1;e->SetProperty("left",std::to_string(at.x)+"px");e->SetProperty("top",std::to_string(at.y)+"px");
        if(id=="main-panel"){mainMoved=true;if(layout=="floating"&&horizontal){sidePanelSide=at.x<view.x*.5f?"left":"right";Select("side-panel-side","side-"+sidePanelSide);prefsDirty=true;}if(layout=="bar"&&vertical){barPosition=at.y<view.y*.5f?"top":"bottom";Select("bar-position","bar-"+barPosition);document->SetClass("bar-top",barPosition=="top");prefsDirty=true;}}
        return horizontal||vertical;}
    void PositionScene(const std::string& identity){positionIdentity=identity;mainMoved=false;fittedLayout.clear();Reflow();for(const auto* id:{"type-panel","inspector"})if(Element(id)->IsVisible())RestorePosition(id);}

    fs::file_time_type preferencesStamp{};
    double nextPreferencesRead=0;
    void PollPreferences(double now) {
        if(preferences.empty()||prefsDirty||now<nextPreferencesRead)return;nextPreferencesRead=now+.5;
        std::error_code error;const auto stamp=fs::last_write_time(preferences,error);
        if(error||stamp==preferencesStamp)return;
        const auto before=layout,beforeSide=sidePanelSide,beforeBar=barPosition;LoadPreferences(!preview);Typography();Materials();SyncSettings();
        if(before!=layout)Layout(layout);
        if(beforeSide!=sidePanelSide)PanelSide(sidePanelSide);
        if(beforeBar!=barPosition)BarEdge(barPosition);
    }
    bool typographySync=false;
    std::unordered_set<Rml::Element*> clearForeground;
    double lastForeground=-1;
    std::array<float,3> clearAccent{};Backdrop::SceneColor titleBackdrop{};
    bool AccentLight()const {return appearance==4&&accentCharacter>=20&&accentCharacter<72;}
    MaterialColor::Color ActiveAccent()const {
        if(accentMode=="theme"){const float tone=BaseAppearance()==1?.32f:BaseAppearance()==2?.64f:.82f;return {tone,tone,tone};}
        return accentMode=="custom"?MaterialColor::ParseAccent(customAccent,accent):adaptiveAccent;
    }
    std::array<float,3> SurfaceTint()const {if(accentMode=="adaptive"&&BaseAppearance()==3)return MaterialColor::AdaptiveClearSurface(ActiveAccent());return MaterialColor::AccentSurface(ActiveAccent(),accentCharacter,accentMode=="adaptive"?std::min(accentSaturation,100.f):accentSaturation);}
    void UpdateAccent(const Backdrop& backdrop,double now) {
        const float dt=lastAccentUpdate<0?0.f:float(std::clamp(now-lastAccentUpdate,0.,.1));lastAccentUpdate=now;
        if(accentMode!="adaptive")return;
        if(now>=nextAccentSample){nextAccentSample=now+.15;auto* main=Element("main-panel");const auto at=main->GetAbsoluteOffset(Rml::BoxArea::Border),size=main->GetBox().GetSize(Rml::BoxArea::Border);auto sample=backdrop.Accent(at.x,at.y,size.x,size.y);if(!sample.valid)sample=backdrop.Background(at.x,at.y,size.x,size.y);
            if(sample.valid){const auto candidate=MaterialColor::SceneAccent({sample.r,sample.g,sample.b});float difference=0;for(size_t i=0;i<3;++i)difference+=std::abs(candidate[i]-adaptiveTarget[i]);if(difference>.045f)adaptiveTarget=candidate;if(!adaptiveSeeded){adaptiveAccent=adaptiveTarget;adaptiveSeeded=true;}}}
        const float amount=float(1-std::exp(-dt/.22f));for(size_t i=0;i<3;++i)adaptiveAccent[i]+=(adaptiveTarget[i]-adaptiveAccent[i])*amount;

    }
    MaterialColor::Color AccentBackdrop(size_t slot,Backdrop::SceneColor local={}) {
        const auto scene=local.valid?local:filtered[slot];MaterialColor::Color base=scene.valid?MaterialColor::Color{scene.r,scene.g,scene.b}:MaterialColor::Color{.35f,.35f,.35f};
        if(appearance==3)base=MaterialColor::ClearSurface(base,clearOpacity/100.f,MaterialColor::Mode(surfaceBlend),blendStrength/100.f);
        else if(appearance==4){const auto tint=SurfaceTint();for(size_t i=0;i<3;++i)base[i]=base[i]*(1-accentOpacity/100.f)+tint[i]*accentOpacity/100.f;}
        else {const float tint=(appearance==1?lightOpacity:darkOpacity)/100.f,tone=appearance==1?.86f:.07f;for(auto& channel:base)channel=channel*(1-tint)+tone*tint;}
        return base;
    }
    std::string AccentTone(size_t slot,bool heading,Backdrop::SceneColor local={}) {
        const auto active=ActiveAccent();auto source=active;
        // Headings share a theme reference, including across detached windows.
        // Scene adaptation belongs to the glass, not each heading's ink.
        const float headingBase=(appearance==1||AccentLight())?.86f:BaseAppearance()==3?.58f:.24f;
        const auto base=heading?MaterialColor::Color{headingBase,headingBase,headingBase}:AccentBackdrop(slot,local);
        const auto& mode=heading?headingAccentBlend:controlAccentBlend;const float strength=(heading?headingAccentStrength:controlAccentStrength)/100.f;
        auto mixed=MaterialColor::Blend(base,source,MaterialColor::Mode(mode));
        if(mode=="screen"&&MaterialColor::LinearLuma(source)>.55f)mixed=source;
        for(size_t i=0;i<3;++i)source[i]+=(mixed[i]-source[i])*strength;
        if(heading&&!customTheme){if(BaseAppearance()==3)source=MaterialColor::ClearHeading(active);else if(BaseAppearance()==2)source=MaterialColor::Blend({.24f,.24f,.24f},active,MaterialColor::Mode("screen"));else source=MaterialColor::Blend(base,MaterialColor::Saturation(active,150),MaterialColor::Mode("multiply"));}
        if(heading&&(BaseAppearance()==3||BaseAppearance()==2)){MaterialColor::Color brightest{0,0,0};float luma=-1;for(size_t i=0;i<4;++i){if(!Element(i==0?"main-panel":i==1?"inspector":i==2?"welcome":"type-panel")->IsVisible())continue;const auto background=AccentBackdrop(i);const float value=MaterialColor::LinearLuma(background);if(value>luma){luma=value;brightest=background;}}if(titleBackdrop.valid){const auto titleSurface=AccentBackdrop(0,titleBackdrop);if(MaterialColor::LinearLuma(titleSurface)>luma)brightest=titleSurface;}source=MaterialColor::LightenForContrast(source,brightest);}
        if(appearance==1||AccentLight()){
            const float contrast=(MaterialColor::LinearLuma(base)+.05f)/(MaterialColor::LinearLuma(source)+.05f);
            if(MaterialColor::YellowFamily(active)){
                if(heading&&(contrast<4.5f||MaterialColor::MuddyShade(source)))return "#3e3b37ff";
                if(!MaterialColor::MuddyShade(active)&&MaterialColor::MuddyShade(source))source=active;
            }else {const float target=heading?4.5f:3.f;for(int step=0;step<64&&(MaterialColor::LinearLuma(base)+.05f)/(MaterialColor::LinearLuma(source)+.05f)<target;++step)for(auto& channel:source)channel*=.96f;}
        }
        return Hex(source[0],source[1],source[2]);
    }
    void AdaptiveForeground(const Backdrop& backdrop,double now) {
        UpdateAccent(backdrop,now);
        auto* title=Element("main-panel")->QuerySelector("h1");const auto titleAt=title->GetAbsoluteOffset(Rml::BoxArea::Border),titleSize=title->GetBox().GetSize(Rml::BoxArea::Border);titleBackdrop=backdrop.Background(titleAt.x,titleAt.y,titleSize.x,titleSize.y);
        const float dt=lastForeground<0?.1f:float(now-lastForeground);lastForeground=now;document->SetClass("clear-foreground",BaseAppearance()==3);
        if(clearAccent!=accent)clearAccent=accent;
        Rml::ElementList elements;document->QuerySelectorAll(elements,"h1,h2,h3,h1 span,h2 span,h3 span,label,input,.hint,.brand,.welcome-wordmark,.welcome-message,.preview-note,button,select,selectvalue,.button-label,.field-heading span,.status-note,.glyph,.metadata-line,.mini-stat strong,.mini-stat-detail");
        const std::unordered_set<Rml::Element*> alive(elements.begin(),elements.end());
        std::erase_if(clearForeground,[&](auto* e){return !alive.contains(e);});
        if(BaseAppearance()!=3){for(auto* e:clearForeground){e->RemoveProperty("color");e->RemoveProperty("image-color");e->RemoveProperty("font-effect");}clearForeground.clear();return;}
        const auto headingInk=AccentTone(0,true);
        for(auto* e:elements){bool panel=false,menu=false;for(auto* p=e;p;p=p->GetParentNode()){if(p->IsClassSet("glass"))panel=true;if(p->GetId()=="settings-menu"||p->GetTagName()=="selectbox")menu=true;}if(!panel||menu)continue;
            Rml::Element* heading=nullptr;for(auto* p=e;p;p=p->GetParentNode())if(p->GetTagName()=="h1"||p->GetTagName()=="h2"||p->GetTagName()=="h3")heading=p;
            clearForeground.insert(e);
            const auto property=e->IsClassSet("glyph")?"image-color":"color";const auto desired=heading?headingInk:"#f5f1eaff";
            const auto packed=std::stoul(desired.substr(1),nullptr,16);const Rml::Colourb color{Rml::byte(packed>>24),Rml::byte(packed>>16),Rml::byte(packed>>8),Rml::byte(packed)};
            const auto* local=e->GetLocalProperty(property);if(!local||local->Get<Rml::Colourb>()!=color)e->SetProperty(property,desired);
            // Keep the existing subtle material-wide text depth. Never add a
            // second, high-opacity shadow or outline to individual headings.
            if(e->GetLocalProperty("font-effect"))e->RemoveProperty("font-effect");
        }
    }
    void Raise(const std::string& id) {
        std::erase(stacking,id);stacking.push_back(id);
        if(layout=="centered" && id=="main-panel" && Element("inspector")->IsVisible()) {std::erase(stacking,std::string("inspector"));stacking.push_back("inspector");}
        for(size_t i=0;i<stacking.size();++i)Element(stacking[i].c_str())->SetProperty("z-index",std::to_string(i+1));
    }
    void UseTheme(int mode) {
        const auto theme=ForgeAppearance::Get(mode);appearance=mode;customTheme=false;headingAccentBlend=(mode==1||mode==4)?"multiply":"screen";controlAccentBlend=(mode==1||mode==4)?"normal":"screen";headingAccentStrength=100;controlAccentStrength=65;
        lightOpacity=ForgeAppearance::Light.tint;darkOpacity=ForgeAppearance::Dark.tint;clearOpacity=ForgeAppearance::Clear.tint;accentCharacter=35;accentOpacity=MaterialColor::AccentOpacity(accentCharacter)*100;accentSaturation=100;
        blurRadius=theme.blur;grainAmount=theme.grain;surfaceBlend=theme.blend;blendStrength=theme.strength;invertDark=false;textDepth=true;Materials();
    }
    int BaseAppearance() const {return appearance==4?(accentCharacter<20?3:accentCharacter<72?1:2):appearance;}
    void UseAppearance(int base,bool tint) {UseTheme(tint?4:base);if(tint){accentCharacter=base==3?10.f:base==1?50.f:100.f;accentSaturation=base==2?94.f:200.f;accentOpacity=100*MaterialColor::AccentOpacity(accentCharacter);headingAccentBlend=base==1?"multiply":"screen";controlAccentBlend=base==1?"normal":"screen";Materials();}}
    void ShowAppearance() {
        Visible("type-panel",true);Raise("type-panel");document->GetContext()->Update();
        const auto at=Element("main-panel")->GetAbsoluteOffset(Rml::BoxArea::Border),main=Element("main-panel")->GetBox().GetSize(Rml::BoxArea::Border),size=Element("type-panel")->GetBox().GetSize(Rml::BoxArea::Border);const auto view=document->GetContext()->GetDimensions();
        const float inset=TopInset();Element("type-panel")->SetProperty("left",std::to_string(std::clamp(layout=="floating"&&sidePanelSide=="right"?at.x-size.x-24:at.x+main.x+24,12.f,std::max(12.f,view.x-size.x-12)))+"px");Element("type-panel")->SetProperty("top",std::to_string(std::clamp(layout=="bar"?(barPosition=="top"?at.y+main.y+20:at.y-size.y-20):at.y,inset,std::max(inset,view.y-size.y-12)))+"px");RestorePosition("type-panel");Enter("type-panel");
    }
    void Materials() {
        if(typographySync)return;typographySync=true;
        if(accentMode=="theme"&&appearance==4)appearance=BaseAppearance();
        if(appearance==4&&!customTheme){headingAccentBlend=AccentLight()?"multiply":"screen";controlAccentBlend=AccentLight()?"normal":"screen";}
        const float opacity=appearance==1?lightOpacity:appearance==3?clearOpacity:appearance==4?accentOpacity:darkOpacity;
        dynamic_cast<Rml::ElementFormControl*>(Element("tint-opacity"))->SetValue(std::to_string(opacity));
        Element("tint-opacity-value")->SetInnerRML(std::to_string(int(opacity))+"%");
        dynamic_cast<Rml::ElementFormControl*>(Element("surface-blend"))->SetValue(surfaceBlend);
        dynamic_cast<Rml::ElementFormControl*>(Element("blur-radius"))->SetValue(std::to_string(blurRadius));Element("blur-radius-value")->SetInnerRML(std::to_string(int(blurRadius))+" px");
        dynamic_cast<Rml::ElementFormControl*>(Element("grain-amount"))->SetValue(std::to_string(grainAmount));char grain[24];std::snprintf(grain,sizeof(grain),"%.1f%%",grainAmount);Element("grain-amount-value")->SetInnerRML(grain);
        dynamic_cast<Rml::ElementFormControl*>(Element("blend-strength"))->SetValue(std::to_string(blendStrength));Element("blend-strength-value")->SetInnerRML(std::to_string(int(blendStrength))+"%");dynamic_cast<Rml::ElementFormControl*>(Element("blend-strength"))->SetDisabled(surfaceBlend=="normal");
        for(const auto& entry:std::vector<std::pair<std::string,std::pair<std::string,float>>>{{"heading",{headingAccentBlend,headingAccentStrength}},{"control",{controlAccentBlend,controlAccentStrength}}}){dynamic_cast<Rml::ElementFormControl*>(Element((entry.first+"-accent-mode").c_str()))->SetValue(entry.second.first);dynamic_cast<Rml::ElementFormControl*>(Element((entry.first+"-accent-strength").c_str()))->SetValue(std::to_string(entry.second.second));Element((entry.first+"-accent-strength-value").c_str())->SetInnerRML(std::to_string(int(entry.second.second))+"%");}
        Element("text-depth")->SetClass("on",textDepth);Element("dark-inverted")->SetClass("on",invertDark);Element("motion-effects")->SetClass("on",motionEnabled);
        Visible("dark-inversion-row",preview&&appearance==2);document->SetClass("production-ui",!preview);Visible("appearance-more",setupStep<0);Visible("appearance-details",moreOpen&&setupStep<0);Element("appearance-more")->SetClass("expanded",moreOpen);
        Visible("appearance-god-mode",preview&&setupStep<0);Visible("appearance-god-details",preview&&godModeOpen&&setupStep<0);Element("appearance-god-mode")->SetClass("expanded",godModeOpen);
        Visible("accent-character-row",preview&&godModeOpen&&appearance==4);dynamic_cast<Rml::ElementFormControl*>(Element("accent-character"))->SetValue(std::to_string(accentCharacter));Element("accent-character-value")->SetInnerRML(accentCharacter<25?"Clear":accentCharacter<72?"Light":"Dark");
        Visible("accent-saturation-row",preview&&godModeOpen&&appearance==4);dynamic_cast<Rml::ElementFormControl*>(Element("accent-saturation"))->SetValue(std::to_string(accentSaturation));Element("accent-saturation-value")->SetInnerRML(std::to_string(int(accentSaturation))+"%");
        for(const auto* mode:{"theme","custom","adaptive"})Element((std::string("accent-source-")+mode).c_str())->SetClass("selected",accentMode==mode);
        Visible("accent-custom-row",accentMode=="custom");Visible("accent-tint",accentMode!="theme");ColorEditor();
        Element("accent-source-hint")->SetInnerRML(accentMode=="theme"?"Neutral controls, without a surface tint.":accentMode=="custom"?"Your game’s Library color, or a color you choose.":"Samples the scene behind this panel, with gentle transitions.");
        Element("accent-tint")->SetClass("selected",appearance==4);Element("accent-tint")->QuerySelector(".switch")->SetClass("on",appearance==4);
        if(!preview)Element("font-select")->GetParentNode()->SetProperty("display","none");else Element("font-select")->GetParentNode()->RemoveProperty("display");
        Element("toast-pill")->SetClass("selected",toastPill);Element("toast-rounded")->SetClass("selected",!toastPill);
        Element("theme-label")->SetInnerRML(customTheme?"Custom":BaseAppearance()==1?"Light":BaseAppearance()==2?"Dark":"Clear");Element("theme-description")->SetInnerRML(customTheme?(appearance==1?"Custom · based on Light":appearance==2?"Custom · based on Dark":appearance==4?"Custom · based on Accent":"Custom · based on Clear"):"Select a surface to restore its defaults.");
        document->SetClass("dark-inverted",appearance==2 && invertDark);Element("welcome")->SetProperty("--corner-radius",toastPill?"28":"14");Element("welcome")->SetProperty("border-radius",toastPill?"28dp":"14dp");
        typographySync=false;prefsDirty=true;Reflow();
    }
    void LoadPreferences(bool runtime=false,const fs::path& explicitPath={}) {
        wchar_t folder[32768]{};if(!GetEnvironmentVariableW(L"LOCALAPPDATA",folder,32768))return;
        preferences=fs::path(folder)/(runtime?L"rtxForge/overlay-appearance.ini":L"rtxForge/prototypes/overlay-rmlui.ini");
        if(runtime){wchar_t executable[32768]{};const auto count=GetModuleFileNameW(nullptr,executable,32768);uint64_t identity=14695981039346656037ull;for(DWORD i=0;i<count;++i){identity^=uint64_t(towlower(executable[i]));identity*=1099511628211ull;}const auto defaults=preferences;preferences=defaults.parent_path()/L"overlay-games"/(std::to_wstring(identity)+L".ini");std::error_code error;fs::create_directories(preferences.parent_path(),error);if(!fs::exists(preferences)&&fs::exists(defaults))fs::copy_file(defaults,preferences,fs::copy_options::none,error);}
        if(!explicitPath.empty())preferences=explicitPath;
        setupPreferences=(runtime?fs::path(folder)/L"rtxForge":preferences.parent_path())/(runtime?L"overlay-setup.ini":L"overlay-preview-setup.ini");setupComplete=GetPrivateProfileIntW(L"Setup",L"Version",0,setupPreferences.c_str())>=1;
        const auto number=[&](const wchar_t* key,int fallback,int low,int high){return std::clamp(int(GetPrivateProfileIntW(L"Appearance",key,fallback,preferences.c_str())),low,high);};
        copySize=number(L"TextSize",22,16,26);copyWeight=number(L"TextWeight",500,100,900);headingSize=36;headingWeight=400;overlayScale=number(L"ScaleBaseline",0,0,120)==120?number(L"Scale",100,70,150):100;
        const bool current=number(L"ThemeVersion",0,0,ForgeAppearance::Version)==ForgeAppearance::Version;
        appearance=current?number(L"Theme",4,1,4):4;
        const auto theme=ForgeAppearance::Get(appearance);
        lightOpacity=current?float(number(L"LightTint",100,0,100)):100;darkOpacity=current?float(number(L"DarkTint",80,0,100)):80;clearOpacity=current?float(number(L"ClearTint",20,0,100)):20;
        accentCharacter=float(number(L"AccentCharacter",10,0,100));accentOpacity=float(number(L"AccentTint",int(MaterialColor::AccentOpacity(accentCharacter)*100),0,100));
        accentSaturation=float(number(L"AccentSaturation",100,0,200));
        blurRadius=current?float(number(L"Blur",int(theme.blur),16,48)):theme.blur;grainAmount=current?number(L"Grain",40,0,80)/10.f:4;
        customTheme=current&&number(L"Custom",0,0,1)!=0;textDepth=number(L"TextDepth",1,0,1)!=0;invertDark=number(L"InvertDark",0,0,1)!=0;toastPill=number(L"ToastPill",0,0,1)!=0;motionEnabled=number(L"Motion",1,0,1)!=0;
        blendStrength=current?float(number(L"BlendStrength",int(theme.strength),0,100)):theme.strength;surfaceBlend=theme.blend;
        originalLabels=number(L"OriginalLabels",0,0,1)!=0;Labels();showStats=number(L"ShowStats",1,0,1)!=0;showWelcome=number(L"ShowWelcome",1,0,1)!=0;showNotifications=number(L"ShowNotifications",1,0,1)!=0;
        shortcut=number(L"Shortcut",Rml::Input::KI_DELETE,0,255);shortcutModifiers=number(L"ShortcutModifiers",0,0,7);
        for(auto& [key,on]:menuSettings)on=number(fs::path("Menu-"+key).c_str(),on,0,1)!=0;
        wchar_t source[80]{};GetPrivateProfileStringW(L"Appearance",L"AccentMode",L"adaptive",source,80,preferences.c_str());accentMode=Utf8(source);if(accentMode!="theme"&&accentMode!="custom")accentMode="adaptive";
        GetPrivateProfileStringW(L"Appearance",L"AccentColor",L"",source,80,preferences.c_str());customAccent=Utf8(source);if(!MaterialColor::ValidAccent(customAccent))customAccent.clear();
        dynamic_cast<Rml::ElementFormControl*>(Element("accent-color"))->SetValue(customAccent);
        wchar_t text[80]{};GetPrivateProfileStringW(L"Appearance",L"HeadingFont",L"bakbak",text,80,preferences.c_str());const auto heading=Utf8(text);if(heading=="bakbak"||heading=="roboto"||heading=="inter"||heading=="aptos")headingFont=heading;
        GetPrivateProfileStringW(L"Appearance",L"TextFont",L"roboto",text,80,preferences.c_str());const auto copy=Utf8(text);if(copy=="roboto"||copy=="inter"||copy=="aptos")copyFont=copy;
        if(current){GetPrivateProfileStringW(L"Appearance",L"SurfaceBlend",fs::path(theme.blend).c_str(),text,80,preferences.c_str());const auto blend=Utf8(text);if(MaterialColor::Valid(blend))surfaceBlend=blend;}
        headingAccentBlend=(appearance==1||AccentLight())?"multiply":"screen";controlAccentBlend=(appearance==1||AccentLight())?"normal":"screen";
        headingAccentStrength=float(number(L"HeadingAccentStrength",int(headingAccentStrength),0,100));controlAccentStrength=float(number(L"ControlAccentStrength",int(controlAccentStrength),0,100));
        if(customTheme)for(const auto& [key,destination]:std::vector<std::pair<const wchar_t*,std::string*>>{{L"HeadingAccentBlend",&headingAccentBlend},{L"ControlAccentBlend",&controlAccentBlend}}){GetPrivateProfileStringW(L"Appearance",key,fs::path(*destination).c_str(),text,80,preferences.c_str());const auto mode=Utf8(text);if(MaterialColor::Valid(mode))*destination=mode;}
        GetPrivateProfileStringW(L"Appearance",L"ShortcutLabel",L"Del",text,80,preferences.c_str());shortcutLabel=Utf8(text);
        GetPrivateProfileStringW(L"Appearance",L"WelcomePosition",L"top-right",text,80,preferences.c_str());welcomePosition=Utf8(text);
        GetPrivateProfileStringW(L"Appearance",L"PrimaryMenu",L"game",text,80,preferences.c_str());primaryMenu=Utf8(text)=="optiscaler"?"optiscaler":"game";
        GetPrivateProfileStringW(L"Appearance",L"OptiShortcut",L"Insert",text,80,preferences.c_str());optiShortcut=Utf8(text)=="F8"?"F8":Utf8(text)=="Disabled"?"Disabled":"Insert";
        GetPrivateProfileStringW(L"Appearance",L"Layout",L"floating",text,80,preferences.c_str());const auto savedLayout=Utf8(text);if(savedLayout=="floating"||savedLayout=="centered"||savedLayout=="bar")layout=savedLayout;
        GetPrivateProfileStringW(L"Appearance",L"SidePanelSide",L"left",text,80,preferences.c_str());sidePanelSide=Utf8(text)=="right"?"right":"left";
        GetPrivateProfileStringW(L"Appearance",L"BarPosition",L"bottom",text,80,preferences.c_str());barPosition=Utf8(text)=="top"?"top":"bottom";
        positionPreferences=preferences;
        std::error_code error;preferencesStamp=fs::last_write_time(preferences,error);
    }
    void SavePreferences() {
        if(preferences.empty())return;fs::create_directories(preferences.parent_path());
        const auto put=[&](const wchar_t* key,int value){const auto text=std::to_wstring(value);WritePrivateProfileStringW(L"Appearance",key,text.c_str(),preferences.c_str());};
        WritePrivateProfileStringW(L"Appearance",L"AccentMode",fs::path(accentMode).c_str(),preferences.c_str());WritePrivateProfileStringW(L"Appearance",L"AccentColor",fs::path(customAccent).c_str(),preferences.c_str());
        put(L"TextSize",copySize);put(L"TextWeight",copyWeight);put(L"HeadingSize",headingSize);put(L"HeadingWeight",headingWeight);put(L"Scale",overlayScale);put(L"Theme",appearance);put(L"LightTint",int(lightOpacity));put(L"DarkTint",int(darkOpacity));
        put(L"ThemeVersion",ForgeAppearance::Version);put(L"ScaleBaseline",120);put(L"Custom",customTheme);put(L"TextDepth",textDepth);put(L"InvertDark",invertDark);put(L"ToastPill",toastPill);put(L"Motion",motionEnabled);put(L"Grain",int(grainAmount*10));put(L"BlendStrength",int(blendStrength));put(L"ClearTint",int(clearOpacity));put(L"AccentCharacter",int(accentCharacter));put(L"AccentTint",int(accentOpacity));put(L"AccentSaturation",int(accentSaturation));put(L"Blur",int(blurRadius));
        put(L"HeadingAccentStrength",int(headingAccentStrength));put(L"ControlAccentStrength",int(controlAccentStrength));WritePrivateProfileStringW(L"Appearance",L"HeadingAccentBlend",fs::path(headingAccentBlend).c_str(),preferences.c_str());WritePrivateProfileStringW(L"Appearance",L"ControlAccentBlend",fs::path(controlAccentBlend).c_str(),preferences.c_str());
        WritePrivateProfileStringW(L"Appearance",L"HeadingFont",fs::path(headingFont).c_str(),preferences.c_str());WritePrivateProfileStringW(L"Appearance",L"SurfaceBlend",fs::path(surfaceBlend).c_str(),preferences.c_str());prefsDirty=false;
        WritePrivateProfileStringW(L"Appearance",L"TextFont",fs::path(copyFont).c_str(),preferences.c_str());
        put(L"OriginalLabels",originalLabels);put(L"ShowStats",showStats);put(L"ShowWelcome",showWelcome);put(L"ShowNotifications",showNotifications);put(L"Shortcut",shortcut);put(L"ShortcutModifiers",shortcutModifiers);
        for(const auto& [key,on]:menuSettings)put(fs::path("Menu-"+key).c_str(),on);
        for(const auto& [key,value]:std::map<std::wstring,std::string>{{L"ShortcutLabel",shortcutLabel},{L"WelcomePosition",welcomePosition},{L"PrimaryMenu",primaryMenu},{L"OptiShortcut",optiShortcut},{L"Layout",layout},{L"SidePanelSide",sidePanelSide},{L"BarPosition",barPosition}})WritePrivateProfileStringW(L"Appearance",key.c_str(),fs::path(value).c_str(),preferences.c_str());
        std::error_code error;preferencesStamp=fs::last_write_time(preferences,error);
    }
    void Typography() {
        if(typographySync)return;typographySync=true;
        headingFont="bakbak";copyWeight=500;headingWeight=400;headingSize=copySize+14;
        document->GetContext()->SetDensityIndependentPixelRatio(1.2f*overlayScale/100.f);
        document->SetProperty("--copy-font",copyFont=="aptos"?"Overlay UI":copyFont=="inter"?"Inter Variable":"Roboto");document->SetProperty("--heading-font","Bakbak One");
        document->SetProperty("--copy-weight","500");document->SetProperty("--heading-weight","400");
        document->SetProperty("--copy-size",std::to_string(copySize)+"dp");document->SetProperty("--page-size",std::to_string(copySize+8)+"dp");document->SetProperty("--group-size",std::to_string(copySize-2)+"dp");document->SetProperty("--utility-size",std::to_string(copySize-3)+"dp");document->SetProperty("--segment-size",std::to_string(copySize-2)+"dp");document->SetProperty("--meta-size",std::to_string(copySize-6)+"dp");document->SetProperty("--micro-size",std::to_string(copySize-8)+"dp");document->SetProperty("--glyph-size",std::to_string(copySize)+"dp");document->SetProperty("--heading-glyph-size",std::to_string(copySize+4)+"dp");document->SetProperty("--sample-size",std::to_string(copySize+4)+"dp");document->SetProperty("--sample-small",std::to_string(copySize+1)+"dp");document->SetProperty("--sample-large",std::to_string(copySize+7)+"dp");document->SetProperty("--heading-size",std::to_string(headingSize)+"dp");document->SetProperty("--section-size",std::to_string(headingSize-10)+"dp");document->SetProperty("--hint-size",std::to_string(copySize-4)+"dp");document->SetProperty("--value-size",std::to_string(copySize-3)+"dp");
        dynamic_cast<Rml::ElementFormControl*>(Element("font-select"))->SetValue(copyFont);Element("scale-value")->SetInnerRML(std::to_string(overlayScale)+"%");
        for(const auto* id:{"text-smaller","text-default","text-larger"})Element(id)->SetClass("selected",copySize==(std::string(id)=="text-smaller"?20:std::string(id)=="text-larger"?24:22));
        typographySync=false;prefsDirty=true;
    }
    void Layout(const std::string& mode) {
        Settings(false);QuickLayouts(false);prefsDirty=true;mainMoved=false;
        auto* metadata=Element("open-session");if(!metadataHome)metadataHome=metadata->GetParentNode();auto* metadataTarget=mode=="bar"?document->QuerySelector(".brand-row"):metadataHome;if(metadata->GetParentNode()!=metadataTarget){auto moved=metadata->GetParentNode()->RemoveChild(metadata);if(mode=="bar")metadataTarget->InsertBefore(std::move(moved),document->QuerySelector(".window-actions"));else metadataTarget->InsertBefore(std::move(moved),metadataTarget->GetChild(0));}
        auto* status=Element("feature-status");if(!statusHome)statusHome=status->GetParentNode();auto* statusTarget=mode=="centered"?Element("overview-metadata"):statusHome;if(status->GetParentNode()!=statusTarget){auto moved=status->GetParentNode()->RemoveChild(status);if(mode=="centered")statusTarget->InsertBefore(std::move(moved),statusTarget->QuerySelector(".session-facts"));else statusTarget->AppendChild(std::move(moved));}
        auto* live=Element("compact-live");if(!compactLiveHome)compactLiveHome=live->GetParentNode();auto* liveTarget=mode=="bar"?Element("bar-live"):compactLiveHome;if(live->GetParentNode()!=liveTarget)liveTarget->AppendChild(live->GetParentNode()->RemoveChild(live));
        if(mode=="floating"&&status->GetParentNode()==statusHome){auto moved=statusHome->RemoveChild(status);statusHome->InsertBefore(std::move(moved),Element("compact-live"));}
        layout=mode;document->SetClass("overview-page",mode=="centered");document->SetClass("layout-centered",mode=="centered");document->SetClass("layout-bar",mode=="bar");document->SetClass("bar-top",barPosition=="top");
        hdr.EntryVisibility();
        document->SetClass("frame-page",false);document->SetClass("neural-page",false);document->SetClass("hdr-page",false);Navigation("nav-overview");navigationHistory.clear();UpdateBack();
        for(const auto* id:{"main-panel","inspector"})for(const auto* property:{"left","top","margin-left","margin-top"})Element(id)->RemoveProperty(property);
        inspectorAnchored=false;
        Visible("overview",true);Visible("inspector",false);Select("layout-switch","layout-"+mode);Select("side-panel-side","side-"+sidePanelSide);
        Element("main-panel")->SetScrollTop(0);
        fittedLayout.clear();
        Reflow();
        Enter("main-panel");
        document->GetContext()->Update();
    }
    void PanelSide(const std::string& side) {
        sidePanelSide=side=="right"?"right":"left";prefsDirty=true;
        Select("side-panel-side","side-"+sidePanelSide);
        if(layout=="floating"){
            mainMoved=false;fittedLayout.clear();coasting.clear();entrances.clear();pendingEntrance.clear();
            Visible("inspector",false);Visible("type-panel",false);Reflow();Enter("main-panel");
        }
    }
    void BarEdge(const std::string& edge) {
        barPosition=edge=="top"?"top":"bottom";prefsDirty=true;Select("bar-position","bar-"+barPosition);document->SetClass("bar-top",barPosition=="top");
        if(layout=="bar"){mainMoved=false;fittedLayout.clear();coasting.clear();entrances.clear();pendingEntrance.clear();inspectorAnchored=false;if(!BarSettings())Visible("inspector",false);Reflow();Enter("main-panel");}
    }
    static std::string Hex(float r,float g,float b,float a=1) {char text[16];std::snprintf(text,sizeof(text),"#%02x%02x%02x%02x",int(std::clamp(r,0.f,1.f)*255),int(std::clamp(g,0.f,1.f)*255),int(std::clamp(b,0.f,1.f)*255),int(std::clamp(a,0.f,1.f)*255));return text;}
    static float Luma(Backdrop::SceneColor c) {const auto linear=[](float x){return x<=.04045f?x/12.92f:std::pow((x+.055f)/1.055f,2.4f);};return .2126f*linear(c.r)+.7152f*linear(c.g)+.0722f*linear(c.b);}
    std::unordered_map<std::string,std::string> adaptiveProperties;
    void Adapt(const std::array<Backdrop::SceneColor,4>& colors,double now)
    {
        const float amount=lastAdapt<0 ? 1.f:float(1-std::exp(-std::clamp(now-lastAdapt,0.,.1)/.65));lastAdapt=now;
        for(size_t i=0;i<4;++i) {
            auto& c=filtered[i];const bool first=!c.valid;
            if(colors[i].valid) {if(first)c=colors[i];else{c.r+=(colors[i].r-c.r)*amount;c.g+=(colors[i].g-c.g)*amount;c.b+=(colors[i].b-c.b)*amount;}}
            const float light=c.valid?Luma(c):.4f;
            const bool isDark=appearance==2 || (appearance==4&&!AccentLight()) || (appearance==3 && (first?light<.18f:panelDark[i]?light<.20f:light<.16f));
            panelDark[i]=isDark;auto* e=Element(i==0?"main-panel":i==1?"inspector":i==2?"welcome":"type-panel");
            const auto set=[&](const char* name,const std::string& value){const auto key=e->GetId()+name;auto& previous=adaptiveProperties[key];if(previous!=value){previous=value;e->SetProperty(name,value);}};e->SetClass("dark",isDark);
            // Constrain the neutral base. Scene chroma comes through the blurred
            // layer; the material's tone does not add a blue cast of its own.
            set("--surface-tone",std::to_string(appearance==3?.96f:isDark?(invertDark?.13f:.07f):.86f));
            set("--surface-grounding",std::to_string((appearance==4?accentOpacity:appearance==3?clearOpacity:isDark?darkOpacity:lightOpacity)/100.f));
            set("--material-blur",std::to_string(blurRadius));e->SetClass("clear",appearance==3);e->SetClass("accent-theme",appearance==4);
            set("--material-blend",surfaceBlend);set("--material-blend-opacity",std::to_string(blendStrength/100.f));set("--material-texture",std::to_string(grainAmount/100.f));
            set("--accent",AccentTone(i,false));set("--accent-ink",AccentTone(i,true));
            set("--accent-soft",AccentTone(i,false).substr(0,7)+"55");
            const bool lightMenu=BaseAppearance()==1;const auto menuSurface=lightMenu?MaterialColor::Color{.94f,.94f,.94f}:BaseAppearance()==2?MaterialColor::Color{.11f,.12f,.12f}:MaterialColor::Color{.22f,.23f,.24f};set("--menu-fill",Hex(menuSurface[0],menuSurface[1],menuSurface[2],.91f));set("--menu-ink",lightMenu?"#202020ff":"#faf9f7ff");set("--menu-hover",lightMenu?"#0000000f":"#ffffff18");

            set("--shadow-opacity",std::to_string(i==2?.10f:.26f));
        }
        Select("theme-menu",customTheme?"":BaseAppearance()==1?"theme-light":BaseAppearance()==3?"theme-clear":"theme-dark");
        auto* popup=Element("accent-editor");auto* appearancePanel=Element("type-panel");
        popup->SetClass("dark",appearancePanel->IsClassSet("dark"));popup->SetClass("clear",appearance==3);popup->SetClass("accent-theme",appearance==4);
        for(const auto* name:{"--accent","--accent-ink","--accent-soft"})if(const auto* value=appearancePanel->GetProperty(name)){const auto text=value->Get<Rml::String>();const auto key=std::string("accent-editor")+name;if(adaptiveProperties[key]!=text){adaptiveProperties[key]=text;popup->SetProperty(name,text);}}
        QuickLayoutTheme();
    }
    Rml::Element* Element(const char* id) { auto* e=document->GetElementById(id);Require(e!=nullptr,id);return e; }
    // Runs for dozens of controls every frame; an unchanged state touches nothing.
    void Disabled(const char* id,bool disabled) {auto* e=Element(id);if(e->HasAttribute("disabled")==disabled&&e->IsPseudoClassSet("disabled")==disabled)return;if(disabled)e->SetAttribute("disabled","");else e->RemoveAttribute("disabled");e->SetPseudoClass("disabled",disabled);e->SetProperty("focus",disabled?"none":"auto");}
    void Visible(const char* id,bool visible) { Element(id)->SetProperty("display",visible ? (std::string(id)=="welcome"||std::string(id)=="main-panel"||std::string(id)=="appearance-more"||std::string(id)=="appearance-god-mode"||std::string(id)=="accent-tint"?"flex":"block"):"none"); }
    void Message(const std::string& text) { Element("feedback")->SetInnerRML(text); }
    void Put(const std::string& key,float value) { auto before=values;values[key]=value;edits.Record(before,values); }
    void Select(const char* container,const std::string& id) {
        auto* parent=Element(container);
        for(int i=0;i<parent->GetNumChildren();++i) parent->GetChild(i)->SetClass("selected",parent->GetChild(i)->GetId()==id);
    }
    void Sync()
    {
        if(syncing || typographySync||colorPicking)return;
        syncing=true;
        auto range=[&](const char* id,const std::string& key) {
            const auto value=values.at(key);auto* field=dynamic_cast<Rml::ElementFormControl*>(Element(id));Require(field!=nullptr,"Expected range control");
            field->SetValue(std::to_string(value));char text[32];std::snprintf(text,sizeof(text),"%.2f",value);
            Element((std::string(id)+"-value").c_str())->SetInnerRML(text);
        };
        range("strength","intensity");range("detail","detail");range("colour","colour");range("tone","tone");
        dynamic_cast<Rml::ElementFormControl*>(Element("render-resolution"))->SetValue(std::to_string(int(std::round(values.at("work_scale")*100))));
        RenderResolutionLabel();
        const int passCount=int(values.at("passes"));
        Element("pass-count")->SetInnerRML(std::to_string(passCount)+(passCount==1?" pass":" passes"));
        Disabled("pass-minus",passCount<=1);Disabled("pass-plus",passCount>=passesMax);if(pass>passCount)pass=2;
        const auto prefix="pass"+std::to_string(pass)+"_";
        for(const auto* key : {"strength","tone","structure","skin"})range((std::string("pass-")+key).c_str(),prefix+key);
        Element("inherit")->SetClass("on",values[prefix+"inherit"]!=0);Element("pass-fields")->SetProperty("opacity",values[prefix+"inherit"] ? ".35":"1");
        for(const auto* key : {"strength","tone","structure","skin"})dynamic_cast<Rml::ElementFormControl*>(Element((std::string("pass-")+key).c_str()))->SetDisabled(values[prefix+"inherit"]!=0);
        for(const auto* id : {"pass-style-default","pass-style-natural","pass-style-cinematic"})Disabled(id,values[prefix+"inherit"]!=0);
        Select("pass-style",values[prefix+"style"]==0 ? "pass-style-default":values[prefix+"style"]==1 ? "pass-style-natural":"pass-style-cinematic");
        Element("pass-2")->SetClass("selected",pass==2);Element("pass-3")->SetClass("selected",pass==3);Element("pass-4")->SetClass("selected",pass==4);
        Disabled("pass-3",values["passes"]<3);Disabled("pass-4",values["passes"]<4);Disabled("open-passes",values["passes"]<2);
        Element("nr-toggle")->SetClass("on",values["enabled"]!=0||nrPreviewActive);Visible("nr-body",values["enabled"]!=0||nrPreviewActive);
        Element("mfg-toggle")->SetClass("on",values["mfg_enabled"]!=0);Visible("mfg-body",values["mfg_enabled"]!=0);
        for(const auto& [id,on]:std::map<std::string,bool>{{"extra-neural",values["enabled"]!=0},{"extra-frame",values["mfg_enabled"]!=0}}){if(on)Element(id.c_str())->RemoveProperty("display");else Element(id.c_str())->SetProperty("display","none");}
        Disabled("open-processing",values["enabled"]==0);Disabled("open-frame-options",values["mfg_enabled"]==0);
        Element("ratios")->SetProperty("display",values["multiplier"]>=2 ? "flex":"none");
        Select("nr-style",values["style"]==0 ? "style-default":values["style"]==1 ? "style-natural":"style-cinematic");
        Select("mfg-mode",values["dynamic_mfg"]!=0 ? "mode-dynamic":values["multiplier"]<0 ? "mode-auto":"mode-custom");
        Element("mfg-hint")->SetInnerRML(values["dynamic_mfg"]!=0 ? "Adjusts frame generation up to the selected limit.":values["multiplier"]<0 ? "Follows the game’s frame generation setting.":"Uses the selected frame generation multiplier.");
        Select("ratios","ratio-"+std::to_string(int(values["multiplier"])));
        Element("preview-original")->SetClass("selected",nrPreviewActive);
        Element("preview-original-label")->SetInnerRML(nrPreviewActive?"Without NR · release to return":"Hold to preview without NR");
        Disabled("preview-original",(!nrPreviewActive&&values["enabled"]==0)||Element("nr-toggle")->IsPseudoClassSet("disabled"));
        Disabled("undo",edits.past.empty());Disabled("redo",edits.future.empty());
        for(const auto& [id,key] : std::map<std::string,std::string>{{"model-preset","preset"},{"processing-stage","pre_sr"}})
            if(values.contains(key))dynamic_cast<Rml::ElementFormControl*>(Element(id.c_str()))->SetValue(std::to_string(int(values[key])));
        for(const auto& [id,control]:extraFields) {const float value=values.at(control->key);auto* e=Element(id.c_str());if(std::string(control->kind)=="toggle")e->SetClass("on",value!=0);else {dynamic_cast<Rml::ElementFormControl*>(e)->SetValue(std::string(control->kind)=="choice"?std::to_string(int(value)):std::to_string(value));if(std::string(control->kind)!="choice"){char text[48];std::snprintf(text,sizeof(text),std::string(control->key)=="interval"?(value==1?"Every frame":"Every %.0f frames"):std::string(control->key)=="work_scale"?"%.0f%%":control->step>=1?"%.0f":"%.2f",std::string(control->key)=="work_scale"?value*100:value);Element((id+"-value").c_str())->SetInnerRML(std::string(control->key)=="work_scale"?RenderResolutionText():text);}}}
        for(const auto& [id,control]:extraFields)if(std::string(control->key)=="interval"){auto* field=Element(id.c_str());dynamic_cast<Rml::ElementFormControl*>(field)->SetDisabled(values.at("cache")==0||!nrAvailable);field->GetParentNode()->SetClass("inactive-dependent",values.at("cache")==0);}
        auto* passLabel=Element("pass-strength-value")->GetParentNode()->QuerySelector("label");passLabel->SetAttribute("data-control","pass"+std::to_string(pass)+"_strength");
        Labels();syncing=false;
    }
    void Open(const std::string& panel) {
        if(BarSettings())Settings(false);
        if(layout=="bar"&&inspectorAnchored&&Element("inspector")->IsVisible()&&inspectorPanel==panel){Visible("inspector",false);inspectorAnchored=false;return;}
        inspectorPanel=panel;Element("inspector")->SetProperty("margin-left","0px");Element("inspector")->SetProperty("margin-top","0px");
        Element("inspector")->SetScrollTop(0);
        Element("inspector")->SetClass("opening",true);
        Visible("inspector",true);Visible("pass-inspector",panel=="passes");Visible("look-inspector",panel=="look");Visible("extra-processing",panel=="processing");Visible("extra-frame-popup",panel=="frame");Visible("popup-metadata",panel=="overview");Visible("hdr-inspector",panel=="hdr");Visible("effects-inspector",panel=="effects");Visible("addons-inspector",panel=="addons");Element("inspector")->SetClass("session-inspector",panel=="overview");
        const auto icon=panel=="effects"||panel=="addons"?"stack":panel=="hdr"?"sun":panel=="overview"?"gauge":panel=="passes"?"stack":panel=="look"?"sliders-horizontal":panel=="frame"?"film-strip":"cpu";
        const auto title=panel=="effects"?"EFFECTS":panel=="addons"?"SPLIT RENDER":panel=="hdr"?"HDR":panel=="overview"?"SESSION":panel=="processing"?"NEURAL RENDERING":panel=="passes"?"PASS TUNING":panel=="look"?"LOOK &amp; DETAIL":panel=="frame"?"FRAME GENERATION":"PROCESSING";
        Element("inspector-title")->SetInnerRML(std::string("<img class=\"glyph\" src=\"icons/")+icon+"-light.png\"/><span>"+title+"</span>");
        if(layout=="centered")Visible("overview",false);
        Reflow();Raise("inspector");Enter("inspector");inspectorAnchored=layout=="bar";Element("inspector")->SetClass("anchored",inspectorAnchored);
        if(layout=="floating"){
            auto* main=Element("main-panel");auto* popup=Element("inspector");const auto at=main->GetAbsoluteOffset(Rml::BoxArea::Border),mainSize=main->GetBox().GetSize(Rml::BoxArea::Border),size=popup->GetBox().GetSize(Rml::BoxArea::Border);const auto view=document->GetContext()->GetDimensions();
            const float dp=document->GetContext()->GetDensityIndependentPixelRatio();
            popup->SetProperty("left",std::to_string(std::clamp(sidePanelSide=="right"?at.x-size.x-20*dp:at.x+mainSize.x+20*dp,12*dp,std::max(12*dp,view.x-size.x-12*dp)))+"px");popup->SetProperty("top",std::to_string(std::max(TopInset(),at.y))+"px");
        }
        if(inspectorAnchored) {inspectorSource=panel=="effects"?"open-effects":panel=="addons"?"open-addons":panel=="hdr"?"open-hdr":panel=="overview"?"open-session":panel=="passes"?"open-passes":panel=="frame"?"open-frame-options":panel=="processing"?"open-processing":"open-look";PlaceAnchoredInspector();}
        if(RestorePosition("inspector")){inspectorAnchored=false;Element("inspector")->SetClass("anchored",false);}
    }
    void PlaceAnchoredInspector() {
        auto* context=document->GetContext();context->Update();const auto viewport=context->GetDimensions();const float dp=context->GetDensityIndependentPixelRatio();
        auto* source=Element(inspectorSource.c_str());const auto at=source->GetAbsoluteOffset(Rml::BoxArea::Border),bounds=source->GetBox().GetSize(Rml::BoxArea::Border);
        const bool below=barPosition=="top";const float anchor=below?at.y+bounds.y+20*dp:at.y-20*dp;
        auto* popup=Element("inspector");popup->SetProperty("margin-left","0px");popup->SetProperty("margin-top","0px");popup->SetProperty("max-height",std::to_string(std::max(96*dp,below?viewport.y-anchor-24*dp:anchor-TopInset()))+"px");context->Update();
        const auto size=popup->GetBox().GetSize(Rml::BoxArea::Border);inspectorAnchorX=at.x+bounds.x*.5f;
        const Rml::Vector2f target{std::clamp(inspectorAnchorX-size.x*.5f,12*dp,std::max(12*dp,viewport.x-size.x-12*dp)),std::clamp(below?anchor:anchor-size.y,TopInset(),std::max(TopInset(),viewport.y-size.y-12*dp))};
        popup->SetProperty("left",std::to_string(target.x)+"px");popup->SetProperty("top",std::to_string(target.y)+"px");if(auto it=entrances.find("inspector");it!=entrances.end())it->second.target=target;
    }
    void ProcessEvent(Rml::Event& event) override
    {
        if(syncing || typographySync||colorPicking)return;
        auto* target=event.GetTargetElement();
        if(setupStep>=0&&!colorEditorOpen&&event.GetType()=="keydown"&&event.GetParameter<int>("key_identifier",0)==Rml::Input::KI_TAB){
            const std::vector<const char*> choices=setupStep==2?std::vector<const char*>{"appearance-back","setup-native-global","setup-skip","setup-native-confirm"}:setupStep==1?std::vector<const char*>{"appearance-back","theme-light","theme-clear","theme-dark","accent-source-theme","accent-source-adaptive","accent-source-custom","accent-swatch","accent-tint","setup-next"}:std::vector<const char*>{"setup-layout-floating","setup-layout-centered","setup-layout-bar","setup-appearance","setup-native","setup-skip","setup-next"};
            std::vector<Rml::Element*> visible;for(const auto* id:choices){auto* e=Element(id);if(e->IsVisible(true)&&!e->IsPseudoClassSet("disabled"))visible.push_back(e);}auto* focused=document->GetContext()->GetFocusElement();int index=-1;for(size_t i=0;i<visible.size();++i)if(visible[i]==focused)index=int(i);const int direction=event.GetParameter<int>("shift_key",0)?-1:1;if(!visible.empty())visible[(index+direction+int(visible.size()))%int(visible.size())]->Focus();event.StopPropagation();return;
        }
        const auto inside=[&](const char* id){for(auto* e=target;e;e=e->GetParentNode())if(e->GetId()==id)return true;return false;};
        if(event.GetType()=="keydown"&&spectrumOpen&&(inside("spectrum-plane")||inside("spectrum-hue"))){const int key=event.GetParameter<int>("key_identifier",0);bool changed=false;
            if(key==Rml::Input::KI_RETURN||key==Rml::Input::KI_NUMPADENTER||key==Rml::Input::KI_SPACE){if(inside("spectrum-plane"))ChooseSpectrum();else Element("spectrum-plane")->Focus();event.StopPropagation();return;}
            if(inside("spectrum-hue")&&(key==Rml::Input::KI_LEFT||key==Rml::Input::KI_RIGHT)){spectrumHsv[0]=std::clamp(spectrumHsv[0]+(key==Rml::Input::KI_RIGHT?1.f:-1.f)/MaterialColor::SpectrumHues,0.f,.9999f);changed=true;}
            else if(inside("spectrum-plane")){if(key==Rml::Input::KI_LEFT||key==Rml::Input::KI_RIGHT){spectrumHsv[1]=std::clamp(spectrumHsv[1]+(key==Rml::Input::KI_RIGHT?.02f:-.02f),0.f,1.f);changed=true;}if(key==Rml::Input::KI_UP||key==Rml::Input::KI_DOWN){spectrumHsv[2]=std::clamp(spectrumHsv[2]+(key==Rml::Input::KI_UP?.02f:-.02f),0.f,1.f);changed=true;}}
            if(changed){Spectrum();event.StopPropagation();return;}}
        const bool previewTarget=inside("preview-original");
        if(event.GetType()=="mouseup"||(event.GetType()=="blur"&&previewTarget)||(event.GetType()=="keyup"&&(event.GetParameter<int>("key_identifier",0)==Rml::Input::KI_SPACE||event.GetParameter<int>("key_identifier",0)==Rml::Input::KI_RETURN)))EndNrPreview();
        if(previewTarget&&(event.GetType()=="mousedown"||(event.GetType()=="keydown"&&(event.GetParameter<int>("key_identifier",0)==Rml::Input::KI_SPACE||event.GetParameter<int>("key_identifier",0)==Rml::Input::KI_RETURN)))){BeginNrPreview();event.StopPropagation();return;}
        if(event.GetType()=="keydown"&&event.GetParameter<int>("key_identifier",0)==Rml::Input::KI_ESCAPE){EndNrPreview();if(colorEditorOpen){colorEditorOpen=false;ColorEditor();Element("accent-swatch")->Focus();}else if(setupStep>=0)FinishSetup();else if(Element("layout-picker")->IsVisible())QuickLayouts(false);else if(BarSettings())Settings(false);else if(inspectorAnchored){Visible("inspector",false);inspectorAnchored=false;}event.StopPropagation();return;}
        if(event.GetType()=="mousedown"&&colorEditorOpen&&!inside("accent-editor")&&!inside("accent-swatch")){colorEditorOpen=false;ColorEditor();}
        if(event.GetType()=="mousedown"&&!inside("open-layout")&&!inside("layout-picker"))QuickLayouts(false);
        if(event.GetType()=="mousedown"&&inspectorAnchored&&!inside("inspector")&&!inside(inspectorSource.c_str())){Visible("inspector",false);inspectorAnchored=false;}
        if(event.GetType()=="mousedown"&&BarSettings()&&!inside("inspector")&&!inside("type-panel")&&!inside("accent-editor")){Settings(false);event.StopPropagation();return;}
        if(event.GetType()=="keydown") {
            const int key=event.GetParameter<int>("key_identifier",0);const int mods=event.GetParameter<int>("key_modifier_state",0)&7;
            if(bindingShortcut){
                if(key==Rml::Input::KI_ESCAPE){bindingShortcut=false;SyncSettings();event.StopPropagation();return;}
                if(key==Rml::Input::KI_DELETE||(key>=Rml::Input::KI_A&&key<=Rml::Input::KI_Z)||(key>=Rml::Input::KI_F1&&key<=Rml::Input::KI_F12)){
                    shortcut=key;shortcutModifiers=mods;shortcutLabel=(mods&Rml::Input::KM_CTRL?"Ctrl + ":"") + std::string(mods&Rml::Input::KM_ALT?"Alt + ":"") + (mods&Rml::Input::KM_SHIFT?"Shift + ":"");
                    shortcutLabel+=key==Rml::Input::KI_DELETE?"Del":key>=Rml::Input::KI_F1&&key<=Rml::Input::KI_F12?"F"+std::to_string(key-Rml::Input::KI_F1+1):std::string(1,char('A'+key-Rml::Input::KI_A));
                    bindingShortcut=false;prefsDirty=true;SyncSettings();Notify("Shortcut changed to "+shortcutLabel,"sliders");event.StopPropagation();return;
                }
                event.StopPropagation();return;
            }
            if(key==shortcut&&mods==shortcutModifiers){ToggleOverlay();event.StopPropagation();return;}
        }
        if(event.GetType()=="mousemove"&&resizing){
            const float dp=document->GetContext()->GetDensityIndependentPixelRatio();const auto view=document->GetContext()->GetDimensions();const Rml::Vector2f delta{event.GetParameter<float>("mouse_x",0)-resizeStart.x,event.GetParameter<float>("mouse_y",0)-resizeStart.y};
            const bool horizontal=resizeEdge=="resize-left"||resizeEdge=="resize-right",left=resizeEdge=="resize-left",top=resizeEdge=="resize-top";
            const auto center=resizeOrigin+resizeSize*.5f;float w=resizeSize.x,h=resizeSize.y;
            const float maxW=std::max(1.f,std::min(view.x-48*dp,2*std::min(center.x-12*dp,view.x-12*dp-center.x))),maxH=layout=="bar"?std::min(view.y*.68f,view.y-TopInset()-24*dp):std::max(1.f,2*std::min(center.y-TopInset(),view.y-12*dp-center.y));
            if(horizontal)w=std::clamp(resizeSize.x+2*(left?-delta.x:delta.x),std::min((layout=="centered"?900.f:480.f)*dp,maxW),std::min((layout=="centered"?10000.f:760.f)*dp,maxW));else h=std::clamp(resizeSize.y+(layout=="bar"?1.f:2.f)*(top?-delta.y:delta.y),std::min(280*dp,maxH),maxH);
            layoutSizes[layout]={w/dp,h/dp};fittedLayout.clear();mainMoved=true;auto* main=Element("main-panel");main->SetProperty("left",std::to_string(center.x-w*.5f)+"px");main->SetProperty("top",std::to_string(layout=="bar"?(barPosition=="top"?resizeOrigin.y:resizeOrigin.y+resizeSize.y-h):center.y-h*.5f)+"px");Reflow();event.StopPropagation();return;
        }
        if(event.GetType()=="mousemove" && dragged) {
            Rml::Vector2f delta{event.GetParameter<float>("mouse_x",0)-dragStart.x,event.GetParameter<float>("mouse_y",0)-dragStart.y};
            if(!dragStarted){if(delta.x*delta.x+delta.y*delta.y<dragThreshold*dragThreshold)return;dragStarted=true;dragStart={event.GetParameter<float>("mouse_x",0),event.GetParameter<float>("mouse_y",0)};delta={};if(dragged==Element("inspector")){inspectorAnchored=false;Element("inspector")->SetClass("anchored",false);}}
            if(dragged==Element("main-panel")&&std::fabs(delta.x)+std::fabs(delta.y)>3)mainMoved=true;
            const auto viewport=document->GetContext()->GetDimensions();const auto size=dragged->GetBox().GetSize(Rml::BoxArea::Border);
            const auto position=SnappedPosition(Rml::Vector2f{dragOrigin.x+delta.x,dragOrigin.y+delta.y},size);
            const double now=Rml::GetSystemInterface()->GetElapsedTime();const float elapsed=std::max(.004f,float(now-dragTime));const auto raw=(position-dragLast)/elapsed;dragVelocity={std::clamp(dragVelocity.x*.6f+raw.x*.4f,-2200.f,2200.f),std::clamp(dragVelocity.y*.6f+raw.y*.4f,-2200.f,2200.f)};dragLast=position;dragTime=now;windowVelocity[dragged->GetId()]=dragVelocity;
            dragged->SetProperty("left",std::to_string(position.x)+"px");dragged->SetProperty("top",std::to_string(position.y)+"px");

            if(dragFollower){dragFollower->SetProperty("left",std::to_string(followerOrigin.x+position.x-dragOrigin.x)+"px");dragFollower->SetProperty("top",std::to_string(followerOrigin.y+position.y-dragOrigin.y)+"px");if(layout=="bar")inspectorAnchorX=followerAnchorOrigin+position.x-dragOrigin.x;}return;
        }
        if(event.GetType()=="mouseup") {if(resizing){resizing=false;resizeEdge.clear();RememberPosition("main-panel");event.StopPropagation();return;}if(dragged){const auto id=dragged->GetId();const bool snapped=dragStarted&&SnapReleased(id);if(dragStarted){RememberPosition(id);if(dragFollower)RememberPosition(dragFollower->GetId());}if(dragStarted && !snapped && !reducedMotion && std::fabs(dragVelocity.x)+std::fabs(dragVelocity.y)>50)coasting[id]={dragLast,dragVelocity,dragFollower?dragFollower->GetId():"",dragFollower?followerOrigin-dragOrigin:Rml::Vector2f{}};else windowVelocity[id]={};}dragged=nullptr;dragFollower=nullptr;dragStarted=false;return;}
        if(event.GetType()=="mousedown") {
            for(auto* edge=target;edge;edge=edge->GetParentNode())if(edge->IsClassSet("resize-edge")){
                resizeEdge=edge->GetId();if(layout=="bar"&&resizeEdge!=(barPosition=="top"?"resize-bottom":"resize-top"))return;resizing=true;EndNrPreview();QuickLayouts(false);dragged=nullptr;Raise("main-panel");resizeStart={event.GetParameter<float>("mouse_x",0),event.GetParameter<float>("mouse_y",0)};resizeOrigin=Element("main-panel")->GetAbsoluteOffset(Rml::BoxArea::Border);resizeSize=Element("main-panel")->GetBox().GetSize(Rml::BoxArea::Border);coasting.erase("main-panel");entrances.erase("main-panel");pendingEntrance.erase("main-panel");event.StopPropagation();return;
            }
            auto* glass=target;bool interactive=false;
            while(glass && !glass->IsClassSet("glass")) {const auto tag=glass->GetTagName();if(tag=="button"||tag=="input"||tag=="select"||tag=="option"||tag.find("slider")!=std::string::npos||tag.find("scrollbar")!=std::string::npos)interactive=true;glass=glass->GetParentNode();}
            if(glass) {const auto id=glass->GetId();if(id=="game-picker"||id=="accent-editor")return;Raise(id);
                if(!interactive&&!(BarSettings()&&glass==Element("inspector"))) {dragStarted=false;dragThreshold=(glass==Element("inspector")&&inspectorAnchored?18.f:4.f)*document->GetContext()->GetDensityIndependentPixelRatio();dragged=layout=="centered" && (id=="main-panel"||id=="inspector")?Element("main-panel"):glass;coasting.erase(dragged->GetId());entrances.erase(dragged->GetId());dragStart={event.GetParameter<float>("mouse_x",0),event.GetParameter<float>("mouse_y",0)};dragOrigin=dragged->GetAbsoluteOffset(Rml::BoxArea::Border);dragLast=dragOrigin;dragVelocity={};dragTime=Rml::GetSystemInterface()->GetElapsedTime();dragged->SetProperty("margin-left","0px");dragged->SetProperty("margin-top","0px");dragged->SetProperty("left",std::to_string(dragOrigin.x)+"px");dragged->SetProperty("top",std::to_string(dragOrigin.y)+"px");
                    if((layout=="centered" || (layout=="bar" && inspectorAnchored)) && dragged==Element("main-panel") && Element("inspector")->IsVisible()){dragFollower=Element("inspector");followerOrigin=dragFollower->GetAbsoluteOffset(Rml::BoxArea::Border);followerAnchorOrigin=inspectorAnchorX;dragFollower->SetProperty("margin-left","0px");dragFollower->SetProperty("margin-top","0px");}}
            }
            return;
        }
        auto* button=target;while(button && button->GetTagName()!="button")button=button->GetParentNode();
        if(button)target=button;
        while(target && target->GetId().empty())target=target->GetParentNode();
        if(!target)return;const auto id=target->GetId();
        if(effects.Event(id,event)||hdr.Event(id,event)||addons.Event(id,event))return;
        if(event.GetType()=="mouseover") {
            if(inside("open-layout")||inside("layout-picker")){QuickLayouts(true);return;}
            auto* tip=event.GetTargetElement();while(tip&&!tip->HasAttribute("title"))tip=tip->GetParentNode();const auto title=tip?tip->GetAttribute<Rml::String>("title",""):"";if(!title.empty()) {const auto at=tip->GetAbsoluteOffset(Rml::BoxArea::Border);Element("tooltip")->SetInnerRML(Rml::StringUtilities::EncodeRml(title));Element("tooltip")->SetProperty("left",std::to_string(at.x-60)+"px");Element("tooltip")->SetProperty("top",std::to_string(at.y+38)+"px");Visible("tooltip",true);}
            return;
        }
        if(event.GetType()=="mouseout") {Visible("tooltip",false);if(inside("open-layout")||inside("layout-picker"))layoutPickerDismiss=Rml::GetSystemInterface()->GetElapsedTime()+.24;return;}
        if(target->IsPseudoClassSet("disabled"))return;
        if(event.GetType()=="keydown") {
            const auto key=event.GetParameter<int>("key_identifier",0);
            if(target->GetTagName()=="button" && (key==Rml::Input::KI_RETURN || key==Rml::Input::KI_SPACE)) {event.StopPropagation();target->DispatchEvent("click",{});}
            return;
        }
        if(event.GetType()=="change") {
            auto* field=dynamic_cast<Rml::ElementFormControl*>(target);if(!field)return;
            if(id=="accent-color"){auto color=field->GetValue();if(MaterialColor::ValidAccent(color)){customAccent=color;colorEditorOpen=false;Materials();}return;}
            if(id=="scene-select") {const auto value=field->GetValue();if(!value.empty())sceneRequest=std::stoi(value);return;}
            if(id=="welcome-position"){welcomePosition=field->GetValue();prefsDirty=true;PositionWelcome();return;}
            if(id=="primary-menu"){primaryMenu=field->GetValue();prefsDirty=true;return;}
            if(id=="opti-shortcut"){optiShortcut=field->GetValue();prefsDirty=true;return;}
            if(extraFields.contains(id)) {Put(extraFields.at(id)->key,std::stof(field->GetValue()));Sync();return;}
            if(id=="accent-character"){accentCharacter=std::clamp(std::stof(field->GetValue()),0.f,100.f);accentOpacity=100*MaterialColor::AccentOpacity(accentCharacter);headingAccentBlend=AccentLight()?"multiply":"screen";controlAccentBlend=AccentLight()?"normal":"screen";Materials();return;}
            if(id=="accent-saturation"){accentSaturation=std::clamp(std::stof(field->GetValue()),0.f,200.f);Materials();return;}
            if(id=="tint-opacity") {customTheme=true;if(appearance==1)lightOpacity=std::stof(field->GetValue());else if(appearance==3)clearOpacity=std::stof(field->GetValue());else if(appearance==4)accentOpacity=std::stof(field->GetValue());else darkOpacity=std::stof(field->GetValue());Materials();return;}
            if(id=="blur-radius") {customTheme=true;blurRadius=std::stof(field->GetValue());Materials();return;} if(id=="grain-amount"){customTheme=true;grainAmount=std::stof(field->GetValue());Materials();return;} if(id=="blend-strength"){customTheme=true;blendStrength=std::stof(field->GetValue());Materials();return;}
            if(id=="surface-blend") {customTheme=true;surfaceBlend=field->GetValue();Materials();return;}
            if(id=="heading-accent-mode"||id=="control-accent-mode"||id=="heading-accent-strength"||id=="control-accent-strength"){const bool heading=id.rfind("heading",0)==0;if(id.find("-mode")!=std::string::npos){if(MaterialColor::Valid(field->GetValue()))(heading?headingAccentBlend:controlAccentBlend)=field->GetValue();}else (heading?headingAccentStrength:controlAccentStrength)=std::clamp(std::stof(field->GetValue()),0.f,100.f);customTheme=true;Materials();return;}
            if(id=="overlay-scale") {overlayScale=std::stoi(field->GetValue());Typography();return;}
            if(id=="font-select") {copyFont=field->GetValue();Typography();return;}
            if(id=="copy-size"||id=="copy-weight"||id=="heading-size"||id=="heading-weight") {const int value=std::stoi(field->GetValue());if(id=="copy-size")copySize=value;else if(id=="copy-weight")copyWeight=value;else if(id=="heading-size")headingSize=value;else headingWeight=value;Typography();return;}
            if(id=="render-resolution"){Put("work_scale",std::stof(field->GetValue())/100.f);Sync();return;}
            const auto mapping=std::map<std::string,std::string>{{"strength","intensity"},{"detail","detail"},{"colour","colour"},{"tone","tone"},{"model-preset","preset"},{"processing-stage","pre_sr"}};
            if(const auto found=mapping.find(id);found!=mapping.end())Put(found->second,std::stof(field->GetValue()));
            else if(id.rfind("pass-",0)==0)Put("pass"+std::to_string(pass)+"_"+id.substr(5),std::stof(field->GetValue()));
            else if(id=="presets") {
                const auto name=field->GetValue();auto before=values;
                if(presets.contains(name))values=presets.at(name);
                else {values["style"]=name=="natural" ? 1.f:2.f;values["intensity"]=name=="natural" ? 1.f:.8f;}
                edits.Record(before,values);edits.saved=values;Message(preview?"Preset loaded into this preview":"Preset selected");Notify(name+std::string(preview?" preset loaded · Preview":" preset loaded"),"floppy-disk");
            }
        } else if(event.GetType()=="click") {
            if(id=="accent-spectrum-swatch"){spectrumOpen=!spectrumOpen;if(spectrumOpen)spectrumHsv=MaterialColor::ToHsv(ActiveAccent());Materials();if(spectrumOpen)Element("spectrum-plane")->Focus();return;}
            if(id=="spectrum-plane"||id=="spectrum-hue"){const auto at=target->GetAbsoluteOffset(Rml::BoxArea::Border),size=target->GetBox().GetSize(Rml::BoxArea::Border);const float x=std::clamp((event.GetParameter<float>("mouse_x",0)-at.x)/size.x,0.f,1.f),y=std::clamp((event.GetParameter<float>("mouse_y",0)-at.y)/size.y,0.f,1.f);
                if(id=="spectrum-hue"){spectrumHsv[0]=std::min(x,.9999f);Spectrum();}else{spectrumHsv[1]=x;spectrumHsv[2]=1-y;ChooseSpectrum();}return;}
            if(id=="accent-swatch"){colorEditorOpen=!colorEditorOpen;Materials();if(colorEditorOpen)Element("accent-color")->Focus();return;}
            if(id=="accent-use-game"){customAccent.clear();colorEditorOpen=false;Materials();return;}
            if(id=="accent-eyedropper"){screenColorPicker.Start();colorPicking=true;Visible("tooltip",false);document->SetClass("color-picking",true);return;}
            if(id=="accent-poster"&&samplePoster){const auto at=target->GetAbsoluteOffset(Rml::BoxArea::Border);const auto size=target->GetBox().GetSize(Rml::BoxArea::Border);const auto color=samplePoster((event.GetParameter<float>("mouse_x",0)-at.x)/size.x,(event.GetParameter<float>("mouse_y",0)-at.y)/size.y);if(MaterialColor::ValidAccent(color)&&!color.empty()){customAccent=color;colorEditorOpen=false;Materials();}return;}
            if(id.rfind("accent-source-",0)==0){const auto mode=id.substr(14);if(mode=="theme"||mode=="custom"||mode=="adaptive"){accentMode=mode;nextAccentSample=0;Materials();}return;}
            if(id=="preview-close"&&closePreview)closePreview();
            else if(id=="close"){if(closePreview)closePreview();else ToggleOverlay();}
            else if(id=="window-back")Back();
            else if(id=="inspector-back"){if(BarSettings())Settings(false);else if(layout=="centered")Back();else{Visible("inspector",false);inspectorAnchored=false;}}
            else if(id=="appearance-back"){if(setupStep>=0){setupStep=0;UpdateSetup();}else Visible("type-panel",false);}
            else if(id=="setup-next"){if(setupStep==1){setupStep=0;UpdateSetup();}else FinishSetup();}
            else if(id=="setup-appearance"){setupStep=1;UpdateSetup();}
            else if(id=="setup-native"){setupStep=2;UpdateSetup();}
            else if(id=="setup-native-confirm")UseNativeOverlays();
            else if(id=="setup-skip"){if(setupStep==2){setupStep=0;UpdateSetup();}else FinishSetup();}
            else if(id.rfind("setup-layout-",0)==0){setupLayoutChosen=true;Layout(id.substr(13));UpdateSetup();}
            else if(id=="open-layout")QuickLayouts(true);
            else if(id.rfind("quick-",0)==0)Layout(id.substr(6));
            else if(id=="setting-original-labels"){originalLabels=!originalLabels;prefsDirty=true;Labels();}
            else if(id=="pass-minus"||id=="pass-plus")Put("passes",std::clamp(values.at("passes")+(id=="pass-minus"?-1.f:1.f),1.f,float(passesMax)));
            else if(id.rfind("group-toggle-",0)==0){auto* group=Element(id.substr(13).c_str());group->SetProperty("display",group->IsVisible()?"none":"flex");target->SetClass("expanded",group->IsVisible());}
            else if(id.rfind("reset-extra-",0)==0 && extraFields.contains(id.substr(6)))Put(extraFields.at(id.substr(6))->key,defaults.at(extraFields.at(id.substr(6))->key));
            else if(extraFields.contains(id)) {const auto* control=extraFields.at(id);if(std::string(control->kind)=="toggle")Put(control->key,values.at(control->key)==0?1.f:0.f);}
            else if(id=="open-settings"||id=="nav-settings")Settings(!settingsOpen);
            else if(id=="settings-back"||id=="settings-modal-close")Settings(false);
            else if(id=="shortcut-bind") {bindingShortcut=true;SyncSettings();document->Focus();}
            else if(id=="setting-stats") {showStats=!showStats;prefsDirty=true;Session(session);SyncSettings();}
            else if(id=="setting-welcome") {showWelcome=!showWelcome;prefsDirty=true;if(!showWelcome)Visible("welcome",false);SyncSettings();}
            else if(id=="setting-notifications") {showNotifications=!showNotifications;prefsDirty=true;SyncSettings();}
            else if(id=="welcome-test")Welcome();
            else if(id=="setting-helper"||id=="setting-startup"){if(id=="setting-helper")helperEnabled=!helperEnabled;else startWithWindows=!startWithWindows;prefsDirty=true;SyncSettings();}
            else if(id=="menus-review"){if(!requestJson||!requestJson("{\"op\":\"menus-review\"}"))Message("Connect the background helper to review installed games.");}
            else if(id=="discard-review"){if(requestJson)requestJson("{\"op\":\"discard-review\"}");Visible("review-panel",false);reviewId=0;}
            else if(id=="apply-review"){if(reviewId>0&&requestJson)requestJson("{\"op\":\"apply-review\",\"review_id\":"+std::to_string(reviewId)+"}");}
            else if(id.rfind("setting-",0)==0&&menuSettings.contains(id.substr(8))) {menuSettings[id.substr(8)]=!menuSettings[id.substr(8)];prefsDirty=true;SyncSettings();}
            else if(id=="open-appearance")ShowAppearance();
            else if(id=="appearance-more") {moreOpen=!moreOpen;Materials();}
            else if(id=="appearance-god-mode"&&preview) {godModeOpen=!godModeOpen;Materials();}
            else if(id=="theme-reset")UseAppearance(BaseAppearance(),appearance==4);
            else if(id=="text-smaller"||id=="text-default"||id=="text-larger") {copySize=id=="text-smaller"?20:id=="text-larger"?24:22;Typography();}
            else if(id=="scale-minus"||id=="scale-plus") {overlayScale=std::clamp(overlayScale+(id=="scale-plus"?10:-10),70,150);Typography();}
            else if(id=="text-depth") {textDepth=!textDepth;customTheme=true;Materials();}
            else if(id=="dark-inverted") {invertDark=!invertDark;customTheme=true;Materials();}
            else if(id=="toast-pill"||id=="toast-rounded") {toastPill=id=="toast-pill";Materials();}
            else if(id=="motion-effects") {motionEnabled=!motionEnabled;Materials();}
            else if(id=="type-close")Visible("type-panel",false);
            else if(id=="type-reset") {copyFont="roboto";headingFont="bakbak";copySize=22;copyWeight=500;headingSize=36;headingWeight=400;Typography();}
            else if(id=="side-left"||id=="side-right")PanelSide(id.substr(5));
            else if(id=="bar-top"||id=="bar-bottom")BarEdge(id.substr(4));
            else if(id.rfind("layout-",0)==0)Layout(id.substr(7));
            else if(id=="nav-overview"||id=="nav-frame"||id=="nav-neural"||id=="nav-hdr"||id=="nav-effects"||id=="nav-look"||id=="nav-passes") {Settings(false);Page(id);}
            else if(id=="open-addons")Open("addons");
            else if(id=="open-effects"){if(layout=="centered"){Settings(false);Page("nav-effects");}else Open("effects");}
            else if(id=="open-hdr"){if(layout=="centered"){Settings(false);Page("nav-hdr");}else Open("hdr");}
            else if(id=="welcome-close")Visible("welcome",false);
            else if(id=="theme")Visible("theme-menu",!Element("theme-menu")->IsVisible());
            else if(id=="theme-light"||id=="theme-dark"||id=="theme-clear")UseAppearance(id=="theme-light"?1:id=="theme-dark"?2:3,appearance==4);
            else if(id=="accent-tint"&&accentMode!="theme")UseAppearance(BaseAppearance(),appearance!=4);

            else if(id=="open-passes")Open("passes");else if(id=="open-look")Open("look");
            else if(id=="open-session")Open("overview");
            else if(id=="open-processing")Open("processing");else if(id=="open-frame-options")Open("frame");
            else if(id=="inspector-close") {Visible("inspector",false);Visible("overview",true);if(layout=="centered")Page(inspectorPanel=="look"||inspectorPanel=="passes"?"nav-neural":"nav-overview");Element("inspector")->SetClass("opening",false);}
            else if(id=="pass-2" || id=="pass-3" || id=="pass-4")pass=id.back()-'0';
            else if(id=="inherit")Put("pass"+std::to_string(pass)+"_inherit",values["pass"+std::to_string(pass)+"_inherit"] ? 0.f:1.f);
            else if(id=="nr-toggle") {Put("enabled",values["enabled"] ? 0.f:1.f);Notify(values["enabled"]?(preview?"Neural rendering on · Preview":"Neural rendering on"):(preview?"Neural rendering off · Preview":"Neural rendering off"),"cpu");}
            else if(id=="mfg-toggle")Put("mfg_enabled",values["mfg_enabled"] ? 0.f:1.f);
            else if(id=="undo")values=edits.Undo(values);else if(id=="redo")values=edits.Redo(values);
            else if(id=="defaults") {edits.Record(values,defaults);values=defaults;Notify(preview?"Settings reset · Preview":"Settings reset for this game","arrow-counter-clockwise");}
            else if(id=="save"&&!preview){Visible("save-sheet",!Element("save-sheet")->IsVisible());}
            else if(id=="delete-preset"&&deletePreset){const auto name=dynamic_cast<Rml::ElementFormControl*>(Element("presets"))->GetValue();if(!name.empty()&&deletePreset(name)){Visible("save-sheet",false);Message("Deleting preset…");}}
            else if(id=="save-cancel")Visible("save-sheet",false);
            else if(id=="save-confirm"&&savePreset){const auto name=dynamic_cast<Rml::ElementFormControl*>(Element("preset-name"))->GetValue();if(name.empty()||name.size()>60)Message(name.empty()?"Name your preset.":"Use a shorter preset name.");else if(savePreset(name)){Visible("save-sheet",false);Message("Saving preset…");}else Message("The helper is busy. Try saving again.");}
            else if(id=="save") {const auto name=dynamic_cast<Rml::ElementFormControl*>(Element("presets"))->GetValue();presets[name]=values;edits.saved=values;Message("Session preset saved in memory · game settings unchanged");Notify("Preset saved · Preview","floppy-disk");}
            else if(id=="reset-inspector" && inspectorPanel=="hdr"){if(hdr.available)hdr.Reset();}
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
