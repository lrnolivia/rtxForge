using Microsoft.UI.Text;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation.Peers;
using Microsoft.UI.Xaml.Automation.Provider;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using RtxForge.Windows.Models;
using Windows.System;

namespace RtxForge.Windows.GameMode;

/// <summary>
/// Windows Game Mode: the approved controller-first design (MagicPath
/// radiant-rock-8795) as native WinUI. A full-screen view inside the main
/// window with the same engine, library, artwork and accents as the desktop.
///
///   header   brand (main menu) · LB  Library  Presets  Settings  RB
///   body     the current page (Library, Details, Presets, Settings)
///   footer   controller / keyboard hints and context help
///   modal    one dialog at a time; traps focus and restores it on close
/// </summary>
public sealed partial class GameModeView : UserControl
{
    readonly MainWindow shell;
    readonly FocusVisualKind desktopFocusKind = Application.Current.FocusVisualKind;
    GmTheme t;
    GmUi ui;

    readonly Grid root = new();
    readonly AppHeroBackdrop appHero = new();
    readonly ArtworkLightLayer artworkLight = new();
    ArtworkLightLayer pageLight = new();
    readonly Grid pageGrid = new();
    readonly ContentControl pageHost = new()
    {
        IsTabStop = false, HorizontalContentAlignment = HorizontalAlignment.Stretch, VerticalContentAlignment = VerticalAlignment.Stretch,
    };
    readonly Grid header = new();
    readonly Grid body = new();
    ScrollViewer? mainScroller;
    readonly Grid footer = new();
    readonly Grid bottomNav = new();
    readonly Grid modalLayer = new() { Visibility = Visibility.Collapsed };
    readonly Border toastHost = new() { Visibility = Visibility.Collapsed, HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Bottom };
    readonly Microsoft.UI.Dispatching.DispatcherQueueTimer toastTimer;

    string page = "library";          // library · presets · packages · extras · settings · details
    string inputKind = "keyboard";    // keyboard · controller: drives hint glyphs
    string family = "xbox";
    string detectedFamily = "xbox";
    DateTime lastControllerInput;
    global::Windows.Foundation.Point? pointerPosition;
    double PageInset => t.Px(ActualWidth <= 1050 ? 32 : ActualWidth <= 1500 ? 48 : 64);
    readonly Stack<Modal> modals = new();

    sealed record Modal(UIElement Element, Action OnBack, DependencyObject? Restore);

    /// <summary>The user chose Desktop UI (main menu or Settings › Interface).</summary>
    public event Action? ExitRequested;

