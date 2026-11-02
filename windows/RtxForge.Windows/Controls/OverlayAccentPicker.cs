using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Imaging;
using RtxForge.Windows.Models;
using RtxForge.Windows.Services;
using Windows.UI;

namespace RtxForge.Windows.Controls;

static class OverlayAccentPicker
{
    public static async Task<string?> ShowAsync(FrameworkElement owner,Game? game,Color initial)
    {
        var picker=new ColorPicker {Color=initial,IsAlphaEnabled=false,IsColorSliderVisible=false,IsColorChannelTextInputVisible=false,IsHexInputVisible=true,MaxWidth=300};
        var poster=new Image {Width=88,MaxHeight=132,Stretch=Stretch.Uniform};
        var column=new StackPanel {Spacing=12};column.Children.Add(poster);
        var readout=new TextBlock {Text=ArtAccent.Hex(initial),HorizontalAlignment=HorizontalAlignment.Center};column.Children.Add(readout);
        var dropper=new Button {Content=new FontIcon {Glyph="\uEF3C"},HorizontalAlignment=HorizontalAlignment.Center};
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(dropper,"Pick a color from the screen");
        ToolTipService.SetToolTip(dropper,"Pick any color on screen");column.Children.Add(dropper);
        var stage=new StackPanel {Orientation=Orientation.Horizontal,Spacing=20};stage.Children.Add(picker);stage.Children.Add(column);
        var hint=new TextBlock {Text="Choose a color, sample the poster, or use the screen eyedropper.",TextWrapping=TextWrapping.Wrap,MaxWidth=410};
        var body=new StackPanel {Spacing=12};body.Children.Add(stage);body.Children.Add(hint);
        var dialog=new ContentDialog {Title="Custom color",Content=body,XamlRoot=owner.XamlRoot,RequestedTheme=owner.ActualTheme,
            PrimaryButtonText="Done",SecondaryButtonText="Use game color",CloseButtonText="Cancel",DefaultButton=ContentDialogButton.Primary};
        using var lifetime=new CancellationTokenSource();
        dialog.Closing+=(_,_)=>lifetime.Cancel();
        picker.ColorChanged+=(_,e)=>readout.Text=ArtAccent.Hex(e.NewColor).ToUpperInvariant();
        dropper.Click+=async(_,_)=>{
            dropper.IsEnabled=false;dialog.IsPrimaryButtonEnabled=false;dialog.IsSecondaryButtonEnabled=false;
            var previous=picker.Color;hint.Text="Click any color on screen. Escape or right-click cancels.";
            try {var chosen=await ScreenColorPicker.PickAsync(owner.DispatcherQueue,c=>readout.Text=ArtAccent.Hex(c).ToUpperInvariant(),lifetime.Token);picker.Color=chosen??previous;}
            catch(Exception error)when(error is InvalidOperationException or System.ComponentModel.Win32Exception){hint.Text=error.Message;}
            finally {dropper.IsEnabled=true;dialog.IsPrimaryButtonEnabled=true;dialog.IsSecondaryButtonEnabled=true;readout.Text=ArtAccent.Hex(picker.Color).ToUpperInvariant();}
        };
        var source=game is null?null:OverlayPreview.Poster(game);
        if(source is not null)try {
            var bytes=await ArtAccent.LoadAsync(source);var (pixels,width,height)=await ArtAccent.DecodeAsync(bytes);
            poster.Source=RtxForge.Windows.ViewModels.GameItem.Image(source);
            poster.Tapped+=(_,e)=>{var at=e.GetPosition(poster);var scale=Math.Min(poster.ActualWidth/width,poster.ActualHeight/height);
                var x=(int)((at.X-(poster.ActualWidth-width*scale)/2)/scale);var y=(int)((at.Y-(poster.ActualHeight-height*scale)/2)/scale);
                if(x>=0&&y>=0&&x<width&&y<height){var i=(int)((y*width+x)*4);picker.Color=Color.FromArgb(255,pixels[i+2],pixels[i+1],pixels[i]);}};
        }catch(Exception error)when(error is IOException or HttpRequestException or System.Runtime.InteropServices.COMException){poster.Visibility=Visibility.Collapsed;}
        else poster.Visibility=Visibility.Collapsed;
        var result=await dialog.ShowAsync();
        return result==ContentDialogResult.Primary?ArtAccent.Hex(picker.Color):result==ContentDialogResult.Secondary?"":null;
    }
}
