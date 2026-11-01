#include <windows.h>
#include "EffectBridge.h"

extern "C" __declspec(dllexport) const char* NAME="rtxForge ReShade controls";
extern "C" __declspec(dllexport) const char* DESCRIPTION="Live effect parameters for the rtxForge overlay.";
namespace {
void finish(reshade::api::effect_runtime* runtime,reshade::api::command_list*,reshade::api::resource_view,reshade::api::resource_view){ForgeReShade::Update(runtime);}
}
BOOL APIENTRY DllMain(HMODULE module,DWORD reason,LPVOID) {
    if(reason==DLL_PROCESS_ATTACH){DisableThreadLibraryCalls(module);if(!reshade::register_addon(module))return FALSE;
        reshade::register_event<reshade::addon_event::init_effect_runtime>(ForgeReShade::Attach);
        reshade::register_event<reshade::addon_event::destroy_effect_runtime>(ForgeReShade::Detach);
        reshade::register_event<reshade::addon_event::reshade_reloaded_effects>(ForgeReShade::Reload);
        reshade::register_event<reshade::addon_event::reshade_finish_effects>(finish);
    }else if(reason==DLL_PROCESS_DETACH){
        reshade::unregister_event<reshade::addon_event::reshade_finish_effects>(finish);
        reshade::unregister_event<reshade::addon_event::reshade_reloaded_effects>(ForgeReShade::Reload);
        reshade::unregister_event<reshade::addon_event::destroy_effect_runtime>(ForgeReShade::Detach);
        reshade::unregister_event<reshade::addon_event::init_effect_runtime>(ForgeReShade::Attach);reshade::unregister_addon(module);
    }
    return TRUE;
}
