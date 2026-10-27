#if DEBUG
using System.Text.Json;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;

namespace RtxForge.Windows.GameMode;

public sealed partial class GameModeView
{
    // Uses WinUI's actual hit-test tree; no input injection or game operations.
    async void StartPointerReview()
    {
        var path = Environment.GetEnvironmentVariable("RTXFORGE_POINTER_REVIEW");
        if (!shell.Service.IsPreview || string.IsNullOrWhiteSpace(path) || !Path.IsPathFullyQualified(path)) return;
        var checks = new List<object>();
        try
        {
            await Task.Delay(700);
            OpenMainMenu();
            await Task.Delay(350);
            foreach (var button in Descendants(modals.Peek().Element).OfType<Button>())
            {
                var point = button.TransformToVisual(root).TransformPoint(new(button.ActualWidth / 2, button.ActualHeight / 2));
                var hits = VisualTreeHelper.FindElementsInHostCoordinates(point, root).ToList();
                checks.Add(new { criterion = "menu_button_accepts_pointer", label = string.Join(" ", Descendants(button).OfType<TextBlock>().Select(t => t.Text)),
                    pass = hits.Any(hit => ReferenceEquals(hit, button)), enabled = button.IsEnabled,
                    hits = hits.Select(hit => hit.GetType().Name).ToArray() });
            }
            CloseModal();
        }
        catch (Exception error) { checks.Add(new { criterion = "pointer_review_error", pass = false, detail = error.ToString() }); }
        File.WriteAllText(path, JsonSerializer.Serialize(new { process_id = Environment.ProcessId, checks }, new JsonSerializerOptions { WriteIndented = true }));
    }
}
#endif
