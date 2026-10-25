using Microsoft.UI.Text;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using RtxForge.Windows.Models;
using RtxForge.Windows.Services;
using RtxForge.Windows.ViewModels;

namespace RtxForge.Windows.GameMode;

/// <summary>
/// Operations in Game Mode: optional presets (Cancel/Continue) → engine review
/// (ready and skipped targets) → progress (poster, status, Cancel) → done.
/// The same IForgeService review/execute as the desktop; nothing is written
/// before the user confirms the review.
/// </summary>
public sealed partial class GameModeView
{
    /// <summary>Runs after the reviewed operation completes; each operation sets or clears it.</summary>
    Action? whenCompleted;

    async Task RunOperationAsync(string operation, IReadOnlyList<Game> targets, Tuning? values = null, Action? completed = null)
    {
        whenCompleted = completed;
        if (shell.Busy) { Toast("Another operation is running."); return; }
        ArgumentNullException.ThrowIfNull(targets);
        if (targets.Count == 0) { Toast("No eligible games."); return; }
        if ((operation == "uninstall" || operation == "install" && targets.All(g => g.AdoptionAvailable)) && targets.Any(g => g.AdoptionAvailable))
        {
            // Another tool's setup: installing only such games offers Adoption's choices; in a group install
            // the engine adopts them in the same review. Restore has nothing of rtxForge's to undo.
            var adoptable = targets.Where(g => g.AdoptionAvailable).ToArray();
            if (operation == "install") await shell.ReviewAdoptionAsync(adoptable);
            else Toast(MainWindow.AdoptionSkipped(adoptable.Length));
            targets = targets.Where(g => !g.AdoptionAvailable).ToArray();
            if (targets.Count == 0) return;
        }
        // One game: its accent on every screen of the flow, as in its Details.
        await UseGameAccentAsync(Controls.AccentResources.Single(targets));
        if (operation == "install" && values is null)
        {
            values = await AskPresetsAsync(targets.Count == 1 ? shell.GameTuning(targets[0]) : shell.Settings.Presets, GameOverview.Mode(targets, shell.Mode));
            if (values is null) return;
        }
        values ??= shell.Settings.Presets;

        // Checking: the engine verifies every target; nothing is written.
        var step = new GmStep(this);
        var cancelChecking = ui.Button("Cancel", CloseModal, GmKind.Card, 0.92);
        ShowModal(ReviewTitle(operation), step.Root, [cancelChecking], CloseModal, 1100, cancelChecking);
        var checkingModal = modals.Peek();
        step.Show("Checking", targets[0], 0, null, "Checking game files");
        OperationReview review;
        try
        {
            var progress = new Progress<PrepareProgress>(p => step.Show("Checking",
                targets.FirstOrDefault(g => g.Name == p.Game), p.Checked, p.Total > 0 ? p.Total : null, p.Label));
            review = await shell.Service.PrepareAsync(operation, targets, values, shell.Mode, progress);
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or InvalidOperationException)
        {
            if (modals.Count > 0 && ReferenceEquals(modals.Peek(), checkingModal)) CloseModal();
            ShowDone(false, "Could not check these games", error.Message);
            return;
        }
        if (modals.Count == 0 || !ReferenceEquals(modals.Peek(), checkingModal))
        { shell.Service.DiscardOperation(review); return; }   // cancelled while checking
        CloseModal();
        ShowReview(operation, review);
    }

    Services.AccentPalette? modalPalette;

    async Task UseGameAccentAsync(Game? game) =>
        UseGameAccent(game is null ? null : await ArtAccent.ForGameAsync(game));

    /// <summary>Primary buttons, toggles and WinUI accent controls follow this palette; null restores the theme's.</summary>
    void UseGameAccent(Services.AccentPalette? palette)
    {
        modalPalette = palette;
        if (palette is null) { (ui.Accent, ui.AccentInk) = (GmTheme.Accent, GmTheme.AccentInk); return; }
        var colors = t.GameColors(palette);
        (ui.Accent, ui.AccentInk) = (colors.Accent, colors.Ink);
    }

    static string ReviewTitle(string operation) => operation switch
    {
        "install" => "Review Installation",
        "uninstall" => "Review Restoration",
        "update-dlss" => "Review DLSS Update",
        _ => "Review Presets",
    };

    static string Verb(string operation) => operation switch
    {
        "install" => "Install", "uninstall" => "Restore", "update-dlss" => "Update", _ => "Apply",
    };

