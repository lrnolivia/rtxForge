using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace RtxForge.Windows.GameMode;

/// <summary>Keep authored rows, but realize their native templates only near the viewport.</summary>
sealed class GmElementFactory : IElementFactory
{
    public UIElement GetElement(ElementFactoryGetArgs args) => (UIElement)args.Data;
    public void RecycleElement(ElementFactoryRecycleArgs args) { }
}
