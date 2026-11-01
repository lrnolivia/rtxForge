#pragma once
#include <RmlUi/Core.h>
#include <RmlUi/Core/Elements/ElementFormControl.h>
#include <map>
#include <vector>
#include <functional>
#include <cmath>
#include <cstdio>
#include <cctype>

namespace ForgeGlass {
struct HdrField {
    std::string key,label,section,kind,options,unit;
    float minimum{},maximum{},step{1},initial{},value{};
    bool reset{true},automatic{};
};
struct HdrControls {
    Rml::ElementDocument* document{};
    std::vector<HdrField> fields;
    std::map<std::string,float> pending;
    bool available{},installed{},syncing{};
    Rml::Element* E(const std::string& id) {return document->GetElementById(id);}
    static std::string Escape(const std::string& s) {return Rml::StringUtilities::EncodeRml(s);}
    static std::string Number(float n,bool whole=false) {char text[48];std::snprintf(text,sizeof(text),whole?"%.0f":"%.2f",n);return text;}
    static bool Primary(const std::string& key) {return key=="ToneMapPeakNits"||key=="ToneMapGameNits"||key=="ToneMapUINits"||key=="ToneMapType";}
    std::string Control(const HdrField& f,const std::string& prefix) {
        const auto id=prefix+f.key;
        std::string out="<div class=\"slider-field hdr-field\"><div class=\"field-heading\"><label>"+Escape(f.label)+"</label>";
        if(f.kind!="choice")out+="<span id=\""+id+"-value\"/>";
        out+="</div>";
        std::string options=f.options;const std::string source=">RenoDRT</option>";if(const auto at=options.find(source);at!=std::string::npos)options.replace(at,source.size(),">RenoDX (RenoDRT)</option>");
        if(f.kind=="choice")out+="<select id=\""+id+"\">"+options+"</select>";
        else out+="<input id=\""+id+"\" class=\"range\" type=\"range\" min=\""+Number(f.minimum)+"\" max=\""+Number(f.maximum)+"\" step=\""+Number(f.step)+"\"/>";
        return out+="</div>";
    }
    void Build() {
        std::string main,popup,lastSection;
        for(const auto& f:fields){if(f.section!=lastSection){if(!lastSection.empty())main+="</div>";lastSection=f.section;std::string title=lastSection;for(auto& ch:title)ch=char(std::toupper(static_cast<unsigned char>(ch)));main+="<div class=\"option-group\"><h3>"+Escape(title)+"</h3>";}main+=Control(f,"hdr-main-");if(Primary(f.key))popup+=Control(f,"hdr-popup-");}
        if(!lastSection.empty())main+="</div>";
        std::string more;for(const auto& f:fields)if(!Primary(f.key))more+=Control(f,"hdr-popup-");
        if(!more.empty())popup+="<div class=\"option-group\"><button id=\"hdr-more\" class=\"group-heading\"><span>More HDR options</span><span class=\"chevron\"/></button><div id=\"hdr-more-body\" class=\"group-body\" style=\"display: none\">"+more+"</div></div>";
        if(!fields.empty())main+="<button id=\"hdr-reset\" class=\"quiet\"><span>Reset HDR preferences</span></button>";
        E("hdr-main-fields")->SetInnerRML(main);E("hdr-popup-fields")->SetInnerRML(popup);
    }
    void Set(std::vector<HdrField> next,bool supported,bool present,const std::string& message) {
        bool rebuild=fields.size()!=next.size();
        if(!rebuild)for(size_t i=0;i<fields.size();++i)if(fields[i].key!=next[i].key||fields[i].options!=next[i].options||fields[i].minimum!=next[i].minimum||fields[i].maximum!=next[i].maximum){rebuild=true;break;}
        for(auto& f:next)if(pending.contains(f.key)){f.value=pending.at(f.key);f.automatic=false;}
        fields=std::move(next);available=supported;installed=present;
        for(const auto* id:{"hdr-main-note","hdr-popup-note"})E(id)->SetInnerRML(Escape(message));
        for(const auto* id:{"open-hdr","nav-hdr"})E(id)->SetProperty("display",supported||present?"flex":"none");
        if(rebuild)Build();Sync();
    }
    void Sync() {
        syncing=true;
        for(const auto& f:fields)for(const auto* prefix:{"hdr-main-","hdr-popup-"})if(auto* e=E(std::string(prefix)+f.key)) {
            if(auto* input=dynamic_cast<Rml::ElementFormControl*>(e)){input->SetValue(Number(f.value,f.kind=="choice"));input->SetDisabled(!available);}
            if(auto* label=E(std::string(prefix)+f.key+"-value"))label->SetInnerRML(f.automatic?"Display default":Number(f.value,f.step>=1)+(f.unit.empty()?"":" "+Escape(f.unit)));
        }
        syncing=false;
    }
    void Reset() {for(auto& f:fields)if(f.reset){f.value=f.initial;pending[f.key]=f.value;}Sync();}
    bool Event(const std::string& id,Rml::Event& event) {
        if(event.GetType()=="click"&&id=="hdr-more"){auto* body=E("hdr-more-body");const bool show=!body->IsVisible();body->SetProperty("display",show?"block":"none");E("hdr-more")->SetClass("expanded",show);return true;}
        if(event.GetType()=="click"&&id=="hdr-reset"){if(available)Reset();return true;}
        if(event.GetType()!="change"||syncing||!available)return false;
        for(auto& f:fields)if(id=="hdr-main-"+f.key||id=="hdr-popup-"+f.key){auto* input=dynamic_cast<Rml::ElementFormControl*>(E(id));if(!input)return true;try{const float value=std::stof(input->GetValue());if(std::isfinite(value)&&value>=f.minimum&&value<=f.maximum){f.value=value;f.automatic=false;pending[f.key]=value;Sync();}}catch(...){}return true;}
        return false;
    }
    bool Flush(const std::function<bool(const std::string&)>& send) {
        if(pending.empty()||!send)return false;
        std::string changes;for(const auto& [key,value]:pending){if(!changes.empty())changes+=",";changes+="\""+key+"\":"+Number(value);}
        if(!send("{\"op\":\"hdr-save\",\"changes\":{"+changes+"}}"))return false;
        pending.clear();return true;
    }
};
}