    static string Doing(string operation) => operation switch
    {
        "install" => "Installing", "uninstall" => "Restoring", "update-dlss" => "Updating", _ => "Applying",
    };

    Task<Tuning?> AskPresetsAsync(Tuning initial, string mode)
    {
        var done = new TaskCompletionSource<Tuning?>();
        var (rows, value) = PresetRows(initial, legacy: shell.Settings.RuntimeProvider != "skynizz", embedded: true,
            dynamicSupported: shell.Settings.DynamicMfgSupported, installation: true, mode: mode);
        var content = new StackPanel { Spacing = t.Px(20) };
        content.Children.Add(ui.P($"{ProviderName()} · Choose startup settings. You can adjust them later.", 0.8));
        if (shell.Settings.RuntimeProvider != "feeder")
        {
            var editor = new StackPanel { Spacing = t.Px(28) };
            foreach (var row in rows) editor.Children.Add(row);
            content.Children.Add(editor);
        }
        var startup = new CheckBox { Content = "Enable NR on launch", IsChecked = shell.Settings.NrOnLaunch };
        var separateStartup = shell.Settings.RuntimeProvider != "skynizz";
        if (separateStartup && mode != "mfg-only") content.Children.Add(startup);
        void Cancel() { CloseModal(); done.TrySetResult(null); }
        var cancel = ui.Button("Cancel", Cancel, GmKind.Card, 0.92);
        var next = ui.Button("Review games", () => { CloseModal(); done.TrySetResult(separateStartup ? value() with { NrOnLaunch = startup.IsChecked == true } : value()); }, GmKind.Primary, 0.92);
        ShowModal("Install Features", content, [cancel, next], Cancel, 1120, cancel);
        return done.Task;
    }

    void ShowReview(string operation, OperationReview review)
    {
        var content = new StackPanel { Spacing = t.Px(20) };
        var summary = new StackPanel { Spacing = t.Px(10) };
        // One list for every package: games that get only part of the selection show what they get.
        var games = review.AllGames;
        var count = games.Count;
        var mixed = review.Steps.Count > 1 || review.Supported.Count > 0;
        summary.Children.Add(ui.H2(count > 0 ? $"{count} game{(count == 1 ? "" : "s")} ready" : "Nothing ready yet", 1.3));
        if (operation == "install") summary.Children.Add(ui.P(shell.Settings.RuntimeProvider == "feeder" || (count > 0 && !mixed && review.Ready.All(r => r.Game.IsFeeder))
            ? "NR Only · Feeder NR" : mixed ? ModeLabel() : $"{ModeLabel()} · {ProviderName()}"));
        content.Children.Add(summary);

        var list = new StackPanel();
        var group = new List<UIElement>();
        foreach (var (item, part) in games)
            group.Add(ReviewRow(item.Game, item.Game.Name, part is null ? item.Summary : item.Summary + "\n" + part.Reason, true, item.Detail,
                part?.Badge ?? (operation == "install" && item.Game.AdoptionAvailable ? "Adopt" : null)));
        if (group.Count > 0) list.Children.Add(ui.Group(group, t.Card));
        foreach (var warning in review.Warnings)
        {
            var note = new StackPanel { Spacing = t.Px(6), Margin = new Thickness(0, t.Px(18), 0, 0) };
            note.Children.Add(ui.Heading("Warning · " + warning.Name, 0.82, t.Danger));
            note.Children.Add(ui.Text(warning.Reason, 0.74, t.Fg, wrap: true));
            list.Children.Add(note);
        }
        if (review.Blocked.Count > 0)
        {
            list.Children.Add(ui.Heading($"Skipped · {review.Blocked.Count}", 0.88).With(x => x.Margin = new Thickness(0, t.Px(26), 0, t.Px(14))));
            list.Children.Add(ui.Group(review.Blocked.Select(b => (UIElement)ReviewRow(b.Game, b.Name, b.Summary ?? b.Reason, false,
                b.Summary is null ? null : b.Reason)), t.Card));
        }
        var scroll = new ScrollViewer { Content = list, MaxHeight = t.Px(t.Compact ? 260 : 380), HorizontalScrollMode = ScrollMode.Disabled };
        content.Children.Add(scroll);
        content.Children.Add(ui.P("Your files only change after you confirm.", 0.8));
        void Dismiss() { shell.Service.DiscardOperation(review); CloseModal(); }
        var cancel = ui.Button("Cancel", Dismiss, GmKind.Card, 0.92);
        var go = ui.Button(Verb(operation), () =>
        {
            CloseModal();
            _ = ExecuteAsync(operation, review.Supported.Count > 0 ? review.IncludeSupported() : review);
        }, GmKind.Primary, 0.92, enabled: count > 0);
        ShowModal(ReviewTitle(operation), content, [cancel, go], Dismiss, 1100, cancel);
    }

