#pragma once
#include <json.hpp>
#include "HdrControls.h"

namespace ForgeGlass {
struct EffectControls {
    using Json=nlohmann::json;
    Rml::ElementDocument* document{};
    Json fields=Json::array(),schema=Json::array();
    uint64_t generation{};
    std::map<size_t,std::string> drafts;
    bool syncing{};
    std::function<bool(const std::string&)> send;
    Rml::Element* E(const std::string& id){return document->GetElementById(id);}
    static std::string Escape(const std::string& text){return Rml::StringUtilities::EncodeRml(text);}
    static std::string Number(double value){char text[64];std::snprintf(text,sizeof(text),"%.6g",value);return text;}
    void Set(const Json& data) {
        if(!document||!data.is_object())return;
        auto next=data.value("fields",Json::array());if(!next.is_array()||next.size()>512)return;
        const auto version=data.value("generation",uint64_t(0));auto shape=next;
        for(auto& field:shape)field.erase("value");
        const bool rebuild=shape!=schema||version!=generation;if(rebuild)drafts.clear();generation=version;schema=shape;fields=next;
        const bool available=generation&&!fields.empty();
        for(const auto* id:{"open-effects","nav-effects"})E(id)->SetProperty("display",available?"flex":"none");
        E("effects-note")->SetInnerRML(Escape(data.value("status",std::string("No effect parameters are exposed by this ReShade runtime."))));
        if(rebuild){
            std::string markup,last;bool group=false;
            for(size_t i=0;i<fields.size();++i){const auto& f=fields[i];const auto effect=f.value("effect",std::string()),category=f.value("category",std::string());
                const auto section=effect+(category.empty()?"":" · "+category);if(section!=last||!group){if(group)markup+="</div>";last=section;group=true;markup+="<div class=\"option-group\"><h3>"+Escape(section)+"</h3>";}
                const auto id="effect-field-"+std::to_string(i),kind=f.value("kind",std::string("number")),label=Escape(f.value("label",std::string("Parameter"))),tooltip=Escape(f.value("tooltip",std::string()));
                if(kind=="toggle")markup+="<div class=\"inherit-row option-toggle\" title=\""+tooltip+"\"><label>"+label+"</label><button id=\""+id+"\" class=\"switch\"><span class=\"thumb\"/></button></div>";
                else {
                    markup+="<div class=\"slider-field\" title=\""+tooltip+"\"><div class=\"field-heading\"><label>"+label+"</label>";
                    if(kind=="range")markup+="<span id=\""+id+"-value\"/>";markup+="</div>";
                    if(kind=="choice") {markup+="<select id=\""+id+"\">";const auto choices=f.value("choices",Json::array());for(size_t choice=0;choice<choices.size();++choice)markup+="<option value=\""+std::to_string(choice)+"\">"+Escape(choices[choice].get<std::string>())+"</option>";markup+="</select>";}
                    else if(kind=="range")markup+="<input id=\""+id+"\" class=\"range\" type=\"range\" min=\""+Number(f.value("minimum",0.))+"\" max=\""+Number(f.value("maximum",1.))+"\" step=\""+Number(f.value("step",.01))+"\"/>";
                    else markup+="<div class=\"save-actions\"><input id=\""+id+"\" class=\"effect-number\" type=\"text\"/><button id=\"effect-apply-"+std::to_string(i)+"\" class=\"quiet\"><span>Apply</span></button></div>";
                    markup+="</div>";
                }
            }
            if(group)markup+="</div>";E("effects-fields")->SetInnerRML(markup);
        }
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
                if(send(Json{{"generation",generation},{"id",index},{"value",text}}.dump())){fields[index]["value"]=text;drafts.erase(index);}return true;
            }
            double value=field.value("value",0.);
            if(field.value("kind",std::string())=="toggle"){if(event.GetType()!="click")return true;value=value==0?1:0;}
            else {const bool number=field.value("kind",std::string())=="number";if(number?(!apply||event.GetType()!="click"):event.GetType()!="change")return true;auto* control=dynamic_cast<Rml::ElementFormControl*>(E("effect-field-"+std::to_string(index)));if(!control)return true;const auto text=control->GetValue();value=std::stod(text,&end);if(end!=text.size())return true;}
            if(!std::isfinite(value))return true;
            if(send(Json{{"generation",generation},{"id",index},{"value",value}}.dump())){fields[index]["value"]=value;drafts.erase(index);}
        }catch(const std::exception&){}
        return true;
    }
};
}