    public GameModeView(MainWindow shell)
    {
        this.shell = shell;
        GmMotion.ReducedMotion = () => shell.Settings.ReduceMotion;
        FontFamily = GmUi.BodyFont;
        t = GmTheme.For(shell.Settings.ResolvedGameModeTheme);
        t.SetCardOpacity(shell.Settings.GameModeCardOpacity);
        t.Scale = shell.Settings.UiScaleKey;
        ui = new GmUi(t) { ArtworkLight = artworkLight };
        Content = root;
        // Page (header, body, bottom navigation) sits in one ContentControl so a
        // dialog can disable it as a whole: the focus trap behind modals.
        pageGrid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        pageGrid.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
        pageGrid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        pageGrid.Children.Add(header);
        Grid.SetRow(body, 1);
        pageGrid.Children.Add(body);
        Grid.SetRow(bottomNav, 2);
        pageGrid.Children.Add(bottomNav);
        pageHost.Content = pageGrid;
        root.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
        root.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        Grid.SetRowSpan(appHero, 2);
        root.Children.Add(appHero);
        Grid.SetRowSpan(artworkLight.Artwork, 2);
        root.Children.Add(artworkLight.Artwork);
        root.Children.Add(pageHost);
        Grid.SetRowSpan(artworkLight, 2);
        // Controller/keyboard hint bar stays (A Select · B Back · Y Library); dialogs sit above it.
        Grid.SetRow(footer, 1);
        root.Children.Add(footer);
        root.Children.Add(modalLayer);
        root.Children.Add(artworkLight);
        root.Children.Add(toastHost);

        // Arrow keys move focus spatially, exactly like the D-pad.
        XYFocusKeyboardNavigation = XYFocusKeyboardNavigationMode.Enabled;
        TabFocusNavigation = KeyboardNavigationMode.Cycle;
        KeyDown += OnKeyDown;
        // WinUI also turns D-pad/stick into key events that move focus natively; with
        // GamepadInput that moved focus twice and skipped rows. One source only.
        PreviewKeyDown += (_, e) =>
        {
            if (e.Key is VirtualKey.GamepadRightThumbstickUp or VirtualKey.GamepadRightThumbstickDown)
            {
                shell.NativeRightStick(e.Key == VirtualKey.GamepadRightThumbstickUp, true);
                ControllerActivity(); e.Handled = true; return;
            }
            if (e.Key is VirtualKey.GoBack or VirtualKey.GoForward && shell.ControllerLegacyInputActive)
            { Handle(e.Key == VirtualKey.GoBack ? "previous" : "next", true); e.Handled = true; return; }
            if (e.Key >= VirtualKey.GamepadA && e.Key <= VirtualKey.GamepadRightThumbstickLeft)
            {
                ControllerActivity();
                if (!shell.ControllerPollingAvailable)
                {
                    if (e.Key == VirtualKey.GamepadLeftShoulder) Handle("previous", true);
                    if (e.Key == VirtualKey.GamepadRightShoulder) Handle("next", true);
                }
                e.Handled = true;
            }
        };
        PreviewKeyUp += (_, e) =>
        {
            if (e.Key is not (VirtualKey.GamepadRightThumbstickUp or VirtualKey.GamepadRightThumbstickDown)) return;
            shell.NativeRightStick(e.Key == VirtualKey.GamepadRightThumbstickUp, false); e.Handled = true;
        };
        XYFocusUpNavigationStrategy = XYFocusDownNavigationStrategy = XYFocusLeftNavigationStrategy = XYFocusRightNavigationStrategy =
            XYFocusNavigationStrategy.Projection;
        PointerMoved += (_, e) =>
        {
            var position = e.GetCurrentPoint(this).Position;
            var previous = pointerPosition; pointerPosition = position;
            if (previous is { } before && DateTime.UtcNow - lastControllerInput > TimeSpan.FromMilliseconds(500)
                && Math.Abs(position.X - before.X) + Math.Abs(position.Y - before.Y) >= 3)
                SetInput("keyboard");
        };
        PointerPressed += (_, _) => SetInput("keyboard");
        SizeChanged += (_, e) =>
        {
            appHero.Apply(t, page != "details", e.NewSize.Width, e.NewSize.Height);
            if (t.Resize(e.NewSize.Width, e.NewSize.Height)) Render(keepFocus: true);
        };

        toastTimer = DispatcherQueue.CreateTimer();
        toastTimer.Interval = TimeSpan.FromSeconds(4);
        toastTimer.Tick += (_, _) => { toastTimer.Stop(); toastHost.Visibility = Visibility.Collapsed; };

        var stopObservingMotion = GmMotion.ObservePreferences(this);
        shell.GamesChanged += OnGamesChanged;
        Unloaded += (_, _) => { shell.NativeRightStick(true, false); shell.NativeRightStick(false, false); stopObservingMotion(); shell.GamesChanged -= OnGamesChanged; Application.Current.FocusVisualKind = desktopFocusKind; };
        Loaded += (_, _) =>
        {
            Application.Current.FocusVisualKind = FocusVisualKind.Reveal; t.Resize(ActualWidth, ActualHeight); Render();
#if DEBUG
            StartMotionReview();
            StartPointerReview();
#endif
        };
    }

    void OnGamesChanged()
    {
        selectedIds.IntersectWith(shell.Games.Select(g => g.Id));
        if (detailsGame is { } current)
        {
            detailsGame = shell.Games.FirstOrDefault(g => g.Id == current.Id);
            if (detailsGame is null) page = "library";
        }
        if (modals.Count == 0) Render(keepFocus: true);
    }

    /// <summary>Theme or appearance changed in Settings.</summary>
    public void ApplySettings()
    {
        var size = (ActualWidth, ActualHeight);
        t = GmTheme.For(shell.Settings.ResolvedGameModeTheme);
        t.SetCardOpacity(shell.Settings.GameModeCardOpacity);
        t.Scale = shell.Settings.UiScaleKey;
        t.Resize(size.ActualWidth, size.ActualHeight);
        ui = new GmUi(t) { ArtworkLight = artworkLight };
        Render(keepFocus: true);
    }

    // ---------- Rendering ----------

    int renderRevision;
    bool entrancePending = true;
    bool entranceThisRender;
    bool changingPageThisRender;
    string? lastLibraryLayout;
    sealed class PageSurface : Grid
    {
        public Grid Motion { get; } = new();
        public ArtworkLightLayer Light { get; }
        public PageSurface(Grid scene, ArtworkLightLayer light)
        {
            Light = light; Motion.Children.Add(scene);
            Children.Add(light.Artwork); Children.Add(Motion); Children.Add(light);
        }
        public void HideLight() { Light.Opacity = 0; Light.Artwork.Opacity = 0; }
    }

    void SlideSurface(Grid surface, ArtworkLightLayer light, int direction)
    {
        var revision = renderRevision;
        light.Opacity = 0; light.Artwork.Opacity = 0;
        GmMotion.Horizontal(surface, direction, t.S, completed: () =>
        {
            if (revision != renderRevision || !light.IsLoaded) return;
            light.RefreshPositions();
            GmMotion.GlowArrival(light.Artwork); GmMotion.GlowArrival(light);
        });
    }