    string ModeLabel() => shell.Mode switch { "nr-only" => "NR Only", "nr-mfg" => "NR + MFG", _ => "MFG Only" };

    Grid ReviewRow(Game? game, string name, string detail, bool ready, string? technical = null, string? state = null)
    {
        var row = new Grid { ColumnSpacing = t.Px(22), Padding = new Thickness(t.Px(22), t.Px(18), t.Px(22), t.Px(18)) };
        row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        var thumb = new Border
        {
            Width = t.Px(128), Height = t.Px(60), CornerRadius = new CornerRadius(t.Px(9)), BorderThickness = new Thickness(t.Px(2)),
            BorderBrush = GmTheme.B(t.Line), Background = GmTheme.B(t.Panel),
        };
        if (game is not null && GameItem.Image(game.CapsulePath ?? game.PosterPath) is { } image)
            thumb.Child = new Border { CornerRadius = new CornerRadius(t.Px(7)), Background = new ImageBrush { ImageSource = image, Stretch = Stretch.UniformToFill } };
        row.Children.Add(thumb);
        var text = new StackPanel { Spacing = t.Px(6), VerticalAlignment = VerticalAlignment.Center };
        var title = ui.Heading(name, 0.9, t.Fg);
        text.Children.Add(title);
        text.Children.Add(ui.Text(detail, 0.72, t.Muted, wrap: true));
        if (!string.IsNullOrWhiteSpace(technical))
        {
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            var info = Controls.TechnicalDetails.Create(technical, t.Px(1), () =>
            {
                var diagnostic = ui.Text(technical, .72, wrap: true); diagnostic.IsTextSelectionEnabled = true;
                ShowModal("Details", diagnostic, [ui.Button("Close", CloseModal, GmKind.Card, .85)], CloseModal, 900);
            });
            info.Style = (Style)Application.Current.Resources["GmButtonStyle"];
            info.Foreground = GmTheme.B(t.Fg); ui.Focusable(info);
            Grid.SetColumn(info, 3); row.Children.Add(info);
        }
        Grid.SetColumn(text, 1);
        row.Children.Add(text);
        var badge = ui.Badge(state ?? (ready ? "Ready" : "Skipped"), t.Panel, ready ? t.Fg : t.Danger, 0.7);
        Grid.SetColumn(badge, 2);
        row.Children.Add(badge);
        if (ready && game is not null) _ = ReviewAccentAsync(game, thumb, title, badge);
        return row;
    }

    async Task ReviewAccentAsync(Game game, Border thumb, TextBlock title, Border badge)
    {
        var colors = t.GameColors(await ArtAccent.ForGameAsync(game));
        thumb.BorderBrush = GmTheme.B(colors.Accent);
        title.Foreground = GmTheme.B(colors.Title);
        badge.Background = GmTheme.B(colors.Tint);
        if (badge.Child is StackPanel line) foreach (var c in line.Children.OfType<TextBlock>()) c.Foreground = GmTheme.B(colors.TintText);
        if (t.IsLight) BadgeTheme.AttachLight(badge, colors.Accent);
    }

    async Task ExecuteAsync(string operation, OperationReview review)
    {
        var step = new GmStep(this);
        var cts = new CancellationTokenSource();
        Button? cancel = null;
        cancel = ui.Button("Cancel", () => { cts.Cancel(); cancel!.IsEnabled = false; step.Show(Doing(operation), null, 0, null, "Cancelling and undoing changes"); }, GmKind.Card, 0.92);
        // Busy-operation protection: Back does not dismiss a running operation.
        ShowModal(null, step.Root, [cancel], () => { }, 1100, cancel);
        step.Show(Doing(operation), review.Ready.FirstOrDefault()?.Game, 0, review.Ready.Count, "Starting");
        var progress = new Progress<OperationStep>(s => step.Show(Doing(operation), s.Game, s.Index, s.Total, s.Caption, s.Fraction));
        try
        {
            var count = await shell.ExecuteAsync(review, progress, cts.Token);
            step.Complete();
            CloseModal();
            whenCompleted?.Invoke();
            ShowDone(true, "Done", $"{count} game{(count == 1 ? "" : "s")} updated.");
        }
        catch (OperationCanceledException)
        {
            CloseModal();
            ShowDone(false, "Cancelled", "Changes to the games in progress were undone.");
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or InvalidOperationException)
        {
            CloseModal();
            ShowDone(false, "Could not finish", error.Message);
        }
        finally { whenCompleted = null; shell.Service.DiscardOperation(review); }
    }

