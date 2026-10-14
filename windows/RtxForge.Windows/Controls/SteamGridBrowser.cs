using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Imaging;
using RtxForge.Windows.Models;

namespace RtxForge.Windows.Controls;

/// <summary>
/// open_steamgrid_search: find the game on SteamGridDB, filter by style, size and format,
/// preview a full-size image, then use it for one artwork role (synced to Steam after review).
/// </summary>
public sealed class SteamGridBrowser
{
    static readonly Dictionary<string, string> Titles = new() { ["poster"] = "Posters", ["capsule"] = "Wide capsules", ["hero"] = "Heroes", ["logo"] = "Logos" };

    readonly MainWindow shell;
    readonly Game game;
    readonly string role;
    readonly ContentDialog dialog;
    readonly TextBox query = new() { PlaceholderText = "Search for a different game" };
    readonly ComboBox style = new() { HorizontalAlignment = HorizontalAlignment.Stretch }, size = new() { HorizontalAlignment = HorizontalAlignment.Stretch }, mime = new() { HorizontalAlignment = HorizontalAlignment.Stretch };
    readonly CheckBox humor = new() { Content = "Include humorous artwork" };
    readonly TextBlock status = Prefs.Label("Community artwork from SteamGridDB · static images");
    readonly StackPanel matches = new() { Spacing = 4 };
    readonly GridView grid = new() { SelectionMode = ListViewSelectionMode.None, IsItemClickEnabled = true, MaxHeight = 380 };
    readonly Image preview = new() { Stretch = Stretch.Uniform, MaxHeight = 360 };
    readonly TextBlock credit = Prefs.Label("", "ForgeCaptionDimTextStyle");
    readonly StackPanel browse = new() { Spacing = 10 }, previewPanel = new() { Spacing = 10, Visibility = Visibility.Collapsed };
    readonly string[] styles, sizes, mimes;
    readonly List<SteamGridAsset> assets = [];
    SteamGridGame? match;
    int page, generation;
    (SteamGridAsset Asset, string Path)? picked;

    public SteamGridBrowser(MainWindow shell, Game game, string role, SteamGridStatus vocabulary)
    {
        this.shell = shell;
        this.game = game;
        this.role = role;
        styles = vocabulary.Styles.GetValueOrDefault(role) ?? [];
        sizes = vocabulary.Dimensions.GetValueOrDefault(role) ?? [];
        mimes = vocabulary.Mimes;
        dialog = shell.NewDialog();
        dialog.Title = Titles[role] + " for " + game.Name;
        dialog.Resources["ContentDialogMaxWidth"] = 900.0;
        query.Text = game.Name;
        query.KeyDown += (_, e) => { if (e.Key == global::Windows.System.VirtualKey.Enter) _ = SearchAsync(); };
        Fill(style, "Styles", styles);
        Fill(size, "Sizes", sizes);
        Fill(mime, "Formats", mimes);
        foreach (var box in new[] { style, size, mime }) box.SelectionChanged += (_, _) => _ = LoadAsync(false);
        humor.Click += (_, _) => _ = LoadAsync(false);
        grid.ItemClick += (_, e) => { if (e.ClickedItem is FrameworkElement { Tag: SteamGridAsset asset }) _ = SelectAsync(asset); };

        var search = new Grid { ColumnSpacing = 8 };
        search.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        search.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        search.Children.Add(query);
        var go = Prefs.ActionButton("Search", (_, _) => _ = SearchAsync());
        Grid.SetColumn(go, 1);
        search.Children.Add(go);
        browse.Children.Add(search);
        var filters = new Grid { ColumnSpacing = 8 };
        foreach (var (index, (label, box)) in new[] { ("Styles", style), ("Sizes", size), ("Formats", mime) }.Select((x, i) => (i, x)))
        {
            filters.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            var cell = new StackPanel { Spacing = 4 };
            cell.Children.Add(Prefs.Label(label, "ForgeCaptionDimTextStyle"));
            cell.Children.Add(box);
            Grid.SetColumn(cell, index);
            filters.Children.Add(cell);
        }
        browse.Children.Add(filters);
        browse.Children.Add(humor);
        browse.Children.Add(matches);
        browse.Children.Add(grid);
        previewPanel.Children.Add(preview);
        previewPanel.Children.Add(credit);

        var body = new StackPanel { Spacing = 12, MinWidth = 720 };
        body.Children.Add(status);
        body.Children.Add(browse);
        body.Children.Add(previewPanel);
        dialog.Content = body;
        dialog.CloseButtonText = "Close";
        dialog.SecondaryButtonText = "Load more";
        dialog.IsSecondaryButtonEnabled = false;
        dialog.PrimaryButtonText = "Use artwork";
        dialog.IsPrimaryButtonEnabled = false;
        dialog.SecondaryButtonClick += (sender, args) =>
        {
            args.Cancel = true;
            if (picked is not null) Back();
            else _ = LoadAsync(true);
        };
    }

