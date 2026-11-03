using System.Text.Json.Nodes;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Markup;
using RtxForge.Windows.Controls;
using RtxForge.Windows.Services;

namespace RtxForge.Windows;

public sealed record OverlayStatusEntry(string Name, string Versions, string Status, string Updated, string Detail);

public sealed partial class MainWindow
{
    public async Task ShowOverlayStatusAsync()
    {
        if (Service is not EngineForgeService engine) return;
        var dialog = NewDialog();
        dialog.Title = "Overlay Status"; dialog.CloseButtonText = "Close";
        dialog.PrimaryButtonText = "Update all"; dialog.DefaultButton = ContentDialogButton.Close;
        dialog.IsPrimaryButtonEnabled = false;
        var body = new StackPanel { Spacing = 16, MinWidth = 320, MaxWidth = 820 };
        var summary = Prefs.Label("Checking installed overlays…");
        var notice = Prefs.Label("", "ForgeCaptionDimTextStyle"); notice.Visibility = Visibility.Collapsed;
        var list = new ListView { SelectionMode = ListViewSelectionMode.None, MaxHeight = 460,
            IsItemClickEnabled = false, HorizontalContentAlignment = HorizontalAlignment.Stretch };
        list.ItemTemplate = (DataTemplate)XamlReader.Load("""
            <DataTemplate xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation">
              <StackPanel Spacing="4" Margin="0,8,0,12">
                <TextBlock Text="{Binding Name}" FontWeight="SemiBold" TextWrapping="Wrap" />
                <TextBlock Text="{Binding Status}" TextWrapping="Wrap" />
                <TextBlock Text="{Binding Versions}" FontSize="12" Opacity="0.8" TextWrapping="Wrap" />
                <TextBlock Text="{Binding Updated}" FontSize="12" Opacity="0.8" TextWrapping="Wrap" />
                <TextBlock Text="{Binding Detail}" FontSize="12" TextWrapping="Wrap" />
              </StackPanel>
            </DataTemplate>
            """);
        body.Children.Add(summary); body.Children.Add(notice); body.Children.Add(list); dialog.Content = body;
        var shown = dialog.ShowAsync();
        try
        {
            var status = await engine.OverlayStatusAsync();
            var games = (status["games"] as JsonArray ?? []).OfType<JsonObject>().ToArray();
            var entries = games.Select(game => new OverlayStatusEntry(
                game["name"]?.ToString() ?? "Unnamed game",
                "Installed: " + (game["installedVersion"]?.ToString() ?? "Not recorded") + " · Current: " + (game["currentVersion"]?.ToString() ?? "Not available"),
                game["status"]?.ToString() switch { "current" => "Current", "update-available" => "Update available",
                    "needs-attention" => "Needs attention", "unavailable" => "Game folder unavailable", _ => "Version not verified" },
                "Last updated: " + (DateTimeOffset.TryParse(game["lastUpdated"]?.ToString(), out var date) ? date.ToLocalTime().ToString("g") : "Not recorded"),
                game["detail"]?.ToString() ?? "")).ToArray();
            list.ItemsSource = entries;
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
}
