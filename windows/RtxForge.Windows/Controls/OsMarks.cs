using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using RtxForge.Windows.Models;

namespace RtxForge.Windows.Controls;

/// <summary>Independent geometries for each supported OS, shared by cards, lists and details.</summary>
public sealed class OsMarks : StackPanel
{
    public static readonly DependencyProperty OsesProperty = DependencyProperty.Register(
        nameof(Oses), typeof(IReadOnlyList<string>), typeof(OsMarks), new PropertyMetadata(null, Changed));
    public static readonly DependencyProperty MarkSizeProperty = DependencyProperty.Register(
        nameof(MarkSize), typeof(double), typeof(OsMarks), new PropertyMetadata(12d, Changed));
    public static readonly DependencyProperty ForegroundProperty = DependencyProperty.Register(
        nameof(Foreground), typeof(Brush), typeof(OsMarks), new PropertyMetadata(null, Changed));
    public IReadOnlyList<string>? Oses { get => (IReadOnlyList<string>?)GetValue(OsesProperty); set => SetValue(OsesProperty, value); }
    public double MarkSize { get => (double)GetValue(MarkSizeProperty); set => SetValue(MarkSizeProperty, value); }
    public Brush? Foreground { get => (Brush?)GetValue(ForegroundProperty); set => SetValue(ForegroundProperty, value); }
    public OsMarks() { Orientation = Orientation.Horizontal; Spacing = 7; VerticalAlignment = VerticalAlignment.Center; }
    static void Changed(DependencyObject sender, DependencyPropertyChangedEventArgs args) => ((OsMarks)sender).Refresh();
    void Refresh()
    {
        Children.Clear();
        var oses = CrossOs.Normalize(Oses);
        var tip = CrossOs.Tooltip(oses);
        foreach (var os in oses)
        {
            var mark = OsMark.Create(os, MarkSize, Foreground ?? new SolidColorBrush(Microsoft.UI.Colors.White));
            ToolTipService.SetToolTip(mark, tip);
            Children.Add(mark);
        }
        ToolTipService.SetToolTip(this, tip);
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(this, tip);
        Visibility = oses.Count > 0 ? Visibility.Visible : Visibility.Collapsed;
    }
}
