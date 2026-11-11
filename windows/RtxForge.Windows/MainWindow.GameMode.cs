using System.Diagnostics;
using System.Text.Json.Serialization;
using RtxForge.Windows.Services;
using RtxForge.Windows.Models;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using RtxForge.Windows.GameMode;

namespace RtxForge.Windows;

/// <summary>
/// Native Game Mode process handoff. Desktop keeps its existing window and
/// engine session, and resumes them when Game Mode closes.
/// </summary>
public sealed partial class MainWindow
{
    GamepadInput? gamepad;
    Process? nativeGameMode;
    bool openingGameMode;
    bool nativeModeRequested;
    bool waitingForGameMode;

    public bool InGameMode => nativeGameMode is not null || openingGameMode;

    void InitializeGameMode()
    {
        gamepad = new GamepadInput(DispatcherQueue, WinRT.Interop.WindowNative.GetWindowHandle(this),
            () => ForegroundProcessId() == Environment.ProcessId);
        gamepad.Action += OnGamepadAction;
        Closed += (_, _) => gamepad?.Dispose();
        if (!Environment.GetCommandLineArgs().Contains("--desktop-mode", StringComparer.OrdinalIgnoreCase) &&
            (Environment.GetCommandLineArgs().Contains("--game-mode", StringComparer.OrdinalIgnoreCase)
            || !string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable("SteamAppId"))))
        {
            QueueNativeGameMode();
        }
    }

    internal bool ControllerLegacyInputActive => gamepad?.LegacyInputActive == true;
    internal bool ControllerPollingAvailable => gamepad?.PollingAvailable == true;
    internal bool ControllerInputForeground => ForegroundProcessId() == Environment.ProcessId;
    internal void NativeRightStick(bool up, bool pressed) => gamepad?.NativeRightStick(up, pressed);

    void OnGamepadAction(string action)
    {
        if (nativeGameMode is not null || openingGameMode) return;
        // Desktop with Big Picture UI chosen: a controller press opens Game Mode (Linux poll_controller).
        if (Settings.BigPictureUi && AppWindow.IsVisible) { EnterGameMode(); }
    }

    public void EnterGameMode() => OpenNativeGameMode(false);
    public void OpenGameModeAppearance() => OpenNativeGameMode(true);

    internal async Task OpenGameModePreview(string view)
    {
        try
        {
            var executable = GameModeLauncher.Resolve(AppContext.BaseDirectory, Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData));
            using var preview = await Task.Run(() => GameModeLauncher.Start(executable, readOnly: true, preview: view));
        }
        catch (Exception error) when (error is IOException or InvalidOperationException or System.ComponentModel.Win32Exception or System.Text.Json.JsonException or UnauthorizedAccessException or KeyNotFoundException or ArgumentException)
        { await Message("Game Mode preview could not open", error.Message); }
    }

    void QueueNativeGameMode()
    {
        nativeModeRequested = true;
        if (waitingForGameMode || InGameMode) return;
        waitingForGameMode = true;
        DispatcherQueue.TryEnqueue(async () =>
        {
            try
            {
                while (Busy && nativeModeRequested) await Task.Delay(150);
                if (nativeModeRequested) EnterGameMode();
            }
            finally { waitingForGameMode = false; }
        });
    }

    async void OpenNativeGameMode(bool appearance)
    {
        nativeModeRequested = true;
        if (InGameMode) return;
        if (Busy) { await Message("Finish the current change", "Wait for the reviewed operation to finish before switching interfaces."); return; }
        openingGameMode = true;
        try
        {
            var executable = GameModeLauncher.Resolve(AppContext.BaseDirectory, Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData));
            var readOnly = Environment.GetCommandLineArgs().Any(value => value is "--preview" or "--library-preview");
            nativeGameMode = await Task.Run(() => GameModeLauncher.Start(executable, readOnly, appearance));
            if (nativeModeRequested) AppWindow.Hide();
            else nativeGameMode.CloseMainWindow();
            await nativeGameMode.WaitForExitAsync();
            var code = nativeGameMode.ExitCode;
            nativeGameMode.Dispose(); nativeGameMode = null;
            RestoreDesktop();
            if (code != 0) await Message("Game Mode closed", $"Game Mode stopped with exit {code}. Your Desktop session is still available.");
        }
        catch (Exception error) when (error is IOException or InvalidOperationException or System.ComponentModel.Win32Exception or System.Text.Json.JsonException or UnauthorizedAccessException or KeyNotFoundException or ArgumentException)
        { RestoreDesktop(); await Message("Game Mode could not open", error.Message); }
        finally { openingGameMode = false; }
    }

    void RestoreDesktop()
    {
        var saved = ForgeSettings.Load();
        foreach (var property in typeof(ForgeSettings).GetProperties())
            if (property.CanWrite && Attribute.IsDefined(property, typeof(JsonPropertyNameAttribute))) property.SetValue(Settings, property.GetValue(saved));
        ThemeController.Apply(this, RootGrid, Settings.Theme);
        ApplyAppAccent();
        AppWindow.Show(); Activate(); SettingsChanged?.Invoke();
        _ = ScanAsync();
    }

    internal void ActivateDesktop(bool gaming)
    {
        nativeModeRequested = gaming;
        if (gaming) { if (nativeGameMode is not null) { NativeFocusGameMode(); return; } QueueNativeGameMode(); }
        else { if (nativeGameMode is not null) nativeGameMode.CloseMainWindow(); else { AppWindow.Show(); Activate(); } }
    }

    void NativeFocusGameMode()
    {
        if (nativeGameMode is not null && !nativeGameMode.HasExited)
        {
            var info = new ProcessStartInfo(nativeGameMode.MainModule!.FileName!) { UseShellExecute=false };
            info.ArgumentList.Add("--desktop-parent"); info.ArgumentList.Add(Environment.ProcessId.ToString());
            using var activation = Process.Start(info);
        }
    }

    public void ExitGameMode()
    {
        nativeModeRequested = false;
        if (nativeGameMode is not null) nativeGameMode.CloseMainWindow();
    }
    void OnNavItemInvoked(NavigationView sender, NavigationViewItemInvokedEventArgs args)
    {
        if (args.InvokedItemContainer?.Tag as string == "GameMode") EnterGameMode();
    }

}
