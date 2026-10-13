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
    GmTheme t;
    GmUi ui;

    readonly Grid root = new();
    readonly Grid pageGrid = new();
    readonly ContentControl pageHost = new()
    {
        IsTabStop = false, HorizontalContentAlignment = HorizontalAlignment.Stretch, VerticalContentAlignment = VerticalAlignment.Stretch,
    };
    readonly Grid header = new();
    readonly Grid body = new();
    readonly Grid footer = new();
    readonly Grid bottomNav = new();
    readonly Grid modalLayer = new() { Visibility = Visibility.Collapsed };
    readonly Border toastHost = new() { Visibility = Visibility.Collapsed, HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Bottom };
    readonly Microsoft.UI.Dispatching.DispatcherQueueTimer toastTimer;

    string page = "library";          // library · presets · settings · details
    string inputKind = "keyboard";    // keyboard · controller: drives hint glyphs
    string family = "xbox";
    readonly Stack<Modal> modals = new();

    sealed record Modal(UIElement Element, Action OnBack, DependencyObject? Restore);

    /// <summary>The user chose Desktop UI (main menu or Settings › Interface).</summary>
    public event Action? ExitRequested;

    public GameModeView(MainWindow shell)
    {
        this.shell = shell;
        t = GmTheme.For(shell.Settings.Theme);
        t.Scale = shell.Settings.UiScaleKey;
        ui = new GmUi(t);
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
        root.Children.Add(pageHost);
        // Controller/keyboard hint bar stays (A Select · B Back · Y Library); dialogs sit above it.
        Grid.SetRow(footer, 1);
        root.Children.Add(footer);
        root.Children.Add(modalLayer);
        root.Children.Add(toastHost);

        // Arrow keys move focus spatially, exactly like the D-pad.
        XYFocusKeyboardNavigation = XYFocusKeyboardNavigationMode.Enabled;
        TabFocusNavigation = KeyboardNavigationMode.Cycle;
        KeyDown += OnKeyDown;
        // WinUI also turns D-pad/stick into key events that move focus natively; with
        // GamepadInput that moved focus twice and skipped rows. One source only.
        PreviewKeyDown += (_, e) => { if (e.Key >= VirtualKey.GamepadA && e.Key <= VirtualKey.GamepadRightThumbstickLeft) e.Handled = true; };
        XYFocusUpNavigationStrategy = XYFocusDownNavigationStrategy = XYFocusLeftNavigationStrategy = XYFocusRightNavigationStrategy =
            XYFocusNavigationStrategy.Projection;
        PointerMoved += (_, _) => SetInput("keyboard");
        SizeChanged += (_, e) => { if (t.Resize(e.NewSize.Width, e.NewSize.Height)) Render(keepFocus: true); };

        toastTimer = DispatcherQueue.CreateTimer();
        toastTimer.Interval = TimeSpan.FromSeconds(4);
        toastTimer.Tick += (_, _) => { toastTimer.Stop(); toastHost.Visibility = Visibility.Collapsed; };

        shell.GamesChanged += OnGamesChanged;
        Unloaded += (_, _) => shell.GamesChanged -= OnGamesChanged;
        Loaded += (_, _) => { t.Resize(ActualWidth, ActualHeight); Render(); };
    }

    void OnGamesChanged()
    {
        if (detailsGame is { } current) detailsGame = shell.Games.FirstOrDefault(g => g.Id == current.Id) ?? current;
        if (modals.Count == 0) Render(keepFocus: true);
    }

    /// <summary>Theme or appearance changed in Settings.</summary>
    public void ApplySettings()
    {
        var size = (ActualWidth, ActualHeight);
        t = GmTheme.For(shell.Settings.Theme);
        t.Scale = shell.Settings.UiScaleKey;
        t.Resize(size.ActualWidth, size.ActualHeight);
        ui = new GmUi(t);
        Render(keepFocus: true);
    }

    // ---------- Rendering ----------

    void Render(bool keepFocus = false)
    {
        var focusedName = keepFocus ? FocusKey(FocusManager.GetFocusedElement(XamlRoot) as DependencyObject) : null;
        root.Background = GmTheme.B(t.Window);
        RenderHeader();
        body.Children.Clear();
        body.Background = GmTheme.B(t.View);
        var content = page switch
        {
            "details" when detailsGame is not null => BuildDetails(detailsGame),
            "presets" => BuildPresets(),
            "settings" => BuildSettings(),
            _ => BuildLibrary(),
        };
        body.Children.Add(content);
        RenderFooter();
        // Focus: keep the same control when re-rendering, else the page's first target.
        DispatcherQueue.TryEnqueue(Microsoft.UI.Dispatching.DispatcherQueuePriority.Low, () =>
        {
            if (modals.Count > 0) return;
            // Library: restore the scroll position first, so focusing only nudges it into view.
            if (page == "library" && libraryScroller is { } scroller) { scroller.UpdateLayout(); scroller.ChangeView(null, libraryScroll, null, true); }
            var target =(focusedName is not null ? FindByKey(body, focusedName) ?? FindByKey(header, focusedName) : null)
                         ?? (pendingFocusKey is not null ? FindByKey(pageGrid, pendingFocusKey) : null)
                         ?? initialFocus ?? FirstFocusable(body);
            initialFocus = null;
            pendingFocusKey = null;
            (target as Control)?.Focus(FocusState.Keyboard);
        });
    }

    Control? initialFocus;
    /// <summary>Focus target by key, resolved after the page renders (controls do not exist before).</summary>
    string? pendingFocusKey;

    readonly List<Button> tabButtons = [];

    void RenderHeader()
    {
        header.Children.Clear();
        header.ColumnDefinitions.Clear();
        header.Background = GmTheme.B(t.Window);
        header.Height = t.Px(t.Compact ? 80 : 104);
        header.Padding = new Thickness(t.Px(56), t.Px(t.Compact ? 10 : 14), t.Px(56), t.Px(t.Compact ? 10 : 14));
        header.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        header.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        header.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });

        // Brand: the main menu (logo menu, never a page tab).
        var brand = new StackPanel { Orientation = Orientation.Horizontal, Spacing = t.Px(16) };
        brand.Children.Add(new Image
        {
            Source = new Microsoft.UI.Xaml.Media.Imaging.SvgImageSource(new Uri("ms-appx:///Assets/rtxforge-mark.svg")),
            Width = t.Px(t.Compact ? 48 : 64), Height = t.Px(t.Compact ? 48 : 64),
        });
        brand.Children.Add(new TextBlock
        {
            Text = "rtxForge", FontSize = t.Em(t.Compact ? 1.4 : 1.62), VerticalAlignment = VerticalAlignment.Center,
            FontFamily = (FontFamily)Application.Current.Resources["ForgeHeroFontFamily"], Foreground = GmTheme.B(t.Fg),
        });
        var brandButton = ui.Button(brand, OpenMainMenu, GmKind.Transparent, 1, radius: 12,
            padding: new Thickness(t.Px(6), 0, t.Px(6), 0), minHeight: 0, name: "rtxForge main menu");
        brandButton.HorizontalAlignment = HorizontalAlignment.Left;
        Key(brandButton, "brand");
        header.Children.Add(brandButton);

        var tabs = BuildTabs();
        if (shell.Settings.NavigationPosition == "bottom")
        {
            bottomNav.Children.Clear();
            bottomNav.Background = GmTheme.B(t.View);
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
        var line = new StackPanel { Orientation = Orientation.Horizontal, Spacing = t.Px(8) };
        foreach (var (key, label) in new[] { ("library", "Library"), ("presets", "Presets"), ("settings", "Settings") })
        {
            var active = page == key || (key == "library" && page == "details");
            var tab = ui.Button(label, () => Open(key), active ? GmKind.Active : GmKind.Transparent, 1, radius: 32,
                padding: new Thickness(t.Px(26), t.Px(8), t.Px(26), t.Px(8)), minHeight: 54);
            GmUi.Capsule(tab);
            Key(tab, "tab-" + key);
            tabButtons.Add(tab);
            line.Children.Add(tab);
        }
        return GmUi.Capsule(new Border
        {
            Background = GmTheme.B(t.Panel), CornerRadius = new CornerRadius(t.Px(40)), Padding = new Thickness(t.Px(8)),
            Child = line, HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center,
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
        footer.MinHeight = t.Px(t.Compact ? 64 : 90);
        footer.Padding = new Thickness(t.Px(56), t.Px(t.Compact ? 14 : 22), t.Px(56), t.Px(t.Compact ? 14 : 22));
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
            pair.Children.Add(ui.Key(key));
            pair.Children.Add(ui.Text(label, 0.85).With(x => x.VerticalAlignment = VerticalAlignment.Center));
            var hint = ui.Button(pair, () => Handle(action), GmKind.Transparent, 1, radius: 8, padding: new Thickness(t.Px(2)), minHeight: 0);
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
        string[] order = ["library", "presets", "settings"];
        var current = Array.IndexOf(order, page == "details" ? "library" : page);
        Open(order[(current + direction + order.Length) % order.Length]);
        pendingFocusKey = "gm_tab-" + order[(current + direction + order.Length) % order.Length];
    }

    void Back()
    {
        if (modals.Count > 0) { modals.Peek().OnBack(); return; }
        switch (page)
        {
            case "details": CloseDetails(); break;
            case "presets" or "settings": Open("library"); break;
            default: break;   // root B stays in Library; Exit App is an explicit menu action
        }
    }

    // ---------- Input ----------

    /// <summary>A controller action (GamepadInput) or its keyboard equivalent.</summary>
    public void Handle(string action, bool fromController = false)
    {
        if (fromController) SetInput("controller");
        WakeHints();
        var focused = FocusManager.GetFocusedElement(XamlRoot) as DependencyObject;
        switch (action)
        {
            case "up" or "down" or "left" or "right":
                if (action is "left" or "right" && (focused as FrameworkElement)?.Tag is Adjustable adjustable)
                {
                    adjustable.Adjust(action == "right" ? 1 : -1);
                    return;
                }
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
        if (inputKind == kind) return;
        inputKind = kind;
        RenderFooter();
    }

    public void SetControllerFamily(string value)
    {
        var chosen = shell.Settings.ControllerGlyphs == "auto" ? value : shell.Settings.ControllerGlyphs;
        if (family == chosen) return;
        family = chosen;
        RenderFooter();
    }

    void OnKeyDown(object sender, KeyRoutedEventArgs e)
    {
        SetInput("keyboard");
        var ctrl = Microsoft.UI.Input.InputKeyboardSource.GetKeyStateForCurrentThread(VirtualKey.Control)
            .HasFlag(global::Windows.UI.Core.CoreVirtualKeyStates.Down);
        if (FocusManager.GetFocusedElement(XamlRoot) is TextBox or PasswordBox && e.Key != VirtualKey.Escape) return;
        switch (e.Key)
        {
            case VirtualKey.Escape or VirtualKey.Back or VirtualKey.GamepadB: Back(); e.Handled = true; break;
            case VirtualKey.Left or VirtualKey.Right when (FocusManager.GetFocusedElement(XamlRoot) as FrameworkElement)?.Tag is Adjustable:
                Handle(e.Key == VirtualKey.Right ? "right" : "left"); e.Handled = true; break;
            case VirtualKey.L when ctrl: Open("library"); e.Handled = true; break;
            case (VirtualKey)188 when ctrl: Open("settings"); e.Handled = true; break;   // Ctrl+,
            case VirtualKey.Number1 when ctrl: Open("library"); e.Handled = true; break;
            case VirtualKey.Number2 when ctrl: Open("presets"); e.Handled = true; break;
            case VirtualKey.Number3 when ctrl: Open("settings"); e.Handled = true; break;
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
                (FrameworkElementAutomationPeer.CreatePeerForElement(button) as IInvokeProvider)?.Invoke();
                break;
            case ToggleButton toggle when toggle.IsEnabled:
                (FrameworkElementAutomationPeer.CreatePeerForElement(toggle) as IToggleProvider)?.Toggle();
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
            Background = GmTheme.B(t.Panel), CornerRadius = new CornerRadius(t.Px(20)),
            Padding = new Thickness(t.Px(t.Compact ? 24 : 40)), Width = Math.Min(t.Px(width), Math.Max(320, ActualWidth - t.Px(96))),
            MaxHeight = Math.Max(240, ActualHeight - footer.ActualHeight - t.Px(96)),
            HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center,
            Child = new ScrollViewer { Content = panel, HorizontalScrollMode = ScrollMode.Disabled, VerticalScrollBarVisibility = ScrollBarVisibility.Auto },
            Shadow = new ThemeShadow(), Translation = new System.Numerics.Vector3(0, 0, 48),
        };
        var layer = new Grid { Background = GmTheme.B(Microsoft.UI.Colors.Black, 0.7), Padding = new Thickness(t.Px(48)) };
        layer.Children.Add(dialog);
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
            var target = focus ?? FirstFocusable(layer) as Control;
            target?.Focus(FocusState.Keyboard);

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
            Background = GmTheme.B(t.Card), CornerRadius = new CornerRadius(t.Px(16)), Padding = new Thickness(t.Px(24), t.Px(14), t.Px(24), t.Px(14)),
            Child = ui.Text(text, 0.85, wrap: true), MaxWidth = t.Px(900),
        };
        toastHost.Margin = new Thickness(0, 0, 0, t.Px(24));
        toastHost.Visibility = Visibility.Visible;
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
            ui.RowButton("Packages", null, () => _ = ShowPackagesAsync()),
            ui.RowButton("Refresh library", null, () => { CloseModal(); _ = RefreshAsync(); }, glyph: ""),
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
        Toast("Refreshing your library…");
        try { await shell.ScanAsync(); Toast("Library refreshed."); }
        catch (InvalidOperationException error) { Toast("Could not refresh: " + error.Message); }
    }
}