    void ShowDone(bool success, string title, string message)
    {
        var line = new Grid { ColumnSpacing = t.Px(32) };
        line.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        line.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        line.Children.Add(ui.Icon(success ? "" : "", 2.6, success ? t.Fg : t.Danger).With(i => i.VerticalAlignment = VerticalAlignment.Center));
        var text = new StackPanel { Spacing = t.Px(12), VerticalAlignment = VerticalAlignment.Center };
        text.Children.Add(ui.H2(title, 1.3));
        text.Children.Add(ui.P(message));
        Grid.SetColumn(text, 1);
        line.Children.Add(text);
        var ok = ui.Button("Done", CloseModal, GmKind.Card, 0.92);
        ShowModal(null, line, [ok], CloseModal, 1100, ok);
    }

    /// <summary>The prototype's progress layout: accent poster, counter, game in accent, phase, accent bar.</summary>
    sealed class GmStep
    {
        readonly GameModeView view;
        readonly Border poster = new();
        readonly TextBlock counter, title, phase;
        readonly ProgressBar bar = new() { Minimum = 0, Maximum = 1, IsIndeterminate = true };
        Game? current;
        public Grid Root { get; } = new();

        public GmStep(GameModeView view)
        {
            this.view = view;
            var t = view.t;
            var ui = view.ui;
            var compact = view.ActualWidth <= 1050;
            Root.ColumnSpacing = t.Px(compact ? 24 : 40);
            Root.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            Root.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            var height = t.Px(t.Compact ? 225 : compact ? 225 : view.ActualWidth <= 1500 ? 270 : 330);
            poster.Height = height;
            poster.Width = Math.Round(height * 2 / 3);
            poster.CornerRadius = new CornerRadius(t.Px(12));
            poster.BorderThickness = new Thickness(t.Px(3));
            poster.BorderBrush = GmTheme.B(t.Line);
            poster.Background = GmTheme.B(t.Card);
            Root.Children.Add(poster);
            var right = new StackPanel { Spacing = t.Px(12), VerticalAlignment = VerticalAlignment.Center };
            counter = ui.Text("Preparing…", 0.85, t.Muted);
            title = ui.Heading("", 1.3, t.Fg);
            phase = ui.Text("", 0.85, t.Muted);
            bar.MinHeight = t.Px(12);
            bar.Background = GmTheme.B(t.Card);
            bar.Foreground = GmTheme.B(GmTheme.Accent);
            bar.CornerRadius = new CornerRadius(t.Px(8));
            bar.Margin = new Thickness(0, t.Px(18), 0, t.Px(10));
            right.Children.Add(counter);
            right.Children.Add(title);
            right.Children.Add(phase);
            right.Children.Add(bar);
            Grid.SetColumn(right, 1);
            Root.Children.Add(right);
        }

        public void Show(string verb, Game? game, int index, int? total, string phaseText, double? fraction = null)
        {
            counter.Text = total is > 0 ? $"{verb} {Math.Min(index + 1, total.Value)} of {total}" : "Preparing…";
            if (!string.IsNullOrEmpty(phaseText)) phase.Text = phaseText.TrimEnd('.', '…') + "…";
            if (total is > 0) { bar.IsIndeterminate = false; bar.Value = Math.Clamp(fraction ?? (double)index / total.Value, 0, 1); }
            else bar.IsIndeterminate = true;
            if (game is null || ReferenceEquals(game, current)) return;
            current = game;
            title.Text = game.Name;
            poster.Child = GameItem.Image(game.PosterPath ?? game.CapsulePath) is { } image
                ? new Border { CornerRadius = new CornerRadius(view.t.Px(9)), Background = new ImageBrush { ImageSource = image, Stretch = Stretch.UniformToFill } }
                : null;
            _ = AccentAsync(game);
        }

        public void Complete() { bar.IsIndeterminate = false; bar.Value = 1; }

        async Task AccentAsync(Game game)
        {
            var colors = view.t.GameColors(await ArtAccent.ForGameAsync(game));
            if (!ReferenceEquals(game, current)) return;
            poster.BorderBrush = GmTheme.B(colors.Accent);
            title.Foreground = GmTheme.B(colors.Title);
            bar.Foreground = GmTheme.B(colors.Accent);
        }
    }
}
