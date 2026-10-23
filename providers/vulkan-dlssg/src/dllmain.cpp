#include <windows.h>
#include "log.h"
#include "vkhooks.h"
#include "config.h"
#include "profile.h"
#include "inputs.h"
static bool active = false;
BOOL APIENTRY DllMain(HMODULE h, DWORD reason, LPVOID) {
  if (reason == DLL_PROCESS_ATTACH) {
    DisableThreadLibraryCalls(h);
    fgvk::LogInit();
    fgvk::Log("DllMain attach - installing hooks");
    if (!fgvk::SelectProfile()) return TRUE;
    active = true;
    fgvk::LoadConfig();
    fgvk::InstallNgxLookupHook();
    fgvk::InstallVkHooks();
  } else if (reason == DLL_PROCESS_DETACH && active) {
    fgvk::RemoveVkHooks();
  }
  return TRUE;
}
