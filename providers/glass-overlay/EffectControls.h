#pragma once
#include <json.hpp>
#include <algorithm>
#include <cctype>
#include <cstring>
#include <map>
#include <set>
#include <vector>
#include "HdrControls.h"

namespace ForgeGlass {
struct EffectControls {
    using Json=nlohmann::json;
    Rml::ElementDocument* document{};
    Json fields=Json::array(),schema=Json::array();
    uint64_t generation{};
    std::map<size_t,std::string> drafts;
    // Sent edits stay pending until the bridge acknowledges them. Bridges
    // without acknowledgments leave the snapshot as the only readback.
    std::set<size_t> pending;uint64_t acknowledged{};std::string result;
    bool syncing{};
    void Result(const std::string& text){result=text;if(auto* e=E("effects-result")){e->SetInnerRML(Escape(text));e->SetProperty("display",text.empty()?"none":"block");}}
    void Pending(size_t index,bool on){if(on)pending.insert(index);else pending.erase(index);if(auto* e=E("effect-field-"+std::to_string(index)))e->SetClass("pending",on);}
    void Acknowledge(const Json& data){
        const auto ack=data.value("acknowledged",Json::object());if(!ack.is_object()||!ack.contains("sequence"))return;
        const auto sequence=ack.value("sequence",uint64_t(0));if(sequence==acknowledged)return;acknowledged=sequence;
        for(const auto& id:ack.value("applied",Json::array()))if(id.is_number_unsigned())Pending(id.get<size_t>(),false);
        std::string refused;
        for(const auto& item:ack.value("rejected",Json::array())){if(!item.is_object())continue;const auto index=item.value("id",size_t(-1));if(!pending.contains(index))continue;Pending(index,false);
            const auto label=index<fields.size()?Friendly(fields[index].value("label",std::string("that setting"))):std::string("that setting");refused="Couldn’t apply "+label+". "+item.value("reason",std::string("The effect refused it."));}
        if(!refused.empty())Result(refused);else if(pending.empty())Result("");
    }
    std::function<bool(const std::string&)> send;
    Rml::Element* E(const std::string& id){return document->GetElementById(id);}
    static std::string Escape(const std::string& text){return Rml::StringUtilities::EncodeRml(text);}
    static std::string Number(double value){char text[64];std::snprintf(text,sizeof(text),"%.6g",value);return text;}
    static constexpr const char* AddonPrefix="Add-on settings · ";
    // ReShade passes code names when an effect has no display label:
    // "LumaSharpen.fx", "fSharpStrength", "DLSS5_Feed". Spell those out.
    static std::string Friendly(std::string text) {
        for(const auto* ext:{".fx",".fxh",".addon64",".addon"})if(text.size()>std::strlen(ext)&&text.ends_with(ext)){text.resize(text.size()-std::strlen(ext));break;}
        if(text.find(' ')!=std::string::npos)return text;
        if(text.size()>2&&(text[0]=='f'||text[0]=='i'||text[0]=='b')&&std::isupper(static_cast<unsigned char>(text[1]))&&std::islower(static_cast<unsigned char>(text[2])))text.erase(0,1);
        std::string out;
        for(size_t i=0;i<text.size();++i){const unsigned char c=text[i];
            if(c=='_'||c=='-'){if(!out.empty()&&out.back()!=' ')out+=' ';continue;}
            if(i>0&&std::isupper(c)&&std::islower(static_cast<unsigned char>(text[i-1]))&&!out.empty()&&out.back()!=' ')out+=' ';
            out+=char(c);}
        while(!out.empty()&&out.back()==' ')out.pop_back();
        return out.empty()?text:out;
    }
    std::string Field(size_t i,const std::string& label) const {
        const auto& f=fields[i];const auto id="effect-field-"+std::to_string(i),kind=f.value("kind",std::string("number")),tooltip=Escape(f.value("tooltip",std::string()));
        const auto name=Escape(label);
        if(kind=="toggle")return "<div class=\"inherit-row option-toggle effect-row\" title=\""+tooltip+"\"><label>"+name+"</label><button id=\""+id+"\" class=\"switch\"><span/></button></div>";
        std::string markup="<div class=\"slider-field effect-row\" title=\""+tooltip+"\"><div class=\"field-heading\"><label>"+name+"</label>";
        if(kind=="range")markup+="<span id=\""+id+"-value\"/>";markup+="</div>";
        if(kind=="choice"){markup+="<select id=\""+id+"\">";const auto choices=f.value("choices",Json::array());for(size_t choice=0;choice<choices.size();++choice)markup+="<option value=\""+std::to_string(choice)+"\">"+Escape(choices[choice].get<std::string>())+"</option>";markup+="</select>";}
        else if(kind=="range")markup+="<input id=\""+id+"\" class=\"range\" type=\"range\" min=\""+Number(f.value("minimum",0.))+"\" max=\""+Number(f.value("maximum",1.))+"\" step=\""+Number(f.value("step",.01))+"\"/>";
        else markup+="<div class=\"effect-entry\"><input id=\""+id+"\" class=\"effect-number\" type=\"text\"/><button id=\"effect-apply-"+std::to_string(i)+"\" class=\"quiet\"><span class=\"button-label\">Apply</span></button></div>";
        return markup+"</div>";
    }
    // One collapsible group per effect: its on/off switch, then its settings
    // under their categories. Add-on INI entries come last, collapsed.
    std::string Markup() const {
        std::vector<std::string> order;std::map<std::string,std::vector<size_t>> byEffect;std::vector<size_t> addon;
        for(size_t i=0;i<fields.size();++i){const auto effect=fields[i].value("effect",std::string());
            if(effect.starts_with(AddonPrefix)){addon.push_back(i);continue;}
            if(!byEffect.contains(effect))order.push_back(effect);byEffect[effect].push_back(i);}
        std::string markup;int group=0;
        const auto open=[&](const std::string& title,bool expanded,const std::string& hint){const auto body="effects-body-"+std::to_string(group++);
            markup+="<div class=\"option-group effect-group\"><button id=\"group-toggle-"+body+"\" class=\"group-heading"+std::string(expanded?" expanded":"")+"\"><img class=\"glyph\" src=\"icons/stack-light.png\"/><span class=\"button-label\">"+Escape(title)+"</span><span class=\"chevron\"/></button><div id=\""+body+"\" class=\"group-body\""+(expanded?"":" style=\"display: none\"")+">";
            if(!hint.empty())markup+="<p class=\"hint\">"+Escape(hint)+"</p>";};
        for(const auto& effect:order){const auto title=Friendly(effect.empty()?std::string("Effect"):effect);open(title,group==0,"");
            auto indices=byEffect[effect];std::stable_partition(indices.begin(),indices.end(),[&](size_t i){return fields[i].value("kind",std::string())=="toggle"&&!fields[i].contains("category");});
            std::string category;
            for(const size_t i:indices){const auto& f=fields[i];const bool technique=f.value("kind",std::string())=="toggle"&&!f.contains("category");
                auto label=Friendly(f.value("label",std::string("Setting")));if(technique&&(label==title||Friendly(effect)==label))label="On";
                const auto next=f.value("category",std::string());if(!technique&&next!=category){category=next;if(!category.empty())markup+="<p class=\"effect-category\">"+Escape(category)+"</p>";}
                markup+=Field(i,label);}
            markup+="</div></div>";}
        if(!addon.empty()){open("Add-on settings",false,"Read when the game starts, so changes here apply after a restart.");
            for(const size_t i:addon)markup+=Field(i,Friendly(fields[i].value("label",std::string("Setting"))));markup+="</div></div>";}
        return markup;
    }
    void Set(const Json& data) {
        if(!document||!data.is_object())return;
        auto next=data.value("fields",Json::array());if(!next.is_array()||next.size()>512)return;
        const auto version=data.value("generation",uint64_t(0));auto shape=next;
        for(auto& field:shape)field.erase("value");
        const bool rebuild=shape!=schema||version!=generation;
        if(rebuild){drafts.clear();if(!pending.empty())Result("The effects reloaded before "+std::to_string(pending.size())+(pending.size()==1?" change was":" changes were")+" applied. Try again.");pending.clear();}
        generation=version;schema=shape;fields=next;
        const bool available=generation&&!fields.empty();
        E("effects-section")->SetProperty("display",available?"block":"none");E("nav-effects")->SetProperty("display",available?"flex":"none");
        E("effects-note")->SetInnerRML(available?"Effects running in this game. Changes apply right away and are saved with your effects preset.":"This game has no adjustable effects.");
        if(rebuild)E("effects-fields")->SetInnerRML(Markup());
        Acknowledge(data);
        syncing=true;
        for(size_t i=0;i<fields.size();++i){const auto& f=fields[i];const auto id="effect-field-"+std::to_string(i);auto* element=E(id);if(!element)continue;
            const bool text=f.value("kind",std::string())=="text";
            if(text){if(auto* input=dynamic_cast<Rml::ElementFormControl*>(element);input&&document->GetContext()->GetFocusElement()!=element)input->SetValue(drafts.contains(i)?drafts.at(i):f.value("value",std::string()));continue;}
            const auto value=f.value("value",0.);element->SetClass("on",value!=0);
            if(auto* input=dynamic_cast<Rml::ElementFormControl*>(element);input&&document->GetContext()->GetFocusElement()!=element)input->SetValue(drafts.contains(i)?drafts.at(i):Number(value));
            if(auto* label=E(id+"-value"))label->SetInnerRML(Number(value));
        }
        syncing=false;
    }
    bool Event(const std::string& id,Rml::Event& event) {
        const bool apply=id.starts_with("effect-apply-");
        if(!id.starts_with("effect-field-")&&!apply)return false;
        if(event.GetType()!="click"&&event.GetType()!="change")return false;
        if(syncing||!send)return true;
        try {
            size_t end=0;const auto index=std::stoul(id.substr(13),&end);if(end!=id.size()-13||index>=fields.size())return true;
            const auto& field=fields[index];
            if(event.GetType()=="change"&&(field.value("kind",std::string())=="text"||field.value("kind",std::string())=="number")){if(auto* control=dynamic_cast<Rml::ElementFormControl*>(E("effect-field-"+std::to_string(index))))drafts[index]=control->GetValue();return true;}
            if(field.value("kind",std::string())=="text"){
                if(!apply||event.GetType()!="click")return true;auto* control=dynamic_cast<Rml::ElementFormControl*>(E("effect-field-"+std::to_string(index)));if(!control)return true;const auto text=control->GetValue();if(text.size()>1024||text.find_first_of("\r\n\0",0,3)!=std::string::npos)return true;
                if(send(Json{{"generation",generation},{"id",index},{"value",text}}.dump())){fields[index]["value"]=text;drafts.erase(index);Pending(index,true);Result("");}else Result("The effects are busy or reloading. Try again.");return true;
            }
            double value=field.value("value",0.);
            if(field.value("kind",std::string())=="toggle"){if(event.GetType()!="click")return true;value=value==0?1:0;}
            else {const bool number=field.value("kind",std::string())=="number";if(number?(!apply||event.GetType()!="click"):event.GetType()!="change")return true;auto* control=dynamic_cast<Rml::ElementFormControl*>(E("effect-field-"+std::to_string(index)));if(!control)return true;const auto text=control->GetValue();value=std::stod(text,&end);if(end!=text.size())return true;}
            if(!std::isfinite(value))return true;
            if(send(Json{{"generation",generation},{"id",index},{"value",value}}.dump())){fields[index]["value"]=value;drafts.erase(index);Pending(index,true);Result("");}else Result("The effects are busy or reloading. Try again.");
        }catch(const std::exception&){}
        return true;
    }
};
}
