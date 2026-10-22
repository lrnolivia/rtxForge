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
    enum Stage { Review, Supported, Progress, Done }

    readonly MainWindow shell;
    readonly string operation;
    readonly IReadOnlyList<Game> targets;
    readonly Tuning values;
    OperationReview? review;
    readonly ContentDialog dialog;
    Stage stage = Stage.Review;
    CancellationTokenSource? cancel;
    bool closed, completed;

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
        dialog.SecondaryButtonClick += (sender, args) =>
        {
            if (stage != Stage.Supported || review is null) return;
            args.Cancel = true;
            foreach (var part in review.Supported) shell.Service.DiscardOperation(part.Review);
            if (review.Ready.Count == 0) { ShowDone(false, "No games selected."); return; }
            review = review with { Supported = [] }; _ = RunAsync();
        };
        dialog.CloseButtonClick += OnClose;
        dialog.Closing += (_, e) => { if (stage == Stage.Progress) e.Cancel = true; };
        dialog.Closed += (_, _) =>
        {
            closed = true;
            if (review is not null) shell.Service.DiscardOperation(review);
        };
    }

    /// <summary>Review, then run with progress, then report. Returns when the dialog closes: true when the reviewed run completed.</summary>
    public static async Task<bool> ShowAsync(MainWindow shell, string operation, IReadOnlyList<Game> targets, Tuning values)
    {
        var flow = new OperationDialog(shell, operation, targets, values);
        flow.ShowChecking();
        var shown = flow.dialog.ShowAsync();
        await flow.PrepareAsync();
        await shown;
        return flow.completed;
    }

    /// <summary>"Install Features" presets step that precedes the review (Linux: _presets_confirmed).</summary>
    public static async Task<Tuning?> AskPresetsAsync(MainWindow shell, Tuning initial)
    {
        var dialog = shell.NewDialog();
        dialog.Title = "Install Features";
        var editorWidth = Math.Max(280, Math.Min(760, ((shell.Content as FrameworkElement)?.XamlRoot?.Size.Width ?? 1120) - 120));
        dialog.Resources["ContentDialogMaxWidth"] = 840.0;
        var tuning = new PresetControlsView(initial, shell.Settings.OverlayControls == "classic", embedded: true, installation: true) { Width = editorWidth };
        tuning.SetMode(shell.Mode, legacy: shell.Settings.RuntimeProvider != "skynizz", dynamicSupported: shell.Settings.DynamicMfgSupported);
        var body = new StackPanel { Spacing = 16 };
        body.Children.Add(Prefs.Label("Choose startup settings. You can adjust them later."));
        var feeder = shell.Settings.RuntimeProvider == "feeder";
        if (!feeder) body.Children.Add(tuning);
        var startup = new CheckBox { Content = "Enable NR on launch", IsChecked = shell.Settings.NrOnLaunch };
        var separateStartup = shell.Settings.RuntimeProvider != "skynizz";
        if (separateStartup && shell.Mode != "mfg-only") body.Children.Add(startup);
        dialog.Content = new ScrollViewer { Content = body, HorizontalScrollMode = ScrollMode.Disabled,
            MaxHeight = Math.Max(280, ((shell.Content as FrameworkElement)?.XamlRoot?.Size.Height ?? 900) - 280) };
        dialog.PrimaryButtonText = "Review games";
        dialog.CloseButtonText = "Cancel";
        dialog.DefaultButton = ContentDialogButton.Primary;
        return await dialog.ShowAsync() == ContentDialogResult.Primary
            ? separateStartup ? tuning.Value with { NrOnLaunch = startup.IsChecked == true } : tuning.Value : null;
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
            if (closed) { shell.Service.DiscardOperation(review); return; }
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
        "adopt" or "adopt-clean" => "Review Adoption",
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
            Text = count > 0 ? $"{count} game{(count == 1 ? "" : "s")} ready" : review.Supported.Count > 0 ? "Supported features available" : "Nothing ready yet",
            FontSize = 20, FontWeight = FontWeights.SemiBold,
        });
        var description = string.Join(" · ", Details());
        if (description.Length > 0) summary.Children.Add(Prefs.Label(description, "ForgeDimTextStyle"));
        body.Children.Add(summary);

        var list = new StackPanel { Spacing = 4 };
        foreach (var item in review.Ready)
            list.Children.Add(ReviewRow(item.Game, item.Game.Name, item.Summary, "Ready", true, item.Detail));
        foreach (var warning in review.Warnings)
            list.Children.Add(new InfoBar
            {
                IsOpen = true, IsClosable = false, Severity = InfoBarSeverity.Warning, Margin = new Thickness(0, 8, 0, 0),
                Title = warning.Name, Message = warning.Reason,
            });
        if (review.Blocked.Count > 0)
        {
            var header = Prefs.Label($"Needs attention · {review.Blocked.Count}", "ForgeHeadingTextStyle");
            header.Margin = new Thickness(0, 12, 0, 2);
            list.Children.Add(header);
            foreach (var block in review.Blocked)
                list.Children.Add(ReviewRow(block.Game, block.Name, block.Summary ?? block.Reason, "Skipped", false,
                    block.Summary is null ? null : block.Reason));
        }
        body.Children.Add(new ScrollViewer { Content = list, MaxHeight = 380, HorizontalScrollMode = ScrollMode.Disabled });
        body.Children.Add(Prefs.Label("Your files will only change after you review and confirm.", "ForgeCaptionDimTextStyle"));

        dialog.Content = body;
        dialog.PrimaryButtonText = review.Supported.Count > 0 ? "Continue" : ActionVerb();
        dialog.IsPrimaryButtonEnabled = count > 0 || review.Supported.Count > 0;
        dialog.CloseButtonText = "Cancel";
        dialog.DefaultButton = ContentDialogButton.Primary;
    }

    void ShowSupportedReview()
    {
        stage = Stage.Supported; dialog.Title = "Install the supported features";
        var body = new StackPanel { Spacing = 16 };
        body.Children.Add(new TextBlock { Text = "These games support part of your selection", FontSize = 20, FontWeight = FontWeights.SemiBold, TextWrapping = TextWrapping.Wrap });
        var list = new StackPanel { Spacing = 8 };
        foreach (var group in review!.Supported)
        foreach (var item in group.Review.Ready)
            list.Children.Add(SupportedFeatureCard.Create(item, group.Nr, group.Mfg, group.Reason));
        body.Children.Add(new ScrollViewer { Content = list, MaxHeight = 420, HorizontalScrollMode = ScrollMode.Disabled });
        body.Children.Add(Prefs.Label($"{review.Ready.Count} games will receive your full selection. Include these additional games with the features shown above.", "ForgeCaptionDimTextStyle"));
        dialog.Content = body; dialog.PrimaryButtonText = "Install supported features"; dialog.IsPrimaryButtonEnabled = true;
        dialog.SecondaryButtonText = "Skip these games"; dialog.CloseButtonText = "Cancel";
    }

    string ActionVerb() => operation switch
    {
        "install" => "Install",
        "uninstall" => "Restore",
        "update-dlss" => "Update",
        "adopt" => "Adopt with rtxForge",
        "adopt-clean" => "Adopt and clean install",
        _ => "Apply presets",
    };

    IEnumerable<string> Details()
    {
        if (operation == "install" && (shell.Settings.RuntimeProvider == "feeder" || targets.All(g => g.IsFeeder)))
        {
            yield return "NR Only";
            yield return "Feeder NR";
            yield break;
        }
        if (operation == "install" && shell.Settings.RuntimeProvider != "feeder")
        {
            yield return shell.Mode switch { "nr-only" => "NR Only", "nr-mfg" => "NR + MFG", _ => "MFG Only" };
            yield return shell.Settings.RuntimeProvider switch
            {
                "skynizz" => "Skynizz",
                "feeder" => "Feeder NR",
                "dlss-unlocked" => "DLSS-Unlocked",
                "custom" => "Custom package",
                _ => "y4my",
            };
        }
    }

    static Border ReviewRow(Game? game, string name, string detail, string state, bool ready, string? technical = null)
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
        if (!string.IsNullOrWhiteSpace(technical))
        {
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            var info = TechnicalDetails.Create(technical); Grid.SetColumn(info, 3); grid.Children.Add(info);
        }
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
        else BadgeTheme.AttachLight(pill, ready
            ? global::Windows.UI.Color.FromArgb(255, 49, 91, 21)
            : global::Windows.UI.Color.FromArgb(255, 155, 48, 40));

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
        BadgeTheme.AttachLight(badge, palette.Color);
    }

    // ---------- Progress (progress_view) ----------

    void OnPrimary(ContentDialog sender, ContentDialogButtonClickEventArgs args)
    {
        if (stage == Stage.Supported && review is not null)
        {
            args.Cancel = true;
            review = review.IncludeSupported();
            _ = RunAsync(); return;
        }
        if (stage != Stage.Review || review is null) return; // Done closes normally
        args.Cancel = true;
        if (review.Supported.Count > 0) { ShowSupportedReview(); return; }
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
        dialog.SecondaryButtonText = "";
        dialog.CloseButtonText = "Cancel";
        progressPanel.AccentChanged += TintButtons;
        progressPanel.Show(ProgressVerb(), review!.Ready.FirstOrDefault()?.Game, 0, review.Ready.Count, "Starting");
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
            completed = true;
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
        dialog.SecondaryButtonText = "";
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
