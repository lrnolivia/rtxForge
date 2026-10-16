using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using RtxForge.Windows.Controls;
using RtxForge.Windows.Models;
using RtxForge.Windows.Views;

namespace RtxForge.Windows;

public sealed partial class MainWindow
{
    public async Task<bool> RescanLibraryAsync()
    {
        if (Busy) { ShowToast("Wait for the current operation before rescanning."); return false; }
        ShowToast("Rescanning your library…");
        try
        {
            Settings.LibraryFilter = "all";
            Query = "";
            SaveSettings();
            await ScanAsync();
            ShowToast($"Library rescanned · {Games.Count} games found.");
            return true;
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or InvalidOperationException)
        { ShowToast("Could not rescan your library: " + error.Message); return false; }
    }

    public async Task AddLibraryFolderAsync(bool collection = false)
    {
        if (Busy) { ShowToast("Wait for the current operation before adding a folder."); return; }
        try
        {
            var picker = new global::Windows.Storage.Pickers.FolderPicker();
            picker.FileTypeFilter.Add("*");
            picker.CommitButtonText = collection ? "Add library folder" : "Add game folder";
            WinRT.Interop.InitializeWithWindow.Initialize(picker, Handle);
            var folder = await picker.PickSingleFolderAsync();
            if (folder is null) return;
            var paths = collection ? Settings.LibraryFolders : Settings.GameFolders;
            if (!paths.Any(path => LibraryLocations.Same(path, folder.Path))) paths.Add(folder.Path);
            if (!collection) LibraryLocations.Show(Settings, folder.Path);
            await RescanLibraryAsync();
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or InvalidOperationException or System.Runtime.InteropServices.COMException)
        { ShowToast("Could not add that folder: " + error.Message); }
    }

    public bool RemoveLibraryEntries(IReadOnlyList<Game> games)
    {
        if (Busy) { ShowToast("Wait for the current operation before removing entries."); return false; }
        LibraryLocations.Remove(Settings, games);
        Games = LibraryLocations.Visible(Games, Settings.RemovedGames);
        SaveSettings();
        GamesChanged?.Invoke();
        ShowToast($"Removed {games.Count} {(games.Count == 1 ? "entry" : "entries")} from the library. Game files are kept.");
        return true;
    }

    public async Task ConfirmRemoveLibraryEntriesAsync(IReadOnlyList<Game> games)
    {
        if (games.Count == 0) { ShowToast("Select the games you want to remove."); return; }
        var dialog = NewDialog();
        dialog.Title = games.Count == 1 ? $"Remove {games[0].Name} from the library?" : $"Remove {games.Count} library entries?";
        dialog.Content = Prefs.Label("This hides these entries from rtxForge. Game files, installed features, artwork and recovery backups stay on disk. You can show the entries again from Removed games.");
        dialog.PrimaryButtonText = "Remove entries";
        dialog.CloseButtonText = "Cancel";
        dialog.DefaultButton = ContentDialogButton.Close;
        if (await dialog.ShowAsync() == ContentDialogResult.Primary && RemoveLibraryEntries(games)
            && ContentFrame.SourcePageType == typeof(GamePage)) Navigate("Library");
    }

    public async Task ShowRemovedGameAsync(string path)
    {
        LibraryLocations.Show(Settings, path);
        await RescanLibraryAsync();
    }

    public async Task ShowRemovedLibraryEntriesAsync()
    {
        if (Settings.RemovedGames.Count == 0) { ShowToast("No removed games."); return; }
        var dialog = NewDialog();
        dialog.Title = "Removed games";
        var list = new StackPanel { Spacing = 8 };
        list.Children.Add(Prefs.Label("These entries stay hidden during rescans. Show an entry again to return it to the library."));
        foreach (var path in Settings.RemovedGames.ToList())
        {
            var show = new Button { Content = "Show again" };
            show.Click += (_, _) => { dialog.Hide(); _ = ShowRemovedGameAsync(path); };
            list.Children.Add(Prefs.Row(Path.GetFileName(path), path, show));
        }
        dialog.Content = new ScrollViewer { Content = list, MaxHeight = 450 };
        dialog.CloseButtonText = "Close";
        await dialog.ShowAsync();
    }
}
