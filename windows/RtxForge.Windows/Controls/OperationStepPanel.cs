using Microsoft.UI.Text;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using RtxForge.Windows.Models;
using RtxForge.Windows.ViewModels;

namespace RtxForge.Windows.Controls;

/// <summary>
/// The one layout for every per-game step of an operation (review checking,
/// install / restore / update progress): accent-stroked poster on the left;
/// on the right a caption counter ("Installing 3 of 20"), the game in its
/// accent, the current phase, and the progress bar in the same accent.
/// </summary>
public sealed class OperationStepPanel
{
    readonly Grid frame = new() { Width = 96, Height = 144, BorderThickness = new Thickness(2) };
    readonly Image poster = new() { Stretch = Stretch.UniformToFill };
    readonly TextBlock counter = Prefs.Label("Preparing…", "ForgeCaptionDimTextStyle");
    readonly TextBlock title = new() { FontSize = 20, FontWeight = FontWeights.SemiBold, TextTrimming = TextTrimming.CharacterEllipsis };
    readonly TextBlock phase = Prefs.Label("", "ForgeDimTextStyle");
    readonly ProgressBar bar = new() { Minimum = 0, Maximum = 1, IsIndeterminate = true, Margin = new Thickness(0, 8, 0, 0) };
    Game? current;

    public Grid Root { get; }
    /// <summary>Raised with the shown game's palette, so the dialog can tint its own buttons.</summary>
    public event Action<Services.AccentPalette>? AccentChanged;

    public OperationStepPanel()
    {
        Root = new Grid { ColumnSpacing = 24, MinWidth = 520 };
        Root.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        Root.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        frame.CornerRadius = (CornerRadius)Application.Current.Resources["ForgeCardCornerRadius"];
        frame.Background = (Brush)Application.Current.Resources["ControlFillColorSecondaryBrush"];
        frame.BorderBrush = (Brush)Application.Current.Resources["CardStrokeColorDefaultBrush"];
        frame.Children.Add(poster);
        Root.Children.Add(frame);
        var text = new StackPanel { Spacing = 4, VerticalAlignment = VerticalAlignment.Center };
        text.Children.Add(counter);
        text.Children.Add(title);
        text.Children.Add(phase);
        text.Children.Add(bar);
        Grid.SetColumn(text, 1);
        Root.Children.Add(text);
    }

    /// <summary>Shows a step. A null total keeps the bar indeterminate (downloads, verification).</summary>
    public void Show(string verb, Game? game, int index, int? total, string phaseText, double? fraction = null)
    {
        counter.Text = total is > 0 ? $"{verb} {Math.Min(index + 1, total.Value)} of {total}" : "Preparing…";
        if (!string.IsNullOrEmpty(phaseText)) phase.Text = phaseText.TrimEnd('.', '…') + "…";
        if (total is > 0)
        {
            bar.IsIndeterminate = false;
            bar.Value = Math.Clamp(fraction ?? (double)index / total.Value, 0, 1);
        }
        else bar.IsIndeterminate = true;
        if (game is not null && !ReferenceEquals(game, current))
        {
            current = game;
            title.Text = game.Name;
            poster.Source = GameItem.Image(game.PosterPath ?? game.CapsulePath);
            _ = AccentAsync(game);
        }
    }

    public void Complete() { bar.IsIndeterminate = false; bar.Value = 1; }

    async Task AccentAsync(Game game)
    {
        var palette = await Services.ArtAccent.ForGameAsync(game);
        if (palette is null || !ReferenceEquals(game, current)) return;
        frame.BorderBrush = palette.AccentBrush;
        title.Foreground = palette.AccentBrush;
        bar.Foreground = palette.AccentBrush;
        AccentChanged?.Invoke(palette);
    }
}
