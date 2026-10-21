using System.Runtime.InteropServices;
using RtxForge.Windows.Services;

static class Program
{
    [STAThread]
    static void Main()
    {
        // No visible test surface or system input. Only a disposable hidden HWND.
        var foreground = GetForegroundWindow();
        var window = CreateWindowExW(0x40100, "STATIC", "rtxForge hidden window fixture", 0,
            -32000, -32000, 200, 200, 0, 0, 0, 0);
        if (window == 0) throw new Exception("Could not create hidden fixture HWND.");
        var original = GetWindowLongPtrW(window, -20).ToInt64();
        try
        {
            using (var host = new OverlayWindowHost(window))
            {
                Check((GetWindowLongPtrW(window, -20).ToInt64() & 0x8040080) == 0x8000080,
                    "Tool/no-activate styles missing or APPWINDOW retained.");
                Check(SendMessageW(window, 0x0021, 0, 0) == 3, "Mouse activation was not suppressed.");
                // WM_POINTERACTIVATE needs a valid system pointer ID. Touch
                // interaction stays unverified in this no-input fixture.
                host.SetKeyboardInteraction(true);
                Check((GetWindowLongPtrW(window, -20).ToInt64() & 0x8000000) == 0, "Settings cannot receive keyboard focus.");
                Check(SendMessageW(window, 0x0021, 0, 0) == 1, "Settings mouse activation was not delegated.");
                host.SetKeyboardInteraction(false);
                Check(SendMessageW(window, 0x0021, 0, 0) == 3, "Returning to controls retained activation.");
                // Exercise the real per-window Shell COM contract. A hidden,
                // inactive HWND cannot displace the user's taskbar or foreground.
                host.SetFullscreen(true);
                Check(host.ShellError is null, "Shell fullscreen contract failed: " + host.ShellError);
                host.SetFullscreen(false);
                Check(!OverlayWindowHost.CoversDisplay(window, -32000, -32000, 200, 200), "Hidden caller accepted as fullscreen.");
                Check(!OverlayWindowHost.CoversDisplay(0, 0, 0, 1920, 1080), "Missing caller accepted as fullscreen.");
            }
            Check(GetWindowLongPtrW(window, -20).ToInt64() == original, "Disposal did not restore native styles.");
            Check(SendMessageW(window, 0x0021, 0, 0) == 1, "Disposal left the subclass attached.");
            Check(GetForegroundWindow() == foreground, "Hidden fixture changed foreground focus.");
            Console.WriteLine("PASS: actual hidden HWND tool/no-activate flags, mouse delivery, keyboard settings transition, Shell COM, fullscreen guards and cleanup; no screen/input used. Real touch/gameplay remain unverified.");
        }
        finally { DestroyWindow(window); }
    }
    static void Check(bool value, string message) { if (!value) throw new Exception(message); }
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern nint CreateWindowExW(uint exStyle, string cls, string name, uint style, int x, int y, int width, int height, nint parent, nint menu, nint instance, nint parameter);
    [DllImport("user32.dll")] static extern bool DestroyWindow(nint hwnd);
    [DllImport("user32.dll")] static extern nint GetWindowLongPtrW(nint hwnd, int index);
    [DllImport("user32.dll")] static extern nint GetForegroundWindow();
    [DllImport("user32.dll")] static extern nint SendMessageW(nint hwnd, uint message, nuint wParam, nint lParam);
}
