using Microsoft.UI.Text;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using RtxForge.Windows.Models;
using RtxForge.Windows.ViewModels;

namespace RtxForge.Windows.Controls;

/// <summary>
/// The Linux operation modal (Window.launch_action → action_ready →
/// progress_view → finish_progress) as one ContentDialog that moves through
/// Review → Progress → Done without closing in between.
/// </summary>
public sealed class OperationDialog
{
    enum Stage { Review, Progress, Done }

    readonly MainWindow shell;
    readonly string operation;
    readonly IReadOnlyList<Game> targets;
    readonly Tuning values;
    OperationReview? review;
    readonly ContentDialog dialog;
    Stage stage = Stage.Review;
    CancellationTokenSource? cancel;

    // One step layout for checking and progress (OperationStepPanel).
    readonly OperationStepPanel checkingPanel = new();
    readonly OperationStepPanel progressPanel = new();

    OperationDialog(MainWindow shell, string operation, IReadOnlyList<Game> targets, Tuning values)
    {
        this.shell = shell;
        this.operation = operation;
        this.values = values;
        this.targets = targets;
        dialog = shell.NewDialog();
        dialog.Resources["ContentDialogMaxWidth"] = 760.0;
        dialog.PrimaryButtonClick += OnPrimary;
        dialog.CloseButtonClick += OnClose;
        dialog.Closing += (_, e) => { if (stage == Stage.Progress) e.Cancel = true; };
    }

    /// <summary>Review, then run with progress, then report. Returns when the dialog closes.</summary>
    public static async Task ShowAsync(MainWindow shell, string operation, IReadOnlyList<Game> targets, Tuning values)
    {
        var flow = new OperationDialog(shell, operation, targets, values);
        flow.ShowChecking();
        var shown = flow.dialog.ShowAsync();
        await flow.PrepareAsync();
        await shown;
    }

    /// <summary>"Install Features" presets step that precedes the review (Linux: _presets_confirmed).</summary>
    public static async Task<Tuning?> AskPresetsAsync(MainWindow shell, Tuning initial)
    {
        var dialog = shell.NewDialog();
        dialog.Title = "Install Features";
        dialog.Resources["ContentDialogMaxWidth"] = 900.0;
        var tuning = new TuningPanel(initial) { MinWidth = 760 };
        tuning.SetMode(shell.Mode);
        var body = new StackPanel { Spacing = 16 };
        body.Children.Add(Prefs.Label("Adjust your presets or continue. You can change these settings later in OptiScaler."));
        body.Children.Add(tuning);
        dialog.Content = body;
        dialog.PrimaryButtonText = "Continue";
        dialog.CloseButtonText = "Cancel";
        dialog.DefaultButton = ContentDialogButton.Primary;
        return await dialog.ShowAsync() == ContentDialogResult.Primary ? tuning.Value : null;
    }

    // ---------- Checking (engine prepare: every target verified, nothing written) ----------

    void ShowChecking()
    {
        dialog.Title = Title();
        checkingPanel.Show("Checking", targets.FirstOrDefault(), 0, null, "Checking game files");
        dialog.Content = checkingPanel.Root;
        dialog.PrimaryButtonText = ActionVerb();
        dialog.IsPrimaryButtonEnabled = false;
        dialog.CloseButtonText = "Cancel";
        dialog.DefaultButton = ContentDialogButton.Primary;
    }

    async Task PrepareAsync()
    {
        var progress = new Progress<PrepareProgress>(step => checkingPanel.Show("Checking",
            targets.FirstOrDefault(g => g.Name == step.Game), step.Checked, step.Total > 0 ? step.Total : null, step.Label));
        try
        {
            review = await shell.Service.PrepareAsync(operation, targets, values, shell.Mode, progress);
            ShowReview(review);
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or InvalidOperationException)
        {
            ShowDone(false, error.Message);
        }
    }
    string Title() => operation switch
    {
        "install" => "Review Installation",
        "uninstall" => "Review Restoration",
        "update-dlss" => "Review DLSS Update",
        _ => "Review Presets",
    };

    // ---------- Review (action_ready) ----------

