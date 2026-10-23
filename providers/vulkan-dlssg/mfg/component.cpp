#include "component.h"
#include "log.h"
#include "quiet_ui.h"
#include <windows.h>
#include <cstdint>
#include <atomic>
#include <filesystem>
#include <mutex>

namespace fgvk {
namespace {
std::once_flag once;
std::atomic<bool> loaded{false};
// Pinned MFG Unlocker 1.6.1's backward-compatible 64-byte query contract.
struct ModuleStatus {
    uint32_t size{64}, version{1}, backendOwner{}, duplicateSuppressed{}, dxgiHooked{}, vulkanHooked{},
        overlayVisible{}, renderFailures{}, shortcutVirtualKey{}, shortcutBindingActive{};
    uint64_t dxgiFrames{}, vulkanFrames{}, renderedFrames{};
};
static_assert(sizeof(ModuleStatus) == 64);
}
bool UniversalMfgLoaded() { return loaded.load(); }
void UniversalMfgNativeMenu(bool enabled) { mfg_ui::nativeMenu.store(enabled); }
bool PrepareUniversalMfg() {
    std::call_once(once, [] {
        HMODULE self{}; wchar_t buffer[MAX_PATH]{};
        if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                               reinterpret_cast<LPCWSTR>(&PrepareUniversalMfg), &self) ||
            !GetModuleFileNameW(self, buffer, MAX_PATH)) return;
        const auto directory = std::filesystem::path(buffer).parent_path() / L"MFG";
        // An existing process-level override describes another MFG installation.
        // Do not redirect its control/status files into this provider's journal.
        if (GetEnvironmentVariableW(L"RTX_MFG_CONFIG_PATH", nullptr, 0) ||
            GetEnvironmentVariableW(L"RTX_MFG_STATUS_PATH", nullptr, 0)) {
            Log("Universal MFG: existing process configuration override; component not loaded"); return;
        }
        const auto config = directory / L"RTXMFG-Universal.json";
        const auto status = directory / L"RTXMFG-Universal.status.json";
        if (!std::filesystem::is_regular_file(config)) { Log("Universal MFG: private configuration missing"); return; }
        SetEnvironmentVariableW(L"RTX_MFG_CONFIG_PATH", config.c_str());
        SetEnvironmentVariableW(L"RTX_MFG_STATUS_PATH", status.c_str());
        const auto path = directory / L"MFGUnlocker.dll";
        const auto module = LoadLibraryExW(path.c_str(), nullptr, LOAD_WITH_ALTERED_SEARCH_PATH);
        if (!module) { Log("Universal MFG: pinned component failed to load, Win32=%lu", GetLastError()); return; }
        wchar_t actual[MAX_PATH]{};
        if (!GetModuleFileNameW(module, actual, MAX_PATH) || _wcsicmp(actual, path.c_str())) {
            Log("Universal MFG: loaded module path differs; component refused"); return;
        }
        using Query = BOOL(WINAPI*)(ModuleStatus*);
        const auto query = reinterpret_cast<Query>(GetProcAddress(module, "MfgUnlockSingleModuleQuery"));
        ModuleStatus state{};
        if (!query || !query(&state) || !state.backendOwner || state.duplicateSuppressed) {
            Log("Universal MFG: backend ownership unavailable or a competing unlock was detected"); return;
        }
        if (!mfg_ui::Install(module)) {
            Log("Universal MFG: pinned UI guard differs or could not be installed; quiet UI policy unavailable");
            return;
        }
        Log("Universal MFG: standalone welcome/menu/input disabled; backend ownership retained");
        loaded.store(true);
        Log("Universal MFG Unlocker 1.6.1 loaded from %ls; capability and actual output remain runtime evidence", path.c_str());
    });
    return loaded.load();
}
}
