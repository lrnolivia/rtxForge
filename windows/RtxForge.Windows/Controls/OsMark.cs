using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Markup;
using Microsoft.UI.Xaml.Media;

namespace RtxForge.Windows.Controls;

/// <summary>
/// The tiny OS mark for cross-OS installs: the paths of Linux's
/// gui/icons/hicolor/scalable/actions/rtx-os-{linux,windows}-symbolic.svg (16 × 16),
/// drawn as a PathIcon so it takes the pill's text color.
/// </summary>
public static class OsMark
{
    const string Linux =
        "F0 M8,1 C6.1,1 5,2.6 5,4.6 c0,1.1 -0.3,1.9 -1,3 C3.2,8.9 2.5,10.3 2.8,12 L1.5,13 c-0.4,0.6 0.1,1.4 1,1.4 h2.4 " +
        "c0.6,0 1,-0.3 1.3,-0.6 h3.6 c0.3,0.3 0.7,0.6 1.3,0.6 h2.4 c0.9,0 1.4,-0.8 1,-1.4 L13.2,12 c0.3,-1.7 -0.4,-3.1 -1.2,-4.4 " +
        "c-0.7,-1.1 -1,-1.9 -1,-3 C11,2.6 9.9,1 8,1 Z " +
        "M8,6.4 c-1.4,0 -2.4,1.9 -2.4,4 c0,1.3 0.9,2.2 2.4,2.2 s2.4,-0.9 2.4,-2.2 c0,-2.1 -1,-4 -2.4,-4 Z " +
        "M6.8,3.2 a0.6,0.7 0 1 0 0,1.4 a0.6,0.7 0 0 0 0,-1.4 Z " +
        "M9.2,3.2 a0.6,0.7 0 1 0 0,1.4 a0.6,0.7 0 0 0 0,-1.4 Z";

    const string Windows =
        "M1,2.6 L6.8,1.8 L6.8,7.4 L1,7.4 Z M7.6,1.7 L15,0.6 L15,7.4 L7.6,7.4 Z " +
        "M1,8.2 L6.8,8.2 L6.8,13.8 L1,13 Z M7.6,8.2 L15,8.2 L15,15.4 L7.6,14.4 Z";

    /// <summary>A new geometry each call: WinUI geometries cannot be shared between elements.</summary>
    public static Geometry? Data(string? os) => os switch
    {
        "linux" => (Geometry)XamlBindingHelper.ConvertValue(typeof(Geometry), Linux),
        "windows" => (Geometry)XamlBindingHelper.ConvertValue(typeof(Geometry), Windows),
        _ => null,
    };

    public static string Tooltip(string? os) => "Installed with rtxForge on " + Models.CrossOs.Name(os);

    /// <summary>The mark at <paramref name="size"/> px in <paramref name="foreground"/>, for code-built UI.</summary>
    public static FrameworkElement Create(string os, double size, Brush foreground)
    {
        var mark = new Viewbox
        {
            Width = size, Height = size, VerticalAlignment = VerticalAlignment.Center,
            Child = new PathIcon { Data = Data(os), Width = 16, Height = 16, Foreground = foreground },
        };
        ToolTipService.SetToolTip(mark, Tooltip(os));
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(mark, Tooltip(os));
        return mark;
    }
}
