using System.ComponentModel;
using System.Windows.Input;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Imaging;
using RtxForge.Windows.Models;
using RtxForge.Windows.Services;
using Windows.UI;

namespace RtxForge.Windows.ViewModels;

/// <summary>Row actions the library wires into each item (list view buttons, selection).</summary>
public sealed record GameActions(Action<Game> Primary, Action<Game, FrameworkElement> More, Action<Game, bool> Select);

/// <summary>
/// Display projection of one library row (LibraryGameItem in GTK), including
/// the per-game accent states from the Linux .art-* CSS: hover ring and
/// title tint, and the accent-filled selected card / row.
/// </summary>
public sealed class GameItem : INotifyPropertyChanged
{
    public event PropertyChangedEventHandler? PropertyChanged;

    static readonly SolidColorBrush InstalledDot = new(Color.FromArgb(0xFF, 0x76, 0xB9, 0x00));
    static readonly SolidColorBrush AvailableDot = new(Color.FromArgb(0xFF, 0x8A, 0x8A, 0x8A));
    static readonly SolidColorBrush UnsupportedDot = new(Color.FromArgb(0xFF, 0xE5, 0x53, 0x4B));
    static readonly SolidColorBrush Transparent = new(Color.FromArgb(0, 0, 0, 0));
    static readonly SolidColorBrush White = new(Color.FromArgb(255, 255, 255, 255));

    readonly GameActions actions;
    readonly Control? themeHost;
    AccentPalette? palette;
    bool selected, hovered, selecting;

    public GameItem(Game game, ForgeSettings settings, GameActions actions, bool selecting, bool selected, int density = 0, Control? themeHost = null)
    {
        // List density: 0 all columns, 1 hides Location, 2 also hides Features.
        LocationWidth = new GridLength(density >= 1 ? 0 : 240);
        FeaturesWidth = new GridLength(density >= 2 ? 0 : 150);
        Game = game;
        this.actions = actions;
        this.themeHost = themeHost;
        this.selected = selected;
        this.selecting = selecting;
        PrimaryCommand = new RelayCommand(_ => actions.Primary(game));
        MoreCommand = new RelayCommand(target => { if (target is FrameworkElement element) actions.More(game, element); });
        NrChip = game.Installed ? $"NR {game.NrStrength ?? settings.NrStrength:0.0}" : "NR —";
        var mfg = game.Installed ? game.MfgMultiplier ?? settings.MfgMultiplier : null;
        MfgChip = mfg switch { null => "MFG —", "auto" => "MFG In game", "0" => "MFG Off", _ => $"MFG {mfg}×" };
        _ = LoadAccentAsync();
    }

    async Task LoadAccentAsync()
    {
        palette = await ArtAccent.ForGameAsync(Game);
        Changed();
    }

    public Game Game { get; }

    // ---------- selection / hover ----------

    // The check appears on hover (Photos / File Explorer), and stays on every
    // card while anything is selected. Unsupported games never show one.
    public Visibility SelectVisibility =>
        !Game.Blocked && (hovered || selected || selecting) ? Visibility.Visible : Visibility.Collapsed;
    // List rows keep the check's space so the row never shifts on hover.
    public double RowCheckOpacity => SelectVisibility == Visibility.Visible ? 1 : 0;
    public bool SelectEnabled => !Game.Blocked;

    /// <summary>True while any game in the library is selected.</summary>
    public bool IsSelecting
    {
        get => selecting;
        set { if (selecting != value) { selecting = value; Changed(); } }
    }

    public bool IsSelected
    {
        get => selected;
        set
        {
            if (selected == value) return;
            selected = value;
            actions.Select(Game, value);
            Changed();
        }
    }

    public bool IsHovered
    {
        get => hovered;
        set { if (hovered != value) { hovered = value; Changed(); } }
    }

