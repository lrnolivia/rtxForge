using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Navigation;

namespace RtxForge.Windows.Views;

public sealed partial class ActivityPage : Page
{
    public ActivityPage()
    {
        InitializeComponent();
    }

    void OnSizeChanged(object sender, SizeChangedEventArgs e) => Body.Padding = Controls.PageMargins.For(e.NewSize.Width, bottom: 36);

    protected override void OnNavigatedTo(NavigationEventArgs e)
    {
        base.OnNavigatedTo(e);
        var log = App.Main!.Log;
        Entries.ItemsSource = log.Reverse().ToList();
        Empty.Visibility = log.Count == 0 ? Visibility.Visible : Visibility.Collapsed;
    }
}
