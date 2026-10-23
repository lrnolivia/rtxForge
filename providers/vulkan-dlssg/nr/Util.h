#pragma once
#include <windows.h>
#include <filesystem>
#include <optional>
namespace Util {
inline std::filesystem::path DllPath() {
    HMODULE module{}; wchar_t path[32768]{};
    if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                           reinterpret_cast<LPCWSTR>(&DllPath), &module) ||
        !GetModuleFileNameW(module, path, 32768)) return {};
    return path;
}
// The model is supplied explicitly beside this provider. Never search game-root
// DLLs: an unrelated NR stack must not be silently adopted.
inline std::filesystem::path ExePath() { return DllPath(); }
inline std::optional<std::filesystem::path> FindFilePath(const std::filesystem::path& base, const wchar_t* name) {
    const auto path = base / name;
    std::error_code error;
    if (std::filesystem::is_regular_file(path, error)) return path;
    return std::nullopt;
}
inline std::optional<std::filesystem::path> FindFilePath(const std::filesystem::path& base, const char* name) {
    return FindFilePath(base, std::filesystem::path(name).c_str());
}
}
