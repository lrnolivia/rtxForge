using Microsoft.UI.Text;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using RtxForge.Windows.Models;
using RtxForge.Windows.ViewModels;

namespace RtxForge.Windows.Controls;

/// <summary>
/// The Linux review panel (review_list / review_entry → start → toast) for every write
/// beyond install and restore: Checking → Review → Working → Done in one ContentDialog.
/// Execution runs the host's stored review by token, so only what was shown is written.
/// </summary>
public sealed class ReviewDialog
{
    enum Stage { Checking, Review, Working, Done }

    readonly MainWindow shell;
    readonly ContentDialog dialog;
    readonly string? emptyMessage;
    EngineReview? review;
    EngineResult? result;
    Stage stage = Stage.Checking;
    CheckBox? trust;

    ReviewDialog(MainWindow shell, string title, string? emptyMessage)
    {
        this.shell = shell;
        this.emptyMessage = emptyMessage;
        dialog = shell.NewDialog();
        dialog.Title = title;
        dialog.Resources["ContentDialogMaxWidth"] = 760.0;
        dialog.PrimaryButtonClick += OnPrimary;
        dialog.Closing += (_, e) => { if (stage == Stage.Working) e.Cancel = true; };
    }

    /// <summary>Checks, shows the review, runs it when confirmed. Returns the result, or null when nothing ran.</summary>
    public static async Task<EngineResult?> ShowAsync(MainWindow shell, string title, Func<Task<EngineReview>> prepare, string? emptyMessage = null)
    {
        var flow = new ReviewDialog(shell, title, emptyMessage);
        flow.ShowWorking("Checking…");
        var shown = flow.dialog.ShowAsync();
        try
        {
            flow.review = await prepare();
            flow.ShowReview(flow.review);
        }
        catch (Exception error) when (error is InvalidOperationException or IOException or UnauthorizedAccessException)
        {
            flow.ShowDone(false, error.Message);
        }
        await shown;
        if (flow.result is null && flow.review is { } pending) shell.Service.DiscardReview(pending);
        return flow.result;
    }

    void ShowWorking(string text)
    {
        var body = new StackPanel { Spacing = 16, MinWidth = 440, Padding = new Thickness(0, 12, 0, 12) };
        body.Children.Add(new ProgressBar { IsIndeterminate = true });
        var phase = Prefs.Label(text);
        body.Children.Add(phase);
        dialog.Content = body;
        dialog.PrimaryButtonText = "";
        dialog.CloseButtonText = stage == Stage.Working ? "" : "Cancel";
        Phase = phase;
    }

    TextBlock? Phase;

    void ShowReview(EngineReview review)
    {
        stage = Stage.Review;
        dialog.Title = review.Title;
        var body = new StackPanel { Spacing = 14, MinWidth = 520 };
        if (!review.Ready)
        {
            body.Children.Add(new TextBlock { Text = emptyMessage ?? (review.Summary.Length > 0 ? review.Summary : "Nothing to change."), FontSize = 18, FontWeight = FontWeights.SemiBold, TextWrapping = TextWrapping.Wrap });
            AddBlocked(body, review);
            dialog.Content = body;
            dialog.PrimaryButtonText = "";
            dialog.CloseButtonText = "Close";
            return;
        }
        if (review.Summary.Length > 0) body.Children.Add(Prefs.Label(review.Summary));
        var list = new StackPanel { Spacing = 4 };
        foreach (var item in review.Items) list.Children.Add(Row(item, true));
        body.Children.Add(new ScrollViewer { Content = list, MaxHeight = 360, HorizontalScrollMode = ScrollMode.Disabled });
        AddBlocked(body, review);
        if (review.Note is { } note) body.Children.Add(Prefs.Label(note, "ForgeCaptionDimTextStyle"));
        if (review.Trust is { } statement)
        {
            trust = new CheckBox { Content = statement };
            trust.Checked += (_, _) => dialog.IsPrimaryButtonEnabled = true;
            trust.Unchecked += (_, _) => dialog.IsPrimaryButtonEnabled = false;
            body.Children.Add(trust);
        }
        else body.Children.Add(Prefs.Label("Your files will only change after you review and confirm.", "ForgeCaptionDimTextStyle"));
        dialog.Content = body;
        dialog.PrimaryButtonText = review.Action;
        dialog.IsPrimaryButtonEnabled = review.Trust is null;
        dialog.CloseButtonText = "Cancel";
        dialog.DefaultButton = ContentDialogButton.Primary;
    }

    void AddBlocked(StackPanel body, EngineReview review)
    {
        if (review.Blocked.Count == 0) return;
        var header = Prefs.Label($"Needs attention · {review.Blocked.Count}", "ForgeHeadingTextStyle");
        header.Margin = new Thickness(0, 8, 0, 0);
        body.Children.Add(header);
        var list = new StackPanel { Spacing = 4 };
        foreach (var item in review.Blocked) list.Children.Add(Row(item, false));
        body.Children.Add(new ScrollViewer { Content = list, MaxHeight = 200, HorizontalScrollMode = ScrollMode.Disabled });
    }

