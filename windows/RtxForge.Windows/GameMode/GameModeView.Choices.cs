using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;

namespace RtxForge.Windows.GameMode;

public sealed partial class GameModeView
{
    sealed record ChoiceMenu(Flyout Popup, List<Button> Options);
    ChoiceMenu? choiceMenu;

    void OpenChoiceMenu(Button anchor, string title, string[] captions, int selected, Action<int> choose)
    {
        choiceMenu?.Popup.Hide();
        var options = new List<Button>();
        var list = new StackPanel { Spacing = t.Px(6), Width = Math.Min(t.Px(380), Math.Max(240, ActualWidth - t.Px(100))) };
        list.Children.Add(ui.P(title, .74).With(x => x.Margin = new Thickness(t.Px(12), t.Px(4), t.Px(12), t.Px(10))));
        var popup = new Flyout { Content = list, Placement = FlyoutPlacementMode.BottomEdgeAlignedRight };
        var presenter = new Style(typeof(FlyoutPresenter));
        presenter.Setters.Add(new Setter(Control.BackgroundProperty, GmTheme.B(t.Panel)));
        presenter.Setters.Add(new Setter(Control.ForegroundProperty, GmTheme.B(t.Fg)));
        presenter.Setters.Add(new Setter(Control.CornerRadiusProperty, new CornerRadius(t.Px(16))));
        presenter.Setters.Add(new Setter(FrameworkElement.RequestedThemeProperty, t.IsLight ? ElementTheme.Light : ElementTheme.Dark));
        popup.FlyoutPresenterStyle = presenter;
        for (var i = 0; i < captions.Length; i++)
        {
            var index = i;
            var line = new Grid { ColumnSpacing = t.Px(16) };
            line.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
            line.ColumnDefinitions.Add(new() { Width = new GridLength(t.Px(22)) });
            line.Children.Add(ui.Text(captions[i], .85, wrap: true));
            if (i == selected) { var check = ui.Icon("", .75); Grid.SetColumn(check, 1); line.Children.Add(check); }
            var option = ui.Button(line, () => { popup.Hide(); choose(index); }, i == selected ? GmKind.Active : GmKind.Transparent,
                .85, radius: 12, padding: new Thickness(t.Px(14), t.Px(12), t.Px(14), t.Px(12)), minHeight: 48,
                name: captions[i] + (i == selected ? ", selected" : ""));
            option.HorizontalAlignment = HorizontalAlignment.Stretch;
            option.HorizontalContentAlignment = HorizontalAlignment.Stretch;
            options.Add(option); list.Children.Add(option);
        }
        var menu = new ChoiceMenu(popup, options);
        choiceMenu = menu;
        popup.Opened += (_, _) => options[Math.Clamp(selected, 0, options.Count - 1)].Focus(FocusState.Keyboard);
        popup.Closed += (_, _) =>
        {
            if (ReferenceEquals(choiceMenu, menu)) choiceMenu = null;
            if (anchor.XamlRoot is not null) anchor.Focus(FocusState.Keyboard);
        };
        list.KeyDown += (_, e) =>
        {
            var action = e.Key switch
            {
                global::Windows.System.VirtualKey.Up => "up", global::Windows.System.VirtualKey.Down => "down",
                global::Windows.System.VirtualKey.Escape => "back", _ => null,
            };
            if (action is not null) { HandleChoiceMenu(action, FocusManager.GetFocusedElement(XamlRoot) as DependencyObject); e.Handled = true; }
        };
        popup.ShowAt(anchor);
    }

    bool HandleChoiceMenu(string action, DependencyObject? focused)
    {
        if (choiceMenu is not { } menu) return false;
        if (action == "back") menu.Popup.Hide();
        else if (action is "up" or "down")
        {
            var index = Math.Max(0, menu.Options.FindIndex(x => ReferenceEquals(x, focused)));
            index = (index + (action == "down" ? 1 : -1) + menu.Options.Count) % menu.Options.Count;
            menu.Options[index].Focus(FocusState.Keyboard);
        }
        else if (action == "accept") Activate(focused);
        return true;
    }
}
