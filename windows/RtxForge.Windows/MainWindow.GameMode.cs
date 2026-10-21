using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using RtxForge.Windows.GameMode;

namespace RtxForge.Windows;

/// <summary>
/// Game Mode hosting (Linux set_input_surface / set_big_picture_ui): a
/// full-screen GameModeView over the desktop shell. Entered from the Game
/// Mode navigation item, `--game-mode`, or controller input when
/// Settings › Interface is Big Picture UI; left through Desktop UI.
/// </summary>
public sealed partial class MainWindow
{
    GameModeView? gameMode;
    GamepadInput? gamepad;

    public bool InGameMode => gameMode is not null;

    void InitializeGameMode()
    {
        gamepad = new GamepadInput(DispatcherQueue, WinRT.Interop.WindowNative.GetWindowHandle(this),
            () => ForegroundProcessId() == Environment.ProcessId);
        gamepad.Action += OnGamepadAction;
        gamepad.Changed += () => gameMode?.SetControllerFamily(gamepad.Family);
        gamepad.Activity += () => gameMode?.ControllerActivity();
        Closed += (_, _) => gamepad?.Dispose();
        if (Environment.GetCommandLineArgs().Contains("--game-mode", StringComparer.OrdinalIgnoreCase)
            || !string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable("SteamAppId")))
            DispatcherQueue.TryEnqueue(EnterGameMode);
    }

    internal bool ControllerLegacyInputActive => gamepad?.LegacyInputActive == true;

    void OnGamepadAction(string action)
    {
        if (gameMode is not null) { gameMode.Handle(action, fromController: true); return; }
        // Desktop with Big Picture UI chosen: a controller press opens Game Mode (Linux poll_controller).
        if (Settings.BigPictureUi && AppWindow.IsVisible) { EnterGameMode(); gameMode?.ControllerActivity(); }
    }

    public void EnterGameMode()
    {
        if (gameMode is not null) return;
        gameMode = new GameModeView(this);
        gameMode.ExitRequested += ExitGameMode;
        if (gamepad is not null) gameMode.SetControllerFamily(gamepad.Family);
        GameModeHost.Children.Add(gameMode);
        GameModeHost.Visibility = Visibility.Visible;
        // The desktop title bar region would otherwise catch clicks over the Game Mode header.
        SetTitleBar(null);
        AppWindow.SetPresenter(AppWindowPresenterKind.FullScreen);
    }

    public void ExitGameMode()
    {
        if (gameMode is null) return;
        GameModeHost.Children.Clear();
        GameModeHost.Visibility = Visibility.Collapsed;
        gameMode = null;
        AppWindow.SetPresenter(AppWindowPresenterKind.Overlapped);
        SetTitleBar(AppTitleBar);
        GamesChanged?.Invoke();
    }

    void OnNavItemInvoked(NavigationView sender, NavigationViewItemInvokedEventArgs args)
    {
        if (args.InvokedItemContainer?.Tag as string == "GameMode") EnterGameMode();
    }
}