    static void Fill(ComboBox box, string title, string[] values)
    {
        box.Items.Add("All " + title.ToLowerInvariant());
        foreach (var value in values)
            box.Items.Add(value.Replace('_', ' ').Replace("material", "Minimal").Replace("image/", "").Replace("x", " × "));
        box.SelectedIndex = 0;
    }

    static string Value(ComboBox box, string[] values) => box.SelectedIndex > 0 && box.SelectedIndex <= values.Length ? values[box.SelectedIndex - 1] : "";

    public async Task ShowAsync()
    {
        var shown = dialog.ShowAsync();
        _ = SearchAsync();
        var choice = await shown;
        if (choice == ContentDialogResult.Primary && picked is { } chosen)
            await shell.UseArtworkAsync(game, role, chosen.Path, "SteamGridDB · " + chosen.Asset.Author);
    }

    async Task SearchAsync()
    {
        var token = ++generation;
        status.Text = "Searching games…";
        matches.Children.Clear();
        grid.Items.Clear();
        assets.Clear();
        match = null;
        try
        {
            var found = await shell.Service.SteamGridSearchAsync(query.Text.Trim());
            if (token != generation) return;
            var exact = found.Where(m => string.Equals(m.Name, query.Text.Trim(), StringComparison.OrdinalIgnoreCase)).ToList();
            if (exact.Count == 1) { match = exact[0]; await LoadAsync(false); return; }
            status.Text = found.Count > 0 ? "Choose the matching game." : "No matching games. Try another title or upload an image.";
            foreach (var candidate in found)
                matches.Children.Add(Prefs.ActionButton(candidate.Name, (_, _) => { match = candidate; matches.Children.Clear(); _ = LoadAsync(false); }));
        }
        catch (InvalidOperationException error) { if (token == generation) status.Text = error.Message; }
    }

    async Task LoadAsync(bool append)
    {
        if (match is null) return;
        var token = ++generation;
        page = append ? page + 1 : 0;
        if (!append) { grid.Items.Clear(); assets.Clear(); }
        status.Text = "Finding " + Titles[role].ToLowerInvariant() + "…";
        dialog.IsSecondaryButtonEnabled = false;
        try
        {
            var found = await shell.Service.SteamGridArtworkAsync(match.Id, role, page, Value(style, styles), Value(size, sizes), Value(mime, mimes), humor.IsChecked == true);
            if (token != generation) return;
            foreach (var asset in found.Where(a => assets.All(x => x.Id != a.Id)))
            {
                assets.Add(asset);
                var card = new StackPanel { Spacing = 4, Width = 150, Tag = asset };
                card.Children.Add(new Image
                {
                    Source = new BitmapImage(new Uri(asset.Thumb ?? asset.Url)) { DecodePixelWidth = 300 },
                    Height = role == "poster" ? 216 : 82, Stretch = Stretch.UniformToFill,
                });
                card.Children.Add(new TextBlock { Text = asset.Author, FontSize = 11, TextTrimming = TextTrimming.CharacterEllipsis });
                ToolTipService.SetToolTip(card, $"{asset.Width} × {asset.Height} · {asset.Author}");
                grid.Items.Add(card);
            }
            status.Text = assets.Count > 0 ? $"{assets.Count} {Titles[role].ToLowerInvariant()} · {match.Name}" : "No artwork matches these filters. Try another style or size.";
            dialog.IsSecondaryButtonEnabled = found.Count > 0 && page < 100;
        }
        catch (InvalidOperationException error) { if (token == generation) status.Text = error.Message; }
    }

    async Task SelectAsync(SteamGridAsset asset)
    {
        var token = ++generation;
        status.Text = "Loading full-size preview…";
        try
        {
            var path = await shell.Service.SteamGridDownloadAsync(asset);
            if (token != generation) return;
            preview.Source = new BitmapImage(new Uri(path));
            credit.Text = $"{asset.Width} × {asset.Height} · {asset.Author}";
            picked = (asset, path);
            browse.Visibility = Visibility.Collapsed;
            previewPanel.Visibility = Visibility.Visible;
            dialog.SecondaryButtonText = "Back to results";
            dialog.IsSecondaryButtonEnabled = true;
            dialog.IsPrimaryButtonEnabled = true;
            status.Text = $"Apply this {MainWindow.ArtworkRoles[role].ToLowerInvariant()} to rtxForge and your selected Steam library.";
        }
        catch (InvalidOperationException error) { if (token == generation) status.Text = error.Message; }
    }

    void Back()
    {
        generation++;
        picked = null;
        browse.Visibility = Visibility.Visible;
        previewPanel.Visibility = Visibility.Collapsed;
        dialog.SecondaryButtonText = "Load more";
        dialog.IsSecondaryButtonEnabled = assets.Count > 0;
        dialog.IsPrimaryButtonEnabled = false;
        status.Text = Titles[role] + " · choose an image to preview and apply";
    }
}
