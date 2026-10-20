using System.ComponentModel;
using System.Runtime.InteropServices;

namespace RtxForge.Windows.Services;

/// <summary>Native tool-window input and per-window Shell state; never changes Explorer.</summary>
internal sealed class OverlayWindowHost : IDisposable
{
    const long ToolWindow = 0x80, AppWindow = 0x40000, NoActivate = 0x08000000;
    readonly nint handle;
    readonly Subclass callback;
    readonly long originalStyle;
    ITaskbarList2? taskbar;
    bool keyboard, fullscreen, changingFullscreen, disposed;
    public string? ShellError { get; private set; }

    public OverlayWindowHost(nint hwnd)
    {
        handle = hwnd; originalStyle = GetWindowLongPtrW(handle, -20).ToInt64();
        callback = WindowProc;
        SetKeyboardInteraction(false);
        if (!SetWindowSubclass(handle, callback, 0x5256, 0)) throw new Win32Exception();
    }

    public void SetKeyboardInteraction(bool enabled)
    {
        keyboard = enabled;
        var style = (GetWindowLongPtrW(handle, -20).ToInt64() | ToolWindow) & ~AppWindow;
        style = enabled ? style & ~NoActivate : style | NoActivate;
        SetWindowLongPtrW(handle, -20, (nint)style);
        // Refresh cached frame attributes without showing or activating the HWND.
        if (!SetWindowPos(handle, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020)
            || GetWindowLongPtrW(handle, -20).ToInt64() != style) throw new Win32Exception();
    }

    public void SetFullscreen(bool enabled)
    {
        if (disposed || changingFullscreen || fullscreen == enabled) return;
        changingFullscreen = true;
        try
        {
            if (taskbar is null)
            {
                taskbar = (ITaskbarList2)Activator.CreateInstance(Type.GetTypeFromCLSID(new Guid("56FDF344-FD6D-11D0-958A-006097C9A090"), true)!)!;
                taskbar.HrInit();
            }
            // Mark only our HWND and only for a genuine fullscreen caller.
            // The Shell handles taskbar z-order while this window is active.
            taskbar.MarkFullscreenWindow(handle, enabled);
            fullscreen = enabled; ShellError = null;
        }
        catch (COMException error) { ShellError = error.Message; }
        finally { changingFullscreen = false; }
    }

    public static bool CoversDisplay(nint window, int x, int y, int width, int height) =>
        window != 0 && IsWindowVisible(window) && !IsIconic(window) && GetWindowRect(window, out var rect)
        && rect.Left <= x && rect.Top <= y && rect.Right >= x + width && rect.Bottom >= y + height;

    nint WindowProc(nint hwnd, uint message, nuint wParam, nint lParam, nuint id, nuint data)
    {
        // Preserve the click/pointer event, but do not leave the game's input
        // context just to move a slider or toggle NR. Settings opt into focus.
        if (!keyboard && (message == 0x0021 || message == 0x024B)) return 3;
        if (message == 0x0006 && (wParam & 0xffff) == 0) SetFullscreen(false);
        return DefSubclassProc(hwnd, message, wParam, lParam);
    }

    public void Dispose()
    {
        if (disposed) return;
        SetFullscreen(false); disposed = true;
        RemoveWindowSubclass(handle, callback, 0x5256);
        var current = GetWindowLongPtrW(handle, -20).ToInt64();
        var mask = ToolWindow | AppWindow | NoActivate;
        SetWindowLongPtrW(handle, -20, (nint)((current & ~mask) | (originalStyle & mask)));
        if (taskbar is not null) { Marshal.ReleaseComObject(taskbar); taskbar = null; }
    }

    [ComImport, Guid("602D4995-B13A-429B-A66E-1935E44F4317"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface ITaskbarList2
    {
        void HrInit(); void AddTab(nint hwnd); void DeleteTab(nint hwnd);
        void ActivateTab(nint hwnd); void SetActiveAlt(nint hwnd);
        void MarkFullscreenWindow(nint hwnd, [MarshalAs(UnmanagedType.Bool)] bool fullscreen);
    }
    [StructLayout(LayoutKind.Sequential)] struct Rect { public int Left, Top, Right, Bottom; }
    [UnmanagedFunctionPointer(CallingConvention.Winapi)] delegate nint Subclass(nint hwnd, uint message, nuint wParam, nint lParam, nuint id, nuint data);
    [DllImport("comctl32.dll", SetLastError = true)] static extern bool SetWindowSubclass(nint hwnd, Subclass proc, nuint id, nuint data);
    [DllImport("comctl32.dll")] static extern bool RemoveWindowSubclass(nint hwnd, Subclass proc, nuint id);
    [DllImport("comctl32.dll")] static extern nint DefSubclassProc(nint hwnd, uint message, nuint wParam, nint lParam);
    [DllImport("user32.dll")] static extern nint GetWindowLongPtrW(nint hwnd, int index);
    [DllImport("user32.dll", SetLastError = true)] static extern nint SetWindowLongPtrW(nint hwnd, int index, nint value);
    [DllImport("user32.dll", SetLastError = true)] static extern bool SetWindowPos(nint hwnd, nint after, int x, int y, int width, int height, uint flags);
    [DllImport("user32.dll")] static extern bool GetWindowRect(nint hwnd, out Rect rect);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(nint hwnd);
    [DllImport("user32.dll")] static extern bool IsIconic(nint hwnd);
}
