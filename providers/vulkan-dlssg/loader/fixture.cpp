#include <windows.h>
#include <cstdio>
#include <cstring>
#if defined(FAKE_BINK)
extern "C" int Stub() { return 42; }
extern "C" int CloseStub() { return 42; }
extern "C" int ErrorStub() { return 47; }
BOOL WINAPI DllMain(HMODULE, DWORD, LPVOID) { return TRUE; }
#elif defined(FAKE_FGVK)
BOOL WINAPI DllMain(HMODULE, DWORD, LPVOID) { return TRUE; }
#elif defined(FAKE_VULKAN)
extern "C" __declspec(dllexport) int WINAPI vkCreateInstance(void*, void*, void*) { return 42; }
#else
extern "C" __declspec(dllimport) int BinkClose();
extern "C" __declspec(dllimport) int BinkGetError();
unsigned char entryInTls[14]{};
unsigned char* executableEntry{};
bool loadedInTls{};
void NTAPI OnTls(void* module, DWORD reason, void*) {
    if (reason != DLL_PROCESS_ATTACH) return;
    auto base = static_cast<unsigned char*>(module);
    const auto dos = reinterpret_cast<IMAGE_DOS_HEADER*>(base);
    const auto nt = reinterpret_cast<IMAGE_NT_HEADERS64*>(base + dos->e_lfanew);
    executableEntry = base + nt->OptionalHeader.AddressOfEntryPoint;
    memcpy(entryInTls, executableEntry, sizeof(entryInTls));
    STARTUPINFOW info{};
    GetStartupInfoW(&info); // Must pass through without loading inside TLS.
    auto vulkan = LoadLibraryW(L"vulkan-1.dll");
    if (vulkan) GetProcAddress(vulkan, "vkCreateInstance");
    loadedInTls = GetModuleHandleW(L"fgvk.dll") != nullptr;
}
#pragma section(".CRT$XLB", long, read)
extern "C" __declspec(allocate(".CRT$XLB")) PIMAGE_TLS_CALLBACK fixtureTls = OnTls;
#pragma comment(linker, "/INCLUDE:_tls_used")
#pragma comment(linker, "/INCLUDE:fixtureTls")
DWORD WINAPI SmallStackThread(LPVOID) { return BinkClose() == 42 ? 0 : 1; }
int main(int argc, char**) {
    auto vulkan = GetModuleHandleW(L"vulkan-1.dll");
    auto create = vulkan ? reinterpret_cast<int(WINAPI*)(void*,void*,void*)>(GetProcAddress(vulkan,"vkCreateInstance")) : nullptr;
    const bool vulkanForwarded = create && create(nullptr,nullptr,nullptr) == 42;
    const bool entryPreserved = executableEntry && !memcmp(entryInTls, executableEntry, sizeof(entryInTls));
    bool expectLoaded = argc == 1;
    bool loaded = GetModuleHandleW(L"fgvk.dll") != nullptr;
    bool forwarded = BinkClose() == 42 && BinkGetError() == 47;
    HANDLE thread = CreateThread(nullptr, 65536, SmallStackThread, nullptr,
                                 STACK_SIZE_PARAM_IS_A_RESERVATION, nullptr);
    DWORD result = 1;
    if (thread) {
        WaitForSingleObject(thread, INFINITE);
        GetExitCodeThread(thread, &result);
        CloseHandle(thread);
    }
    printf("startup module=%d expected=%d original Bink call=%d small-stack thread=%lu TLS-loaded=%d entry-preserved=%d\n",
           loaded, expectLoaded, forwarded, result, loadedInTls, entryPreserved);
    return loaded == expectLoaded && forwarded && vulkanForwarded && result == 0 && !loadedInTls && entryPreserved ? 0 : 1;
}
#endif
