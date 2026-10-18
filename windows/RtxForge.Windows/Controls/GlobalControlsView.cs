using System.Text.Json.Nodes;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using RtxForge.Windows.Models;
using RtxForge.Windows.Services;

namespace RtxForge.Windows.Controls;

/// <summary>A one-time batch, reviewed against the currently installed packages.</summary>
public sealed class GlobalControlsView : StackPanel
{
    readonly EngineForgeService service;
    readonly ComboBox nr = new() { Header = "Neural rendering", ItemsSource = new[] { "Leave as is", "Off", "On" }, SelectedIndex = 0, HorizontalAlignment = HorizontalAlignment.Stretch };
    readonly ComboBox mfg = new() { Header = "Frame generation", ItemsSource = new[] { "Leave as is", "Off", "2×", "3×", "4×", "5×", "6×", "Follow game" }, SelectedIndex = 0, HorizontalAlignment = HorizontalAlignment.Stretch };
    readonly StackPanel entries = new() { Spacing = 12 };
    readonly TextBlock feedback = new() { TextWrapping = TextWrapping.Wrap };
    readonly Button apply = new() { Content = "Review changes", HorizontalAlignment = HorizontalAlignment.Stretch, Height = 44 };
    readonly ProgressBar progress = new() { IsIndeterminate = true, Visibility = Visibility.Collapsed };
    EngineReview? review;
    bool busy;

    public GlobalControlsView(EngineForgeService engine)
    {
        service = engine; Spacing = 20;
        Children.Add(new TextBlock { Text = "Change installed games together. Choose only the controls you want to change; everything else stays as it is.", FontSize = 13, TextWrapping = TextWrapping.Wrap });
        Children.Add(nr); Children.Add(mfg);
        Children.Add(new TextBlock { Text = "Feeder games support NR only. Close running games before applying. This won’t change defaults for future installs.", FontSize = 12, Opacity = .8, TextWrapping = TextWrapping.Wrap });
        Children.Add(progress); Children.Add(entries); Children.Add(feedback); Children.Add(apply);
        nr.SelectionChanged += (_, _) => Invalidate(); mfg.SelectionChanged += (_, _) => Invalidate();
        apply.Click += async (_, _) => await RunAsync();
        Unloaded += (_, _) => { if (review is not null) { service.DiscardReview(review); review = null; } };
        Invalidate();
    }
    void Invalidate()
    {
        if (review is not null) service.DiscardReview(review);
        review = null; entries.Children.Clear(); feedback.Text = ""; apply.Content = "Review changes";
        apply.IsEnabled = !busy && (nr.SelectedIndex != 0 || mfg.SelectedIndex != 0);
    }
    static StackPanel Entry(ReviewItem item)
    {
        var entry = new StackPanel { Spacing = 4 };
        entry.Children.Add(new TextBlock { Text = item.Title, FontWeight = Microsoft.UI.Text.FontWeights.SemiBold, TextWrapping = TextWrapping.Wrap });
        entry.Children.Add(new TextBlock { Text = item.Detail, FontSize = 12, Opacity = .8, TextWrapping = TextWrapping.Wrap });
        if (!string.IsNullOrEmpty(item.Details))
            entry.Children.Add(new TextBlock { Text = item.Details, FontSize = 11, Opacity = .65, TextWrapping = TextWrapping.Wrap });
        return entry;
    }
    async Task RunAsync()
    {
        if (busy) return;
        busy = true;
        apply.IsEnabled = nr.IsEnabled = mfg.IsEnabled = false; progress.Visibility = Visibility.Visible;
        var phases = new Progress<PrepareProgress>(p =>
        {
            if (!busy || !IsLoaded) return;
            feedback.Text = p.Total > 0 ? $"{p.Label} · {p.Checked} of {p.Total}\n{p.Game}" : p.Label;
        });
        try
        {
            if (review is null)
            {
                var changes = new JsonObject();
                if (nr.SelectedIndex > 0) changes["nr"] = nr.SelectedIndex == 2;
                if (mfg.SelectedIndex > 0) changes["mfg"] = mfg.SelectedIndex == 1 ? 0 : mfg.SelectedIndex == 7 ? -1 : mfg.SelectedIndex;
                apply.Content = "Reviewing…"; feedback.Text = "Checking installed games…";
                review = await service.ReviewGlobalControlsAsync(changes, phases);
                if (!IsLoaded) { service.DiscardReview(review); review = null; return; }
                feedback.Text = review.Summary;
                entries.Children.Clear();
                if (review.Items.Count > 0)
                {
                    entries.Children.Add(new TextBlock { Text = $"Ready · {review.Items.Count}", FontWeight = Microsoft.UI.Text.FontWeights.SemiBold });
                    foreach (var item in review.Items) entries.Children.Add(Entry(item));
                }
                if (review.Blocked.Count > 0)
                {
                    entries.Children.Add(new TextBlock { Text = $"Needs attention · {review.Blocked.Count}", FontWeight = Microsoft.UI.Text.FontWeights.SemiBold });
                    foreach (var item in review.Blocked) entries.Children.Add(Entry(item));
                }
                if (review.Skipped.Count > 0)
                {
                    var skipped = new StackPanel { Spacing = 12 };
                    foreach (var item in review.Skipped) skipped.Children.Add(Entry(item));
                    entries.Children.Add(new Expander { Header = $"Unchanged or unavailable · {review.Skipped.Count}", Content = skipped,
                        HorizontalAlignment = HorizontalAlignment.Stretch, HorizontalContentAlignment = HorizontalAlignment.Stretch });
                }
                apply.Content = review.Ready ? "Apply to games" : "Review again";
                if (!review.Ready) { service.DiscardReview(review); review = null; }
            }
            else
            {
                var pending = review; review = null;
                entries.Children.Clear(); apply.Content = "Applying…"; feedback.Text = "Verifying reviewed games…";
                var result = await service.RunReviewAsync(pending, phases);
                await service.ReloadCompanionPresetsAsync();
                await OverlayHelper.CommandAsync("reload-presets", start: false);
                feedback.Text = result.Message; entries.Children.Clear(); apply.Content = "Review changes";
            }
        }
        catch (Exception error) { feedback.Text = error.Message; if (review is not null) service.DiscardReview(review); review = null; apply.Content = "Review changes"; }
        finally { busy = false; nr.IsEnabled = mfg.IsEnabled = true; apply.IsEnabled = nr.SelectedIndex != 0 || mfg.SelectedIndex != 0; progress.Visibility = Visibility.Collapsed; }
    }
}
