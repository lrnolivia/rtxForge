using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using RtxForge.Windows.Models;
using RtxForge.Windows.Services;

namespace RtxForge.Windows.Controls;

/// <summary>Lazy storage accounting; cleanup uses the normal one-shot review flow.</summary>
public sealed class AppStorageView : StackPanel
{
    readonly MainWindow shell;
    readonly EngineForgeService service;
    bool loading;

    public AppStorageView(MainWindow shell, EngineForgeService service)
    {
        this.shell = shell;
        this.service = service;
        Spacing = 4;
        Children.Add(Prefs.Row("App data", "Checking storage…"));
        Loaded += async (_, _) => await RefreshAsync();
    }

    async Task RefreshAsync()
    {
        if (loading) return;
        loading = true;
        try
        {
            var data = await service.AppStorageAsync();
            Children.Clear();
            Children.Add(Prefs.Row("App data · " + AppStorage.Format(data.Bytes), data.Warning ?? "Storage used by rtxForge on this PC.",
                Prefs.ActionButton("View usage", async (_, _) => await ShowUsageAsync(data)), ""));
            var clear = Prefs.ActionButton("Review cleanup", async (_, _) =>
            {
                await ReviewDialog.ShowAsync(shell, "Clear unused downloads", service.ReviewStorageCleanupAsync);
                await RefreshAsync();
            });
            clear.IsEnabled = data.Warning is null && data.DownloadBytes > 0;
            Children.Add(Prefs.Row("Downloads · " + AppStorage.Format(data.DownloadBytes),
                "Clear unused package and DLSS downloads. Future installs may need to download them again.", clear, ""));
            Children.Add(Prefs.Row("Restore data stays protected", "Game originals, Feeder restore files, recovery snapshots and settings are kept. Files referenced by saved records are also kept.", glyph: ""));
        }
        catch (Exception error) when (error is InvalidOperationException or IOException or UnauthorizedAccessException)
        {
            Children.Clear();
            Children.Add(Prefs.Row("Could not check storage", error.Message,
                Prefs.ActionButton("Retry", async (_, _) => await RefreshAsync())));
        }
        finally { loading = false; }
    }

    async Task ShowUsageAsync(AppStorage data)
    {
        var rows = new StackPanel { Spacing = 4 };
        foreach (var item in data.Categories.Where(c => c.Bytes > 0))
            rows.Children.Add(Prefs.Row(item.Title, item.Detail, Prefs.Label(AppStorage.Format(item.Bytes))));
        var dialog = shell.NewDialog();
        dialog.Title = "App storage · " + AppStorage.Format(data.Bytes);
        dialog.CloseButtonText = "Close";
        dialog.Content = new ScrollViewer { Content = rows, MaxHeight = 520, HorizontalScrollMode = ScrollMode.Disabled };
        await dialog.ShowAsync();
    }
}