    void ShowReview(OperationReview review)
    {
        dialog.Title = Title();
        var body = new StackPanel { Spacing = 16 };
        var count = review.Ready.Count;
        var summary = new StackPanel { Spacing = 4 };
        summary.Children.Add(new TextBlock
        {
            Text = count > 0 ? $"{count} game{(count == 1 ? "" : "s")} ready" : "Nothing ready yet",
            FontSize = 20, FontWeight = FontWeights.SemiBold,
        });
        summary.Children.Add(Prefs.Label(string.Join(" · ", Details()), "ForgeDimTextStyle"));
        body.Children.Add(summary);

        var list = new StackPanel { Spacing = 4 };
        foreach (var (game, detail) in review.Ready)
            list.Children.Add(ReviewRow(game, game.Name, detail, "Ready", true));
        if (review.Blocked.Count > 0)
        {
            var header = Prefs.Label($"Needs attention · {review.Blocked.Count}", "ForgeHeadingTextStyle");
            header.Margin = new Thickness(0, 12, 0, 2);
            list.Children.Add(header);
            foreach (var block in review.Blocked)
                list.Children.Add(ReviewRow(block.Game, block.Name, block.Reason, "Skipped", false));
        }
        body.Children.Add(new ScrollViewer { Content = list, MaxHeight = 380, HorizontalScrollMode = ScrollMode.Disabled });
        body.Children.Add(Prefs.Label("Your files will only change after you review and confirm.", "ForgeCaptionDimTextStyle"));

        dialog.Content = body;
        dialog.PrimaryButtonText = ActionVerb();
        dialog.IsPrimaryButtonEnabled = count > 0;
        dialog.CloseButtonText = "Cancel";
        dialog.DefaultButton = ContentDialogButton.Primary;
    }

    string ActionVerb() => operation switch
    {
        "install" => "Install",
        "uninstall" => "Restore",
        "update-dlss" => "Update",
        _ => "Apply presets",
    };

    IEnumerable<string> Details()
    {
        yield return ActionVerb();
        if (operation is "install" or "apply" or "reset")
        {
            yield return shell.Settings.RuntimeProvider switch
            {
                "dlss-unlocked" => "DLSS-Unlocked",
                "custom" => "Custom package",
                _ => "y4my",
            };
            yield return "MFG " + (values.MfgMultiplier switch { "auto" => "In game", "0" => "Off", var m => m + "×" });
        }
    }

