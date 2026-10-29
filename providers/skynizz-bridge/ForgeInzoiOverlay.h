#pragma once
#include <string_view>
#include <cwctype>
#ifdef _WIN32
#include <windows.h>
#endif

namespace ForgeInzoiOverlay
{
enum class Mode { Unchanged, LateFrame, Compatibility };

inline Mode Choose(std::wstring_view executable, bool compatibility)
{
    constexpr std::wstring_view target = L"inzoi-win64-shipping.exe";
    if (executable.size() != target.size()) return Mode::Unchanged;
    for (size_t index = 0; index < target.size(); ++index)
        if (std::towlower(executable[index]) != target[index]) return Mode::Unchanged;
    return compatibility ? Mode::Compatibility : Mode::LateFrame;
}

#ifdef _WIN32
inline Mode Current(std::wstring_view executable)
{
    if (Choose(executable, false) == Mode::Unchanged) return Mode::Unchanged;
    wchar_t value[2] = {};
    const bool compatibility = GetEnvironmentVariableW(L"RTXFORGE_INZOI_LATE_OVERLAY", value, 2) == 1
                               && value[0] == L'0';
    return Choose(executable, compatibility);
}
#endif
}
