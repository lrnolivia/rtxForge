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
            if(value.is_object()&&value.value("request",0)==request)latest=std::move(value);
        }
        return latest;
    }
};
