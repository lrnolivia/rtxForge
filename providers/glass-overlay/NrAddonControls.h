#pragma once
#include "HdrControls.h"

namespace ForgeGlass {
// The DLSS5 NR add-ons rtxForge installed (Lecram, ShortFuse), grouped by role.
// They read ReShade.ini when the game starts, so edits are startup settings:
// the helper queues them and writes them after the game closes.
struct NrAddonControls {
    Rml::ElementDocument* document{};
    std::vector<HdrField> fields;
    std::map<std::string,float> pending;
    bool available{},syncing{};
    Rml::Element* E(const std::string& id) {return document->GetElementById(id);}
    static std::string Escape(const std::string& s) {return Rml::StringUtilities::EncodeRml(s);}
    static std::string Number(float n,bool whole) {char text[48];std::snprintf(text,sizeof(text),whole?"%.0f":"%.2f",n);return text;}
    static bool Whole(const HdrField& f) {return f.step>=1;}
    std::string Control(const HdrField& f) {
        const auto id="addon-"+f.key;
        std::string out="<div class=\"slider-field addon-field\"><div class=\"field-heading\"><label>"+Escape(f.label)+"</label>";
        if(f.kind!="choice")out+="<span id=\""+id+"-value\"/>";
        out+="</div>";
        if(f.kind=="choice")out+="<select id=\""+id+"\">"+f.options+"</select>";
        else out+="<input id=\""+id+"\" class=\"range\" type=\"range\" min=\""+Number(f.minimum,false)+"\" max=\""+Number(f.maximum,false)+"\" step=\""+Number(f.step,false)+"\"/>";
        return out+"</div>";
    }
    void Build() {
        std::string markup,section;
        for(const auto& f:fields){if(f.section!=section){if(!section.empty())markup+="</div>";section=f.section;markup+="<div class=\"option-group\"><h3>"+Escape(section)+"</h3>";}markup+=Control(f);}
        if(!section.empty())markup+="</div>";
        E("addons-fields")->SetInnerRML(markup);
    }
    void Set(std::vector<HdrField> next,bool supported,const std::string& message) {
        bool rebuild=fields.size()!=next.size();
        if(!rebuild)for(size_t i=0;i<fields.size();++i)if(fields[i].key!=next[i].key||fields[i].section!=next[i].section||fields[i].options!=next[i].options||fields[i].minimum!=next[i].minimum||fields[i].maximum!=next[i].maximum){rebuild=true;break;}
        for(auto& f:next)if(pending.contains(f.key)){f.value=pending.at(f.key);f.automatic=false;}
        fields=std::move(next);available=supported&&!fields.empty();
        E("addons-section")->SetProperty("display",available?"block":"none");
        E("addons-note")->SetInnerRML(Escape(message));
        if(rebuild)Build();Sync();
    }
    void Sync() {
        syncing=true;
        for(const auto& f:fields)if(auto* e=E("addon-"+f.key)){
            if(auto* input=dynamic_cast<Rml::ElementFormControl*>(e)){input->SetValue(Number(f.value,f.kind=="choice"||Whole(f)));input->SetDisabled(!available);}
            if(auto* label=E("addon-"+f.key+"-value"))label->SetInnerRML(f.automatic?"Add-on default":Number(f.value,Whole(f))+(f.unit.empty()?"":(f.unit=="%"?"":" ")+Escape(f.unit)));
        }
        syncing=false;
    }
    bool Event(const std::string& id,Rml::Event& event) {
        if(event.GetType()!="change"||syncing||!available||!id.starts_with("addon-"))return false;
        for(auto& f:fields)if(id=="addon-"+f.key){auto* input=dynamic_cast<Rml::ElementFormControl*>(E(id));if(!input)return true;
            try{float value=std::stof(input->GetValue());if(Whole(f)||f.kind=="choice")value=std::round(value);if(std::isfinite(value)&&value>=f.minimum&&value<=f.maximum){f.value=value;f.automatic=false;pending[f.key]=value;Sync();}}catch(...){}
            return true;}
        return false;
    }
    bool Flush(const std::function<bool(const std::string&)>& send) {
        if(pending.empty()||!send)return false;
        std::string changes;for(const auto& [key,value]:pending){const auto* f=Find(key);if(!changes.empty())changes+=",";changes+="\""+key+"\":"+Number(value,f&&(Whole(*f)||f->kind=="choice"));}
        if(!send("{\"op\":\"nr-addons-save\",\"changes\":{"+changes+"}}"))return false;
        pending.clear();return true;
    }
    const HdrField* Find(const std::string& key) const {for(const auto& f:fields)if(f.key==key)return &f;return nullptr;}
};
}
