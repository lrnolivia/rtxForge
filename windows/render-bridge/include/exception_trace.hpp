#pragma once
#include <Windows.h>
#include <TlHelp32.h>
#include <cstdio>

namespace forge::diagnostics {
// Opt-in, bounded first-chance evidence. Never consumes an exception or replaces
// the application's exception filter. No process-memory dump or symbol engine.
inline HANDLE log_file = INVALID_HANDLE_VALUE;
inline PVOID handler_cookie = nullptr;
inline volatile LONG writing = 0, exceptions = 0;
inline LONG exception_counts[4]{};

inline void line(const char *text, DWORD length) noexcept {
    if (log_file == INVALID_HANDLE_VALUE) return;
    DWORD written = 0;
    WriteFile(log_file, text, length, &written, nullptr);
}

inline void stack(CONTEXT context) noexcept {
    // A damaged stack can fault again; the recursion guard leaves that exception
    // to the application's handlers and this SEH boundary bounds our own reader.
    __try {
        for (unsigned i = 0; i < 32 && context.Rip; ++i) {
            MEMORY_BASIC_INFORMATION memory{};
            VirtualQuery(reinterpret_cast<void *>(context.Rip), &memory, sizeof(memory));
            const auto base = reinterpret_cast<DWORD64>(memory.AllocationBase);
            char text[192]{};
            const int count = sprintf_s(text, "frame=%u pc=0x%llx allocation_base=0x%llx offset=0x%llx rsp=0x%llx\r\n",
                i, context.Rip, base, context.Rip - base, context.Rsp);
            if (count > 0) line(text, static_cast<DWORD>(count));
            DWORD64 image = 0;
            const auto entry = RtlLookupFunctionEntry(context.Rip, &image, nullptr);
            if (entry) {
                void *data = nullptr; DWORD64 establisher = 0;
                RtlVirtualUnwind(UNW_FLAG_NHANDLER, image, context.Rip, entry, &context, &data, &establisher, nullptr);
            } else {
                const auto address = *reinterpret_cast<const DWORD64 *>(context.Rsp);
                context.Rip = address; context.Rsp += sizeof(DWORD64);
            }
        }
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        constexpr char text[] = "stack_unwind_incomplete=true\r\n";
        line(text, sizeof(text) - 1);
    }
}

inline LONG WINAPI exception(EXCEPTION_POINTERS *info) noexcept {
    const auto code = info->ExceptionRecord->ExceptionCode;
    if (code != EXCEPTION_ACCESS_VIOLATION && code != EXCEPTION_STACK_OVERFLOW
        && code != EXCEPTION_ILLEGAL_INSTRUCTION && code != 0xC0000409) return EXCEPTION_CONTINUE_SEARCH;
    if (InterlockedCompareExchange(&writing, 1, 0)) return EXCEPTION_CONTINUE_SEARCH;
    const auto sequence = InterlockedIncrement(&exceptions);
    // Some applications deliberately handle many illegal-instruction events.
    // Their budget must not consume the access-violation evidence budget.
    const unsigned category = code == EXCEPTION_ACCESS_VIOLATION ? 0 : code == EXCEPTION_STACK_OVERFLOW ? 1 : code == EXCEPTION_ILLEGAL_INSTRUCTION ? 2 : 3;
    constexpr LONG limits[] = {32, 4, 8, 4};
    const auto count_for_code = ++exception_counts[category];
    if (count_for_code <= limits[category]) {
        char text[384]{};
        const auto &record = *info->ExceptionRecord;
        const int count = sprintf_s(text,
            "first_chance_observation=%ld pid=%lu tid=%lu code=0x%08lx address=%p operation=0x%llx operand=0x%llx handled_by_application=unknown\r\n",
            sequence, GetCurrentProcessId(), GetCurrentThreadId(), code, record.ExceptionAddress,
            record.NumberParameters > 0 ? static_cast<unsigned long long>(record.ExceptionInformation[0]) : 0,
            record.NumberParameters > 1 ? static_cast<unsigned long long>(record.ExceptionInformation[1]) : 0);
        if (count > 0) line(text, static_cast<DWORD>(count));
        if (code != EXCEPTION_STACK_OVERFLOW) stack(*info->ContextRecord);
    } else if (count_for_code == limits[category] + 1) {
        char text[96]{};
        const int count = sprintf_s(text, "exception_trace_budget_exhausted=true code=0x%08lx\r\n", code);
        if (count > 0) line(text, static_cast<DWORD>(count));
    }
    InterlockedExchange(&writing, 0);
    return EXCEPTION_CONTINUE_SEARCH;
}

inline void modules() noexcept {
    if (log_file == INVALID_HANDLE_VALUE) return;
    const auto snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, GetCurrentProcessId());
    if (snapshot == INVALID_HANDLE_VALUE) return;
    MODULEENTRY32W module{}; module.dwSize = sizeof(module);
    if (Module32FirstW(snapshot, &module)) do {
        char path[4096]{}, text[4352]{};
        WideCharToMultiByte(CP_UTF8, 0, module.szExePath, -1, path, sizeof(path), nullptr, nullptr);
        const int count = sprintf_s(text, "module base=%p bytes=%lu path=%s\r\n", module.modBaseAddr, module.modBaseSize, path);
        if (count > 0) line(text, static_cast<DWORD>(count));
    } while (Module32NextW(snapshot, &module));
    CloseHandle(snapshot);
}

inline bool start(const wchar_t *path) noexcept {
    log_file = CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ, nullptr, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (log_file == INVALID_HANDLE_VALUE) return false;
    handler_cookie = AddVectoredExceptionHandler(1, exception);
    if (!handler_cookie) { CloseHandle(log_file); log_file = INVALID_HANDLE_VALUE; return false; }
    constexpr char text[] = "rtxForge opt-in exception observations; first-chance events alone do not prove a crash\r\n";
    line(text, sizeof(text) - 1);
    modules();
    return true;
}

inline void stop(bool process_termination) noexcept {
    if (handler_cookie) { RemoveVectoredExceptionHandler(handler_cookie); handler_cookie = nullptr; }
    if (log_file != INVALID_HANDLE_VALUE) {
        // The loader calls this under its lock. Keep shutdown to a bounded write;
        // allocation, path lookup, module enumeration and unwinding stay outside it.
        const char *text = process_termination ? "addon_detach=process_termination\r\n" : "addon_detach=module_unload\r\n";
        line(text, process_termination ? 34 : 28);
        CloseHandle(log_file); log_file = INVALID_HANDLE_VALUE;
    }
}
}
