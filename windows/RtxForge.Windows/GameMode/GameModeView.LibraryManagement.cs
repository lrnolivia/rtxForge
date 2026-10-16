using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using RtxForge.Windows.Models;

namespace RtxForge.Windows.GameMode;

public sealed partial class GameModeView
{
    void OpenLibraryOptions()
    {
        var rows = new List<UIElement>
        {
            ui.RowButton("Rescan library", "F5", () => { CloseModal(); _ = RefreshAsync(); }, glyph: ""),
            ui.RowButton("Add game folder", null, () => { CloseModal(); _ = shell.AddLibraryFolderAsync(); },
                description: "Choose one game's folder.", glyph: ""),
            ui.RowButton("Add library folder", null, () => { CloseModal(); _ = shell.AddLibraryFolderAsync(collection: true); },
                description: "Scan the games inside a folder, including new additions.", glyph: ""),
            ui.RowButton("Removed games", shell.Settings.RemovedGames.Count.ToString(), () => { CloseModal(); OpenRemovedGames(); }),
        };
        if (selectedIds.Count > 0)
            rows.Add(ui.RowButton("Remove selected entries", selectedIds.Count.ToString(),
                () => { CloseModal(); ConfirmRemoveGames(shell.Games.Where(g => selectedIds.Contains(g.Id)).ToList()); }, danger: true));
        var back = ui.Button("Back", CloseModal, GmKind.Card, 0.92);
        ShowModal("Library options", ui.Group(rows, t.Card), [back], CloseModal, 1000, back);
    }

    void ConfirmRemoveGames(IReadOnlyList<Game> games)
    {
        if (games.Count == 0) return;
        var cancel = ui.Button("Cancel", CloseModal, GmKind.Card, 0.92);
        var remove = ui.Button("Remove entries", () =>
        {
            CloseModal();
            if (!shell.RemoveLibraryEntries(games)) return;
            selectedIds.Clear();
            detailsGame = null;
            Open("library");
            Toast("Entries removed. Game files and recovery backups are kept.");
        }, GmKind.Danger, 0.92, enabled: !shell.Busy);
        ShowModal(games.Count == 1 ? $"Remove {games[0].Name}?" : $"Remove {games.Count} entries?",
            ui.P("This hides the entries from rtxForge. Game files, installed features, artwork and recovery backups stay on disk. You can show them again from Removed games."),
            [cancel, remove], CloseModal, 1000, cancel);
    }

    void OpenRemovedGames()
    {
        var content = new StackPanel { Spacing = t.Px(16) };
        content.Children.Add(ui.P("Removed entries stay hidden during rescans. Show an entry again to return it to the library."));
        foreach (var path in shell.Settings.RemovedGames.ToList())
            content.Children.Add(ui.RowButton(System.IO.Path.GetFileName(path), "Show again", () =>
            {
                CloseModal();
                _ = shell.ShowRemovedGameAsync(path);
            }, description: path));
        if (shell.Settings.RemovedGames.Count == 0) content.Children.Add(ui.P("No removed games."));
        var back = ui.Button("Back", CloseModal, GmKind.Card, 0.92);
        ShowModal("Removed games", new ScrollViewer { Content = content, MaxHeight = t.Px(540) }, [back], CloseModal, 1100, back);
    }
}
