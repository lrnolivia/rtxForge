#include <windows.h>
#include <cstdio>
#if defined(FAKE_BINK)
extern "C" int Stub() { return 42; }
BOOL WINAPI DllMain(HMODULE, DWORD, LPVOID) { return TRUE; }
#elif defined(FAKE_FGVK)
BOOL WINAPI DllMain(HMODULE, DWORD, LPVOID) { return TRUE; }
#else
extern "C" __declspec(dllimport) int BinkClose();
int main(int argc, char**) {
    bool expectLoaded = argc == 1;
    bool loaded = GetModuleHandleW(L"fgvk.dll") != nullptr;
    bool forwarded = BinkClose() == 42;
    printf("startup module=%d expected=%d original Bink call=%d\n", loaded, expectLoaded, forwarded);
    return loaded == expectLoaded && forwarded ? 0 : 1;
}
#endif
