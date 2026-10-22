// BG3 startup loader. The game's Bink exports are forwarded by exports.def.
// No game code or third-party runtime is included in this DLL.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <cstdint>
#include <cstring>
#include "exports.h"

extern "C" { FARPROC ImportFuncTbl[sizeof(exportNames) / sizeof(exportNames[0])]{}; }

namespace {
unsigned char saved[14];
unsigned char* entry;
wchar_t modulePath[32768];
wchar_t logPath[32768];
wchar_t fgvkPath[32768];
wchar_t originalPath[32768];
wchar_t executablePath[32768];
bool armed;

void Log(const char* message) {
    OutputDebugStringA(message);
    wcscpy_s(logPath, modulePath);
    auto slash = wcsrchr(logPath, L'\\');
    if (!slash) return;
    wcscpy_s(slash + 1, 32768 - (slash + 1 - logPath), L"NativeMods\\rtxforge-bg3-loader.log");
    HANDLE file = CreateFileW(logPath, FILE_APPEND_DATA, FILE_SHARE_READ | FILE_SHARE_WRITE,
                              nullptr, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file != INVALID_HANDLE_VALUE) {
        DWORD written;
        WriteFile(file, message, static_cast<DWORD>(strlen(message)), &written, nullptr);
        CloseHandle(file);
    }
}

void WINAPI Start() {
    DWORD protect;
    if (!VirtualProtect(entry, sizeof(saved), PAGE_EXECUTE_READWRITE, &protect)) {
        Log("entry restore failed\r\n");
        ExitProcess(ERROR_INVALID_ACCESS);
    }
    memcpy(entry, saved, sizeof(saved));
    FlushInstructionCache(GetCurrentProcess(), entry, sizeof(saved));
    DWORD ignored;
    VirtualProtect(entry, sizeof(saved), protect, &ignored);
    armed = false;
    wcscpy_s(fgvkPath, modulePath);
    auto slash = wcsrchr(fgvkPath, L'\\');
    if (slash) {
        wcscpy_s(slash + 1, 32768 - (slash + 1 - fgvkPath), L"NativeMods\\fgvk.dll");
        // fgvk performs its lightweight hook installation here, outside loader lock.
        // Streamline initialization remains deferred to the game's vkCreateInstance.
        if (LoadLibraryExW(fgvkPath, nullptr, LOAD_WITH_ALTERED_SEARCH_PATH))
            Log("fgvk loaded before game entry\r\n");
        else
            Log("fgvk load failed; continuing with original game entry\r\n");
    }
    reinterpret_cast<void (WINAPI*)()>(entry)();
}

bool Arm(HMODULE self) {
    if (!GetModuleFileNameW(self, modulePath, 32768)) return false;
    auto base = reinterpret_cast<unsigned char*>(GetModuleHandleW(nullptr));
    if (!base) return false;
    auto dos = reinterpret_cast<IMAGE_DOS_HEADER*>(base);
    if (dos->e_magic != IMAGE_DOS_SIGNATURE) return false;
    auto nt = reinterpret_cast<IMAGE_NT_HEADERS64*>(base + dos->e_lfanew);
    if (nt->Signature != IMAGE_NT_SIGNATURE || nt->FileHeader.Machine != IMAGE_FILE_MACHINE_AMD64)
        return false;
    entry = base + nt->OptionalHeader.AddressOfEntryPoint;
    if (!nt->OptionalHeader.AddressOfEntryPoint ||
        nt->OptionalHeader.AddressOfEntryPoint + sizeof(saved) > nt->OptionalHeader.SizeOfImage)
        return false;
    DWORD protect;
    if (!VirtualProtect(entry, sizeof(saved), PAGE_EXECUTE_READWRITE, &protect)) return false;
    memcpy(saved, entry, sizeof(saved));
    // RIP-relative indirect jump, preserving every register and stack argument.
    unsigned char jump[14] = {0xff, 0x25, 0, 0, 0, 0};
    auto destination = reinterpret_cast<uintptr_t>(&Start);
    memcpy(jump + 6, &destination, sizeof(destination));
    memcpy(entry, jump, sizeof(jump));
    FlushInstructionCache(GetCurrentProcess(), entry, sizeof(jump));
    DWORD ignored;
    VirtualProtect(entry, sizeof(saved), protect, &ignored);
    armed = true;
    return true;
}

bool Forward(HMODULE self) {
    if (!GetModuleFileNameW(self, modulePath, 32768)) return false;
    wcscpy_s(originalPath, modulePath);
    auto slash = wcsrchr(originalPath, L'\\');
    if (!slash) return false;
    wcscpy_s(slash + 1, 32768 - (slash + 1 - originalPath), L"bink2w64_rtxforge_original.dll");
    HMODULE bink = LoadLibraryExW(originalPath, nullptr, LOAD_WITH_ALTERED_SEARCH_PATH);
    if (!bink) return false;
    for (size_t i = 0; i < sizeof(exportNames) / sizeof(exportNames[0]); ++i) {
        ImportFuncTbl[i] = GetProcAddress(bink, exportNames[i]);
        if (!ImportFuncTbl[i]) return false;
    }
    return true;
}
}

BOOL WINAPI DllMain(HMODULE self, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        if (!Forward(self)) return FALSE;
        // This proxy is intentionally scoped to the Vulkan executable.
        // DllMain also runs on game worker threads with small reserved stacks.
        // Keep path buffers static so even THREAD_ATTACH has a small stack frame.
        if (!GetModuleFileNameW(nullptr, executablePath, 32768)) return FALSE;
        auto slash = wcsrchr(executablePath, L'\\');
        if (!slash || _wcsicmp(slash + 1, L"bg3.exe")) return TRUE;
        return Arm(self) ? TRUE : FALSE;
    }
    return TRUE;
}
