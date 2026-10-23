#pragma once
#include <windows.h>
#include <algorithm>
#include <cmath>
#include <cstring>
#include <format>
#include <memory>
#include <string>
#include <vector>
#include "Config.h"
#include "State.h"
#include "VulkanDispatch.h"
#include "log.h"
template<class... T> inline void NrLog(std::string_view format, T&&... args) {
    const auto message = std::vformat(format, std::make_format_args(args...));
    fgvk::Log("%s", message.c_str());
}
#define LOG_INFO(...) NrLog(__VA_ARGS__)
#define LOG_WARN(...) NrLog(__VA_ARGS__)
#define LOG_ERROR(...) NrLog(__VA_ARGS__)
#define LOG_DEBUG(...) do {} while (0)
#define LOG_FUNC() do {} while (0)