    void Render(bool keepFocus = false)
    {
        var revision = ++renderRevision;
        var previousPage = lastRenderedPage;
        var changingPage = previousPage is not null && previousPage != page;
        changingPageThisRender = changingPage;
        entranceThisRender = entrancePending && IsLoaded;
        var direction = ControllerNavigation.PageDirection(previousPage, page);
        var changingLayout = page == "library" && previousPage == "library" && lastLibraryLayout != shell.Settings.LibraryView;
        if (changingLayout)
        {
            string[] layouts = ["posters", "capsules", "list"];
            direction = Array.IndexOf(layouts, shell.Settings.LibraryView) < Array.IndexOf(layouts, lastLibraryLayout) ? -1 : 1;
        }
        var changingContent = changingPage || changingLayout;
        lastLibraryLayout = shell.Settings.LibraryView;
        lastRenderedPage = page;
        var focusedName = keepFocus ? FocusKey(FocusManager.GetFocusedElement(XamlRoot) as DependencyObject) : null;
        var requestedFocus = pendingFocusKey;
        pendingFocusKey = null;
        initialFocus = null;
        root.RequestedTheme = t.IsLight ? ElementTheme.Light : ElementTheme.Dark;
        ui.FocusBrush.Color = t.Focus;
        root.Background = GmTheme.B(page == "details" ? t.Window : t.View);
        appHero.Apply(t, page != "details", ActualWidth, ActualHeight);
        // Pages keep the theme's accent, even while a flow about one game is open.
        var (accent, accentInk) = (ui.Accent, ui.AccentInk);
        (ui.Accent, ui.AccentInk) = (GmTheme.Accent, GmTheme.AccentInk);
        ui.ArtworkLight = artworkLight;
        ui.SelectionGlowDelay = changingContent ? GmMotion.SlideArrival : 0;
        RenderHeader();
        // Retain at most one outgoing surface. New controls receive focus immediately.
        while (body.Children.Count > 1) body.Children.RemoveAt(0);
        var departing = changingContent && GmMotion.Enabled ? body.Children.LastOrDefault() as FrameworkElement : null;
        if (departing is null) body.Children.Clear();
        else { departing.IsHitTestVisible = false; foreach (var oldControl in Descendants(departing).OfType<Control>()) oldControl.IsEnabled = false; }
        pageLight = new ArtworkLightLayer { ControllerFocus = inputKind == "controller" };
        ui.ArtworkLight = pageLight;
        mainScroller = null;
        body.Background = page == "details" ? GmTheme.B(t.View) : null;
        var content = page switch
        {
            "details" when detailsGame is not null => BuildDetails(detailsGame),
            "presets" => BuildPresets(),
            "packages" => BuildPackages(),
            "extras" => BuildExtras(),
            "settings" => BuildSettings(),
            _ => BuildLibrary(),
        };
        if (content is FrameworkElement contentElement)
            contentElement.Loaded += (_, _) => { foreach (var scroll in Descendants(content).OfType<ScrollViewer>()) GmScrollFade.Attach(scroll, t.S); };
        (ui.Accent, ui.AccentInk) = (accent, accentInk);
        var scene = new Grid();
        scene.Children.Add(content);
        var surface = new PageSurface(scene, pageLight); body.Children.Add(surface);
        ui.ArtworkLight = artworkLight;
        if (departing is PageSurface oldSurface)
        {
            oldSurface.HideLight();
            GmMotion.Horizontal(oldSurface.Motion, direction, t.S, outgoing: true,
                completed: () => { if (body.Children.Contains(oldSurface)) body.Children.Remove(oldSurface); });
        }
        if (changingContent)
        {
            SlideSurface(surface.Motion, surface.Light, direction);
        }
        else if (entranceThisRender)
        {
            GmMotion.Reveal(header, 0, t.S);
            GmMotion.Page(content, t.S);
            GmMotion.Reveal(footer, 5, t.S);
            entrancePending = false;
        }
        RenderFooter();
        // Focus: keep the same control when re-rendering, else the page's first target.
        void RestorePageFocus()
        {
            if (revision != renderRevision || modals.Count > 0) return;
            surface.UpdateLayout();
            // Library: restore the scroll position first, so focusing only nudges it into view.
            if (page == "library" && libraryScroller is { } scroller) { scroller.UpdateLayout(); scroller.ChangeView(null, libraryScroll, null, true); }
            Control? Current(string key) => FindByKey(scene, key) ?? FindByKey(header, key) ?? FindByKey(bottomNav, key);
            var target = (requestedFocus is not null ? Current(requestedFocus) : null)
                         ?? (focusedName is not null ? Current(focusedName) : null)
                         ?? initialFocus ?? FirstFocusable(scene) ?? tabButtons.FirstOrDefault(b => b.Name == "gm_tab-" + page);
            initialFocus = null;
            (target as Control)?.Focus(FocusState.Keyboard);
            artworkLight.RefreshPositions();
            pageLight.RefreshPositions();
        }
        void Ready(object sender, RoutedEventArgs args)
        {
            surface.Loaded -= Ready;
            DispatcherQueue.TryEnqueue(RestorePageFocus);
        }
        if (surface.IsLoaded) DispatcherQueue.TryEnqueue(RestorePageFocus);
        else surface.Loaded += Ready;
    }

