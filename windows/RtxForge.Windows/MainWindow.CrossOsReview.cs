#if DEBUG
using System.Text.Json;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using RtxForge.Windows.Controls;
using RtxForge.Windows.Models;

namespace RtxForge.Windows;

public sealed partial class MainWindow
{
    // Opt-in real WinUI binding/layout checks with sample games only. Never saves settings or executes operations.
    async void StartCrossOsReview()
    {
        var destination = Environment.GetEnvironmentVariable("RTXFORGE_CROSS_OS_REVIEW");
        if (!Service.IsPreview || string.IsNullOrWhiteSpace(destination) || !Path.IsPathFullyQualified(destination)) return;
        Settings.InMemoryReview = true;
        var checks = new List<object>();
        void Check(string criterion, bool pass) { checks.Add(new { criterion, pass }); }
        IEnumerable<DependencyObject> Tree(DependencyObject parent)
        {
            for (var i = 0; i < VisualTreeHelper.GetChildrenCount(parent); i++)
            {
                var child = VisualTreeHelper.GetChild(parent, i);
                yield return child;
                foreach (var nested in Tree(child)) yield return nested;
            }
        }
        try
        {
            var sample = Games.First(g => g.Installed);
            sample.InstalledOn = "linux";
            sample.InstalledOses = ["windows", "linux"];
            Query = ""; Settings.LibraryFilter = "all";
            foreach (var theme in new[] { "dark", "light" })
            {
                Settings.Theme = theme;
                Services.ThemeController.Apply(this, RootGrid, theme);
                foreach (var layout in new[] { "posters", "capsules", "list" })
                {
                    Settings.LibraryView = layout;
                    SettingsChanged?.Invoke(); NotifyGamesChanged();
                    Navigate("Library"); await Task.Delay(450);
                    var marks = Tree(ContentFrame).OfType<OsMarks>().Where(m => m.Oses?.Count == 2).ToArray();
                    Check(theme + "_" + layout + "_both_marks_render", marks.Length > 0 && marks.All(m => m.Children.Count == 2 && m.ActualWidth > m.MarkSize * 2));
                }
                Navigate("Game", new GameRequest(sample, "overview")); await Task.Delay(450);
                Check(theme + "_details_both_marks_render", Tree(ContentFrame).OfType<OsMarks>().Any(m => m.Children.Count == 2 && m.ActualWidth > 20));
                Check(theme + "_details_native_actions", !sample.InstalledOnLinux && !Tree(ContentFrame).OfType<TextBlock>().Any(t => t.Text == "Installed on Linux"));

            }
            Settings.LibraryView = "posters"; SettingsChanged?.Invoke(); Navigate("Library"); await Task.Delay(400);
            // Native Game Mode has its own cross-platform UI and adapter checks.

        }
        catch (Exception error) { checks.Add(new { criterion = "native_review_error", pass = false, detail = error.ToString() }); }
        File.WriteAllText(destination, JsonSerializer.Serialize(new { process_id = Environment.ProcessId, checks }, new JsonSerializerOptions { WriteIndented = true }));
    }
}
#endif
