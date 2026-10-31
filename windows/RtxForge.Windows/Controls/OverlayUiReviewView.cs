using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using RtxForge.Windows.Services;

namespace RtxForge.Windows.Controls;

/// <summary>Entry point to the same reviewed operation flow as Install Features.</summary>
public sealed class OverlayUiReviewView : StackPanel
{
    readonly EngineForgeService service;
    readonly Button action;
    readonly TextBlock status = new() { TextWrapping = TextWrapping.Wrap, FontSize = 12, Visibility = Visibility.Collapsed };
    bool busy;

    public OverlayUiReviewView(EngineForgeService engine, bool packages = false, bool settingsRows = false)
    {
        service = engine;
        action = Prefs.ActionButton("Update Overlays", async (_, _) => await Run());
        Spacing = 12;
        const string description = "Review overlay packages, menus, welcome messages and shortcuts for each installed game. Your tuning and original backups are kept.";
        if (settingsRows)
        {
            Children.Add(Prefs.Row("Update overlays", description, action, glyph: "\uE9D9", detail: status));
        }
        else
        {
            if (!packages) Children.Add(Prefs.Label(description, "ForgeCaptionDimTextStyle"));
            Children.Add(status);
            Children.Add(action);
        }
        status.RegisterPropertyChangedCallback(TextBlock.TextProperty, (_, _) =>
            status.Visibility = string.IsNullOrEmpty(status.Text) ? Visibility.Collapsed : Visibility.Visible);
    }

    public void Invalidate() => status.Text = "";

    async Task Run()
    {
        if (busy || App.Main is not { } shell) return;
        busy = true;
        action.IsEnabled = false;
        try
        {
            var completed = await OperationDialog.ShowPreparedAsync(shell, "update-overlays",
                progress => service.ReviewOverlayPackagesAsync(progress));
            if (completed) status.Text = "Updated. Restart the affected games to use these choices.";
        }
        catch (Exception error) { status.Text = error.Message; }
        finally { busy = false; action.IsEnabled = true; }
    }
}