    void Changed() => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(string.Empty));
    public void RefreshTheme() => Changed();

    Brush Resource(string key)
    {
        // The app theme is applied to the window's root, not Application.Current.
        // Read inherited text from the attached page so light cards don't receive dark-theme ink.
        if (themeHost is not null && key is "TextFillColorPrimaryBrush" or "ButtonForeground") return themeHost.Foreground;
        if (themeHost?.Foreground is SolidColorBrush ink && key == "TextFillColorSecondaryBrush")
            return new SolidColorBrush(ink.Color) { Opacity = ink.Opacity * .72 };
        return (Brush)Application.Current.Resources[key];
    }
    Color HoverTitle(AccentPalette p, Color dark) => themeHost?.ActualTheme == ElementTheme.Light
        ? ArtAccent.Readable(p.Color, Color.FromArgb(255, 250, 250, 250)) : dark;
    Brush? Accent(Func<AccentPalette, Color> pick, double opacity = 1) =>
        palette is null ? null : new SolidColorBrush(pick(palette)) { Opacity = opacity };

    // Poster / wide capsule card (.game-card, .gallery-artwork-ring)
    public Brush CardRing => (hovered || selected) && Accent(p => p.Color) is { } ring ? ring : Resource("CardStrokeColorDefaultBrush");
    public Brush CardFill => selected && Accent(p => p.Color) is { } fill ? fill : Transparent;
    public Brush CardTitle =>
        selected && Accent(p => p.SelectedTitle) is { } s ? s
        : hovered && Accent(p => HoverTitle(p, p.CardHoverTitle)) is { } h ? h
        : Resource("TextFillColorPrimaryBrush");
    public Brush CardStatusPillFill => selected && Accent(p => p.SourceBg) is { } b ? b : Resource("ControlFillColorSecondaryBrush");
    public Brush CardStatusPillText => selected && Accent(p => p.SourceFg) is { } f ? f : Resource("TextFillColorPrimaryBrush");
    public Brush CardTestPillFill => selected && Accent(p => p.AccentShadow, 0.94) is { } b ? b : Resource("ControlFillColorSecondaryBrush");
    public Brush CardTestPillIcon => selected ? White : Resource("ForgePillTestedBrush");

    // Check (.{name} check:checked: accent background, accent_dark glyph)
    public Brush CheckFill => selected && Accent(p => p.Color) is { } fill ? fill : new SolidColorBrush(Color.FromArgb(0x73, 0, 0, 0));
    public Brush CheckBorder => selected && Accent(p => p.Color) is { } border ? border : White;
    public Brush CheckGlyph => Accent(p => p.AccentDark) ?? White;
    public Visibility CheckVisibility => selected ? Visibility.Visible : Visibility.Collapsed;
    // List rows: check:checked uses white 72% with the readable accent glyph
    public Brush RowCheckFill => selected ? new SolidColorBrush(Color.FromArgb(0xB8, 255, 255, 255)) : Transparent;
    public Brush RowCheckBorder => selected ? Transparent : Resource("ControlStrongStrokeColorDefaultBrush");
    public Brush RowCheckGlyph => Accent(p => ArtAccent.Readable(p.Color, ArtAccent.Mix(Color.FromArgb(255, 255, 255, 255), p.Color, 0.72))) ?? White;

    // List row (columnview row.game-selected / :hover)
    // List rows share one surface: alternating shades, rounded only at the top and bottom.
    public int Position { get; set; }
    public bool IsLast { get; set; }
    public Brush RowFill => selected && Accent(p => p.Color) is { } fill ? fill
        : Resource(Position % 2 == 0 ? "CardBackgroundFillColorDefaultBrush" : "CardBackgroundFillColorSecondaryBrush");
    public CornerRadius RowCorner
    {
        get
        {
            var r = ((CornerRadius)Application.Current.Resources["ForgeCardCornerRadius"]).TopLeft;
            return new CornerRadius(Position == 0 ? r : 0, Position == 0 ? r : 0, IsLast ? r : 0, IsLast ? r : 0);
        }
    }
    public Brush RowTitle =>
        selected && Accent(p => p.AccentDark) is { } d ? d
        : hovered && Accent(p => HoverTitle(p, p.RowHoverTitle)) is { } h ? h
        : Resource("TextFillColorPrimaryBrush");
    public Brush RowText => selected && Accent(p => p.AccentDark) is { } d ? d : Resource("TextFillColorPrimaryBrush");
    public Brush RowSubtext => selected && Accent(p => p.AccentDark) is { } d ? d : Resource("TextFillColorSecondaryBrush");
    public Brush RowChipFill => selected ? new SolidColorBrush(Color.FromArgb(0x29, 0, 0, 0)) : Resource("ControlFillColorSecondaryBrush");
    public Brush RowArtRing =>
        selected && Accent(p => p.Color) is { } s ? s
        : hovered && Accent(p => p.Color, 0.68) is { } h ? h
        : Transparent;
    // .library-column-actions.selected-actions button
    public Brush RowActionFill => selected && Accent(p => p.Color) is { } fill ? fill : Resource("ButtonBackground");
    public Brush RowActionText => selected && Accent(p => p.AccentDark) is { } d ? d : Resource("ButtonForeground");

    public string Name => Game.Name;
    public string Library => Game.Library;
    public string Location => Game.Location;
    public string Meta => string.Join(" · ", new[] { Game.Library, Game.Release }.Where(s => !string.IsNullOrEmpty(s)));

    // .library-meta-pill / .library-status-stack
    public string Status => Game.AdoptionAvailable ? "ADOPTION" : Game.OfflineOnly ? "OFFLINE ONLY" : Game.Blocked ? Game.BlockedStatus.ToUpperInvariant() : Game.Installed ? "INSTALLED" : "AVAILABLE";
    public string StatusText => Game.AdoptionAvailable ? "Installed · Adoption available" : Game.OfflineOnly ? "Installed · Offline only" : Game.Blocked ? Game.BlockedStatus : Game.Installed ? "Installed" : Game.UsesFeeder ? "Available · Feeder NR" : "Available";
    public string StatusGlyph => Game.Blocked ? "" : Game.Installed ? "" : "";
    public Brush StatusDot => Game.Blocked ? UnsupportedDot : Game.Installed ? InstalledDot : AvailableDot;
    public Visibility TestedVisibility => Game.Tested ? Visibility.Visible : Visibility.Collapsed;

    // Cross-OS installs: the OS mark (Linux rtx-os-*-symbolic) on a translucent badge over the card art,
    // and beside the status in list rows.
    Geometry? osMark;
    bool HasOsMark => Game.Installed && Game.InstalledOn is "linux" or "windows";
    public Geometry? OsMark => HasOsMark ? osMark ??= Controls.OsMark.Data(Game.InstalledOn) : null;
    public Visibility OsMarkVisibility => HasOsMark ? Visibility.Visible : Visibility.Collapsed;
    public string? OsMarkTooltip => HasOsMark ? Controls.OsMark.Tooltip(Game.InstalledOn) : null;

    // Responsive list columns
    public GridLength LocationWidth { get; }
    public GridLength FeaturesWidth { get; }

    // Features column chips
    public string NrChip { get; }
    public string MfgChip { get; }

    // Actions column
    /// <summary>Library in presets mode (Presets › Select games): the row action applies presets.</summary>
    public bool PresetMode { get; init; }
    public string PrimaryLabel => Game.AdoptionAvailable ? "Adopt" : PresetMode ? "Apply" : Game.Installed ? "Restore" : "Install";
    public bool PrimaryEnabled => Game.AdoptionAvailable || (PresetMode ? Game.Installed && !Game.Blocked : !Game.Blocked);
    public ICommand PrimaryCommand { get; }
    public ICommand MoreCommand { get; }

    // Artwork
    // Created once: state changes re-read every binding and must not reload art.
    ImageSource? poster, capsule;
    public ImageSource? Poster => poster ??= Image(Game.PosterPath);
    public ImageSource? Capsule => capsule ??= Image(Game.CapsulePath ?? Game.PosterPath);
    public Visibility PosterVisibility => Game.PosterPath is null ? Visibility.Collapsed : Visibility.Visible;
    /// <summary>Capsule as a brush, so a rounded Border clips it (an Image inside a Grid is not clipped).</summary>
    public Brush? CapsuleBrush => Capsule is { } source ? new ImageBrush { ImageSource = source, Stretch = Stretch.UniformToFill } : null;
    public Visibility CapsuleVisibility => (Game.CapsulePath ?? Game.PosterPath) is null ? Visibility.Collapsed : Visibility.Visible;

    public static ImageSource? Image(string? source)
    {
        if (source is null) return null;
        if (source.StartsWith("https://", StringComparison.OrdinalIgnoreCase)) return new BitmapImage(new Uri(source));
        return File.Exists(source) ? new BitmapImage(new Uri(source)) : null;
    }
}

public sealed class RelayCommand(Action<object?> run) : ICommand
{
    public event EventHandler? CanExecuteChanged { add { } remove { } }
    public bool CanExecute(object? parameter) => true;
    public void Execute(object? parameter) => run(parameter);
}
