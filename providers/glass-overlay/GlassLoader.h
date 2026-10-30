#pragma once
#include "GlassOverlay.h"
#include <filesystem>
namespace ForgeGlass {
class Loader {
    HMODULE module{};Draw draw{};Draw12 draw12{};Release release{};bool attempted=false;
public:
    ~Loader() {Shutdown();if(module)FreeLibrary(module);}
    bool Load(const wchar_t* callerModule) {
        if(attempted)return draw!=nullptr;attempted=true;
        const auto path=std::filesystem::path(callerModule).parent_path()/L"rtxforge-glass.dll";
        module=LoadLibraryExW(path.c_str(),nullptr,LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR|LOAD_LIBRARY_SEARCH_SYSTEM32);
        if(!module)return false;
        draw=reinterpret_cast<Draw>(GetProcAddress(module,"ForgeGlassDraw"));release=reinterpret_cast<Release>(GetProcAddress(module,"ForgeGlassRelease"));
        draw12=reinterpret_cast<Draw12>(GetProcAddress(module,"ForgeGlassDraw12"));
        if(!draw||!release){draw=nullptr;release=nullptr;FreeLibrary(module);module=nullptr;return false;}return true;
    }
    bool Render(const Host& host,Frame& frame) {return draw&&draw(&host,&frame);}
    bool Render(const Host& host,Frame12& frame) {return draw12&&draw12(&host,&frame);}
    void Shutdown() {if(release)release();}
    bool Ready() const {return draw!=nullptr;}
};
}
