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
    EngineReview? preparedReview;
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
        dialog.CloseButtonClick += OnClose;
        dialog.Closing += (_, e) => { if (stage == Stage.Progress) e.Cancel = true; };
        dialog.Closed += (_, _) =>
        {
            closed = true;
            if (preparedReview is not null) shell.Service.DiscardReview(preparedReview);
            else if (review is not null) shell.Service.DiscardOperation(review);
        };
    }

    /// <summary>Review, then run with progress, then report. Returns when the dialog closes: true when the reviewed run completed.</summary>
    public static async Task<bool> ShowAsync(MainWindow shell, string operation, IReadOnlyList<Game> targets, Tuning values)
    {
        var flow = new OperationDialog(shell, operation, targets, values);
        flow.ShowChecking();
        // One game: its accent from the first screen, as in its Details.
        await AccentResources.ApplyAsync(flow.dialog.Resources, AccentResources.Single(targets));
        var shown = flow.dialog.ShowAsync();
        await flow.PrepareAsync();
        await shown;
        return flow.completed;
    }

    /// <summary>Use the installation review, artwork, progress and completion UI for a prepared library update.</summary>
    public static async Task<bool> ShowPreparedAsync(MainWindow shell, string operation,
        Func<IProgress<PrepareProgress>, Task<EngineReview>> prepare)
    {
        var flow = new OperationDialog(shell, operation, shell.Games, shell.Settings.Presets);
        // The engine chooses which games a prepared update covers, so nothing is listed until it answers.
        flow.ShowChecking(listGames: false);
        var shown = flow.dialog.ShowAsync();
        try
        {
            var progress = new Progress<PrepareProgress>(step => flow.checkingPanel.Show("Checking",
                shell.Games.FirstOrDefault(g => g.Name == step.Game), step.Checked, step.Total > 0 ? step.Total : null, step.Label));
            var checkedReview = await prepare(progress);
            if (flow.closed) shell.Service.DiscardReview(checkedReview);
            else
            {
                flow.preparedReview = checkedReview;
                Game GameFor(ReviewItem item) => shell.Games.FirstOrDefault(g => g.Id == item.GameId || g.Name == item.Title)
                    ?? new Game { Id = item.GameId ?? item.Title, Name = item.Title, Location = "" };
                flow.review = new OperationReview(operation, checkedReview.Token,
                    checkedReview.Items.Select(item => new OperationGameReview(GameFor(item), item.Details ?? item.Detail, item.Detail)).ToArray(),
                    checkedReview.Blocked.Concat(checkedReview.Skipped).Select(item =>
                        new ReviewBlock(shell.Games.FirstOrDefault(g => g.Id == item.GameId || g.Name == item.Title), item.Title, item.Details ?? item.Detail, item.Detail)).ToArray());
                flow.ShowReview(flow.review);
            }
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or InvalidOperationException)
        {
            flow.ShowDone(false, error.Message);
        }
        await shown;
        return flow.completed;
    }

    /// <summary>"Install Features" presets step that precedes the review (Linux: _presets_confirmed).</summary>
    public static async Task<Tuning?> AskPresetsAsync(MainWindow shell, Tuning initial, Game? game = null, IReadOnlyList<Game>? targets = null)
    {
        // Show only what these games can get: NR only when none of them has an MFG route.
        var mode = targets is { Count: > 0 } ? GameOverview.Mode(targets, shell.Mode) : shell.Mode;
        var dialog = shell.NewDialog();
        await AccentResources.ApplyAsync(dialog.Resources, game);
        dialog.Title = "Install Features";
        var editorWidth = Math.Max(280, Math.Min(760, ((shell.Content as FrameworkElement)?.XamlRoot?.Size.Width ?? 1120) - 120));
        dialog.Resources["ContentDialogMaxWidth"] = 840.0;
        var tuning = new PresetControlsView(initial, shell.Settings.OverlayControls == "classic", embedded: true, installation: true) { Width = editorWidth };
        tuning.SetMode(mode, legacy: shell.Settings.RuntimeProvider != "skynizz", dynamicSupported: shell.Settings.DynamicMfgSupported);
        var body = new StackPanel { Spacing = 16 };
        body.Children.Add(Prefs.Label("Choose startup settings. You can adjust them later."));
        var feeder = shell.Settings.RuntimeProvider == "feeder";
        if (!feeder) body.Children.Add(tuning);
        var startup = new CheckBox { Content = "Enable NR on launch", IsChecked = shell.Settings.NrOnLaunch };
        var separateStartup = shell.Settings.RuntimeProvider != "skynizz";
        if (separateStartup && mode != "mfg-only") body.Children.Add(startup);
        dialog.Content = new ScrollViewer { Content = body, HorizontalScrollMode = ScrollMode.Disabled,
            MaxHeight = Math.Max(280, ((shell.Content as FrameworkElement)?.XamlRoot?.Size.Height ?? 900) - 280) };
        dialog.PrimaryButtonText = "Review games";
        dialog.CloseButtonText = "Cancel";
        dialog.DefaultButton = ContentDialogButton.Primary;
        return await dialog.ShowAsync() == ContentDialogResult.Primary
            ? separateStartup ? tuning.Value with { NrOnLaunch = startup.IsChecked == true } : tuning.Value : null;
    }

    // ---------- Checking (engine prepare: every target verified, nothing written) ----------

    // Checking and review are one screen: every game's row is listed at once and fills in as it is checked.
    readonly Dictionary<string, (TextBlock Detail, TextBlock State)> checkingRows = new(StringComparer.OrdinalIgnoreCase);
    readonly TextBlock checkingTitle = new() { FontSize = 20, FontWeight = FontWeights.SemiBold };
    string? checkingGame;

    void ShowChecking(bool listGames = true)
    {
        dialog.Title = Title();
        dialog.PrimaryButtonText = ActionVerb();
        dialog.IsPrimaryButtonEnabled = false;
        dialog.CloseButtonText = "Cancel";
        dialog.DefaultButton = ContentDialogButton.Primary;
        if (!listGames || targets.Count == 0)
        {
            checkingPanel.Show("Checking", targets.FirstOrDefault(), 0, null, "Checking game files");
            dialog.Content = checkingPanel.Root;
            return;
        }
        // As wide as the review it becomes.
        var body = new StackPanel { Spacing = 16, MinWidth = ReviewWidth };
        var summary = new StackPanel { Spacing = 4 };
        checkingTitle.Text = $"Checking {targets.Count} game{(targets.Count == 1 ? "" : "s")}";
        summary.Children.Add(checkingTitle);
        summary.Children.Add(Prefs.Label("Each game is checked before anything changes.", "ForgeDimTextStyle"));
        body.Children.Add(summary);
        var list = new StackPanel { Spacing = 4 };
        foreach (var game in targets.OrderBy(g => g.Name, StringComparer.CurrentCultureIgnoreCase))
        {
            list.Children.Add(ReviewRow(game, game.Name, "Waiting to be checked", "Waiting", true, null, out var detail, out var state, ""));
            checkingRows[game.Name] = (detail, state);
        }
        body.Children.Add(new ScrollViewer { Content = list, MaxHeight = 380, HorizontalScrollMode = ScrollMode.Disabled });
        body.Children.Add(Prefs.Label("Your files will only change after you review and confirm.", "ForgeCaptionDimTextStyle"));
        dialog.Content = body;
    }

    /// <summary>The game being checked now; the one before it is done.</summary>
    void ShowChecked(PrepareProgress step)
    {
        if (checkingRows.Count == 0)
        {
            checkingPanel.Show("Checking", targets.FirstOrDefault(g => g.Name == step.Game), step.Checked, step.Total > 0 ? step.Total : null, step.Label);
            return;
        }
        if (step.Total > 0) checkingTitle.Text = $"Checking {Math.Min(step.Checked + 1, step.Total)} of {step.Total}";
        if (step.Game is not { Length: > 0 } game || game == checkingGame || !checkingRows.TryGetValue(game, out var row)) return;
        if (checkingGame is not null && checkingRows.TryGetValue(checkingGame, out var previous))
            MarkChecking(previous, "Checked", "Checked", "");
        MarkChecking(row, "Checking game files…", "Checking", "");
        checkingGame = game;
    }

    static void MarkChecking((TextBlock Detail, TextBlock State) row, string detail, string state, string glyph)
    {
        (row.Detail.Text, row.State.Text) = (detail, state.ToUpperInvariant());
        if (row.State.Parent is StackPanel line && line.Children.OfType<FontIcon>().FirstOrDefault() is { } icon) icon.Glyph = glyph;
    }

    async Task PrepareAsync()
    {
        var progress = new Progress<PrepareProgress>(ShowChecked);
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
        "update-overlays" => "Update Overlays",
        "adopt" or "adopt-clean" => "Review Adoption",
        _ => "Review Presets",
    };

    // ---------- Review (action_ready) ----------

    const double ReviewWidth = 640;

    void ShowReview(OperationReview review)
    {
        dialog.Title = Title();
        var body = new StackPanel { Spacing = 16, MinWidth = ReviewWidth };
        // One list for every package: games that get only part of the selection show what they get.
        var games = review.AllGames;
        var count = games.Count;
        var summary = new StackPanel { Spacing = 4 };
        summary.Children.Add(new TextBlock
        {
            Text = count > 0 ? $"{count} game{(count == 1 ? "" : "s")} ready" : "Nothing ready yet",
            FontSize = 20, FontWeight = FontWeights.SemiBold,
        });
        var description = string.Join(" · ", Details());
        if (description.Length > 0) summary.Children.Add(Prefs.Label(description, "ForgeDimTextStyle"));
        body.Children.Add(summary);

        var list = new StackPanel { Spacing = 4 };
        foreach (var (item, part) in games)
            list.Children.Add(ReviewRow(item.Game, item.Game.Name, part is null ? item.Summary : item.Summary + "\n" + part.Reason,
                part?.Badge ?? (operation == "install" && item.Game.AdoptionAvailable ? "Adopt" : "Ready"), true, item.Detail));
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
        dialog.PrimaryButtonText = ActionVerb();
        dialog.IsPrimaryButtonEnabled = count > 0;
        if (preparedReview?.Trust is { Length: > 0 } trust)
        {
            var consent = new CheckBox { Content = new TextBlock { Text = trust, TextWrapping = TextWrapping.Wrap } };
            dialog.IsPrimaryButtonEnabled = false;
            consent.Checked += (_, _) => dialog.IsPrimaryButtonEnabled = count > 0;
            consent.Unchecked += (_, _) => dialog.IsPrimaryButtonEnabled = false;
            body.Children.Add(consent);
        }
        dialog.CloseButtonText = "Cancel";
        AccentPrimary();
    }

    /// <summary>
    /// The primary button in the accent style. The dialog opened while checking, already
    /// with Primary as its default button; setting the same value again doesn't restyle
    /// the now-enabled button, so step through None.
    /// </summary>
    void AccentPrimary()
    {
        dialog.DefaultButton = ContentDialogButton.None;
        dialog.DefaultButton = ContentDialogButton.Primary;
    }

    string ActionVerb() => operation switch
    {
        "install" => "Install",
        "uninstall" => "Restore",
        "update-dlss" => "Update",
        "update-overlays" => "Update Overlays",
        "adopt" => "Adopt with rtxForge",
        "adopt-clean" => "Adopt and clean install",
        _ => "Apply presets",
    };

    IEnumerable<string> Details()
    {
        if (preparedReview is not null)
        {
            yield return preparedReview.Summary;
            if (preparedReview.Note is { Length: > 0 } note) yield return note;
            yield break;
        }
        if (operation == "install" && (shell.Settings.RuntimeProvider == "feeder" || targets.All(g => g.IsFeeder)))
        {
            yield return "NR Only";
            yield return "Feeder NR";
            yield break;
        }
        if (operation == "install" && shell.Settings.RuntimeProvider != "feeder")
        {
            yield return shell.Mode switch { "nr-only" => "NR Only", "nr-mfg" => "NR + MFG", _ => "MFG Only" };
            // Several packages: each game's row names its own.
            if (review is { } mixed && (mixed.Steps.Count > 1 || mixed.Supported.Count > 0)) yield break;
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

    static Border ReviewRow(Game? game, string name, string detail, string state, bool ready, string? technical = null) =>
        ReviewRow(game, name, detail, state, ready, technical, out _, out _);

    static Border ReviewRow(Game? game, string name, string detail, string state, bool ready, string? technical,
        out TextBlock detailText, out TextBlock stateText, string? glyph = null)
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
        detailText = Prefs.Label(detail, "ForgeCaptionDimTextStyle");
        text.Children.Add(detailText);
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
            Glyph = glyph ?? (ready ? "" : ""), FontSize = 10,
            Foreground = (Brush)Application.Current.Resources[ready ? "ForgePillTestedBrush" : "ForgeRemoveBrush"],
        });
        stateText = new TextBlock { Text = state.ToUpperInvariant(), FontSize = 9, FontWeight = FontWeights.Bold, CharacterSpacing = 42 };
        pillLine.Children.Add(stateText);
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
        if (stage != Stage.Review || review is null) return; // Done closes normally
        args.Cancel = true;
        if (review.Supported.Count > 0) review = review.IncludeSupported();
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
        dialog.CloseButtonText = preparedReview is null ? "Cancel" : "";
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
            if (preparedReview is { } pending)
            {
                var steps = new Progress<PrepareProgress>(step => progressPanel.Show(ProgressVerb(),
                    review.Ready.FirstOrDefault(item => item.Game.Name == step.Game)?.Game,
                    step.Checked, step.Total > 0 ? step.Total : review.Ready.Count, step.Label));
                var result = await shell.Service.RunReviewAsync(pending, steps);
                preparedReview = null;
                completed = result.Errors.Count == 0;
                progressPanel.Complete();
                ShowDone(completed, result.Message + (result.Errors.Count > 0 ? "\n\n" + string.Join("\n", result.Errors) : ""));
                return;
            }
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
        "update-overlays" => "Updating",
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
        AccentPrimary();
    }
}
