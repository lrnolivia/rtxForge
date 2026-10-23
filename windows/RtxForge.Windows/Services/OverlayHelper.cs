using System.Diagnostics;
using System.IO.Pipes;
using System.Runtime.InteropServices;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.Win32;
using RtxForge.Windows.Models;
using RtxForge.Windows.Views;

namespace RtxForge.Windows.Services;

/// <summary>A per-session helper; no manager window, artwork or library scan.</summary>
public static class OverlayHelper
{
    internal static string PipeName => "rtxForge.Overlay." + Process.GetCurrentProcess().SessionId;
    public static string StartupCommand(string executable) => $"\"{executable}\" --overlay-helper";

    public static async Task CacheGameIdentitiesAsync(IEnumerable<Game> games)
    {
        try
        {
            using var identities = Registry.CurrentUser.CreateSubKey(@"Software\rtxForge\Overlay\Games");
            foreach (var game in games.Where(g => g.EngineRow?["exe"] is not null))
            {
                var relative = game.EngineRow!["exe"]!.ToString();
                var exe = Path.GetFullPath(Path.Combine(game.Location, relative));
                if (!File.Exists(exe)) continue;
                var palette = await OverlayAccent.ForGameAsync(game);
                var color = palette.Color;
                identities.SetValue(exe, $"#{color.R:X2}{color.G:X2}{color.B:X2}|{game.Name}", RegistryValueKind.String);
            }
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or ArgumentException or System.Runtime.InteropServices.COMException) { }
    }

    public static void ConfigureStartup(ForgeSettings settings)
    {
        // Read once by bridge 8 at game startup. Never rewrite a game's INI,
        // switch its swapchain hooks, or poll the registry on the render thread.
        using (var overlay = Registry.CurrentUser.CreateSubKey(@"Software\rtxForge\Overlay"))
        {
            overlay.SetValue("UseOptiScaler", settings.OptiScalerUi ? 1 : 0, RegistryValueKind.DWord);
            overlay.SetValue("ShortcutKey", settings.OptiScalerHotkey == "F8" ? 0x77 : settings.OptiScalerHotkey == "Disabled" ? 0 : 0x2D, RegistryValueKind.DWord);
        }
        ConfigurePanel(settings);
        using var key = Registry.CurrentUser.CreateSubKey(@"Software\Microsoft\Windows\CurrentVersion\Run");
        if (settings.OverlayHelper && settings.OverlayStartWithWindows && settings.OverlayRenderer != "optiscaler")
            key.SetValue("rtxForge Overlay", StartupCommand(Environment.ProcessPath!), RegistryValueKind.String);
        else key.DeleteValue("rtxForge Overlay", throwOnMissingValue: false);
    }

    // The helper can start without the manager. Publish only our panel's
    // next-launch preferences; leave other menus and Windows startup alone.
    internal static void ConfigurePanel(ForgeSettings settings)
    {
        using var overlay = Registry.CurrentUser.CreateSubKey(@"Software\rtxForge\Overlay");
        var valid = OverlayShortcut.TryParse(settings.PanelHotkey, out _, out var binding, out _);
        overlay.SetValue("PanelKey", valid ? (int)binding.Key : 0, RegistryValueKind.DWord);
        overlay.SetValue("PanelModifiers", valid ? (int)binding.Modifiers : 0, RegistryValueKind.DWord);
        overlay.SetValue("Advanced", settings.OverlayControls == "classic" ? 1 : 0, RegistryValueKind.DWord);
        overlay.SetValue("ShowLiveStats", settings.OverlayLiveStats ? 1 : 0, RegistryValueKind.DWord);
        overlay.SetValue("InGamePanel", settings.OverlayRenderer == "game" ? 1 : 0, RegistryValueKind.DWord);
    }

