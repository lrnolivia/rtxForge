using Microsoft.UI.Text;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using RtxForge.Windows.Controls;
using RtxForge.Windows.Models;

namespace RtxForge.Windows;

/// <summary>
/// Add rtxForge to Steam (Linux toggle_rtxforge_in_steam / review_rtxforge_steam):
/// review the shortcut and its bundled artwork, then add, refresh or remove it.
/// </summary>
public sealed partial class MainWindow
{
    public event Action? SteamShortcutChanged;

    public static readonly Dictionary<string, string> SteamRoleTitles = new()
    {
        ["poster"] = "Poster", ["capsule"] = "Wide capsule", ["hero"] = "Hero background", ["logo"] = "Transparent logo",
    };

    public static readonly Dictionary<string, string> SteamSlotMessages = new()
    {
        ["add"] = "Add the bundled artwork.",
        ["replace"] = "Replace existing custom artwork. Your current image will be backed up.",
        ["unchanged"] = "The bundled artwork is already in place.",
    };

    /// <summary>Whether this installation is in Steam (false when it cannot be checked).</summary>
    public async Task<bool> SteamShortcutAddedAsync()
    {
        try { return (await Service.SteamStatusAsync()).Added; }
        catch (InvalidOperationException) { return false; }
    }

    public async Task ToggleSteamShortcutAsync()
    {
        if (Service.IsPreview) { ShowToast("Steam integration is disabled in preview mode."); return; }
        SteamShortcutStatus status;
        try { status = await Service.SteamStatusAsync(); }
        catch (InvalidOperationException error) { await Message("Add rtxForge to Steam", error.Message); return; }
        if (status.Added) await RemoveSteamShortcutAsync(status);
        else await AddSteamShortcutAsync();
    }

    public async Task AddSteamShortcutAsync()
    {
        SteamShortcutReview review;
        try { review = await Service.SteamReviewAsync(); }
        catch (InvalidOperationException error) { await Message("Add rtxForge to Steam", error.Message); return; }

        var body = new StackPanel { Spacing = 12, MinWidth = 520 };
        body.Children.Add(new TextBlock { Text = review.Created ? "Add rtxForge to Steam" : "Refresh rtxForge artwork", FontSize = 20, FontWeight = FontWeights.SemiBold });
        body.Children.Add(Prefs.Label($"Steam account {review.Profile} · No SteamGridDB key is needed."));
        body.Children.Add(Prefs.Label("Only this app’s shortcut artwork will change. Replaced images are backed up. Restart Steam afterward to refresh its library.", "ForgeCaptionDimTextStyle"));
        var list = new StackPanel { Spacing = 4 };
        foreach (var slot in review.Slots)
            list.Children.Add(Prefs.Row(SteamRoleTitles.GetValueOrDefault(slot.Role, slot.Role), SteamSlotMessages.GetValueOrDefault(slot.Status, slot.Status),
                Badge(slot.Status switch { "add" => "NEW", "replace" => "REPLACE", _ => "UNCHANGED" })));
        list.Children.Add(Prefs.Row("Logo position", review.CentersLogo
            ? "Center the logo on the hero background."
            : "Keep the logo position already saved in Steam.", Badge(review.CentersLogo ? "NEW" : "KEPT")));
        body.Children.Add(list);

        var dialog = NewDialog();
        dialog.Title = "Review rtxForge in Steam";
        dialog.Content = body;
        dialog.PrimaryButtonText = review.Created ? "Add & apply artwork" : "Apply artwork";
        dialog.CloseButtonText = "Cancel";
        dialog.DefaultButton = ContentDialogButton.Primary;
        if (await dialog.ShowAsync() != ContentDialogResult.Primary) return;

        try
        {
            var result = await Service.SteamAddAsync(review);
            if (result.Errors.Count > 0)
                await Message("Add rtxForge to Steam", "The Steam shortcut is available, but some artwork still needs syncing: " + string.Join("; ", result.Errors));
            else if (result.Preserved) ShowToast("rtxForge is in Steam. Your existing custom artwork was kept.");
            else ShowToast("rtxForge and its artwork are ready in Steam. Restart Steam to refresh its library.");
        }
        catch (InvalidOperationException error) { await Message("Add rtxForge to Steam", error.Message); }
        SteamShortcutChanged?.Invoke();
    }

    /// <summary>Already in Steam: refresh its bundled artwork (and logo position), or remove the shortcut.</summary>
    async Task RemoveSteamShortcutAsync(SteamShortcutStatus status)
    {
        var dialog = NewDialog();
        dialog.Title = "rtxForge is in Steam";
        dialog.Content = Prefs.Label("Refresh applies the bundled artwork again. Removing keeps your games, saved artwork and the installed rtxForge app. Close Steam first.");
        dialog.PrimaryButtonText = "Refresh artwork";
        dialog.SecondaryButtonText = "Remove from Steam";
        dialog.CloseButtonText = "Cancel";
        dialog.DefaultButton = ContentDialogButton.Primary;
        var choice = await dialog.ShowAsync();
        if (choice == ContentDialogResult.Primary) { await AddSteamShortcutAsync(); return; }
        if (choice != ContentDialogResult.Secondary) return;
        try
        {
            await Service.SteamRemoveAsync(status);
            ShowToast("rtxForge was removed from Steam. Your saved artwork was kept.");
        }
        catch (InvalidOperationException error) { await Message("Remove rtxForge from Steam", error.Message); }
        SteamShortcutChanged?.Invoke();
    }

    static Border Badge(string text) => new()
    {
        Style = Prefs.GetStyle("ForgePillStyle"),
        Child = new TextBlock { Text = text, FontSize = 9, FontWeight = FontWeights.Bold, CharacterSpacing = 42 },
    };
}
