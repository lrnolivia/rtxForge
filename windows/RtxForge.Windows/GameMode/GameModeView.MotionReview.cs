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
        var modalOnly = Environment.GetEnvironmentVariable("RTXFORGE_MODAL_FOCUS_REVIEW") == "1";
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
        void Check(string criterion, bool pass, object? detail = null)
        {
            assertions.Add(new { criterion, pass, detail });
            File.WriteAllText(destination + ".progress.json", JsonSerializer.Serialize(new { process_id = Environment.ProcessId, phase, criterion, count = assertions.Count }));
        }
        void ExceptionTrace(object? sender, System.Runtime.ExceptionServices.FirstChanceExceptionEventArgs e)
        {
            if (e.Exception.HResult != unchecked((int)0x80070005)) return;
            File.AppendAllText(destination + ".exceptions.log", phase + Environment.NewLine + e.Exception + Environment.NewLine);
        }
        async Task Settle(int milliseconds = 560) => await Task.Delay(milliseconds);
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
        AppDomain.CurrentDomain.FirstChanceException += ExceptionTrace;
        try
        {
            await Settle(1800);
            for (var attempt = 0; attempt < 100 && !shell.ControllerInputForeground; attempt++) await Settle(100);
            if (!shell.ControllerInputForeground) throw new InvalidOperationException("Native review requires the preview window in the foreground.");
            if (!modalOnly)
            {
            var rowEdge = ui.RowButton("Boundary check", null, () => { });
            Check("row_focus_stroke_on_surface_edge", rowEdge.FocusVisualMargin.Equals(new Thickness(0)));
            var cardMaterial = t.Surface(t.Card);
            var navigationMaterial = t.Surface(t.Panel, navigation: true);
            var originalOpacity = t.CardOpacity;
            var dialogMaterial = t.DialogSurface();
            t.SetCardOpacity(65);
            Check("dialog_tint_is_independent_of_card_slider", dialogMaterial.TintOpacity == .95 && dialogMaterial.Opacity == 1);
            Check("card_material_updates_live_with_navbar_offset", cardMaterial.Opacity == 1 && navigationMaterial.Opacity == 1
                && cardMaterial.TintOpacity == .65 && navigationMaterial.TintOpacity == .5);
            var sidebarHighlight = t.Highlight(GmTheme.Accent, fixedTint: true);
            t.SetCardOpacity(10);
            Check("sidebar_highlight_is_independent_of_card_slider", sidebarHighlight.Surface.TintOpacity == .5 && sidebarHighlight.Surface.Opacity == 1);
            t.SetCardOpacity(originalOpacity);
            var selectionLine = new StackPanel { Orientation = Orientation.Horizontal };
            var selectedButton = ui.Button("Selected", null, GmKind.Active);
            selectionLine.Children.Add(selectedButton);
            new GmUi(t).Selection("review-first-frame", selectionLine, selectedButton, true);
            Check("selection_has_fill_before_first_layout", selectedButton.Background is SolidColorBrush { Color.A: > 0 });
            foreach (var theme in new[] { "night", "dark", "light" }.Select(GmTheme.For))
                foreach (var color in new[] { theme.Card, theme.Active, theme.DangerBg, GmTheme.Accent, GmTheme.Hex("#2d6eb0") })
                {
                    var hover = GmTheme.HoverColors(color);
                    Check("hover_fill_and_ink_have_readable_contrast", Services.ArtAccent.Contrast(hover.Surface, hover.Ink) >= 4.5,
                        new { theme.Name, color, hover });
                }
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
                Open(target); await Settle(80);
                var moving = body.Children.OfType<PageSurface>().Last();
                Check("glows_stay_outside_slide_capture", !Descendants(moving.Motion).OfType<ArtworkLightLayer>().Any()
                    && ReferenceEquals(moving.Light.Parent, moving) && ReferenceEquals(moving.Light.Artwork.Parent, moving));
                Check("new_glows_wait_for_surface_to_settle", moving.Light.Opacity == 0 && moving.Light.Artwork.Opacity == 0);
                await Settle(480);
                Check("glows_return_after_surface_settles", moving.Light.Opacity == 1 && moving.Light.Artwork.Opacity == 1);
                Check("page_has_live_focus", FocusManager.GetFocusedElement(XamlRoot) is Control, target);
            }
            phase = "controller-content-and-tabs";
            Open("library"); await Settle();
            Check("library_is_explicit_scroll_target", ReferenceEquals(mainScroller, libraryScroller));
            foreach (var target in new[] { "presets", "packages", "extras", "settings", "library" })
            {
                Handle("next", true); await Settle(180);
                Check("bumper_cycles_main_tabs", page == target, new { target, page });
            }
            Handle("previous", true); await Settle();
            Check("left_bumper_wraps_main_tabs", page == "settings");
            Open("library"); await Settle();
            first = Descendants(body).OfType<Button>().First(b => b.Name.StartsWith("gm_game-"));
            first.Focus(FocusState.Keyboard); Activate(first); await Settle();
            var detailScroll = mainScroller;
            var sideScroll = Descendants(body).OfType<ScrollViewer>().FirstOrDefault(s => !ReferenceEquals(s, detailScroll) && s.Content is StackPanel);
            var beforeSide = sideScroll?.VerticalOffset;
            var beforeFocus = FocusManager.GetFocusedElement(XamlRoot);
            var beforeContent = detailScroll?.VerticalOffset ?? 0;
            ScrollMainView(300); await Settle(100);
            Check("right_stick_scrolls_details_content", detailScroll is { ScrollableHeight: > 0 } && detailScroll.VerticalOffset > beforeContent);
            Check("right_stick_leaves_sidebar_and_focus", beforeSide == sideScroll?.VerticalOffset && ReferenceEquals(beforeFocus, FocusManager.GetFocusedElement(XamlRoot)));
            Handle("next", true); await Settle();
            Check("details_bumper_leaves_for_presets", page == "presets");
            OpenMainMenu(); await Settle();
            Handle("next", true); ScrollMainView(200); await Settle();
            Check("modal_blocks_background_tab_and_scroll", page == "presets" && modals.Count == 1);
            CloseModal();
            Open("library"); await Settle();
            phase = "rapid-tab-handoff";
            foreach (var target in new[] { "extras", "presets", "library", "settings", "packages", "library" })
            {
                Open(target); await Settle(35);
                Check("rapid_tab_keeps_current_page", page == target);
                Check("outgoing_surfaces_are_bounded", body.Children.Count <= 2);
                Check("rapid_tab_focus_is_live", FocusManager.GetFocusedElement(XamlRoot) is Control { IsEnabled: true });
            }
            await Settle(560);
            Check("outgoing_surface_is_released", body.Children.Count == 1);
            phase = "menu-rows-and-trap";
            OpenMainMenu(); await Settle(180);
            await Move("down", 5, 45); await Move("up", 5, 45);
            Check("modal_traps_focus", modals.Count == 1 && !pageHost.IsEnabled);
            CloseModal(); await Settle(180);
            Check("modal_releases_focus", modals.Count == 0 && pageHost.IsEnabled);
            }
            phase = "long-list";
            var rows = Enumerable.Range(0, 240).Select(i => (UIElement)ui.RowButton($"Review row {i + 1}", null, () => { })).ToList();
            var scroll = new ScrollViewer { Content = ui.Group(rows), MaxHeight = t.Px(500), HorizontalScrollMode = ScrollMode.Disabled };
            PolishScroll(scroll);
            ShowModal("Motion regression", scroll, [ui.Button("Back", CloseModal)], CloseModal);
            await Settle(220);
            Check("long_list_starts_on_a_row", FocusManager.GetFocusedElement(XamlRoot) is Button focusedRow
                && Descendants(scroll).Contains(focusedRow),
                new { focus = FocusManager.GetFocusedElement(XamlRoot)?.GetType().Name, rows = Descendants(scroll).OfType<Button>().Count() });
            Check("long_list_virtualizes_native_templates", Descendants(scroll).OfType<Button>().Count() < 60);
            await Move("down", 45, 25); await Move("up", 24, 25);
            Check("long_list_keeps_focus", FocusManager.GetFocusedElement(XamlRoot) is Control);
            Check("long_list_scrolled", scroll.VerticalOffset > 0, scroll.VerticalOffset);
            CloseModal(); await Settle();
            if (modalOnly) return;
            phase = "layouts-and-input-methods";
            foreach (var layout in new[] { "capsules", "list", "posters" })
            {
                SetLibraryView(layout, persist: false); await Settle(35);
                Check("layout_selector_restores_live_incoming_control", FocusManager.GetFocusedElement(XamlRoot) is Button { IsEnabled: true } live && live.Name == "gm_view-" + layout,
                    new { layout, page, actual = (FocusManager.GetFocusedElement(XamlRoot) as FrameworkElement)?.Name,
                        target = (FindByKey(body, "gm_view-" + layout) as Control)?.IsLoaded });
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
                foreach (var layout in new[] { "posters", "capsules", "list" })
                {
                    SetLibraryView(layout, persist: false); await Settle(80);
                    var selectedLayout = FindByKey(body, "gm_view-" + layout) as Button;
                    Check("selected_layout_keeps_native_fill", selectedLayout?.Background is SolidColorBrush { Color.A: 255 }, new { theme, layout });
                    Check("selected_tab_keeps_native_fill", tabButtons.First(b => b.Name == "gm_tab-library").Background is SolidColorBrush { Color.A: 255 }, theme);
                }
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
            AppDomain.CurrentDomain.FirstChanceException -= ExceptionTrace;
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