    public static async Task<string?> CommandAsync(string command, bool start = true)
    {
        bool launched = false;
        for (int attempt = 0; attempt < 5; attempt++)
        {
            try
            {
                using var pipe = new NamedPipeClientStream(".", PipeName, PipeDirection.InOut, PipeOptions.Asynchronous | PipeOptions.CurrentUserOnly);
                await pipe.ConnectAsync(500);
                using var writer = new StreamWriter(pipe, leaveOpen: true) { AutoFlush = true };
                using var reader = new StreamReader(pipe, leaveOpen: true);
                await writer.WriteLineAsync(command);
                return await reader.ReadLineAsync().WaitAsync(TimeSpan.FromSeconds(5));
            }
            catch (Exception error) when (error is TimeoutException or IOException)
            {
                if (!start) return null;
                if (!launched)
                {
                    var info = new ProcessStartInfo(Environment.ProcessPath!) { UseShellExecute = false, CreateNoWindow = true };
                    info.ArgumentList.Add("--overlay-helper");
                    Process.Start(info);
                    launched = true;
                }
                await Task.Delay(250);
            }
        }
        throw new IOException("The overlay helper didn't respond. Try starting it again in Settings → Overlay.");
    }
}

public sealed class OverlayHelperWindow : Window
{
    readonly Mutex instance;
    readonly CancellationTokenSource stopping = new();
    readonly Subclass callback;
    readonly nint handle;
    EngineForgeService? engine;
    NativePanelCoordinator? nativePanel;
    string? problem;
    bool closing, trayAdded;
    const uint TrayMessage = 0x8001;

    public OverlayHelperWindow(Mutex ownership)
    {
        instance = ownership;
        Title = "rtxForge Overlay helper";
        Content = new Grid();
        AppWindow.IsShownInSwitchers = false;
        handle = WinRT.Interop.WindowNative.GetWindowHandle(this);
        callback = WindowProc;
        SetWindowSubclass(handle, callback, 0x5255, 0);
        AppWindow.Hide();
        ConfigureShortcut();
        Closed += (_, _) => Cleanup();
        AppWindow.Closing += (_, e) => { if (nativePanel?.Applying == true) e.Cancel = true; };
        _ = ListenAsync();
        _ = StartEngineAsync();
    }

    async Task StartEngineAsync()
    {
        try
        {
            var result = await EngineForgeService.TryStartAsync("overlay-engine.log");
            if (closing) { result.Service?.Dispose(); return; }
            engine = result.Service;
            if (engine is null) { problem = result.Problem ?? "The overlay engine couldn't start."; return; }
            nativePanel = new NativePanelCoordinator(engine, DispatcherQueue, ConfigureShortcut, Close);
        }
        catch (Exception error) { problem = error.Message; }
    }

    // The panel lives in the game (OptiScaler or ReShade); the game reads its
    // shortcut from the registry, so the helper registers no desktop hotkey.
    void ConfigureShortcut()
    {
        var settings = ForgeSettings.Load();
        if (settings.PanelHotkeyMigrated) settings = ForgeSettings.EditOverlay(s => s.PanelHotkey = s.PanelHotkey);
        OverlayHelper.ConfigurePanel(settings);
        Tray(true);
        engine?.Settings.CopyOverlayFrom(settings);
        problem = OverlayShortcut.TryParse(settings.PanelHotkey, out _, out _, out var error) ? null : error;
    }

    static void OpenSettings() =>
        Process.Start(new ProcessStartInfo(Environment.ProcessPath!, "--overlay-settings") { UseShellExecute = false });

    async Task ListenAsync()
    {
        while (!stopping.IsCancellationRequested)
        {
            try
            {
                using var pipe = new NamedPipeServerStream(OverlayHelper.PipeName, PipeDirection.InOut, 1,
                    PipeTransmissionMode.Byte, PipeOptions.Asynchronous | PipeOptions.CurrentUserOnly);
                await pipe.WaitForConnectionAsync(stopping.Token);
                using var reader = new StreamReader(pipe, leaveOpen: true);
                using var writer = new StreamWriter(pipe, leaveOpen: true) { AutoFlush = true };
                var command = await reader.ReadLineAsync(stopping.Token).AsTask().WaitAsync(TimeSpan.FromSeconds(3));
                if (command == "reload") ConfigureShortcut();
                else if (command == "reload-presets" && engine is not null) await engine.ReloadCompanionPresetsAsync();
                else if (command == "refresh-targets" && nativePanel is not null) await nativePanel.ReloadTargetsAsync();
                if (command == "exit" && nativePanel?.Applying == true)
                { await writer.WriteLineAsync("Game settings are still being applied. Wait for them to finish."); continue; }
                await writer.WriteLineAsync(problem ?? "");
                if (command == "exit") { Close(); return; }
            }
            catch (OperationCanceledException) { return; }
            catch (Exception error) when (error is IOException or TimeoutException) { }
        }
    }

