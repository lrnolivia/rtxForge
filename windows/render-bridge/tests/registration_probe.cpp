#include <reshade.hpp>
static void device(reshade::api::device *) { reshade::log::message(reshade::log::level::info, "rtxForge SDK registration probe reached init_device."); }
extern "C" __declspec(dllexport) const char *NAME="rtxForge SDK Registration Probe";
BOOL APIENTRY DllMain(HMODULE module,DWORD reason,LPVOID) {
    if(reason==DLL_PROCESS_ATTACH) { if(!reshade::register_addon(module))return FALSE; reshade::register_event<reshade::addon_event::init_device>(device); }
    else if(reason==DLL_PROCESS_DETACH) { reshade::unregister_event<reshade::addon_event::init_device>(device); reshade::unregister_addon(module); }
    return TRUE;
}
