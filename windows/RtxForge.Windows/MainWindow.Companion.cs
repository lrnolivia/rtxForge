using System.Runtime.InteropServices;
using RtxForge.Windows.Models;
using RtxForge.Windows.Services;
using RtxForge.Windows.Views;

namespace RtxForge.Windows;

public sealed partial class MainWindow
{
    CompanionWindow? companion;
    CompanionSubclass? companionSubclass;
    const int CompanionHotkeyId = 0x5254;
    bool companionHooked;
    public static readonly string[] CompanionShortcuts = ["Ctrl+Shift+R", "Ctrl+Alt+R", "Ctrl+Shift+F10", "Disabled"];
    public string? CompanionShortcutProblem { get; private set; }

    void InitializeCompanion()
    {
        if (Service is not EngineForgeService) return;
        companionSubclass = CompanionWindowProc;
        companionHooked = SetWindowSubclass(Handle, companionSubclass, 0x5254, 0);
        ConfigureCompanionShortcut();
        Closed += (_, _) =>
        {
            UnregisterHotKey(Handle, CompanionHotkeyId);
            if (companionHooked) RemoveWindowSubclass(Handle, companionSubclass, 0x5254);
            companion?.Shutdown();
        };
    }

    public void OpenCompanion(Game? game = null)
    {
        if (Service is not EngineForgeService engine) { ShowToast("Live controls require the installed engine."); return; }
        companion ??= new CompanionWindow(this, engine);
        companion.Present(game);
    }

    public void ConfigureCompanionShortcut()
    {
        UnregisterHotKey(Handle, CompanionHotkeyId);
        CompanionShortcutProblem = null;
        if (Settings.PanelHotkey == "Disabled") return;
        if (!CompanionShortcuts.Contains(Settings.PanelHotkey)) Settings.PanelHotkey = CompanionShortcuts[0];
        uint modifiers = Settings.PanelHotkey == "Ctrl+Alt+R" ? 0x0003u : 0x0006u;
        uint key = Settings.PanelHotkey == "Ctrl+Shift+F10" ? 0x79u : 0x52u;
        if (!companionHooked || !RegisterHotKey(Handle, CompanionHotkeyId, modifiers | 0x4000, key))
            CompanionShortcutProblem = "This shortcut is in use. Choose another in Settings. Live controls remain available from Game Details.";
    }

    nint CompanionWindowProc(nint hwnd, uint message, nuint wParam, nint lParam, nuint id, nuint data)
    {
        if (message == 0x0312 && (int)wParam == CompanionHotkeyId)
        {
            if (companion?.IsShown == true) companion.HidePanel(); else OpenCompanion();
            return 0;
        }
        return DefSubclassProc(hwnd, message, wParam, lParam);
    }

    [UnmanagedFunctionPointer(CallingConvention.Winapi)]
    delegate nint CompanionSubclass(nint hwnd, uint message, nuint wParam, nint lParam, nuint id, nuint data);
    [DllImport("comctl32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    static extern bool SetWindowSubclass(nint hwnd, CompanionSubclass procedure, nuint id, nuint data);
    [DllImport("comctl32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    static extern bool RemoveWindowSubclass(nint hwnd, CompanionSubclass procedure, nuint id);
    [DllImport("comctl32.dll")]
    static extern nint DefSubclassProc(nint hwnd, uint message, nuint wParam, nint lParam);
    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    static extern bool RegisterHotKey(nint hwnd, int id, uint modifiers, uint key);
    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    static extern bool UnregisterHotKey(nint hwnd, int id);
}
