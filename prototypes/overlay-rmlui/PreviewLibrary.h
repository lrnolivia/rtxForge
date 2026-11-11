#pragma once
#include <json.hpp>
#include <optional>

// Preview-only parent pipe. All artwork loading and exact library identity
// stay in the manager; the renderer only consumes its selected scene.
struct PreviewLibrary {
    std::vector<std::string> names;
    int request=0,selected=0;
    std::string incoming;
    explicit PreviewLibrary(const fs::path& catalog) {
        if(catalog.empty())return;
        Require(fs::file_size(catalog)<=1024*1024,"Preview catalog is too large");
        std::ifstream stream(catalog);auto json=nlohmann::json::parse(stream);
        Require(json.is_array()&&json.size()<=1000,"Invalid preview catalog");
        for(const auto& name:json){Require(name.is_string()&&name.get_ref<const std::string&>().size()<=4096,"Invalid preview game name");names.push_back(name.get<std::string>());}
    }
    bool AddChoice(const nlohmann::json& value) {
        const auto name=value.find("available"), index=value.find("index");
        if(name==value.end()||!name->is_string()||index==value.end()||!index->is_number_integer()
            ||names.size()>=1000||*index!=names.size())return false;
        const auto& title=name->get_ref<const std::string&>();
        if(title.empty()||title.size()>4096)return false;
        names.push_back(title);
        return true;
    }
    void Choose(int index) {
        if(index<0||size_t(index)>=names.size())return;
        ++request;
        std::cout<<"{\"previewGame\":"<<index<<",\"request\":"<<request<<"}"<<std::endl;
    }
    std::optional<nlohmann::json> Poll() {
        auto pipe=GetStdHandle(STD_INPUT_HANDLE);DWORD available=0;
        if(!PeekNamedPipe(pipe,nullptr,0,nullptr,&available,nullptr)||!available)return {};
        char data[4096];DWORD read=0;
        if(!ReadFile(pipe,data,std::min<DWORD>(available,sizeof(data)),&read,nullptr))return {};
        incoming.append(data,read);if(incoming.size()>65536){incoming.clear();return {};}
        std::optional<nlohmann::json> latest;
        size_t end;
        while((end=incoming.find('\n'))!=std::string::npos){
            auto line=incoming.substr(0,end);incoming.erase(0,end+1);
            auto value=nlohmann::json::parse(line,nullptr,false);
            if(!value.is_object())continue;
            if(value.contains("available")) {AddChoice(value);continue;}
            const auto reply=value.find("request");
            if(reply!=value.end()&&reply->is_number_integer()&&*reply==request)latest=std::move(value);
        }
        return latest;
    }
};
