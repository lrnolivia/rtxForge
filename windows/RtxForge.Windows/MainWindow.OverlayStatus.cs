using System.Text.Json.Nodes;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using RtxForge.Windows.Controls;
using RtxForge.Windows.Models;
using RtxForge.Windows.Services;

namespace RtxForge.Windows;

public sealed partial class MainWindow
{
    // Overlay Status uses the Review screen's rows, grouped so what needs you comes first.
    static readonly (string Status, string Heading, string Badge, bool Good)[] OverlayStatusGroups =
    [
        ("needs-attention", "Needs attention", "Needs attention", false),
        ("update-available", "Update available", "Update", false),
        ("unknown", "Version not verified", "Not verified", false),
        ("unavailable", "Game folder unavailable", "Folder missing", false),
        ("current", "Current", "Current", true),
    ];

    public async Task ShowOverlayStatusAsync()
    {
        if (Service is not EngineForgeService engine) return;
        var dialog = NewDialog();
        dialog.Title = "Overlay Status"; dialog.CloseButtonText = "Close";
        dialog.PrimaryButtonText = "Update all"; dialog.DefaultButton = ContentDialogButton.Close;
        dialog.IsPrimaryButtonEnabled = false;
        var body = new StackPanel { Spacing = 12, MinWidth = 320, MaxWidth = 820 };
        var summary = Prefs.Label("Checking installed overlays…");
        var notice = Prefs.Label("", "ForgeCaptionDimTextStyle"); notice.Visibility = Visibility.Collapsed;
        var list = new StackPanel { Spacing = 4 };
        body.Children.Add(summary); body.Children.Add(notice);
        body.Children.Add(new ScrollViewer { Content = list, MaxHeight = 460, HorizontalScrollMode = ScrollMode.Disabled });
        dialog.Content = body;
        var shown = dialog.ShowAsync();
        try
        {
            var status = await engine.OverlayStatusAsync();
            var games = (status["games"] as JsonArray ?? []).OfType<JsonObject>().ToArray();
            foreach (var (key, heading, badge, good) in OverlayStatusGroups)
            {
                var group = games.Where(game => (game["status"]?.ToString() is var s && OverlayStatusGroups.Any(g => g.Status == s) ? s : "unknown") == key).ToArray();
                if (group.Length == 0) continue;
                var header = Prefs.Label($"{heading} · {group.Length}", "ForgeHeadingTextStyle");
                header.Margin = new Thickness(0, list.Children.Count == 0 ? 0 : 10, 0, 2);
                list.Children.Add(header);
                foreach (var game in group)
                    list.Children.Add(ReviewDialog.Entry(this, new ReviewItem(game["name"]?.ToString() ?? "Unnamed game",
                        OverlayStatusDetail(game), badge, game["game"]?.ToString(),
                        game["detail"]?.ToString() is { Length: > 0 } detail ? detail : null), good));
            }
            var current = games.Count(game => game["status"]?.ToString() == "current");
            summary.Text = games.Length == 0 ? "No managed game overlays are installed."
                : $"{games.Length} game overlays · {current} current";
            var warnings = (status["warnings"] as JsonArray ?? []).Select(value => value?.ToString()).Where(value => !string.IsNullOrWhiteSpace(value));
            notice.Text = string.Join("\n", warnings); notice.Visibility = string.IsNullOrEmpty(notice.Text) ? Visibility.Collapsed : Visibility.Visible;
            dialog.IsPrimaryButtonEnabled = games.Length > 0 && !engine.IsPreview && !Busy;
        }
        catch (Exception error) { summary.Text = "Overlay Status could not be read."; notice.Text = error.Message; notice.Visibility = Visibility.Visible; }
        if (await shown != ContentDialogResult.Primary) return;
        var completed = await OperationDialog.ShowPreparedAsync(this, "update-overlays", progress => engine.ReviewOverlayPackagesAsync(progress));
        if (completed) await ShowOverlayStatusAsync();
    }

    static string OverlayStatusDetail(JsonObject game)
    {
        var installed = game["installedVersion"]?.ToString();
        var current = game["currentVersion"]?.ToString();
        var version = installed is null ? "Version not recorded"
            : current is null || current == installed ? installed : $"{installed} → {current}";
        var updated = DateTimeOffset.TryParse(game["lastUpdated"]?.ToString(), out var date) ? "updated " + date.ToLocalTime().ToString("d") : "update date not recorded";
        return version + " · " + updated;
    }
}
