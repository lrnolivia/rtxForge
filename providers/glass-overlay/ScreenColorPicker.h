#pragma once
#include <windows.h>
#include <atomic>
#include <thread>
#include <optional>

namespace ForgeGlass {
// Runs only for an explicit pick. No hooks, screen reads or worker remain idle.
class ScreenColorPicker {
    std::thread worker;
    std::atomic<DWORD> thread{0};
    std::atomic_bool done{true},cancelled{false},selected{false};
    std::atomic<COLORREF> color{0};
    inline static thread_local ScreenColorPicker* active=nullptr;
    static LRESULT CALLBACK Mouse(int code,WPARAM message,LPARAM data) {
        if(code>=0&&active&&(message==WM_LBUTTONDOWN||message==WM_RBUTTONDOWN)){
            if(message==WM_LBUTTONDOWN){const auto at=reinterpret_cast<MSLLHOOKSTRUCT*>(data)->pt;const auto dc=GetDC(nullptr);if(dc){const auto rgb=GetPixel(dc,at.x,at.y);ReleaseDC(nullptr,dc);if(rgb!=CLR_INVALID){active->color=rgb;active->selected=true;}}}
            PostQuitMessage(0);return 1;
        }
        return CallNextHookEx(nullptr,code,message,data);
    }
    static LRESULT CALLBACK Keyboard(int code,WPARAM message,LPARAM data) {
        if(code>=0&&active&&(message==WM_KEYDOWN||message==WM_SYSKEYDOWN)&&reinterpret_cast<KBDLLHOOKSTRUCT*>(data)->vkCode==VK_ESCAPE){PostQuitMessage(0);return 1;}
        return CallNextHookEx(nullptr,code,message,data);
    }
public:
    ~ScreenColorPicker(){Cancel();}
    void Cancel(){cancelled=true;if(const auto id=thread.load())PostThreadMessageW(id,WM_QUIT,0,0);if(worker.joinable())worker.join();thread=0;done=true;}
    void Start(){
        Cancel();cancelled=false;selected=false;done=false;
        worker=std::thread([this]{
            active=this;MSG message{};PeekMessageW(&message,nullptr,WM_USER,WM_USER,PM_NOREMOVE);thread=GetCurrentThreadId();
            HMODULE module{};GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,reinterpret_cast<LPCWSTR>(&Mouse),&module);
            const auto mouse=SetWindowsHookExW(WH_MOUSE_LL,Mouse,module,0),keyboard=SetWindowsHookExW(WH_KEYBOARD_LL,Keyboard,module,0);
            if(mouse&&keyboard&&!cancelled)while(GetMessageW(&message,nullptr,0,0)>0){TranslateMessage(&message);DispatchMessageW(&message);}
            if(mouse)UnhookWindowsHookEx(mouse);if(keyboard)UnhookWindowsHookEx(keyboard);thread=0;active=nullptr;done=true;
        });
    }
    bool Finished()const{return done;}
    std::optional<COLORREF> Result(){if(worker.joinable())worker.join();return selected?std::optional<COLORREF>(color.load()):std::nullopt;}
};
}