    static Border ReviewRow(Game? game, string name, string detail, string state, bool ready)
    {
        var grid = new Grid { ColumnSpacing = 12 };
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });

        var thumb = new Grid
        {
            Width = 92, Height = 43,
            CornerRadius = (CornerRadius)Application.Current.Resources["ForgeArtCornerRadius"],
            Background = (Brush)Application.Current.Resources["ControlFillColorSecondaryBrush"],
        };
        if (game is not null)
            thumb.Children.Add(new Image { Source = GameItem.Image(game.CapsulePath ?? game.PosterPath), Stretch = Stretch.UniformToFill });
        thumb.BorderThickness = new Thickness(2);
        grid.Children.Add(thumb);

        var text = new StackPanel { VerticalAlignment = VerticalAlignment.Center, Spacing = 1 };
        text.Children.Add(new TextBlock { Text = name, FontWeight = FontWeights.SemiBold, TextTrimming = TextTrimming.CharacterEllipsis });
        text.Children.Add(Prefs.Label(detail, "ForgeCaptionDimTextStyle"));
        Grid.SetColumn(text, 1);
        grid.Children.Add(text);

        var pill = new Border { Style = Prefs.GetStyle("ForgePillStyle"), VerticalAlignment = VerticalAlignment.Center };
        var pillLine = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 4 };
        pillLine.Children.Add(new FontIcon
        {
            Glyph = ready ? "" : "", FontSize = 10,
            Foreground = (Brush)Application.Current.Resources[ready ? "ForgePillTestedBrush" : "ForgeRemoveBrush"],
        });
        pillLine.Children.Add(new TextBlock { Text = state.ToUpperInvariant(), FontSize = 9, FontWeight = FontWeights.Bold, CharacterSpacing = 42 });
        pill.Child = pillLine;
        Grid.SetColumn(pill, 2);
        grid.Children.Add(pill);
        if (ready && game is not null) _ = ReviewAccentAsync(thumb, pill, pillLine, game);

        return new Border { Style = Prefs.GetStyle("ForgeSettingsCardStyle"), MinHeight = 0, Padding = new Thickness(10, 8, 12, 8), Child = grid };
    }

    /// <summary>.review-game.{art}: bezel in the accent, badge readable(color, card) on mix(color, card, 0.10).</summary>
    static async Task ReviewAccentAsync(Grid thumb, Border badge, StackPanel badgeLine, Game game)
    {
        var palette = await Services.ArtAccent.ForGameAsync(game);
        if (palette is null) return;
        thumb.BorderBrush = palette.AccentBrush;
        badge.Background = palette.Brush(palette.BadgeBg);
        foreach (var child in badgeLine.Children)
        {
            if (child is FontIcon icon) icon.Foreground = palette.Brush(palette.BadgeFg);
            if (child is TextBlock text) text.Foreground = palette.Brush(palette.BadgeFg);
        }
    }

    // ---------- Progress (progress_view) ----------

    void OnPrimary(ContentDialog sender, ContentDialogButtonClickEventArgs args)
    {
        if (stage != Stage.Review || review is null) return; // Done closes normally
        args.Cancel = true;
        _ = RunAsync();
    }

    void OnClose(ContentDialog sender, ContentDialogButtonClickEventArgs args)
    {
        if (stage != Stage.Progress) return;
        args.Cancel = true;
        cancel?.Cancel();
        dialog.CloseButtonText = "Cancelling…";
    }

    async Task RunAsync()
    {
        stage = Stage.Progress;
        cancel = new CancellationTokenSource();
        dialog.Title = null;
        dialog.PrimaryButtonText = "";
        dialog.CloseButtonText = "Cancel";
        progressPanel.AccentChanged += TintButtons;
        progressPanel.Show(ProgressVerb(), review!.Ready.FirstOrDefault().Game, 0, review.Ready.Count, "Starting");
        dialog.Content = progressPanel.Root;

        var done = 0;
        var progress = new Progress<OperationStep>(step =>
        {
            done = step.Index;
            progressPanel.Show(ProgressVerb(), step.Game, step.Index, step.Total, step.Caption, step.Fraction);
        });

        try
        {
            var count = await shell.ExecuteAsync(review!, progress, cancel.Token);
            progressPanel.Complete();
            ShowDone(true, $"{count} game{(count == 1 ? "" : "s")} updated.");
        }
        catch (OperationCanceledException)
        {
            ShowDone(false, $"Cancelled. Changes to the remaining games were undone ({done} of {review!.Ready.Count} had started).", "Cancelled");
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or InvalidOperationException)
        {
            ShowDone(false, error.Message);
        }
    }

    string ProgressVerb() => operation switch
    {
        "install" => "Installing",
        "uninstall" => "Restoring",
        "update-dlss" => "Updating",
        _ => "Applying",
    };

    /// <summary>The current game's accent on the dialog's suggested button (Linux button.suggested-action).</summary>
    void TintButtons(Services.AccentPalette palette)
    {
        dialog.Resources["AccentButtonBackground"] = palette.AccentBrush;
        dialog.Resources["AccentButtonBackgroundPointerOver"] = palette.Brush(palette.Color, 0.9);
        dialog.Resources["AccentButtonBackgroundPressed"] = palette.Brush(palette.Color, 0.8);
        dialog.Resources["AccentButtonForeground"] = palette.Brush(palette.AccentFg);
        dialog.Resources["AccentButtonForegroundPointerOver"] = palette.Brush(palette.AccentFg);
        dialog.Resources["AccentButtonForegroundPressed"] = palette.Brush(palette.AccentFg);
    }
    // ---------- Done (finish_progress) ----------

    void ShowDone(bool success, string message, string? title = null)
    {
        stage = Stage.Done;
        dialog.Title = null;
        dialog.Resources["ContentDialogMaxWidth"] = 520.0;

        var line = new Grid { ColumnSpacing = 24, MinWidth = 440 };
        line.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        line.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        line.Children.Add(new FontIcon
        {
            Glyph = success ? "" : "", FontSize = 64, VerticalAlignment = VerticalAlignment.Center,
            Foreground = (Brush)Application.Current.Resources[success ? "AccentFillColorDefaultBrush" : "SystemFillColorCautionBrush"],
        });
        var text = new StackPanel { Spacing = 8, VerticalAlignment = VerticalAlignment.Center };
        text.Children.Add(new TextBlock { Text = title ?? (success ? "Done" : "Could not finish"), FontSize = 28, FontWeight = FontWeights.SemiBold });
        text.Children.Add(Prefs.Label(message, "ForgeDimTextStyle"));
        Grid.SetColumn(text, 1);
        line.Children.Add(text);

        dialog.Content = line;
        dialog.CloseButtonText = "";
        dialog.PrimaryButtonText = "Done";
        dialog.IsPrimaryButtonEnabled = true;
        dialog.DefaultButton = ContentDialogButton.Primary;
    }
}
