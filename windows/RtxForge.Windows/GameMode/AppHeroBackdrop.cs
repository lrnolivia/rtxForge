using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Animation;
using Microsoft.UI.Xaml.Media.Imaging;
using Windows.UI;

namespace RtxForge.Windows.GameMode;

/// <summary>The app's Steam artwork behind the shared shell, fading into its content surface.</summary>
sealed class AppHeroBackdrop : Grid
{
    readonly Image artwork = new()
    {
        Source = new BitmapImage(new Uri("ms-appx:///Assets/GameMode/steam-hero.png")),
        Stretch = Stretch.UniformToFill,
        HorizontalAlignment = HorizontalAlignment.Stretch,
        VerticalAlignment = VerticalAlignment.Stretch,
    };
    readonly Border fade = new();
    bool introduced;

    public AppHeroBackdrop()
    {
        IsHitTestVisible = false;
        VerticalAlignment = VerticalAlignment.Top;
        HorizontalAlignment = HorizontalAlignment.Stretch;
        AutomationProperties.SetAccessibilityView(this, Microsoft.UI.Xaml.Automation.Peers.AccessibilityView.Raw);
        Children.Add(artwork);
        Children.Add(fade);
        artwork.ImageOpened += (_, _) =>
        {
            if (introduced || !GmUi.Animations) return;
            introduced = true;
            var reveal = new DoubleAnimation
            {
                From = .6, To = 1, Duration = TimeSpan.FromMilliseconds(GmMotionTokens.Surface),
                EasingFunction = new ExponentialEase { Exponent = 6, EasingMode = EasingMode.EaseOut },
            };
            Storyboard.SetTarget(reveal, this);
            Storyboard.SetTargetProperty(reveal, "Opacity");
            var story = new Storyboard();
            story.Children.Add(reveal);
            story.Begin();
        };
    }

    public void Apply(GmTheme theme, bool visible, double width, double height)
    {
        Visibility = visible ? Visibility.Visible : Visibility.Collapsed;
        Height = Math.Max(1, Math.Min(width * 1240 / 3840, height * .78));
        artwork.Opacity = theme.IsLight ? .24 : theme.Name == "night" ? .40 : .94;
        Color Shade(byte opacity) => Color.FromArgb(opacity, theme.View.R, theme.View.G, theme.View.B);
        fade.Background = new LinearGradientBrush
        {
            StartPoint = new(0, 0), EndPoint = new(0, 1),
            GradientStops =
            {
                new GradientStop { Offset = 0, Color = Shade(20) },
                new GradientStop { Offset = .2, Color = Shade(26) },
                new GradientStop { Offset = .42, Color = Shade(65) },
                new GradientStop { Offset = .65, Color = Shade(160) },
                new GradientStop { Offset = .84, Color = Shade(231) },
                new GradientStop { Offset = 1, Color = Shade(255) },
            },
        };
    }
}
