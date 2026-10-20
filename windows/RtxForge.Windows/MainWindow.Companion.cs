using System.Runtime.InteropServices;
using RtxForge.Windows.Models;
using RtxForge.Windows.Services;

namespace RtxForge.Windows;

public sealed partial class MainWindow
{
    public string? CompanionShortcutProblem { get; private set; }

    void InitializeCompanion()
    {
        if (!Service.IsPreview) ConfigureCompanionShortcut();
    }

    public async void OpenCompanion(Game? game = null)
    {
        if (Service.IsPreview) { ShowToast("Live controls require the installed engine."); return; }
        if (Settings.OverlayRenderer == "game") { ShowToast("Press " + Settings.PanelHotkey + " inside a game with the in-game renderer package."); return; }
        try { await OverlayHelper.CommandAsync("show"); }
        catch (Exception error) { ShowToast(error.Message); }
    }

    public async void ConfigureCompanionShortcut()
    {
        if (Service.IsPreview) return;
        try
        {
            OverlayHelper.ConfigureStartup(Settings);
            CompanionShortcutProblem = await OverlayHelper.CommandAsync(Settings.OverlayHelper ? "reload" : "exit", Settings.OverlayHelper);
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or System.ComponentModel.Win32Exception)
        { CompanionShortcutProblem = error.Message; ShowToast("Overlay helper: " + error.Message); }
    }
    internal static uint ForegroundProcessId()
    {
        GetWindowThreadProcessId(GetForegroundWindow(), out var pid);
        return pid;
    }
    [DllImport("user32.dll")]
    static extern nint GetForegroundWindow();
    [DllImport("user32.dll")]
    static extern uint GetWindowThreadProcessId(nint hwnd, out uint pid);
}
