using System.Text.Json.Nodes;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using RtxForge.Windows.Models;
using RtxForge.Windows.Services;

namespace RtxForge.Windows.Controls;

public sealed class OverlayUiReviewView : StackPanel
{
    readonly EngineForgeService service;
    readonly Button action = new() { Content = "Review installed games", HorizontalAlignment = HorizontalAlignment.Stretch, MinHeight = 44 };
    readonly StackPanel rows = new() { Spacing = 10 };
    readonly TextBlock status = new() { TextWrapping = TextWrapping.Wrap, FontSize = 12 };
    EngineReview? review;
    bool busy;
    int generation;
    public OverlayUiReviewView(EngineForgeService engine)
    {
        service = engine; Spacing = 12;
        Children.Add(new TextBlock { Text = "Saved choices are used for future installs. Review installed games to update their menus and intro messages too.", TextWrapping = TextWrapping.Wrap, FontSize = 12 });
        Children.Add(rows); Children.Add(status); Children.Add(action);
        action.Click += async (_, _) => await Run();
        Unloaded += (_, _) => Invalidate();
    }
    public void Invalidate()
    {
        generation++;
        if (review is not null) service.DiscardReview(review);
        review = null; rows.Children.Clear(); status.Text = ""; action.Content = "Review installed games";
    }
    async Task Run()
    {
        if (busy) return;
        busy = true; action.IsEnabled = false;
        var started = generation;
        try
        {
            if (review is null)
            {
                action.Content = "Reviewing games…";
                var s = ForgeSettings.Load();
                review = await service.ReviewOverlayUiAsync(s.GameUiOptions(), new Progress<PrepareProgress>(p =>
                {
                    if (started == generation && IsLoaded) status.Text = p.Label;
                }));
                if (started != generation || !IsLoaded) { service.DiscardReview(review); review = null; return; }
                rows.Children.Clear();
                void Group(string label, IReadOnlyList<ReviewItem> items, bool collapsed = false)
                {
                    if (items.Count == 0) return;
                    var group = new StackPanel { Spacing = 10 };
                    foreach (var item in items)
                    {
                        var line = new Grid { ColumnSpacing = 12 };
                        line.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
                        line.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
                        var row = new StackPanel { Spacing = 3 };
                        row.Children.Add(new TextBlock { Text = item.Title, FontWeight = Microsoft.UI.Text.FontWeights.SemiBold, TextWrapping = TextWrapping.Wrap });
                        row.Children.Add(new TextBlock { Text = item.Detail, FontSize = 12, TextWrapping = TextWrapping.Wrap });
                        line.Children.Add(row);
                        if (!string.IsNullOrWhiteSpace(item.Details))
                        {
                            var info = TechnicalDetails.Create(item.Details); Grid.SetColumn(info, 1); line.Children.Add(info);
                        }
                        group.Children.Add(line);
                    }
                    if (collapsed) rows.Children.Add(new Expander { Header = $"{label} · {items.Count}", Content = group,
                        HorizontalAlignment = HorizontalAlignment.Stretch, HorizontalContentAlignment = HorizontalAlignment.Stretch });
                    else
                    {
                        rows.Children.Add(new TextBlock { Text = $"{label} · {items.Count}", FontWeight = Microsoft.UI.Text.FontWeights.SemiBold });
                        rows.Children.Add(group);
                    }
                }
                Group("Ready", review.Items);
                Group("Needs attention", review.Blocked);
                Group("Unchanged or unavailable", review.Skipped, collapsed: true);
                status.Text = review.Summary + " Restart updated games to use these choices.";
                action.Content = review.Items.Count > 0 ? "Apply to games" : "Review installed games";
                if (review.Items.Count == 0) { service.DiscardReview(review); review = null; }
            }
            else
            {
                var pending = review; review = null; action.Content = "Applying…";
                var result = await service.RunReviewAsync(pending);
                if (started != generation || !IsLoaded) return;
                rows.Children.Clear(); status.Text = result.Message + " Takes effect next launch."; action.Content = "Review installed games";
            }
        }
        catch (Exception error) { Invalidate(); status.Text = error.Message; }
        finally { busy = false; action.IsEnabled = true; }
    }
}
