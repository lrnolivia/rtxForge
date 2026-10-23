using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using RtxForge.Windows.Controls;
using RtxForge.Windows.Models;
using RtxForge.Windows.Services;

namespace RtxForge.Windows;

public sealed partial class MainWindow
{
    /// <summary>Restore skips setups another tool made; adopting them is a choice in each game's Details.</summary>
    public static string AdoptionSkipped(int count) =>
        $"Skipped {count} game{(count == 1 ? "" : "s")} set up by another tool. Adopt from Game Details to manage or restore {(count == 1 ? "it" : "them")} with rtxForge.";

    public async Task ReviewAdoptionAsync(IReadOnlyList<Game> candidates)
    {
        if (Busy || candidates.Count == 0) return;
        var dialog = NewDialog();
        dialog.Title = "Adoption";
        dialog.Resources["ContentDialogMaxWidth"] = 680.0;
        var body = new StackPanel { Spacing = 16, MinWidth = 480 };
        body.Children.Add(Prefs.Label("Found feature packages outside rtxForge’s management. Choose the games to review."));
        var list = new StackPanel { Spacing = 8 };
        var selections = new List<(Game Game, CheckBox Check)>();
        foreach (var game in candidates)
        {
            var check = new CheckBox { Content = game.Name, IsChecked = true };
            selections.Add((game, check)); list.Children.Add(check);
            if (game.EngineRow?["offline_available"]?.GetValue<bool>() == true)
                list.Children.Add(Prefs.Label("Offline only · reviewed launch route available", "ForgeCaptionDimTextStyle"));
        }
        body.Children.Add(new ScrollViewer { Content = list, MaxHeight = 220 });
        var keep = new RadioButton { Content = "Adopt existing setup", GroupName = "AdoptionAction", IsChecked = true };
        var clean = new RadioButton { Content = "Back up and clean install", GroupName = "AdoptionAction" };
        body.Children.Add(keep);
        body.Children.Add(Prefs.Label("Keep current files and settings, when rtxForge recognizes the package. Enable management in rtxForge.", "ForgeCaptionDimTextStyle"));
        body.Children.Add(clean);
        body.Children.Add(Prefs.Label("Works with any setup found: install the newest version of the package chosen in Packages, with fresh settings. Restore can return to today’s setup.", "ForgeCaptionDimTextStyle"));
        var startup = new CheckBox { Content = "Enable NR on launch", IsChecked = Settings.NrOnLaunch, IsEnabled = false };
        clean.Checked += (_, _) => startup.IsEnabled = true;
        keep.Checked += (_, _) => startup.IsEnabled = false;
        body.Children.Add(startup);
        body.Children.Add(Prefs.Label("Next: review the verified package, files and any offline-only exception. Nothing changes yet.", "ForgeCaptionDimTextStyle"));
        dialog.Content = body;
        dialog.PrimaryButtonText = "Review Adoption"; dialog.CloseButtonText = "Not now";
        if (await dialog.ShowAsync() != ContentDialogResult.Primary) return;
        var targets = selections.Where(x => x.Check.IsChecked == true).Select(x => x.Game).ToArray();
        if (targets.Length == 0) return;
        await LaunchAction(clean.IsChecked == true ? "adopt-clean" : "adopt", targets,
            Settings.Presets with { NrOnLaunch = startup.IsChecked == true });
    }

    public async Task LaunchOfflineAsync(Game game)
    {
        if (Service is not EngineForgeService engine || Busy) return;
        try
        {
            await engine.LaunchOfflineAsync(game);
            ShowToast("Launching offline. Choose offline mode in the game. Online features are unavailable.");
        }
        catch (InvalidOperationException error) { await Message("Could not launch offline", error.Message); }
    }
}
