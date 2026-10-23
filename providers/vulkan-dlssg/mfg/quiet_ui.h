#pragma once
#include <windows.h>
#include <detours.h>
#include <array>
#include <atomic>
#include <cstring>

namespace fgvk::mfg_ui {
// MFG 1.6.1 has no public switch for its standalone UI. Its source separates
// OverlayAllowed from OwnsBackend: this one guard gates menu rendering and
// input, while the unlock and follow-game controls remain owned by the core.
// Bind only the exact pinned release's guard, never a signature search or an
// assumed layout in another version. Keep the installed vendor file intact.
inline constexpr size_t GuardRva = 0xb80d0;
inline constexpr std::array<unsigned char,36> GuardBytes = {
    0x48,0x83,0xec,0x28,0x80,0x3d,0x45,0xe9,0x37,0x00,0x00,0x74,0x10,
    0xe8,0x7e,0x22,0xf8,0xff,0x84,0xc0,0x75,0x07,0xb0,0x01,0x48,0x83,
    0xc4,0x28,0xc3,0x32,0xc0,0x48,0x83,0xc4,0x28,0xc3
};
inline bool (*original)(){};
inline std::atomic<bool> nativeMenu{false};
inline bool Allowed() { return nativeMenu.load() && original && original(); }
inline bool Matches(HMODULE module) {
    if(!module) return false;
    const auto base = reinterpret_cast<const unsigned char*>(module);
    const auto dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(base);
    if(dos->e_magic!=IMAGE_DOS_SIGNATURE || dos->e_lfanew<64 || dos->e_lfanew>4096) return false;
    const auto nt = reinterpret_cast<const IMAGE_NT_HEADERS64*>(base+dos->e_lfanew);
    return nt->Signature==IMAGE_NT_SIGNATURE && nt->FileHeader.Machine==IMAGE_FILE_MACHINE_AMD64
        && nt->OptionalHeader.SizeOfImage>GuardRva+GuardBytes.size()
        && !std::memcmp(base+GuardRva,GuardBytes.data(),GuardBytes.size());
}
inline bool Install(HMODULE module) {
    if(original) return true;
    if(!Matches(module)) return false;
    original = reinterpret_cast<bool(*)()>(reinterpret_cast<unsigned char*>(module)+GuardRva);
    LONG result = DetourTransactionBegin();
    if(result==NO_ERROR) result=DetourUpdateThread(GetCurrentThread());
    if(result==NO_ERROR) result=DetourAttach(reinterpret_cast<PVOID*>(&original),reinterpret_cast<PVOID>(&Allowed));
    if(result!=NO_ERROR) { DetourTransactionAbort(); original=nullptr; return false; }
    result=DetourTransactionCommit();
    if(result!=NO_ERROR) original=nullptr;
    return result==NO_ERROR;
}
}
