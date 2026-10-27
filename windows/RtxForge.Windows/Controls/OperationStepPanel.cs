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
/// The panel has a fixed width, so a long game title is trimmed instead of
/// widening the dialog.
/// </summary>
public sealed class OperationStepPanel
{
    readonly Grid frame = new() { Width = 96, Height = 144, BorderThickness = new Thickness(2) };
    readonly Image poster = new() { Stretch = Stretch.UniformToFill };
    readonly TextBlock counter = Prefs.Label("Preparing…", "ForgeCaptionDimTextStyle");
    readonly TextBlock title = new() { FontSize = 20, FontWeight = FontWeights.SemiBold, TextWrapping = TextWrapping.NoWrap, TextTrimming = TextTrimming.CharacterEllipsis };
    readonly TextBlock phase = Prefs.Label("", "ForgeDimTextStyle");
    readonly ProgressBar bar = new() { Minimum = 0, Maximum = 1, IsIndeterminate = true, Margin = new Thickness(0, 8, 0, 0) };
    readonly StepCount count = new();
    Game? current;

    public Grid Root { get; }
    /// <summary>Raised with the shown game's palette, so the dialog can tint its own buttons.</summary>
    public event Action<Services.AccentPalette>? AccentChanged;

    public OperationStepPanel()
    {
        Root = new Grid { ColumnSpacing = 24, Width = 560 };
        phase.TextWrapping = TextWrapping.NoWrap;
        phase.TextTrimming = TextTrimming.CharacterEllipsis;
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

    /// <summary>
    /// Shows a step. A null total keeps the bar indeterminate (downloads, verification)
    /// until the step is counted; after that, uncounted sub-steps only update the phase.
    /// </summary>
    public void Show(string verb, Game? game, int index, int? total, string phaseText, double? fraction = null)
    {
        if (!string.IsNullOrEmpty(phaseText)) phase.Text = phaseText.TrimEnd('.', '…') + "…";
        if (count.Next(verb, index, total, fraction) is { } shown)
        {
            counter.Text = $"{verb} {shown.At} of {shown.Of}";
            bar.IsIndeterminate = false;
            bar.Value = shown.Value;
        }
        else
        {
            counter.Text = "Preparing…";
            bar.IsIndeterminate = true;
        }
        if (game is not null && !ReferenceEquals(game, current))
        {
            current = game;
            title.Text = game.Name;
            poster.Source = GameItem.Image(game.PosterPath ?? game.CapsulePath);
            _ = AccentAsync(game);
        }
    }

    public void Complete() { bar.IsIndeterminate = false; bar.Value = 1; }

    /// <summary>Work with no countable progress (cancelling and undoing): the bar goes indeterminate.</summary>
    public void Busy(string phaseText)
    {
        count.Reset();
        phase.Text = phaseText.TrimEnd('.', '…') + "…";
        bar.IsIndeterminate = true;
    }

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

/// <summary>
/// The counter and bar position of a per-game step. The engine reports
/// uncounted sub-steps (verifying a package, loading a model) between counted
/// ones; those keep the last count instead of flipping the bar back to
/// indeterminate or its position back to the start. A new verb starts afresh.
/// </summary>
public sealed class StepCount
{
    string? verb;
    (int At, int Of, double Value)? last;

    public (int At, int Of, double Value)? Next(string stepVerb, int index, int? total, double? fraction)
    {
        if (stepVerb != verb) { verb = stepVerb; last = null; }
        if (total is > 0)
        {
            var value = Math.Clamp(fraction ?? (double)index / total.Value, 0, 1);
            // The bar never moves backwards within one step.
            if (last is { } before && before.Of == total.Value && value < before.Value)
                return last;
            last = (Math.Min(index + 1, total.Value), total.Value, value);
        }
        return last;
    }

    public void Reset() { verb = null; last = null; }
}