    /// <summary>review_entry: artwork bezel (the game's capsule, or an icon), title, detail, badge, expandable full text.</summary>
    Border Row(ReviewItem item, bool ready)
    {
        var game = item.GameId is null ? null : shell.Games.FirstOrDefault(g => g.Id == item.GameId)
            ?? shell.Games.FirstOrDefault(g => g.Name == item.Title);
        var grid = new Grid { ColumnSpacing = 12 };
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        var thumb = new Grid
        {
            Width = 92, Height = 43, BorderThickness = new Thickness(2),
            CornerRadius = (CornerRadius)Application.Current.Resources["ForgeArtCornerRadius"],
            Background = (Brush)Application.Current.Resources["ControlFillColorSecondaryBrush"],
        };
        if (game is not null && GameItem.Image(game.CapsulePath ?? game.PosterPath) is { } image)
            thumb.Children.Add(new Image { Source = image, Stretch = Stretch.UniformToFill });
        else thumb.Children.Add(new FontIcon { Glyph = item.Details is null ? "" : "", FontSize = 18 });
        if (game is not null) _ = AccentAsync(thumb, game);
        grid.Children.Add(thumb);
        var text = new StackPanel { VerticalAlignment = VerticalAlignment.Center, Spacing = 1 };
        text.Children.Add(new TextBlock { Text = item.Title, FontWeight = FontWeights.SemiBold, TextTrimming = TextTrimming.CharacterEllipsis });
        if (item.Detail.Length > 0) text.Children.Add(Prefs.Label(item.Detail, "ForgeCaptionDimTextStyle"));
        if (item.Details is { } details)
        {
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            var info = TechnicalDetails.Create(details); Grid.SetColumn(info, 3); grid.Children.Add(info);
        }
        Grid.SetColumn(text, 1);
        grid.Children.Add(text);
        var badge = ready ? item.Badge : item.Badge.Length > 0 ? item.Badge : "Skipped";
        if (badge.Length > 0)
        {
            var pill = new Border
            {
                Style = Prefs.GetStyle("ForgePillStyle"), VerticalAlignment = VerticalAlignment.Center,
                Child = new TextBlock { Text = badge.ToUpperInvariant(), FontSize = 9, FontWeight = FontWeights.Bold, CharacterSpacing = 42 },
            };
            Grid.SetColumn(pill, 2);
            grid.Children.Add(pill);
        }
        return new Border { Style = Prefs.GetStyle("ForgeSettingsCardStyle"), MinHeight = 0, Padding = new Thickness(10, 8, 12, 8), Child = grid };
    }

    static async Task AccentAsync(Grid thumb, Game game)
    {
        if (await Services.ArtAccent.ForGameAsync(game) is { } palette) thumb.BorderBrush = palette.AccentBrush;
    }

    void OnPrimary(ContentDialog sender, ContentDialogButtonClickEventArgs args)
    {
        if (stage != Stage.Review || review is null) return;   // Done closes normally
        args.Cancel = true;
        _ = RunAsync(review);
    }

    async Task RunAsync(EngineReview reviewed)
    {
        stage = Stage.Working;
        ShowWorking(reviewed.Action + "…");
        var progress = new Progress<PrepareProgress>(p => { if (Phase is not null && p.Label.Length > 0) Phase.Text = p.Label; });
        try
        {
            result = await shell.Service.RunReviewAsync(reviewed, progress);
            var message = result.Errors.Count > 0 ? result.Message + "\n\n" + string.Join("\n", result.Errors) : result.Message;
            ShowDone(result.Errors.Count == 0, message);
        }
        catch (Exception error) when (error is InvalidOperationException or IOException or UnauthorizedAccessException)
        {
            result = new EngineResult(error.Message, null, [error.Message]);
            ShowDone(false, error.Message);
        }
    }

    void ShowDone(bool success, string message)
    {
        stage = Stage.Done;
        var line = new Grid { ColumnSpacing = 24, MinWidth = 440 };
        line.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        line.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        line.Children.Add(new FontIcon
        {
            Glyph = success ? "" : "", FontSize = 48, VerticalAlignment = VerticalAlignment.Center,
            Foreground = (Brush)Application.Current.Resources[success ? "AccentFillColorDefaultBrush" : "SystemFillColorCautionBrush"],
        });
        var text = new StackPanel { Spacing = 8, VerticalAlignment = VerticalAlignment.Center };
        text.Children.Add(new TextBlock { Text = success ? "Done" : "Could not finish", FontSize = 24, FontWeight = FontWeights.SemiBold });
        text.Children.Add(new TextBlock { Text = message, TextWrapping = TextWrapping.Wrap, IsTextSelectionEnabled = true, Style = Prefs.GetStyle("ForgeDimTextStyle") });
        Grid.SetColumn(text, 1);
        line.Children.Add(text);
        dialog.Content = line;
        dialog.PrimaryButtonText = "";
        dialog.CloseButtonText = "Close";
        dialog.DefaultButton = ContentDialogButton.Close;
    }
}
