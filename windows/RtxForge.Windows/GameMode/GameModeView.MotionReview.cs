#if DEBUG
using System.Diagnostics;
using System.Text.Json;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;

namespace RtxForge.Windows.GameMode;

public sealed partial class GameModeView
{
    // Opt-in native integration harness. Preview service only; it never invokes game operations.
    async void StartMotionReview()
    {
        var destination = Environment.GetEnvironmentVariable("RTXFORGE_MOTION_REVIEW");
        if (!shell.Service.IsPreview || string.IsNullOrWhiteSpace(destination) || !System.IO.Path.IsPathFullyQualified(destination)) return;
        var assertions = new List<object>();
        var frames = new List<object>();
        var actionTimes = new List<object>();
        var phase = "startup";
        var timer = Stopwatch.StartNew();
        double previous = 0;
        var originalView = shell.Settings.LibraryView;
        var originalMotion = shell.Settings.ReduceMotion;
        var originalTheme = shell.Settings.Theme;
        var originalGameTheme = shell.Settings.GameModeTheme;
        var originalThemeLink = shell.Settings.GameModeThemeLinked;
        void Frame(object? sender, object args)
        {
            var now = timer.Elapsed.TotalMilliseconds;
            if (previous > 0) frames.Add(new { phase, at_ms = now, interval_ms = now - previous });
            previous = now;
        }
        void Check(string criterion, bool pass, object? detail = null) => assertions.Add(new { criterion, pass, detail });
        async Task Settle(int milliseconds = 300) => await Task.Delay(milliseconds);
        async Task Move(string direction, int count, int interval)
        {
            for (var i = 0; i < count; i++)
            {
                var inputStarted = Stopwatch.GetTimestamp();
                Handle(direction, true);
                actionTimes.Add(new { phase, action = direction, milliseconds = Stopwatch.GetElapsedTime(inputStarted).TotalMilliseconds });
                Check("direction_keeps_focus", FocusManager.GetFocusedElement(XamlRoot) is Control, direction);
                await Settle(interval);
            }
        }
        CompositionTarget.Rendering += Frame;
        try
        {
            await Settle(700);
            phase = "first-visit-card-focus";
            shell.Settings.LibraryView = "posters"; Open("library"); await Settle();
            Check("initial_selection_surfaces_measured", ui.SelectionSurfacesMeasured);
            for (var rebuild = 0; rebuild < 3; rebuild++)
            {
                Render(keepFocus: true); await Settle(90);
                Check("same_geometry_rebuild_keeps_selection_surface", ui.SelectionSurfacesMeasured, rebuild);
            }
            var first = Descendants(body).OfType<Button>().First(b => b.Name.StartsWith("gm_game-"));
            first.Focus(FocusState.Keyboard); await Settle(200);
            Check("native_contact_initialized", GmMotion.Initialized(first));
            var name = first.Name; var offset = libraryScroller?.VerticalOffset ?? 0;
            var originalWidth = first.ActualWidth;
            phase = "rapid-reversal";
            await Move("right", 18, 35); await Move("left", 18, 35);
            Check("focus_scale_does_not_relayout", Math.Abs(first.ActualWidth - originalWidth) < .01);
            phase = "details-and-back";
            first.Focus(FocusState.Keyboard); Activate(first); await Settle();
            Check("details_opens_without_input_gate", page == "details");
            Handle("back", true); await Settle();
            Check("back_restores_card", (FocusManager.GetFocusedElement(XamlRoot) as FrameworkElement)?.Name == name);
            Check("back_restores_scroll", Math.Abs((libraryScroller?.VerticalOffset ?? 0) - offset) < 2);
            phase = "tabs";
            foreach (var target in new[] { "presets", "packages", "extras", "settings", "library" })
            {
                Open(target); await Settle(180);
                Check("page_has_live_focus", FocusManager.GetFocusedElement(XamlRoot) is Control, target);
            }
            phase = "rapid-tab-handoff";
            foreach (var target in new[] { "extras", "presets", "library", "settings", "packages", "library" })
            {
                Open(target); await Settle(35);
                Check("rapid_tab_keeps_current_page", page == target);
                Check("outgoing_surfaces_are_bounded", body.Children.Count <= 2);
                Check("rapid_tab_focus_is_live", FocusManager.GetFocusedElement(XamlRoot) is Control { IsEnabled: true });
            }
            await Settle(180);
            Check("outgoing_surface_is_released", body.Children.Count == 1);
            phase = "menu-rows-and-trap";
            OpenMainMenu(); await Settle(180);
            await Move("down", 5, 45); await Move("up", 5, 45);
            Check("modal_traps_focus", modals.Count == 1 && !pageHost.IsEnabled);
            CloseModal(); await Settle(180);
            Check("modal_releases_focus", modals.Count == 0 && pageHost.IsEnabled);
            phase = "long-list";
            var rows = Enumerable.Range(0, 240).Select(i => (UIElement)ui.RowButton($"Review row {i + 1}", null, () => { })).ToList();
            var scroll = new ScrollViewer { Content = ui.Group(rows), MaxHeight = t.Px(500), HorizontalScrollMode = ScrollMode.Disabled };
            PolishScroll(scroll);
            ShowModal("Motion regression", scroll, [ui.Button("Back", CloseModal)], CloseModal);
            await Settle(220);
            Check("long_list_virtualizes_native_templates", Descendants(scroll).OfType<Button>().Count() < 60);
            await Move("down", 45, 25); await Move("up", 24, 25);
            Check("long_list_keeps_focus", FocusManager.GetFocusedElement(XamlRoot) is Control);
            Check("long_list_scrolled", scroll.VerticalOffset > 0, scroll.VerticalOffset);
            CloseModal(); await Settle();
            phase = "layouts-and-input-methods";
            foreach (var layout in new[] { "capsules", "list", "posters" })
            {
                SetLibraryView(layout, persist: false); await Settle(35);
                Check("layout_selector_restores_live_incoming_control", FocusManager.GetFocusedElement(XamlRoot) is Button { IsEnabled: true } live && live.Name == "gm_view-" + layout);
                await Settle(165);
                await Move("down", 3, 55); SetInput("keyboard"); await Settle(100); ControllerActivity();
                Check("input_change_keeps_focus", FocusManager.GetFocusedElement(XamlRoot) is Control, layout);
            }
            phase = "theme-isolation";
            shell.Settings.Theme = "dark"; shell.Settings.LinkGameModeTheme(false); shell.Settings.SetGameModeTheme("night"); ApplySettings();
            Check("game_mode_theme_is_independent", t.Name == "night" && shell.Settings.Theme == "dark");
            shell.Settings.Theme = "light"; ApplySettings();
            Check("desktop_theme_does_not_recolor_game_mode", t.Name == "night");
            shell.Settings.LinkGameModeTheme(true); ApplySettings();
            Check("theme_relink_follows_desktop", t.Name == "light");
            phase = "reduced-motion-and-themes";
            shell.Settings.ReduceMotion = true;
            foreach (var theme in new[] { "night", "dark", "light" })
            {
                shell.Settings.Theme = theme; ApplySettings(); await Settle(200);
                await Move("right", 3, 40);
                Check("reduced_motion_keeps_focus", !GmMotion.Enabled && FocusManager.GetFocusedElement(XamlRoot) is Control, theme);
            }
            phase = "settled-idle";
            await Settle(1200);
        }
        catch (Exception error) { Check("unhandled_native_review_error", false, error.ToString()); }
        finally
        {
            CompositionTarget.Rendering -= Frame;
            shell.Settings.LibraryView = originalView; shell.Settings.ReduceMotion = originalMotion; shell.Settings.Theme = originalTheme; shell.Settings.GameModeTheme = originalGameTheme; shell.Settings.GameModeThemeLinked = originalThemeLink;
            CloseAllModals(); page = "library"; ApplySettings();
            var report = new { generated_at = DateTimeOffset.UtcNow, process_id = Environment.ProcessId,
                window_dips = new { width = ActualWidth, height = ActualHeight }, rasterization_scale = XamlRoot.RasterizationScale,
                measure = "UI Rendering callback intervals; not GPU-present or scanout frame times", assertions, frames, actionTimes };
            System.IO.File.WriteAllText(destination, JsonSerializer.Serialize(report, new JsonSerializerOptions { WriteIndented = true }));
        }
    }
}
#endif
