using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using RtxForge.Windows.Models;
using RtxForge.Windows.Views;

namespace RtxForge.Windows;

public sealed partial class MainWindow
{
    readonly Dictionary<string, (Window Window, Frame Frame)> gameWindows = [];
    FrameworkElement? detailsDialogRoot;
    bool gameWindowsInitialized;

    void OpenGameWindow(Game game, string section)
    {
        if (gameWindows.TryGetValue(game.Id, out var existing))
        {
            if (existing.Frame.Content is GamePage page) page.SelectSection(section);
            existing.Window.Activate(); return;
        }
        var frame = new Frame();
        var window = new Window { Title = game.Name + " · rtxForge", Content = frame, SystemBackdrop = new MicaBackdrop() };
        frame.RequestedTheme = Settings.Theme == "light" ? ElementTheme.Light
            : Settings.Theme is "dark" or "night" ? ElementTheme.Dark : ElementTheme.Default;
        frame.Navigate(typeof(GamePage), new GameRequest(game, section, SeparateWindow: true));
        gameWindows[game.Id] = (window, frame);
        window.Activated += (_, e) =>
        {
            if (e.WindowActivationState != WindowActivationState.Deactivated) detailsDialogRoot = frame;
            else if (ReferenceEquals(detailsDialogRoot, frame)) detailsDialogRoot = null;
        };
        window.Closed += (_, _) =>
        {
            gameWindows.Remove(game.Id);
            if (ReferenceEquals(detailsDialogRoot, frame)) detailsDialogRoot = null;
            frame.Content = null;
        };
        if (!gameWindowsInitialized)
        {
            gameWindowsInitialized = true;
            Closed += (_, _) => { foreach (var child in gameWindows.Values.ToArray()) child.Window.Close(); };
        }
        var display = Microsoft.UI.Windowing.DisplayArea.GetFromWindowId(AppWindow.Id, Microsoft.UI.Windowing.DisplayAreaFallback.Primary);
        var work = display.WorkArea;
        var width = Math.Min(1500, work.Width - 80); var height = Math.Min(1100, work.Height - 80);
        window.AppWindow.MoveAndResize(new global::Windows.Graphics.RectInt32(
            work.X + (work.Width - width) / 2, work.Y + (work.Height - height) / 2, width, height));
        window.Activate();
    }
}
