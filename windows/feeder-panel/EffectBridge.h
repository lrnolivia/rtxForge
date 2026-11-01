#pragma once
#include "reshade.hpp"
#include <json.hpp>
#include <algorithm>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <set>
#include <mutex>
#include <vector>
#include <cmath>

// ReShade supplies the schema. No package names or shader parameters are known
// here. Handles stay on ReShade's rendering thread and expire on every reload.
namespace ForgeReShade {
using Json=nlohmann::json;
using Runtime=reshade::api::effect_runtime;
struct Field {reshade::api::effect_uniform_variable uniform{};reshade::api::effect_technique technique{};reshade::api::format type{};unsigned component{},count{};std::string section,key;};
inline Runtime* current{};
inline uint64_t generation=1;
inline std::vector<Field> fields;
inline std::mutex mutex;
inline Json pending=Json::array();
inline std::string snapshot="{}";
inline ULONGLONG refreshed{};
inline bool rebuild=true;

inline std::string Annotation(Runtime* runtime,reshade::api::effect_uniform_variable value,const char* key) {
    char text[2048]{};size_t size=sizeof(text);
    if(!runtime->get_annotation_string_from_uniform_variable(value,key,text,&size)||size>sizeof(text))return {};
    return {text,size?size-1:0};
}
inline double Value(Runtime* runtime,const Field& f) {
    if(f.technique.handle)return runtime->get_technique_state(f.technique)?1:0;
    if(f.type==reshade::api::format::r32_float){float v[16]{};runtime->get_uniform_value_float(f.uniform,v,f.count);return v[f.component];}
    if(f.type==reshade::api::format::r32_sint){int32_t v[16]{};runtime->get_uniform_value_int(f.uniform,v,f.count);return v[f.component];}
    if(f.type==reshade::api::format::r32_uint){uint32_t v[16]{};runtime->get_uniform_value_uint(f.uniform,v,f.count);return v[f.component];}
    bool v[16]{};runtime->get_uniform_value_bool(f.uniform,v,f.count);return v[f.component]?1:0;
}
inline void Set(Runtime* runtime,const Field& f,double value) {
    if(!std::isfinite(value))return;
    if(f.technique.handle){runtime->set_technique_state(f.technique,value!=0);return;}
    if(f.type==reshade::api::format::r32_float){float v[16]{};runtime->get_uniform_value_float(f.uniform,v,f.count);v[f.component]=float(value);runtime->set_uniform_value_float(f.uniform,v,f.count);}
    else if(f.type==reshade::api::format::r32_sint){if(value<INT32_MIN||value>INT32_MAX)return;int32_t v[16]{};runtime->get_uniform_value_int(f.uniform,v,f.count);v[f.component]=int32_t(value);runtime->set_uniform_value_int(f.uniform,v,f.count);}
    else if(f.type==reshade::api::format::r32_uint){if(value<0||value>UINT32_MAX)return;uint32_t v[16]{};runtime->get_uniform_value_uint(f.uniform,v,f.count);v[f.component]=uint32_t(value);runtime->set_uniform_value_uint(f.uniform,v,f.count);}
    else {bool v[16]{};runtime->get_uniform_value_bool(f.uniform,v,f.count);v[f.component]=value!=0;runtime->set_uniform_value_bool(f.uniform,v,f.count);}
}
inline void Reload(Runtime* runtime) {
    if(runtime!=current)return;
    std::lock_guard lock(mutex);++generation;fields.clear();pending=Json::array();snapshot="{}";rebuild=true;refreshed=0;
}
inline void Attach(Runtime* runtime) {current=runtime;Reload(runtime);}
inline void Detach(Runtime* runtime) {if(runtime!=current)return;Reload(runtime);current=nullptr;}
inline Json schema=Json::array();
inline std::string Trim(const std::string& value){const auto start=value.find_first_not_of(" \t\r\n");if(start==std::string::npos)return {};return value.substr(start,value.find_last_not_of(" \t\r\n")-start+1);}
inline std::string ConfigValue(const Field& f) {
    char text[4096]{};size_t size=sizeof(text);
    if(!reshade::get_config_value(nullptr,f.section.c_str(),f.key.c_str(),text,&size)||!size||size>sizeof(text))return {};
    // Multi-value entries need the add-on's own schema, rather than guessing
    // whether commas represent vectors, lists, paths or literal text.
    if(std::strlen(text)+1<size)return {};
    return text;
}
inline void IniFields() {
    wchar_t executable[32768]{};if(!GetModuleFileNameW(nullptr,executable,std::size(executable)))return;
    const auto path=std::filesystem::path(executable).parent_path()/L"ReShade.ini";
    std::error_code error;if(std::filesystem::file_size(path,error)>512*1024||error)return;
    std::ifstream input(path);std::string line,section;std::set<std::pair<std::string,std::string>> seen;
    const std::set<std::string> core={"GENERAL","INPUT","OVERLAY","SCREENSHOT","STYLE","rtxForge.UI","RenoDX.DLSS5"};
    while(fields.size()<512&&std::getline(input,line)) {
        line=Trim(line);if(line.empty()||line[0]==';'||line[0]=='#')continue;
        if(line[0]=='['&&line.back()==']'){section=Trim(line.substr(1,line.size()-2));continue;}
        const auto at=line.find('=');if(section.empty()||core.contains(section)||at==std::string::npos)continue;
        const auto key=Trim(line.substr(0,at));if(key.empty()||key.size()>256||section.size()>256||!seen.insert({section,key}).second)continue;
        Field f{};f.section=section;f.key=key;char raw[4096]{};size_t length=sizeof(raw);
        if(!reshade::get_config_value(nullptr,section.c_str(),key.c_str(),raw,&length)||!length||length>sizeof(raw)||std::strlen(raw)+1<length)continue;
        schema.push_back({{"id",fields.size()},{"label",key},{"effect","Add-on settings · "+section},{"kind","text"},{"value",raw},{"tooltip","ReShade.ini / "+section+" / "+key+". This add-on may read the setting only when the game starts."}});fields.push_back(std::move(f));
    }
}
inline void UpdateImpl(Runtime* runtime) {
    if(runtime!=current)return;
    Json edits;{std::lock_guard lock(mutex);edits=std::move(pending);pending=Json::array();}
    bool changed=false;
    for(const auto& edit:edits) {
        if(edit.value("generation",uint64_t(0))!=generation)continue;
        const auto index=edit.value("id",size_t(-1));if(index>=fields.size()||!edit.contains("value"))continue;
        if(!fields[index].key.empty()) {
            if(!edit["value"].is_string())continue;const auto value=edit["value"].get<std::string>();
            if(value.size()>1024||value.find_first_of("\r\n\0",0,3)!=std::string::npos)continue;
            reshade::set_config_value(nullptr,fields[index].section.c_str(),fields[index].key.c_str(),value.c_str());changed=true;continue;
        }
        if(!edit["value"].is_number())continue;
        const double v=edit["value"].get<double>();const auto& meta=schema[index];
        if(meta.contains("minimum")&&(v<meta["minimum"].get<double>()||v>meta["maximum"].get<double>()))continue;
        if(meta.contains("choices")&&(v<0||v>=meta["choices"].size()||std::floor(v)!=v))continue;
        if(!std::isfinite(v))continue;Set(runtime,fields[index],v);changed=true;
    }
    if(changed)runtime->save_current_preset();
    if(!rebuild&&!changed&&GetTickCount64()-refreshed<250)return;
    refreshed=GetTickCount64();
    if(rebuild){
        rebuild=false;fields.clear();schema=Json::array();
        runtime->enumerate_techniques(nullptr,[](Runtime* runtime,reshade::api::effect_technique technique){
            if(fields.size()>=512)return;char name[256]{},effect[256]{};runtime->get_technique_name(technique,name);runtime->get_technique_effect_name(technique,effect);
            schema.push_back({{"id",fields.size()},{"label",name},{"effect",effect},{"kind","toggle"}});fields.push_back({{},technique});
        });
        runtime->enumerate_uniform_variables(nullptr,[](Runtime* runtime,reshade::api::effect_uniform_variable uniform){
            bool hidden=false;runtime->get_annotation_bool_from_uniform_variable(uniform,"hidden",&hidden,1);if(hidden)return;
            runtime->get_annotation_bool_from_uniform_variable(uniform,"ui_hidden",&hidden,1);if(hidden||!Annotation(runtime,uniform,"source").empty())return;
            reshade::api::format type{};uint32_t rows{},columns{},array{};runtime->get_uniform_variable_type(uniform,&type,&rows,&columns,&array);
            const auto count=uint64_t(rows)*columns*std::max(1u,array);if(!count||count>16||fields.size()+count>512)return;
            char name[256]{},effect[256]{};runtime->get_uniform_variable_name(uniform,name);runtime->get_uniform_variable_effect_name(uniform,effect);
            auto label=Annotation(runtime,uniform,"ui_label");if(label.empty())label=name;
            const auto tooltip=Annotation(runtime,uniform,"ui_tooltip"),category=Annotation(runtime,uniform,"ui_category"),ui=Annotation(runtime,uniform,"ui_type");
            Json choices=Json::array();auto items=Annotation(runtime,uniform,"ui_items");size_t start=0;while(start<items.size()&&choices.size()<128){auto end=items.find('\0',start);if(end==std::string::npos)end=items.size();if(end>start)choices.push_back(items.substr(start,end-start));start=end+1;}
            float minimum[16]{},maximum[16]{},step[16]{};
            const bool bounded=runtime->get_annotation_float_from_uniform_variable(uniform,"ui_min",minimum,size_t(count))&&runtime->get_annotation_float_from_uniform_variable(uniform,"ui_max",maximum,size_t(count));
            runtime->get_annotation_float_from_uniform_variable(uniform,"ui_step",step,size_t(count));
            for(unsigned component=0;component<count;++component){
                const bool boolean=type==reshade::api::format::r32_typeless;
                Json item={{"id",fields.size()},{"label",label+(count>1?" ["+std::to_string(component+1)+"]":"")},{"effect",effect},{"category",category},{"tooltip",tooltip},{"kind",boolean?"toggle":!choices.empty()?"choice":bounded?"range":"number"}};
                if(!choices.empty())item["choices"]=choices;
                if(bounded&&std::isfinite(minimum[component])&&std::isfinite(maximum[component])&&minimum[component]<maximum[component]){item["minimum"]=minimum[component];item["maximum"]=maximum[component];item["step"]=step[component]>0?step[component]:type==reshade::api::format::r32_float?.01:1.;}else if(!boolean&&choices.empty())item["kind"]="number";
                schema.push_back(std::move(item));fields.push_back({uniform,{},type,component,unsigned(count)});
            }
        });
        IniFields();
    }
    Json result=schema;for(size_t i=0;i<fields.size();++i){if(!fields[i].key.empty())result[i]["value"]=ConfigValue(fields[i]);else {const double v=Value(runtime,fields[i]);result[i]["value"]=std::isfinite(v)?v:0.;}}
    const auto text=Json{{"generation",generation},{"fields",result},{"status","Shader changes are live and save to the current preset. Add-on INI settings may require restarting the game."}}.dump(-1,' ',false,Json::error_handler_t::replace);
    {std::lock_guard lock(mutex);snapshot=text.size()<=1024*1024?text:"{}";}
}
inline void Update(Runtime* runtime) noexcept {
    try {UpdateImpl(runtime);}
    catch(const std::exception&){std::lock_guard lock(mutex);snapshot="{}";pending=Json::array();rebuild=true;}
}
}

extern "C" __declspec(dllexport) size_t __cdecl ForgeReShadeReadV1(char* out,size_t size) {
    std::lock_guard lock(ForgeReShade::mutex);const auto needed=ForgeReShade::snapshot.size()+1;
    if(out&&size>=needed)std::memcpy(out,ForgeReShade::snapshot.c_str(),needed);return needed;
}
extern "C" __declspec(dllexport) bool __cdecl ForgeReShadeWriteV1(const char* text) {
    if(!text||std::strlen(text)>4096)return false;const auto edit=ForgeReShade::Json::parse(text,nullptr,false);
    if(!edit.is_object()||!edit.contains("generation")||!edit["generation"].is_number_unsigned()||!edit.contains("id")||!edit["id"].is_number_unsigned()||!edit.contains("value")||!(edit["value"].is_number()||edit["value"].is_string()))return false;
    std::lock_guard lock(ForgeReShade::mutex);if(edit["generation"]!=ForgeReShade::generation||ForgeReShade::pending.size()>=64)return false;
    ForgeReShade::pending.push_back(edit);return true;
}
