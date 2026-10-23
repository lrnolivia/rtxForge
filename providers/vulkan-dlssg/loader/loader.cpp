// Vulkan startup loader. The game's Bink exports are forwarded by exports.def.
// No game code or third-party runtime is included in this DLL.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <cstdint>
#include <cstring>
#include <iterator>
#include <intrin.h>
#include "exports.h"

extern "C" { FARPROC ImportFuncTbl[sizeof(exportNames) / sizeof(exportNames[0])]{}; }

namespace {
wchar_t modulePath[32768];
wchar_t logPath[32768];
wchar_t fgvkPath[32768];
wchar_t originalPath[32768];
wchar_t executablePath[32768];
struct ImportSlot { void** address; void* original; void* wrapper; };
ImportSlot slots[128]{};
size_t slotCount{};
volatile LONG started{};
struct Range { uintptr_t begin, end; };
Range tlsRanges[64]{};
size_t tlsCount{};

void Log(const char* message) {
    OutputDebugStringA(message);
    wcscpy_s(logPath, modulePath);
    auto slash = wcsrchr(logPath, L'\\');
    if (!slash) return;
    wcscpy_s(slash + 1, 32768 - (slash + 1 - logPath), L"NativeMods\\rtxforge-vulkan-loader.log");
    HANDLE file = CreateFileW(logPath, FILE_APPEND_DATA, FILE_SHARE_READ | FILE_SHARE_WRITE,
                              nullptr, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file != INVALID_HANDLE_VALUE) {
        DWORD written;
        WriteFile(file, message, static_cast<DWORD>(strlen(message)), &written, nullptr);
        CloseHandle(file);
    }
}

[[noreturn]] void WINAPI MissingExport() {
    Log("original Bink does not implement this optional export\r\n");
    ExitProcess(ERROR_PROC_NOT_FOUND);
}

// Both tested games import Bink by name. Their ordinal tables differ. Refuse
// a mismatched ordinal import rather than silently calling a different API.
bool ImportsMatch(HMODULE bink) {
    const auto base = reinterpret_cast<unsigned char*>(GetModuleHandleW(nullptr));
    const auto dos = reinterpret_cast<IMAGE_DOS_HEADER*>(base);
    if (dos->e_magic != IMAGE_DOS_SIGNATURE) return false;
    const auto nt = reinterpret_cast<IMAGE_NT_HEADERS64*>(base + dos->e_lfanew);
    if (nt->Signature != IMAGE_NT_SIGNATURE || nt->FileHeader.Machine != IMAGE_FILE_MACHINE_AMD64) return false;
    const auto directory = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
    if (!directory.VirtualAddress) return true;
    const auto imports = reinterpret_cast<IMAGE_IMPORT_DESCRIPTOR*>(base + directory.VirtualAddress);
    for (const auto* item = imports; item->Name; ++item) {
        if (_stricmp(reinterpret_cast<const char*>(base + item->Name), "bink2w64.dll")) continue;
        if (!item->OriginalFirstThunk) return false;
        const auto thunk = reinterpret_cast<IMAGE_THUNK_DATA64*>(base + item->OriginalFirstThunk);
        for (const auto* symbol = thunk; symbol->u1.AddressOfData; ++symbol) {
            FARPROC expected{}, actual{};
            if (IMAGE_SNAP_BY_ORDINAL64(symbol->u1.Ordinal)) {
                const auto ordinal = IMAGE_ORDINAL64(symbol->u1.Ordinal);
                expected = GetProcAddress(bink, MAKEINTRESOURCEA(ordinal));
                for (size_t i = 0; i < std::size(exportNames); ++i)
                    if (exportOrdinals[i] == ordinal) actual = ImportFuncTbl[i];
            } else {
                const auto name = reinterpret_cast<IMAGE_IMPORT_BY_NAME*>(base + symbol->u1.AddressOfData)->Name;
                expected = GetProcAddress(bink, name);
                for (size_t i = 0; i < std::size(exportNames); ++i)
                    if (!strcmp(exportNames[i], name)) actual = ImportFuncTbl[i];
            }
            if (!expected || actual != expected) {
                Log("Bink import mismatch; loader refused before game entry\r\n"); return false;
            }
        }
    }
    return true;
}

bool InLoaderCallback() {
    // Windows x64 PEB LoaderLock, also used by Ultimate ASI Loader's startup
    // guard. A TLS/DllMain call must never initialize the graphics runtime.
    const auto peb = reinterpret_cast<const unsigned char*>(__readgsqword(0x60));
    const auto lock = *reinterpret_cast<RTL_CRITICAL_SECTION* const*>(peb + 0x110);
    if (!lock || reinterpret_cast<ULONG_PTR>(lock->OwningThread) == GetCurrentThreadId()) return true;
    // Executable TLS callbacks can also be invoked with no loader-lock owner.
    // Check their unwind ranges in the current stack, including helper calls.
    void* frames[48]{};
    const auto count = CaptureStackBackTrace(0, static_cast<DWORD>(std::size(frames)), frames, nullptr);
    for (USHORT i = 0; i < count; ++i)
        for (size_t j = 0; j < tlsCount; ++j)
            if (reinterpret_cast<uintptr_t>(frames[i]) >= tlsRanges[j].begin &&
                reinterpret_cast<uintptr_t>(frames[i]) < tlsRanges[j].end) return true;
    return false;
}

void RestoreImports() {
    for (size_t i = 0; i < slotCount; ++i) {
        auto& slot = slots[i];
        DWORD protect{};
        if (!VirtualProtect(slot.address, sizeof(void*), PAGE_READWRITE, &protect)) continue;
        InterlockedCompareExchangePointer(slot.address, slot.original, slot.wrapper);
        DWORD ignored{};
        VirtualProtect(slot.address, sizeof(void*), protect, &ignored);
    }
}

void MaybeStart() {
    if (InterlockedCompareExchange(&started, 0, 0) || InLoaderCallback()) return;
    if (InterlockedCompareExchange(&started, 1, 0)) return;
    RestoreImports();
    wcscpy_s(fgvkPath, modulePath);
    auto slash = wcsrchr(fgvkPath, L'\\');
    if (slash) {
        wcscpy_s(slash + 1, 32768 - (slash + 1 - fgvkPath), L"NativeMods\\fgvk.dll");
        // Called from the game's API use, outside DLL/TLS initialization.
        // Streamline initialization remains deferred to the game's vkCreateInstance.
        if (LoadLibraryExW(fgvkPath, nullptr, LOAD_WITH_ALTERED_SEARCH_PATH))
            Log("fgvk loaded from game API outside loader callback\r\n");
        else
            Log("fgvk load failed; continuing original game API\r\n");
    }
}

FARPROC WINAPI Lookup(HMODULE module, LPCSTR name) {
    if (reinterpret_cast<uintptr_t>(name) > 0xffff &&
        (!strcmp(name, "vkGetInstanceProcAddr") || !strcmp(name, "vkCreateInstance")) &&
        module == GetModuleHandleW(L"vulkan-1.dll")) MaybeStart();
    return GetProcAddress(module, name);
}

bool Arm() {
    auto base = reinterpret_cast<unsigned char*>(GetModuleHandleW(nullptr));
    if (!base) return false;
    auto dos = reinterpret_cast<IMAGE_DOS_HEADER*>(base);
    if (dos->e_magic != IMAGE_DOS_SIGNATURE) return false;
    auto nt = reinterpret_cast<IMAGE_NT_HEADERS64*>(base + dos->e_lfanew);
    if (nt->Signature != IMAGE_NT_SIGNATURE || nt->FileHeader.Machine != IMAGE_FILE_MACHINE_AMD64)
        return false;
    const auto tlsDirectory = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_TLS];
    if (tlsDirectory.VirtualAddress) {
        const auto tls = reinterpret_cast<IMAGE_TLS_DIRECTORY64*>(base + tlsDirectory.VirtualAddress);
        const auto callbacks = reinterpret_cast<PIMAGE_TLS_CALLBACK*>(tls->AddressOfCallBacks);
        if (callbacks) for (size_t i = 0; i < std::size(tlsRanges) && callbacks[i]; ++i) {
            DWORD64 image{};
            const auto address = reinterpret_cast<DWORD64>(callbacks[i]);
            const auto function = RtlLookupFunctionEntry(address, &image, nullptr);
            tlsRanges[tlsCount++] = function ? Range{image + function->BeginAddress, image + function->EndAddress}
                                            : Range{address, address + 16};
        }
    }
    const auto directory = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
    if (!directory.VirtualAddress) return false;
    const auto imports = reinterpret_cast<IMAGE_IMPORT_DESCRIPTOR*>(base + directory.VirtualAddress);
    for (const auto* item = imports; item->Name; ++item) {
        if (!item->OriginalFirstThunk) continue;
        const auto names = reinterpret_cast<IMAGE_THUNK_DATA64*>(base + item->OriginalFirstThunk);
        const auto addresses = reinterpret_cast<IMAGE_THUNK_DATA64*>(base + item->FirstThunk);
        for (size_t i = 0; names[i].u1.AddressOfData && slotCount < std::size(slots); ++i) {
            if (IMAGE_SNAP_BY_ORDINAL64(names[i].u1.Ordinal)) continue;
            const auto symbol = reinterpret_cast<IMAGE_IMPORT_BY_NAME*>(base + names[i].u1.AddressOfData);
            if (strcmp(symbol->Name, "GetProcAddress")) continue;
            auto wrapper = reinterpret_cast<void*>(&Lookup);
            const auto address = reinterpret_cast<void**>(&addresses[i].u1.Function);
            // Do not replace an identically named export from a game/mod DLL.
            auto kernel = GetModuleHandleW(L"kernel32.dll");
            if (*address != reinterpret_cast<void*>(GetProcAddress(kernel, symbol->Name))) continue;
            DWORD protect{};
            if (!VirtualProtect(address, sizeof(void*), PAGE_READWRITE, &protect)) continue;
            slots[slotCount++] = {address, *address, wrapper};
            InterlockedExchangePointer(address, wrapper);
            DWORD ignored{};
            VirtualProtect(address, sizeof(void*), protect, &ignored);
        }
    }
    Log(slotCount ? "Vulkan lookup startup armed; executable entry unchanged\r\n"
                  : "no supported startup imports; forwarding only\r\n");
    return slotCount != 0;
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
        // A union proxy may export a newer optional API absent from an older
        // original. Never substitute a differently numbered function.
        if (!ImportFuncTbl[i]) ImportFuncTbl[i] = reinterpret_cast<FARPROC>(&MissingExport);
    }
    return ImportsMatch(bink);
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
        if (!slash || (_wcsicmp(slash + 1, L"bg3.exe") && _wcsicmp(slash + 1, L"RDR2.exe"))) return TRUE;
        // Preserve the game even if no safe startup trigger is available.
        Arm();
        return TRUE;
    }
    return TRUE;
}
