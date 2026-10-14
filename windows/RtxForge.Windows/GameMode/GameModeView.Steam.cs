using Microsoft.UI.Xaml;
using RtxForge.Windows.Models;

namespace RtxForge.Windows.GameMode;

/// <summary>Add rtxForge to Steam in Game Mode: the desktop review and actions, as Game Mode dialogs.</summary>
public sealed partial class GameModeView
{
    bool? steamAdded;

    /// <summary>Settings row label; refreshed after the status loads.</summary>
    string SteamRowTitle() => steamAdded == true ? "rtxForge is in Steam" : "Add rtxForge to Steam";

    async void LoadSteamStatus()
    {
        var added = await shell.SteamShortcutAddedAsync();
        if (added == steamAdded) return;
        steamAdded = added;
        if (page == "settings" && modals.Count == 0) Render(keepFocus: true);
    }

    async Task ToggleSteamAsync()
    {
        if (shell.Service.IsPreview) { Toast("Steam integration is disabled in preview mode."); return; }
        SteamShortcutStatus status;
        try { status = await shell.Service.SteamStatusAsync(); }
        catch (InvalidOperationException error) { ShowDone(false, "Add rtxForge to Steam", error.Message); return; }
        if (status.Added) ConfirmSteamRemove(status);
        else await ReviewSteamAddAsync();
    }

    async Task ReviewSteamAddAsync()
    {
        SteamShortcutReview review;
        try { review = await shell.Service.SteamReviewAsync(); }
        catch (InvalidOperationException error) { ShowDone(false, "Add rtxForge to Steam", error.Message); return; }
        var rows = review.Slots.Select(slot => (UIElement)ui.PreferenceRow(
            MainWindow.SteamRoleTitles.GetValueOrDefault(slot.Role, slot.Role),
            MainWindow.SteamSlotMessages.GetValueOrDefault(slot.Status, slot.Status),
            ui.Text(slot.Status switch { "add" => "New", "replace" => "Replace", _ => "Unchanged" }, 0.8, t.Muted), minHeight: 80)).ToList();
        rows.Add(ui.PreferenceRow("Logo position",
            review.CentersLogo ? "Center the logo on the hero background." : "Keep the logo position already saved in Steam.",
            ui.Text(review.CentersLogo ? "New" : "Kept", 0.8, t.Muted), minHeight: 80));
        var content = new Microsoft.UI.Xaml.Controls.StackPanel { Spacing = t.Px(18) };
        content.Children.Add(ui.P($"Steam account {review.Profile} · No SteamGridDB key is needed. Replaced images are backed up. Restart Steam afterward to refresh its library.", 0.88));
        content.Children.Add(ui.Group(rows, t.Card));
        var cancel = ui.Button("Cancel", CloseModal, GmKind.Card, 0.92);
        var add = ui.Button(review.Created ? "Add & apply artwork" : "Apply artwork", () => { CloseModal(); _ = AddSteamAsync(review); }, GmKind.Primary, 0.92);
        ShowModal(review.Created ? "Add rtxForge to Steam" : "Refresh rtxForge artwork", content, [cancel, add], CloseModal, 1100, cancel);
    }

    async Task AddSteamAsync(SteamShortcutReview review)
    {
        try
        {
            var result = await shell.Service.SteamAddAsync(review);
            if (result.Errors.Count > 0)
                ShowDone(false, "Some artwork still needs syncing", "The Steam shortcut is available. " + string.Join("; ", result.Errors));
            else ShowDone(true, "rtxForge is in Steam", result.Preserved
                ? "Your existing custom artwork was kept. Restart Steam to refresh its library."
                : "Its artwork is ready. Restart Steam to refresh its library.");
        }
        catch (InvalidOperationException error) { ShowDone(false, "Could not add rtxForge to Steam", error.Message); }
        steamAdded = null;
        LoadSteamStatus();
    }

    void ConfirmSteamRemove(SteamShortcutStatus status)
    {
        var keep = ui.Button("Cancel", CloseModal, GmKind.Card, 0.92);
        var remove = ui.Button("Remove from Steam", () =>
        {
            CloseModal();
            _ = RemoveSteamAsync(status);
        }, GmKind.Danger, 0.92);
        var refresh = ui.Button("Refresh artwork", () => { CloseModal(); _ = ReviewSteamAddAsync(); }, GmKind.Primary, 0.92);
        ShowModal("rtxForge is in Steam", ui.P("Refresh applies the bundled artwork again. Removing keeps your games, saved artwork and the installed rtxForge app. Close Steam first."),
            [keep, remove, refresh], CloseModal, 1000, refresh);
    }

    async Task RemoveSteamAsync(SteamShortcutStatus status)
    {
        try
        {
            await shell.Service.SteamRemoveAsync(status);
            ShowDone(true, "Removed from Steam", "Your saved artwork was kept.");
        }
        catch (InvalidOperationException error) { ShowDone(false, "Could not remove rtxForge from Steam", error.Message); }
        steamAdded = null;
        LoadSteamStatus();
    }
}