    nint WindowProc(nint hwnd, uint message, nuint wParam, nint lParam, nuint id, nuint data)
    {
        if (message == TrayMessage)
        {
            var action = (uint)lParam & 0xffff;
            if (action == 0x0202) OpenSettings();
            else if (action == 0x0205) ShowTrayMenu();
            return 0;
        }
        return DefSubclassProc(hwnd, message, wParam, lParam);
    }

    void ShowTrayMenu()
    {
        var menu = CreatePopupMenu();
        try
        {
            AppendMenuW(menu, 0, 2, "Overlay settings");
            AppendMenuW(menu, 0x800, 0, "");
            AppendMenuW(menu, 0, 3, "Exit overlay helper");
            GetCursorPos(out var point);
            SetForegroundWindow(handle);
            var selected = TrackPopupMenu(menu, 0x100, point.X, point.Y, 0, handle, 0);
            if (selected == 2) OpenSettings();
            if (selected == 3) Close();
        }
        finally { DestroyMenu(menu); }
    }

    void Tray(bool add)
    {
        var icon = LoadImageW(0, Path.Combine(AppContext.BaseDirectory, "Assets", "rtxforge.ico"), 1, 16, 16, 0x10);
        var value = new NotifyIcon { Size = Marshal.SizeOf<NotifyIcon>(), Window = handle, Id = 1, Flags = 7,
            Callback = TrayMessage, Icon = icon, Tip = "rtxForge Overlay · " + ForgeSettings.Load().PanelHotkey,
            Info = "", InfoTitle = "" };
        Shell_NotifyIconW(add ? (trayAdded ? 1u : 0u) : 2u, ref value);
        trayAdded = add;
        if (icon != 0) DestroyIcon(icon);
    }

    void Cleanup()
    {
        if (closing) return;
        closing = true; stopping.Cancel(); Tray(false);
        RemoveWindowSubclass(handle, callback, 0x5255);
        nativePanel?.Dispose(); engine?.Dispose();
        instance.ReleaseMutex(); instance.Dispose();
    }

    [StructLayout(LayoutKind.Sequential)] struct Point { public int X, Y; }
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)] struct NotifyIcon
    {
        public int Size; public nint Window; public uint Id, Flags, Callback; public nint Icon;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)] public string Tip;
        public uint State, StateMask;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 256)] public string Info;
        public uint Timeout;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 64)] public string InfoTitle;
        public uint InfoFlags; public Guid Guid; public nint BalloonIcon;
    }
    [UnmanagedFunctionPointer(CallingConvention.Winapi)] delegate nint Subclass(nint hwnd, uint message, nuint wParam, nint lParam, nuint id, nuint data);
    [DllImport("comctl32.dll")] static extern bool SetWindowSubclass(nint hwnd, Subclass proc, nuint id, nuint data);
    [DllImport("comctl32.dll")] static extern bool RemoveWindowSubclass(nint hwnd, Subclass proc, nuint id);
    [DllImport("comctl32.dll")] static extern nint DefSubclassProc(nint hwnd, uint message, nuint wParam, nint lParam);
    [DllImport("shell32.dll", CharSet = CharSet.Unicode)] static extern bool Shell_NotifyIconW(uint message, ref NotifyIcon value);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern nint LoadImageW(nint instance, string name, uint type, int width, int height, uint flags);
    [DllImport("user32.dll")] static extern bool DestroyIcon(nint icon);
    [DllImport("user32.dll")] static extern nint CreatePopupMenu();
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern bool AppendMenuW(nint menu, uint flags, nuint id, string text);
    [DllImport("user32.dll")] static extern uint TrackPopupMenu(nint menu, uint flags, int x, int y, int reserved, nint hwnd, nint rect);
    [DllImport("user32.dll")] static extern bool DestroyMenu(nint menu);
    [DllImport("user32.dll")] static extern bool GetCursorPos(out Point point);
    [DllImport("user32.dll")] static extern bool SetForegroundWindow(nint hwnd);
}
