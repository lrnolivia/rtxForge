#pragma once
#include "HdrControls.h"

namespace ForgeGlass {
// The DLSS 5 NR add-ons rtxForge installed (Lecram, ShortFuse), grouped by role.
// ShortFuse edits use its verified live setter. Other builds use the helper’s
// startup settings queue.
struct NrAddonControls {
    Rml::ElementDocument* document{};
    std::vector<HdrField> fields;
    std::map<std::string,float> pending;
    std::map<std::string,std::pair<float,bool>> livePrevious;
    bool available{},syncing{},shortFuseLive{},showMore{};
    static bool ShortFuse(const HdrField& f) {return f.section.ends_with(" · ShortFuse");}
    bool HasShortFuse() const {
        return available&&std::any_of(fields.begin(),fields.end(),ShortFuse);
    }
    void LiveMessage(const std::string& message) {
        auto* note=E("addons-live-status");
        note->SetInnerRML(Escape(message));
        E("addons-live")->SetProperty("display",HasShortFuse()?"flex":"none");
    }
    void SetShortFuseLive(bool ready) {
        if(shortFuseLive==ready)return;
        shortFuseLive=ready;
        LiveMessage(ready?"Live · ShortFuse":"Waiting for the verified ShortFuse add-on to load.");
        Sync();
    }
    Rml::Element* E(const std::string& id) {return document->GetElementById(id);}
    static std::string Escape(const std::string& s) {return Rml::StringUtilities::EncodeRml(s);}
    static std::string Number(float n,bool whole) {char text[48];std::snprintf(text,sizeof(text),whole?"%.0f":"%.2f",n);return text;}
    static bool Whole(const HdrField& f) {return f.step>=1;}
    std::string Control(const HdrField& f) {
        const auto id="addon-"+f.key;
        const bool choice=f.kind=="choice";
        const auto glyph=f.key.ends_with("_hook_point")?"lightning":f.key.ends_with("_character_mask")?"circle-half":f.key.ends_with("_resolution_scale")?
            "app-window":f.key.ends_with("_character")?"sliders-horizontal":f.key.ends_with("_passes")?"stack":"";
        const auto icon=std::string(glyph).empty()?"":std::string("<img class=\"glyph\" src=\"icons/")+glyph+"-light.png\"/>";
        std::string out=std::string("<div class=\"slider-field addon-field")+(choice?" addon-choice":"")+
            "\"><div class=\"field-heading\"><label class=\"split-control-label\" for=\""+id+"\">"+icon+"<span>"+Escape(f.label)+"</span></label>";
        if(f.kind!="choice")out+="<span id=\""+id+"-value\"/>";
        out+="</div>";
        if(f.kind=="choice")out+="<select id=\""+id+"\">"+f.options+"</select>";
        else out+="<input id=\""+id+"\" class=\"range\" type=\"range\" min=\""+Number(f.minimum,false)+"\" max=\""+Number(f.maximum,false)+"\" step=\""+Number(f.step,false)+"\"/>";
        return out+"</div>";
    }
    void ShowMore(bool open) {
        showMore=open;
        if(auto* toggle=E("addons-more")) {
            toggle->SetClass("expanded",open);
            toggle->SetAttribute("aria-expanded",open?"true":"false");
            E("addons-more-label")->SetInnerRML(open?"Fewer options":"More options");
            E("addons-extra")->SetClass("expanded",open);
        }
    }
    void Build() {
        std::string markup;
        const auto rank=[](const HdrField& field) {
            const auto& key=field.key;
            if(key.ends_with("_hook_point"))return -1;
            if(key.ends_with("_character_mask"))return 0;
            if(key.ends_with("_resolution_scale"))return 1;
            if(key.ends_with("_character"))return 2;
            if(key.ends_with("_intensity")||!ShortFuse(field))return 3;
            return 4;
        };
        for(auto first=fields.begin();first!=fields.end();) {
            const auto end=std::find_if(first,fields.end(),[&](const auto& f){return f.section!=first->section;});
            const auto glyph=first->key.starts_with("character_")?"circle-half":"app-window";
            markup+=std::string("<div class=\"option-group\"><h3 class=\"split-addon-title\"><img class=\"glyph\" src=\"icons/")+
                glyph+"-light.png\"/><span>"+Escape(first->section)+"</span></h3>";
            for(int priority=-1;priority<4;++priority)
                for(auto field=first;field!=end;++field)
                    if(rank(*field)==priority)markup+=Control(*field);
            if(std::any_of(first,end,[&](const auto& field){return rank(field)==4;})) {
                markup+=R"(<button id="addons-more" class="more-trigger split-more-trigger" aria-controls="addons-extra">
                    <img class="glyph" src="icons/sliders-horizontal-light.png" />
                    <span id="addons-more-label">More options</span><span class="chevron" />
                    </button><div id="addons-extra" class="split-extra-options"><h4>Model and processing</h4>)";
                for(auto field=first;field!=end;++field)
                    if(rank(*field)==4)markup+=Control(*field);
                markup+="</div>";
            }
            markup+="</div>";
            first=end;
        }
        E("addons-fields")->SetInnerRML(markup);
        ShowMore(showMore);
    }
    void Set(std::vector<HdrField> next,bool supported,const std::string& message) {
        bool rebuild=fields.size()!=next.size();
        if(!rebuild)for(size_t i=0;i<fields.size();++i)if(fields[i].key!=next[i].key||fields[i].section!=next[i].section||fields[i].options!=next[i].options||fields[i].minimum!=next[i].minimum||fields[i].maximum!=next[i].maximum){rebuild=true;break;}
        if(rebuild){pending.clear();livePrevious.clear();}
        for(auto& f:next)if(pending.contains(f.key)){f.value=pending.at(f.key);f.automatic=false;}
        const bool hadShortFuse=HasShortFuse();
        fields=std::move(next);available=supported&&!fields.empty();
        const bool hasStartupFields=std::any_of(fields.begin(),fields.end(),[](const auto& f){return !ShortFuse(f);});
        E("addons-note")->SetInnerRML(Escape(message));
        E("addons-note")->SetProperty("display",hasStartupFields&&!message.empty()?"block":"none");
        if(hadShortFuse!=HasShortFuse())LiveMessage(shortFuseLive?"Live · ShortFuse":"Waiting for the verified ShortFuse add-on to load.");
        if(rebuild)Build();
        Sync();
    }
    void Sync() {
        syncing=true;
        for(const auto& f:fields)if(auto* e=E("addon-"+f.key)){
            if(auto* input=dynamic_cast<Rml::ElementFormControl*>(e)){input->SetValue(Number(f.value,f.kind=="choice"||Whole(f)));input->SetDisabled(!available||(ShortFuse(f)&&!shortFuseLive));}
            if(auto* label=E("addon-"+f.key+"-value"))label->SetInnerRML(f.automatic?"Add-on default":Number(f.value,Whole(f))+(f.unit.empty()?"":(f.unit=="%"?"":" ")+Escape(f.unit)));
        }
        syncing=false;
    }
    bool Event(const std::string& id,Rml::Event& event) {
        if(id=="addons-more"&&event.GetType()=="click"){ShowMore(!showMore);return true;}
        if(event.GetType()!="change"||syncing||!available||!id.starts_with("addon-"))return false;
        for(auto& f:fields)if(id=="addon-"+f.key){auto* input=dynamic_cast<Rml::ElementFormControl*>(E(id));if(!input||(ShortFuse(f)&&!shortFuseLive))return true;
            try {
                float value=std::stof(input->GetValue());
                if(Whole(f)||f.kind=="choice")value=std::round(value);
                if(std::isfinite(value)&&value>=f.minimum&&value<=f.maximum) {
                    if(ShortFuse(f))livePrevious.try_emplace(f.key,f.value,f.automatic);
                    f.value=value;
                    f.automatic=false;
                    pending[f.key]=value;
                    Sync();
                }
            }catch(const std::exception&){}
            return true;}
        return false;
    }
    bool Flush(const std::function<bool(const std::string&)>& send) {
        if(pending.empty()||!send)return false;
        std::string changes;
        std::vector<std::string> queued;
        for(const auto& [key,value]:pending) {
            const auto* field=Find(key);
            if(!field||ShortFuse(*field))continue;
            if(!changes.empty())changes+=",";
            changes+="\""+key+"\":"+Number(value,Whole(*field)||field->kind=="choice");
            queued.push_back(key);
        }
        if(changes.empty()||!send("{\"op\":\"nr-addons-save\",\"changes\":{"+changes+"}}"))return false;
        for(const auto& key:queued)pending.erase(key);
        return true;
    }
    bool FlushLive(const std::function<bool(const HdrField&,float)>& apply) {
        if(livePrevious.empty())return false;
        bool accepted=true;
        for(auto& field:fields) {
            const auto previous=livePrevious.find(field.key);
            if(previous==livePrevious.end())continue;
            if(!shortFuseLive||!apply(field,pending.at(field.key))) {
                field.value=previous->second.first;
                field.automatic=previous->second.second;
                accepted=false;
            }
            pending.erase(field.key);
        }
        livePrevious.clear();
        LiveMessage(accepted?"Applied in game · ShortFuse":"ShortFuse did not accept the change.");
        Sync();
        return accepted;
    }
    const HdrField* Find(const std::string& key) const {for(const auto& f:fields)if(f.key==key)return &f;return nullptr;}
};
}
