#pragma once
#include "menu.h"
#include "log.h"
namespace fgvk::RuntimeErrors {
enum class Code { MenuInit, MenuRender, VulkanDevice };
inline void ReportError(Code, const char* detail, int native = 0) {
    MenuError(detail); Log("Vulkan panel: %s (result=%d)", detail, native);
}
inline void ClearError(Code) {}
}
