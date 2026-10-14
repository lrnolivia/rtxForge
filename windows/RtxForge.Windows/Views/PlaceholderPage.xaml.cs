using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Navigation;

namespace RtxForge.Windows.Views;

public sealed partial class PlaceholderPage : Page
{
    public PlaceholderPage()
    {
        InitializeComponent();
    }

    protected override void OnNavigatedTo(NavigationEventArgs e)
    {
        base.OnNavigatedTo(e);
        var tag = e.Parameter as string ?? "Packages";
        TitleText.Text = tag;
        (Icon.Glyph, Description.Text) = tag == "Extras"
            ? ("", "Extra tools arrive with the Windows engine bridge.")
            : ("", "Pinned provider packages, hashes and downloads arrive with the Windows engine bridge.");
    }
}