    Control? initialFocus;
    /// <summary>Focus target by key, resolved after the page renders (controls do not exist before).</summary>
    string? pendingFocusKey;

    readonly List<Button> tabButtons = [];
    string? lastRenderedPage;
    readonly Dictionary<string, string> renderedSections = [];
    FrameworkElement AnimateSection(string area, string key, FrameworkElement content)
    {
        var wrapper = new Grid(); wrapper.Children.Add(content);
        if (!changingPageThisRender && renderedSections.TryGetValue(area, out var previous) && previous != key)
        {
            var order = area == "settings" ? SettingsSections : Sections;
            var direction = Array.IndexOf(order, key) < Array.IndexOf(order, previous) ? -1 : 1;
            SlideSurface(wrapper, pageLight, direction);
        }
        renderedSections[area] = key;
        return wrapper;
    }

    public void AnimateExit(Action completed) => GmMotion.Exit(root, t.S, completed);

    void RenderHeader()
    {
        var tight = t.HeaderDensity > 0;
        header.Children.Clear();
        header.ColumnDefinitions.Clear();
        header.Background = page == "details" ? GmTheme.B(t.Window) : null;
        header.Height = t.Px(t.Compact ? 92 : 114);
        header.Margin = new Thickness(0, t.Px(12), 0, 0);
        header.Padding = new Thickness(t.Px(56), t.Px(t.Compact ? 10 : 14), t.Px(56), t.Px(t.Compact ? 10 : 14));
        header.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        header.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        header.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });

        // Branding is informational. The menu has its own explicit control.
        var brand = new StackPanel { Orientation = Orientation.Horizontal, Spacing = t.Px(tight ? 10 : 16),
            HorizontalAlignment = HorizontalAlignment.Left, VerticalAlignment = VerticalAlignment.Center, IsHitTestVisible = false };
        brand.Children.Add(new Image
        {
            Source = new Microsoft.UI.Xaml.Media.Imaging.SvgImageSource(new Uri("ms-appx:///Assets/rtxforge-mark.svg")),
            Width = t.Px(tight ? 40 : t.Compact ? 48 : 64), Height = t.Px(tight ? 40 : t.Compact ? 48 : 64),
        });
        if (t.HeaderDensity < 2) brand.Children.Add(new TextBlock
        {
            Text = "rtxForge", FontSize = t.Em(tight ? 1.2 : t.Compact ? 1.4 : 1.62), VerticalAlignment = VerticalAlignment.Center,
            FontFamily = (FontFamily)Application.Current.Resources["ForgeHeroFontFamily"], Foreground = GmTheme.B(t.Fg),
        });
        header.Children.Add(brand);
        var menu = ui.Button(ui.Icon("", .95), OpenMainMenu, GmKind.Transparent, radius: 12,
            padding: new Thickness(t.Px(14)), minHeight: 48, name: "Main menu");
        menu.HorizontalAlignment = HorizontalAlignment.Right;
        menu.VerticalAlignment = VerticalAlignment.Center;
        ToolTipService.SetToolTip(menu, "Main menu");
        Key(menu, "menu");
        Grid.SetColumn(menu, 2);
        header.Children.Add(menu);

        var tabs = BuildTabs();
        if (shell.Settings.NavigationPosition == "bottom")
        {
            bottomNav.Children.Clear();
            bottomNav.Background = page == "details" ? GmTheme.B(t.View) : null;
            bottomNav.Padding = new Thickness(0, t.Px(8), 0, t.Px(18));
            bottomNav.Children.Add(tabs);
            bottomNav.Visibility = Visibility.Visible;
        }
        else
        {
            bottomNav.Visibility = Visibility.Collapsed;
            Grid.SetColumn(tabs, 1);
            header.Children.Add(tabs);
        }
    }

    Border BuildTabs()
    {
        tabButtons.Clear();
        var tight = t.HeaderDensity > 0;
        var line = new StackPanel { Orientation = Orientation.Horizontal, Spacing = t.Px(tight ? 8 : 12) };
        foreach (var (key, label, glyph) in new[] { ("library", "Library", "\uE7FC"), ("presets", "Presets", "\uE9F5"),
            ("packages", "Packages", "\uE7B8"), ("extras", "Extras", "\uE90F"), ("settings", "Settings", "\uE713") })
        {
            var active = page == key || (key == "library" && page == "details");
            var caption = ui.IconLabel(glyph, label, 12);
            var icon = (FontIcon)caption.Children[0];
            icon.FontSize = t.Em(1.08); icon.Width = t.Px(28);
            var tab = ui.Button(caption, () => Open(key), active ? GmKind.Active : GmKind.Transparent, .92, radius: 32,
                padding: new Thickness(t.Px(tight ? 16 : 24), t.Px(12), t.Px(tight ? 16 : 24), t.Px(12)), minHeight: t.Compact ? 52 : 60);
            Key(tab, "tab-" + key);
            tabButtons.Add(tab);
            line.Children.Add(tab);
        }
        return GmUi.Capsule(new Border
        {
            Background = t.Surface(t.Panel, navigation: true), CornerRadius = new CornerRadius(t.Px(40)), Padding = new Thickness(t.Px(t.Compact ? 8 : 10)),
            Child = ui.Selection("navigation", line, tabButtons.First(b => b.Name == "gm_tab-" + (page == "details" ? "library" : page)), true), HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center,
        });
    }

    readonly StackPanel hintsPanel = new() { Orientation = Orientation.Horizontal };
    Microsoft.UI.Dispatching.DispatcherQueueTimer? hintTimer;

    /// <summary>
    /// The controller / keyboard hint bar (prototype .rf-footer): the button
    /// glyphs only. The help sentences ("Arrows navigate · Tab moves focus…",
    /// "D-pad moves between games…") are contextual tips instead.
    /// </summary>
    void RenderFooter()
    {
        footer.Visibility = Visibility.Visible;
        footer.Children.Clear();
        footer.Background = GmTheme.B(t.Window);
        footer.MinHeight = t.Px(t.Compact ? 48 : 58);
        footer.Padding = new Thickness(PageInset, t.Px(8), PageInset, t.Px(8));
        hintsPanel.Children.Clear();
        hintsPanel.Spacing = t.Px(30);
        hintsPanel.VerticalAlignment = VerticalAlignment.Center;
        var keyboard = inputKind == "keyboard";
        var (accept, back, library, _) = GamepadInput.Glyphs(family);
        var acceptLabel = page == "library" && modals.Count == 0 && !selecting ? "Game Details" : "Select";
        foreach (var (key, label, action) in new[]
        {
            (keyboard ? "Enter" : accept, acceptLabel, "accept"),
            (keyboard ? "Esc" : back, "Back", "back"),
            (keyboard ? "Ctrl+L" : library, "Library", "search"),
        })
        {
            if (action == "search" && modals.Count > 0) continue;
            var pair = new StackPanel { Orientation = Orientation.Horizontal, Spacing = t.Px(10) };
            pair.Children.Add(keyboard ? ui.Key(key) : ui.ControllerKey(family, action));
            pair.Children.Add(ui.Text(label, 0.85).With(x => x.VerticalAlignment = VerticalAlignment.Center));
            var hint = ui.Button(pair, () => Handle(action), GmKind.Transparent, 1, radius: 8, padding: new Thickness(t.Px(2)), minHeight: 0);
            hint.Background = GmTheme.B(Microsoft.UI.Colors.Transparent);
            hint.BorderThickness = new Thickness(0);
            hint.Style = (Style)Application.Current.Resources["GmBareButtonStyle"];
            hint.IsTabStop = false;
            hintsPanel.Children.Add(hint);
        }
        footer.Children.Add(hintsPanel);
        WakeHints();
    }

    /// <summary>Settings › Controller hints › Hide when idle fades the bar after 3.5 s without input.</summary>
    void WakeHints()
    {
        hintsPanel.Opacity = 1;
        if (hintTimer is null)
        {
            hintTimer = DispatcherQueue.CreateTimer();
            hintTimer.Interval = TimeSpan.FromSeconds(3.5);
            hintTimer.Tick += (_, _) => { hintTimer.Stop(); hintsPanel.Opacity = 0; };
        }
        hintTimer.Stop();
        if (shell.Settings.ControllerHints == "auto") hintTimer.Start();
    }

    // ---------- Navigation ----------

    void Open(string target)
    {
        CloseAllModals();
        if (target != "details") detailsGame = target == "library" ? detailsGame : detailsGame;
        page = target;
        Render();
    }

    void CycleTab(int direction)
    {
        if (modals.Count > 0 || choiceMenu is not null) return;
        var target = ControllerNavigation.NextTab(page, direction);
        pendingFocusKey = "gm_tab-" + target;
        Open(target);
    }

    /// <summary>Scroll the active content, regardless of header or sidebar focus.</summary>
    public void ScrollMainView(double delta)
    {
        if (choiceMenu is not null || !double.IsFinite(delta)) return;
        var scroll = modals.Count > 0
            ? Descendants(modals.Peek().Element).OfType<ScrollViewer>().FirstOrDefault(s => s.ScrollableHeight > 0)
            : mainScroller;
        if (scroll is null || scroll.XamlRoot is null) return;
        ControllerActivity();
        var requested = Math.Clamp(scroll.VerticalOffset + t.Px(delta), 0, scroll.ScrollableHeight);
        ControllerDiagnostics.View(page, scroll.VerticalOffset, requested, scroll.ScrollableHeight);
        scroll.ChangeView(null, requested, null, true);
    }

    void Back()
    {
        if (modals.Count > 0) { modals.Peek().OnBack(); return; }
        switch (page)
        {
            case "details": CloseDetails(); break;
            case "presets" or "packages" or "extras" or "settings": Open("library"); break;
            default: break;   // root B stays in Library; Exit App is an explicit menu action
        }
    }

    // ---------- Input ----------

    /// <summary>A controller action (GamepadInput) or its keyboard equivalent.</summary>
    public void Handle(string action, bool fromController = false)
    {
        if (fromController) ControllerActivity();
        WakeHints();
        var focused = FocusManager.GetFocusedElement(XamlRoot) as DependencyObject;
        if (HandleChoiceMenu(action, focused)) return;
        switch (action)
        {
            case "up" or "down" or "left" or "right":
                NavigationMotion();
                if (action is "left" or "right" && (focused as FrameworkElement)?.Tag is Adjustable adjustable)
                {
                    adjustable.Adjust(action == "right" ? 1 : -1);
                    return;
                }
                if (action is "up" or "down" && MoveVirtualRow(focused, action == "down" ? 1 : -1)) return;
                var direction = action switch
                {
                    "up" => FocusNavigationDirection.Up, "down" => FocusNavigationDirection.Down,
                    "left" => FocusNavigationDirection.Left, _ => FocusNavigationDirection.Right,
                };
                var options = new FindNextElementOptions
                {
                    SearchRoot = modals.Count > 0 ? (DependencyObject)modals.Peek().Element : root,
                    XYFocusNavigationStrategyOverride = XYFocusNavigationStrategyOverride.Projection,
                };
                if (!FocusManager.TryMoveFocus(direction, options) && focused is null) FocusFirst();
                break;
            case "accept": Activate(focused); break;
            case "back": Back(); break;
            case "search": if (modals.Count == 0) Open("library"); break;
            case "settings": if (modals.Count == 0) Open("settings"); break;
            case "menu": if (modals.Count == 0) OpenMainMenu(); break;
            case "previous": if (modals.Count == 0) CycleTab(-1); break;
            case "next": if (modals.Count == 0) CycleTab(1); break;
            case "select": ToggleSelectFocused(focused); break;
        }
    }

    void SetInput(string kind)
    {
        if (kind == "keyboard")
        {
            DispatcherQueue.TryEnqueue(Microsoft.UI.Dispatching.DispatcherQueuePriority.Low, () =>
                ApplyInput(shell.ControllerLegacyInputActive ? "controller" : "keyboard"));
            return;
        }
        ApplyInput(kind);
    }

    void ApplyInput(string kind)
    {
        if (kind == "keyboard" && shell.ControllerLegacyInputActive) { ControllerActivity(); return; }
        if (inputKind == kind) return;
        inputKind = kind;
        foreach (var light in Descendants(root).OfType<ArtworkLightLayer>()) light.ControllerFocus = kind == "controller";
        RenderFooter();
    }

    public void SetControllerFamily(string value)
    {
        detectedFamily = value;
        var chosen = shell.Settings.ControllerGlyphs == "auto" ? value : shell.Settings.ControllerGlyphs;
        if (family == chosen) return;
        family = chosen;
        RenderFooter();
    }

    public void ControllerActivity()
    {
        lastControllerInput = DateTime.UtcNow;
        SetInput("controller");
        WakeHints();
    }

    void OnKeyDown(object sender, KeyRoutedEventArgs e)
    {
        if (e.Key >= VirtualKey.GamepadA && e.Key <= VirtualKey.GamepadRightThumbstickLeft)
        { ControllerActivity(); e.Handled = true; return; }
        SetInput("keyboard");
        if (e.Key is VirtualKey.Up or VirtualKey.Down or VirtualKey.Left or VirtualKey.Right) NavigationMotion();
        var ctrl = Microsoft.UI.Input.InputKeyboardSource.GetKeyStateForCurrentThread(VirtualKey.Control)
            .HasFlag(global::Windows.UI.Core.CoreVirtualKeyStates.Down);
        if (FocusManager.GetFocusedElement(XamlRoot) is TextBox or PasswordBox && e.Key != VirtualKey.Escape) return;
        if (e.Key is VirtualKey.Up or VirtualKey.Down && MoveVirtualRow(FocusManager.GetFocusedElement(XamlRoot) as DependencyObject, e.Key == VirtualKey.Down ? 1 : -1))
        { e.Handled = true; return; }
        if (e.Key == VirtualKey.Tab)
        {
            var backwards = Microsoft.UI.Input.InputKeyboardSource.GetKeyStateForCurrentThread(VirtualKey.Shift).HasFlag(global::Windows.UI.Core.CoreVirtualKeyStates.Down);
            if (MoveVirtualRow(FocusManager.GetFocusedElement(XamlRoot) as DependencyObject, backwards ? -1 : 1)) { e.Handled = true; return; }
        }
        switch (e.Key)
        {
            case VirtualKey.Escape or VirtualKey.Back or VirtualKey.GamepadB: Back(); e.Handled = true; break;
            case VirtualKey.Left or VirtualKey.Right when (FocusManager.GetFocusedElement(XamlRoot) as FrameworkElement)?.Tag is Adjustable:
                Handle(e.Key == VirtualKey.Right ? "right" : "left"); e.Handled = true; break;
            case VirtualKey.L when ctrl: Open("library"); e.Handled = true; break;
            case (VirtualKey)188 when ctrl: Open("settings"); e.Handled = true; break;   // Ctrl+,
            case VirtualKey.Number1 when ctrl: Open("library"); e.Handled = true; break;
            case VirtualKey.Number2 when ctrl: Open("presets"); e.Handled = true; break;
            case VirtualKey.Number3 when ctrl: Open("packages"); e.Handled = true; break;
            case VirtualKey.Number4 when ctrl: Open("extras"); e.Handled = true; break;
            case VirtualKey.Number5 when ctrl: Open("settings"); e.Handled = true; break;
            case VirtualKey.F10: OpenMainMenu(); e.Handled = true; break;
            case VirtualKey.X: Handle("select"); e.Handled = true; break;
            case VirtualKey.PageUp: CycleTab(-1); e.Handled = true; break;
            case VirtualKey.PageDown: CycleTab(1); e.Handled = true; break;
        }
    }

    /// <summary>A (South) activates the focused control once.</summary>
    static void Activate(DependencyObject? focused)
    {
        switch (focused)
        {
            case Button button when button.IsEnabled:
                GmMotion.Acknowledge(button);
                (FrameworkElementAutomationPeer.CreatePeerForElement(button) as IInvokeProvider)?.Invoke();
                break;
            case ToggleButton toggle when toggle.IsEnabled:
                (FrameworkElementAutomationPeer.CreatePeerForElement(toggle) as IToggleProvider)?.Toggle();
                break;
            case ToggleSwitch toggle when toggle.IsEnabled:
                toggle.IsOn = !toggle.IsOn;
                break;
            case TextBox box:
                box.Focus(FocusState.Keyboard);
                break;
            case PasswordBox secret:
                secret.Focus(FocusState.Keyboard);
                break;
        }
    }

    void FocusFirst() => (FirstFocusable(modals.Count > 0 ? modals.Peek().Element : body) as Control)?.Focus(FocusState.Keyboard);

    static DependencyObject? FirstFocusable(DependencyObject scope) => FocusManager.FindFirstFocusableElement(scope);

    // Stable keys let re-renders restore focus to "the same" control.
    static void Key(FrameworkElement element, string key) => element.Name = "gm_" + key;
    static string? FocusKey(DependencyObject? element)
    {
        for (; element is not null; element = VisualTreeHelper.GetParent(element))
            if (element is FrameworkElement { Name: { Length: > 3 } name } && name.StartsWith("gm_", StringComparison.Ordinal)) return name;
        return null;
    }
    static Control? FindByKey(DependencyObject scope, string key)
    {
        if (scope is Control { Name: var name } control && name == key) return control;
        for (var i = 0; i < VisualTreeHelper.GetChildrenCount(scope); i++)
            if (FindByKey(VisualTreeHelper.GetChild(scope, i), key) is { } found) return found;
        return null;
    }

    // ---------- Modal layer ----------

    /// <summary>
    /// Shows a dialog over the page (the footer stays visible with modal hints).
    /// Focus is trapped inside; Back runs <paramref name="onBack"/>; closing
    /// restores the control that opened it.
    /// </summary>
    void ShowModal(string? title, UIElement content, IEnumerable<Button> actions, Action onBack, double width = 1100, Control? focus = null)
    {
        var restore = FocusManager.GetFocusedElement(XamlRoot) as DependencyObject;
        var panel = new StackPanel { Spacing = t.Px(t.Compact ? 18 : 26) };
        if (title is not null) panel.Children.Add(ui.H2(title, 1.38));
        panel.Children.Add(content);
        var row = new StackPanel { Orientation = Orientation.Horizontal, Spacing = t.Px(18), HorizontalAlignment = HorizontalAlignment.Right };
        foreach (var action in actions) row.Children.Add(action);
        if (row.Children.Count > 0) panel.Children.Add(row);
        var dialog = new Border
        {
            Background = t.DialogSurface(), CornerRadius = new CornerRadius(t.Px(20)),
            Padding = new Thickness(t.Px(t.Compact ? 24 : 40)), Width = Math.Min(t.Px(width), Math.Max(320, ActualWidth - t.Px(96))),
            MaxHeight = Math.Max(240, ActualHeight - footer.ActualHeight - t.Px(96)),
            HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center,
            Child = new ScrollViewer { Content = panel, HorizontalScrollMode = ScrollMode.Disabled, VerticalScrollBarVisibility = ScrollBarVisibility.Auto },
            Shadow = new ThemeShadow(), Translation = new System.Numerics.Vector3(0, 0, t.IsLight ? 12 : 32),
        };
        var layer = new Grid { Background = GmTheme.B(Microsoft.UI.Colors.Black, t.IsLight ? .18 : .60), Padding = new Thickness(t.Px(48)) };
        // A screen about one game also tints its sliders and switches with that game's accent.
        if (modalPalette is not null) Controls.AccentResources.Apply(dialog.Resources, modalPalette);
        var dialogScene = new Grid { HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center };
        var dialogLight = new ArtworkLightLayer { ControllerFocus = inputKind == "controller" };
        dialogScene.Children.Add(dialogLight.Artwork); dialogScene.Children.Add(dialog); dialogScene.Children.Add(dialogLight);
        foreach (var button in Descendants(dialog).OfType<Button>()) GmGlow.Layer(button, dialogLight);
        dialog.Loaded += (_, _) =>
        {
            foreach (var scroll in Descendants(dialog).OfType<ScrollViewer>())
            { scroll.IsTabStop = false; GmScrollFade.Attach(scroll, t.S); }
        };
        layer.Children.Add(dialogScene);
        GmMotion.Dialog(dialogScene, t.S);
        layer.TabFocusNavigation = KeyboardNavigationMode.Cycle;
        layer.XYFocusKeyboardNavigation = XYFocusKeyboardNavigationMode.Enabled;
        modalLayer.Children.Add(layer);
        modalLayer.Visibility = Visibility.Visible;
        // Trap: the page and header cannot take focus while a dialog is open.
        pageHost.IsEnabled = false;
        modals.Push(new Modal(layer, onBack, restore));
        RenderFooter();
        DispatcherQueue.TryEnqueue(Microsoft.UI.Dispatching.DispatcherQueuePriority.Low, () =>
        {
            if (modals.Count == 0 || !ReferenceEquals(modals.Peek().Element, layer)) return;
            layer.UpdateLayout();
            var target = focus ?? FirstFocusable(content) as Control ?? FirstFocusable(layer) as Control;
            target?.Focus(FocusState.Keyboard);
            artworkLight.RefreshPositions();
            pageLight.RefreshPositions();

        });
    }

    void CloseModal()
    {
        if (modals.Count == 0) return;
        var modal = modals.Pop();
        modalLayer.Children.Remove(modal.Element);
        if (modals.Count == 0)
        {
            modalLayer.Visibility = Visibility.Collapsed;
            pageHost.IsEnabled = true;
            // A flow about one game usually opens its next screen straight away; the
            // accent returns to the theme's once nothing replaces the closed modal.
            DispatcherQueue.TryEnqueue(Microsoft.UI.Dispatching.DispatcherQueuePriority.Low, () =>
            {
                if (modals.Count == 0 && !shell.Busy) UseGameAccent(null);
            });
        }
        RenderFooter();
        if (modal.Restore is Control control && control.XamlRoot is not null) control.Focus(FocusState.Keyboard);
        else FocusFirst();
    }

    void CloseAllModals()
    {
        while (modals.Count > 0) CloseModal();
    }

    public void Toast(string text)
    {
        toastHost.Child = new Border
        {
            Background = t.Surface(t.Card), CornerRadius = new CornerRadius(t.Px(16)), Padding = new Thickness(t.Px(24), t.Px(14), t.Px(24), t.Px(14)),
            Child = ui.Text(text, 0.85, wrap: true), MaxWidth = t.Px(900),
        };
        toastHost.Margin = new Thickness(0, 0, 0, t.Px(24));
        toastHost.Visibility = Visibility.Visible;
        GmMotion.Feedback(toastHost);
        toastTimer.Stop();
        toastTimer.Start();
    }

    // ---------- Main menu (logo menu) ----------

    void OpenMainMenu()
    {
        if (modals.Count > 0) return;
        var rows = new List<UIElement>
        {
            ui.RowButton("Library", null, () => { CloseModal(); Open("library"); }),
            ui.RowButton("Rescan library", "F5", () => { CloseModal(); _ = RefreshAsync(); }, glyph: ""),
            ui.RowButton("Library options", null, () => { CloseModal(); OpenLibraryOptions(); }),
            ui.RowButton("Desktop UI", null, () => { CloseModal(); ExitRequested?.Invoke(); }),
            ui.RowButton("Exit App", null, ConfirmExit, danger: true),
        };
        var back = ui.Button("Back", CloseModal, GmKind.Card, 0.92);
        ShowModal("rtxForge", ui.Group(rows, t.Card), [back], CloseModal, 900);
    }

    void ConfirmExit()
    {
        var stay = ui.Button("Stay", CloseModal, GmKind.Card, 0.92);
        var exit = ui.Button("Exit App", () => shell.Close(), GmKind.Danger, 0.92);
        ShowModal("Exit rtxForge?", ui.P("Game Mode closes. Your library and settings are saved."), [stay, exit], CloseModal, 760, stay);
    }

    async Task RefreshAsync()
    {
        Toast("Rescanning your library…");
        if (await shell.RescanLibraryAsync()) Toast($"Library rescanned · {shell.Games.Count} games.");
        else Toast("Could not rescan. Check the folder is available, then try again.");
    }
}
