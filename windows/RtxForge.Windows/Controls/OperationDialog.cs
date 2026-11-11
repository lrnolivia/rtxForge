using Microsoft.UI.Text;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using System.Text.Json.Nodes;
using RtxForge.Windows.Models;
using RtxForge.Windows.Services;
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
    enum FlowStep { Presets, Review, Apply }
    const double InstallWidth = 808;
    const double DialogInset = 24;

    readonly MainWindow shell;
    readonly string operation;
    readonly IReadOnlyList<Game> targets;
    readonly Tuning values;
    readonly bool includesPresets;
    OperationReview? review;
    EngineReview? preparedReview;
    readonly ContentDialog dialog;
    Stage stage = Stage.Review;
    CancellationTokenSource? cancel;
    bool closed, completed;
    bool offlineAcknowledged;
    int splitRevision;
    bool splitReady = true;

    // One step layout for checking and progress (OperationStepPanel).
    readonly OperationStepPanel checkingPanel = new();
    readonly OperationStepPanel progressPanel = new();

    OperationDialog(MainWindow shell, string operation, IReadOnlyList<Game> targets, Tuning values, bool includesPresets = false)
    {
        this.shell = shell;
        this.operation = operation;
        this.values = values;
        this.targets = targets;
        this.includesPresets = includesPresets;
        dialog = shell.NewDialog();
        var width = SetWidth(dialog, 560, 640);
        checkingPanel.Root.MaxWidth = progressPanel.Root.MaxWidth = width - 2 * DialogInset;
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
    public static async Task<bool> ShowAsync(MainWindow shell, string operation, IReadOnlyList<Game> targets, Tuning values, bool includesPresets)
    {
        var flow = new OperationDialog(shell, operation, targets, values, includesPresets);
        // One game: its accent from the first screen, as in its Details.
        await AccentResources.ApplyAsync(flow.dialog.Resources, AccentResources.Single(targets));
        flow.ShowChecking();
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
            var progress = new Progress<PrepareProgress>(step => flow.checkingPanel.Show("Preparing",
                shell.Games.FirstOrDefault(g => g.Name == step.Game), step.Checked, step.Total > 0 ? step.Total : null, "Downloading packages/files…"));
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
        var editorWidth = SetWidth(dialog, 640, mode == "nr-mfg" ? InstallWidth : 688) - 2 * DialogInset;
        var tuning = new PresetControlsView(initial, shell.Settings.OverlayControls == "classic", embedded: true, installation: true) { Width = editorWidth };
        tuning.SetMode(mode, legacy: shell.Settings.RuntimeProvider != "skynizz", dynamicSupported: shell.Settings.DynamicMfgSupported);
        var body = new StackPanel { Spacing = 16 };
        var feeder = shell.Settings.RuntimeProvider == "feeder";
        if (!feeder) body.Children.Add(tuning);
        var startup = new CheckBox { Content = "Enable NR on launch", IsChecked = shell.Settings.NrOnLaunch };
        var separateStartup = shell.Settings.RuntimeProvider != "skynizz";
        if (separateStartup && mode != "mfg-only") body.Children.Add(startup);
        dialog.Content = WithSteps(dialog, new ScrollViewer { Content = body, HorizontalScrollMode = ScrollMode.Disabled,
            MaxHeight = Math.Max(240, ((shell.Content as FrameworkElement)?.XamlRoot?.Size.Height ?? 900) - 312) },
            FlowStep.Presets, "Install", includesPresets: true,
            description: "Choose presets. You can adjust them later.");
        dialog.PrimaryButtonText = "Review games";
        dialog.CloseButtonText = "Cancel";
        dialog.DefaultButton = ContentDialogButton.Primary;
        return await dialog.ShowAsync() == ContentDialogResult.Primary
            ? separateStartup ? tuning.Value with { NrOnLaunch = startup.IsChecked == true } : tuning.Value : null;
    }

    // ---------- Checking (engine prepare: every target verified, nothing written) ----------

    void ShowChecking(bool listGames = true)
    {
        dialog.Title = "Preparing";
        dialog.PrimaryButtonText = "";
        dialog.IsPrimaryButtonEnabled = false;
        dialog.CloseButtonText = "Cancel";
        dialog.DefaultButton = ContentDialogButton.Primary;
        dialog.Content = WithSteps(checkingPanel.Root, FlowStep.Review);
        checkingPanel.Show("Preparing", targets.FirstOrDefault(), 0, listGames && targets.Count > 0 ? targets.Count : null, "Downloading packages/files…");
    }

    /// <summary>The game being checked now; the one before it is done.</summary>
    void ShowChecked(PrepareProgress step)
    {
        if (closed || stage != Stage.Review) return;
        checkingPanel.Show("Preparing", targets.FirstOrDefault(g => g.Name == step.Game), step.Checked,
            step.Total > 0 ? step.Total : null, "Downloading packages/files…");
    }

    async Task PrepareAsync()
    {
        var progress = new Progress<PrepareProgress>(ShowChecked);
        try
        {
            review = await shell.Service.PrepareAsync(operation, targets, values, shell.Mode, progress);
            if (closed) { shell.Service.DiscardOperation(review); return; }
            checkingPanel.Complete();
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
        "install-nr-addons" => "Review Split Render",
        "remove-nr-addons" => "Review Split Render removal",
        "uninstall" => "Review Restoration",
        "update-dlss" => "Review DLSS Update",
        "update-overlays" => "Update Overlays",
        "adopt" or "adopt-clean" => "Review Adoption",
        _ => "Review Presets",
    };

    // ---------- Review (action_ready) ----------

    void ShowReview(OperationReview review)
    {
        SetWidth(dialog, 640, 760);
        dialog.Title = Title();
        var body = new StackPanel { Spacing = 16 };
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
        if (operation == "install" && count > 0 && shell.Service is EngineForgeService { SplitRenderEnabled: true } engine)
            _ = AddNrChoicesAsync(body, engine, review, UpdatePrimary);
        body.Children.Add(Prefs.Label("Your files will only change after you review and confirm.", "ForgeCaptionDimTextStyle"));

        dialog.Content = WithSteps(operation == "install" ? new ScrollViewer
        {
            Content = body, HorizontalScrollMode = ScrollMode.Disabled,
            MaxHeight = Math.Max(208, dialog.XamlRoot.Size.Height - 216),
        } : body, FlowStep.Review);
        dialog.PrimaryButtonText = ActionVerb();
        offlineAcknowledged = false;
        if ((preparedReview?.Trust ?? review.RequiredTrust) is { Length: > 0 } trust)
        {
            var consent = new CheckBox { Content = new TextBlock { Text = trust, TextWrapping = TextWrapping.Wrap } };
            consent.Checked += (_, _) => { offlineAcknowledged = true; UpdatePrimary(); };
            consent.Unchecked += (_, _) => { offlineAcknowledged = false; UpdatePrimary(); };
            body.Children.Add(consent);
        }
        UpdatePrimary();

        void UpdatePrimary() => dialog.IsPrimaryButtonEnabled = count > 0 && splitReady
            && (string.IsNullOrEmpty(preparedReview?.Trust ?? review.RequiredTrust) || offlineAcknowledged);
        dialog.CloseButtonText = "Cancel";
        AccentPrimary();
    }

    async Task AddNrChoicesAsync(StackPanel body, EngineForgeService engine, OperationReview review, Action updatePrimary)
    {
        var options = new Expander
        {
            Header = "Split Render",
            Content = Prefs.Label("Loading setups…"),
            HorizontalAlignment = HorizontalAlignment.Stretch,
            HorizontalContentAlignment = HorizontalAlignment.Stretch,
        };
        body.Children.Add(options);
        try
        {
            var catalog = await engine.NrCatalogAsync();
            if (closed || stage != Stage.Review) return;
            var picker = new NrSetupPicker(catalog);
            var fields = new StackPanel { Spacing = 12 };
            fields.Children.Add(Prefs.Label("Optional. Review the DLSS 5 NR setup each game will receive after its main package installs."));
            fields.Children.Add(picker.Root);
            var plans = new StackPanel { Spacing = 4 };
            fields.Children.Add(plans);
            options.Content = fields;
            options.Header = "Split Render · None";
            picker.Changed += async () =>
            {
                int revision = ++splitRevision;
                var choice = picker.Choice;
                options.Header = "Split Render · " + picker.Summary;
                splitReady = false;
                updatePrimary();
                plans.Children.Clear();
                plans.Children.Add(Prefs.Label("Preparing Split Render…"));
                try
                {
                    await Task.Delay(180);
                    if (closed || stage != Stage.Review || revision != splitRevision) return;
                    var rows = await engine.PlanSplitRenderAsync(review, choice, revision);
                    if (closed || stage != Stage.Review || revision != splitRevision) return;
                    plans.Children.Clear();
                    foreach (var row in rows.OfType<JsonObject>())
                    {
                        var name = row["name"]?.ToString() ?? "Game";
                        var reason = row["reason"]?.ToString();
                        var game = review.AllGames.Select(entry => entry.Item.Game).FirstOrDefault(game =>
                            string.Equals(game.Location, row["game"]?.ToString(), StringComparison.OrdinalIgnoreCase))
                            ?? review.AllGames.Select(entry => entry.Item.Game).FirstOrDefault(game => game.Name == name);
                        plans.Children.Add(ReviewRow(game, name, reason ?? row["summary"]?.ToString() ?? "",
                            reason is null ? "Ready" : "Skipped", reason is null, row["details"]?.ToString()));
                    }
                    splitReady = true;
                    updatePrimary();
                }
                catch (Exception error) when (error is IOException or UnauthorizedAccessException or InvalidOperationException)
                {
                    if (closed || stage != Stage.Review || revision != splitRevision) return;
                    plans.Children.Clear();
                    plans.Children.Add(Prefs.Label(error.Message + " Change the setup or choose None to continue."));
                }
            };
        }
        catch (InvalidOperationException)
        {
            if (!closed && stage == Stage.Review)
                body.Children.Remove(options);
        }
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
        "install-nr-addons" => "Install Split Render",
        "remove-nr-addons" => "Remove Split Render",
        "uninstall" => "Restore",
        "update-dlss" => "Update",
        "update-overlays" => "Update Overlays",
        "adopt" => "Adopt with rtxForge",
        "adopt-clean" => "Adopt and clean install",
        _ => "Apply presets",
    };

    UIElement WithSteps(UIElement content, FlowStep current) =>
        WithSteps(dialog, content, current, operation switch
        {
            "update-dlss" => "Update DLSS",
            "uninstall" => "Restore files",
            _ => ActionVerb(),
        }, includesPresets);

    static SolidColorBrush DialogAccent(ContentDialog dialog) =>
        dialog.Resources.ContainsKey("AccentButtonBackground") && dialog.Resources["AccentButtonBackground"] is SolidColorBrush accent
            ? accent : (SolidColorBrush)Application.Current.Resources["AccentFillColorDefaultBrush"];

    internal static double SetWidth(ContentDialog dialog, double minimum, double maximum)
    {
        var available = dialog.XamlRoot?.Size.Width ?? 0;
        if (available > 0) maximum = Math.Min(maximum, Math.Max(280, available - 2 * DialogInset));
        dialog.Resources["ContentDialogMinWidth"] = Math.Min(minimum, maximum);
        dialog.Resources["ContentDialogMaxWidth"] = maximum;
        return maximum;
    }

    internal static StackPanel WithReviewSteps(ContentDialog dialog, UIElement content, bool applying, string action) =>
        WithSteps(dialog, content, applying ? FlowStep.Apply : FlowStep.Review, action, includesPresets: false, reviewLabel: "Review changes");

    static StackPanel WithSteps(ContentDialog dialog, UIElement content, FlowStep current, string action,
        bool includesPresets, string reviewLabel = "Review games", string? description = null)
    {
        const double inset = DialogInset;
        dialog.Resources["ContentDialogPadding"] = new Thickness(inset);
        var body = new StackPanel { Spacing = 12 };
        var steps = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 14,
            HorizontalAlignment = HorizontalAlignment.Right, VerticalAlignment = VerticalAlignment.Center };
        AutomationProperties.SetName(steps, "Operation steps");
        var activeAccent = DialogAccent(dialog);
        var activeInk = new SolidColorBrush(ArtAccent.Palette(activeAccent.Color).AccentFg);
        var neutralCircle = (Brush)Application.Current.Resources["ControlFillColorSecondaryBrush"];
        var phases = new List<(FlowStep Step, string Label)>();
        if (includesPresets) phases.Add((FlowStep.Presets, "Presets"));
        phases.Add((FlowStep.Review, reviewLabel));
        phases.Add((FlowStep.Apply, action));
        for (var index = 0; index < phases.Count; index++)
        {
            var (step, label) = phases[index];
            var active = step == current;
            var number = (index + 1).ToString();
            var item = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 6 };
            var numeral = Prefs.Label(number, active ? "ForgeHeadingTextStyle" : "ForgeCaptionDimTextStyle");
            numeral.FontSize = 10;
            if (active) numeral.Foreground = activeInk;
            numeral.HorizontalAlignment = HorizontalAlignment.Center;
            numeral.VerticalAlignment = VerticalAlignment.Center;
            numeral.RenderTransform = new TranslateTransform { Y = -1 };
            item.Children.Add(new Border
            {
                Child = numeral, Width = 20, Height = 20, CornerRadius = new CornerRadius(10),
                Background = active ? activeAccent : neutralCircle,
            });
            var caption = active ? new TextBlock { Text = label } : Prefs.Label(label, "ForgeCaptionDimTextStyle");
            caption.FontSize = 11;
            caption.VerticalAlignment = VerticalAlignment.Center;
            if (active) AutomationProperties.SetItemStatus(caption, "Current step");
            item.Children.Add(caption);
            steps.Children.Add(item);
        }
        var header = new Grid { ColumnSpacing = 16 };
        header.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
        header.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        if (dialog.Title is string { Length: > 0 } title)
        {
            var copy = new StackPanel { Spacing = 4, VerticalAlignment = VerticalAlignment.Center };
            var heading = Prefs.Label(title, "ForgeHeadingTextStyle");
            heading.FontSize = 20;
            heading.TextWrapping = TextWrapping.Wrap;
            copy.Children.Add(heading);
            if (description is not null) copy.Children.Add(Prefs.Label(description, "ForgeDimTextStyle"));
            header.Children.Add(copy);
            AutomationProperties.SetName(dialog, title);
            dialog.Title = null;
        }
        var pill = new Border
        {
            Child = steps, Padding = new Thickness(18, 6, 18, 6), MinHeight = 34, CornerRadius = new CornerRadius(17),
            Background = (Brush)Application.Current.Resources["ControlFillColorDefaultBrush"],
            HorizontalAlignment = HorizontalAlignment.Right, VerticalAlignment = VerticalAlignment.Center,
        };
        Grid.SetColumn(pill, 1);
        header.Children.Add(pill);
        var radius = (CornerRadius)Application.Current.Resources["OverlayCornerRadius"];
        body.Children.Add(new Border
        {
            Child = header, Padding = new Thickness(inset, 14, inset, 14),
            Margin = new Thickness(-inset, -inset, -inset, 0),
            CornerRadius = new CornerRadius(radius.TopLeft, radius.TopRight, 0, 0),
            Background = (Brush)Application.Current.Resources["ControlFillColorSecondaryBrush"],
        });
        body.Children.Add(content);
        return body;
    }

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
        SetWidth(dialog, 560, 640);
        cancel = new CancellationTokenSource();
        dialog.Title = ProgressVerb();
        dialog.PrimaryButtonText = "";
        dialog.SecondaryButtonText = "";
        dialog.CloseButtonText = preparedReview is null ? "Cancel" : "";
        progressPanel.AccentChanged += TintButtons;
        dialog.Content = WithSteps(progressPanel.Root, FlowStep.Apply);
        progressPanel.Show(ProgressVerb(), review!.Ready.FirstOrDefault()?.Game, 0, review.Ready.Count, "Starting");

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
                // Uncounted engine steps keep the panel's last count (see StepCount).
                var steps = new Progress<PrepareProgress>(step => progressPanel.Show(ProgressVerb(),
                    review.Ready.FirstOrDefault(item => item.Game.Name == step.Game)?.Game,
                    step.Checked, step.Total > 0 ? step.Total : null, step.Label));
                var result = await shell.Service.RunReviewAsync(pending, steps);
                preparedReview = null;
                completed = result.Errors.Count == 0;
                progressPanel.Complete();
                ShowDone(completed, result.Message + (result.Errors.Count > 0 ? "\n\n" + string.Join("\n", result.Errors) : ""));
                return;
            }
            var count = await shell.ExecuteAsync(review!.AcknowledgeOffline(offlineAcknowledged), progress, cancel.Token);
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
        "install-nr-addons" => "Installing Split Render",
        "remove-nr-addons" => "Removing Split Render",
        "uninstall" => "Restoring",
        "update-dlss" => "Updating",
        "update-overlays" => "Updating",
        _ => "Applying",
    };

    /// <summary>The current game's accent on the dialog's suggested button (Linux button.suggested-action).</summary>
    void TintButtons(Services.AccentPalette palette)
    {
        if (stage != Stage.Progress) return;
        dialog.Resources["AccentButtonBackground"] = palette.AccentBrush;
        dialog.Resources["AccentButtonBackgroundPointerOver"] = palette.Brush(palette.Color, 0.9);
        dialog.Resources["AccentButtonBackgroundPressed"] = palette.Brush(palette.Color, 0.8);
        dialog.Resources["AccentButtonForeground"] = palette.Brush(palette.AccentFg);
        dialog.Resources["AccentButtonForegroundPointerOver"] = palette.Brush(palette.AccentFg);
        dialog.Resources["AccentButtonForegroundPressed"] = palette.Brush(palette.AccentFg);
    }
    // ---------- Done (finish_progress) ----------

    internal static void UseDoneButton(ContentDialog dialog)
    {
        var settings = App.Main!.Settings;
        var color = AccentResources.Resolve(settings.DesktopAccentSource, settings.DesktopAccentColor);
        AccentResources.Apply(dialog.Resources, ArtAccent.Palette(color));
        var button = new Style(typeof(Button)) { BasedOn = Prefs.GetStyle("AccentButtonStyle") };
        button.Setters.Add(new Setter(FrameworkElement.HorizontalAlignmentProperty, HorizontalAlignment.Right));
        button.Setters.Add(new Setter(FrameworkElement.MinWidthProperty, 0.0));
        button.Setters.Add(new Setter(Control.PaddingProperty, new Thickness(18, 6, 18, 6)));
        dialog.PrimaryButtonStyle = button;
        dialog.PrimaryButtonText = "Done";
        dialog.IsPrimaryButtonEnabled = true;
        dialog.DefaultButton = ContentDialogButton.None;
        dialog.DefaultButton = ContentDialogButton.Primary;
    }

    void ShowDone(bool success, string message, string? title = null)
    {
        stage = Stage.Done;
        SetWidth(dialog, 420, 560);
        dialog.SecondaryButtonText = "";
        dialog.Title = null;
        AutomationProperties.SetName(dialog, title ?? (success ? "Done" : "Could not finish"));
        var line = new Grid { ColumnSpacing = 24 };
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
        UseDoneButton(dialog);
    }
}
