#include <windows.h>
#include <cstdio>
#if defined(FAKE_BINK)
extern "C" int Stub() { return 42; }
BOOL WINAPI DllMain(HMODULE, DWORD, LPVOID) { return TRUE; }
#elif defined(FAKE_FGVK)
BOOL WINAPI DllMain(HMODULE, DWORD, LPVOID) { return TRUE; }
#else
extern "C" __declspec(dllimport) int BinkClose();
DWORD WINAPI SmallStackThread(LPVOID) { return BinkClose() == 42 ? 0 : 1; }
int main(int argc, char**) {
    bool expectLoaded = argc == 1;
    bool loaded = GetModuleHandleW(L"fgvk.dll") != nullptr;
    bool forwarded = BinkClose() == 42;
    HANDLE thread = CreateThread(nullptr, 65536, SmallStackThread, nullptr,
                                 STACK_SIZE_PARAM_IS_A_RESERVATION, nullptr);
    DWORD result = 1;
    if (thread) {
        WaitForSingleObject(thread, INFINITE);
        GetExitCodeThread(thread, &result);
        CloseHandle(thread);
    }
    printf("startup module=%d expected=%d original Bink call=%d small-stack thread=%lu\n",
           loaded, expectLoaded, forwarded, result);
    return loaded == expectLoaded && forwarded && result == 0 ? 0 : 1;
}
#endif
