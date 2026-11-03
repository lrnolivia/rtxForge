using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Imaging;
using RtxForge.Windows.Services;
using System.Text.Json.Nodes;
using Windows.Graphics.Imaging;
using Windows.Storage.Streams;

namespace RtxForge.Windows.Controls;

/// <summary>Native Game Mode appearance without launching another interface.</summary>
internal sealed class GameModeAppearanceView : UserControl
{
    readonly StackPanel body = new() { Spacing=16 };
    UIElementCollection Children => body.Children;
    readonly EngineForgeService engine;
    readonly GameModeAppearance store;
    readonly SemaphoreSlim edits = new(1, 1);
    readonly TextBlock feedback = new() { FontSize=12, TextWrapping=TextWrapping.Wrap, Visibility=Visibility.Collapsed };
    readonly Canvas sample = new() { Width=480, Height=270, IsHitTestVisible=false };
    JsonObject appearance = GameModeAppearance.Defaults;
    bool ready;
    bool detailsSample;
    Border? tintRow;
    string backgroundKey = "";
    Task<BitmapImage?>? backgroundImage;
    public List<PreferencesGroup> Groups { get; } = [];

    public GameModeAppearanceView(EngineForgeService service)
    {
        engine=service; store=new(engine.EngineRoot); Content=body;
        Children.Add(Prefs.Label("Loading Game Mode appearance…"));
        Loaded += async (_, _) => { if (ready) return; ready=true; await LoadAsync(); };
    }

    async Task LoadAsync()
    {
        try { appearance=await store.ReadAsync() ?? GameModeAppearance.Defaults; Build(); }
        catch (Exception error) { Children.Clear(); Children.Add(Prefs.Label(error.Message));
            Children.Add(Prefs.ActionButton("Try again", async (_, _) => await LoadAsync())); }
    }

    string Text(string key) => appearance[key]?.ToString() ?? "";
    double Number(string key, double fallback) => double.TryParse(Text(key), out var value) ? value : fallback;
    bool On(string key) => appearance[key]?.GetValue<bool>() == true;
    async Task ChangeAsync(string key, JsonNode? value)
    {
        await edits.WaitAsync();
        try
        {
            var latest=await store.ReadAsync() ?? appearance.DeepClone().AsObject(); latest[key]=value?.DeepClone();
            appearance=await store.WriteAsync(latest); Paint();
            if(tintRow is not null)tintRow.Visibility=Text("accentMode")=="theme"?Visibility.Collapsed:Visibility.Visible;
            ShowFeedback("Saved");
        }
        catch (Exception error) { ShowFeedback(error.Message); }
        finally { edits.Release(); }
    }
    void ShowFeedback(string text) { feedback.Text=text; feedback.Visibility=string.IsNullOrEmpty(text)?Visibility.Collapsed:Visibility.Visible; }

    void Build()
    {
        if(sample.Parent is Viewbox previous)previous.Child=null;
        if(feedback.Parent is Panel feedbackParent)feedbackParent.Children.Remove(feedback);
        Children.Clear(); Groups.Clear();
        var surface = new PreferencesGroup("Game Mode appearance", "The same preferences as Game Mode, saved automatically.");
        var layout = new Grid { ColumnSpacing=24, RowSpacing=16 };
        layout.ColumnDefinitions.Add(new()); layout.ColumnDefinitions.Add(new() { Width=new GridLength(440) });
        layout.RowDefinitions.Add(new() { Height=GridLength.Auto }); layout.RowDefinitions.Add(new() { Height=GridLength.Auto });
        var material = new StackPanel { Spacing=12 };
        material.Children.Add(Prefs.Label("Surface"));
        var themes = new OverlayThemePicker(Text("theme"));
        themes.SelectionChanged += async (_, _) => { if(themes.SelectedIndex>=0) await ChangeAsync("theme",JsonValue.Create(new[] {"light","clear","dark"}[themes.SelectedIndex])); };
        material.Children.Add(themes); layout.Children.Add(material);
        var preview = new StackPanel { Spacing=8 };
        var which = new ComboBox { ItemsSource=new[] {"Library preview","Game Details preview"}, SelectedIndex=0,
            HorizontalAlignment=HorizontalAlignment.Stretch };
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(which,"Game Mode appearance preview");
        which.SelectionChanged += (_, _) => { detailsSample=which.SelectedIndex==1; Paint(); };
        preview.Children.Add(which); preview.Children.Add(new Viewbox { Child=sample, Stretch=Stretch.Uniform, MaxHeight=248 });
        Grid.SetColumn(preview,1); layout.Children.Add(preview);
        layout.SizeChanged += (_, eventArgs) => { var wide=eventArgs.NewSize.Width>=820; layout.ColumnDefinitions[1].Width=wide?new GridLength(440):new GridLength(0);Grid.SetColumn(preview,wide?1:0);Grid.SetRow(preview,wide?0:1); };
        surface.Add(new Border { Style=Prefs.GetStyle("ForgeSettingsCardStyle"), Child=layout }); Groups.Add(surface);

        var main = new PreferencesGroup("Main interface", "Navigation and focus use this accent. Game colors remain separate.");
        var swatch = new Microsoft.UI.Xaml.Shapes.Ellipse { Width=24,Height=24,
            Fill=new SolidColorBrush(ArtAccent.TryParse(Text("accent"),out var color)?color:ArtAccent.NoArtwork) };
        var colorButton = new Button { Content=swatch, Width=40,Height=40,Padding=new Thickness(6),CornerRadius=new CornerRadius(20) };
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(colorButton,"Game Mode accent color");
        colorButton.Click += async (_, _) => { var picker=new ColorPicker { IsAlphaEnabled=false,Color=((SolidColorBrush)swatch.Fill).Color,
            IsMoreButtonVisible=false,IsColorChannelTextInputVisible=true,IsHexInputVisible=true,MaxWidth=340 };
            var dialog=App.Main!.NewDialog(); dialog.Title="Game Mode accent color";dialog.Content=picker;dialog.PrimaryButtonText="Use color";dialog.CloseButtonText="Cancel";
            if(await dialog.ShowAsync()==ContentDialogResult.Primary){await ChangeAsync("accent",JsonValue.Create(ArtAccent.Hex(picker.Color)));swatch.Fill=new SolidColorBrush(picker.Color);} };
        main.Add(Prefs.Row("Accent color", null, colorButton,"\uE790"));
        var backgroundButtons=new StackPanel { Orientation=Orientation.Horizontal,Spacing=8 };
        backgroundButtons.Children.Add(Prefs.ActionButton("Choose image",async (_, _) => await ChooseBackgroundAsync()));
        backgroundButtons.Children.Add(Prefs.ActionButton("Use default",async (_, _) => await ChangeAsync("background",null)));
        main.Add(Prefs.Row("Background","PNG, JPEG or WebP for the main Game Mode interface.",backgroundButtons,"\uEB9F")); Groups.Add(main);

        var details = new PreferencesGroup("Game Details", "Surface Tint follows each game's saved color or artwork.");
        Choice(details,"Accent",null,"accentMode",["None","Adaptive","Game"],["theme","adaptive","custom"]);
        var tint = new Slider { Minimum=0,Maximum=100,Value=Number("tintStrength",50),StepFrequency=5,Width=200 };
        var strength=Prefs.Row("Surface Tint","Tint strength for Game Details.",tint,"\uE790");tintRow=strength;
        strength.Visibility=Text("accentMode")=="theme"?Visibility.Collapsed:Visibility.Visible;
        tint.ValueChanged += async (_, args) => { if(ready)await ChangeAsync("tintStrength",JsonValue.Create((int)args.NewValue)); };
        details.Add(strength);
        Choice(details,"Game Details navigation",null,"detailsNavigation",["Sidebar","Tabs"],["sidebar","tabs"]); Groups.Add(details);
        var reading = new PreferencesGroup("Reading and motion");
        Choice(reading,"Text size",null,"text",["Standard","Large"],["standard","large"]);
        var (row,motion)=Prefs.SwitchRow("Motion","Follows your system's reduced-motion preference.",On("motion"),"\uE768");
        motion.Toggled += async (_, _) => await ChangeAsync("motion",JsonValue.Create(motion.IsOn));reading.Add(row);Groups.Add(reading);
        var placement = new PreferencesGroup("Layout");
        Choice(placement,"Navigation placement",null,"navigation",["Top","Bottom"],["top","bottom"]);
        Choice(placement,"Interface scale","Automatic adapts to the display.","scale",["Automatic","100%","125%","130%","150%","175%","200%"],["auto","100","125","130","150","175","200"]);Groups.Add(placement);
        placement.Add(Prefs.Row("Reset appearance", "Restore the Game Mode appearance defaults.", Prefs.ActionButton("Reset", async (_, _) =>
        { try { appearance=await store.WriteAsync(GameModeAppearance.Defaults); Build(); ShowFeedback("Appearance reset"); } catch(Exception error){ShowFeedback(error.Message);} }),"\uE777"));
        placement.Add(feedback);
        Children.Add(Groups[0].Root);
        var columns=new PresetColumns(480,2) {ColumnSpacing=24,RowSpacing=16};
        foreach(var group in Groups.Skip(1))columns.Children.Add(group.Root);Children.Add(columns);
        IsEnabled=!engine.IsPreview; Paint();
    }

    void Choice(PreferencesGroup group,string title,string? copy,string key,string[] labels,string[] values)
    {
        var (row,choice)=Prefs.ComboRow(title,copy,labels,Math.Max(0,Array.IndexOf(values,Text(key))),"\uE8A7");
        choice.SelectionChanged += async (_, _) => { if(choice.SelectedIndex<0)return;var value=values[choice.SelectedIndex];
            await ChangeAsync(key,key=="scale"&&int.TryParse(value,out var scale)?JsonValue.Create(scale):JsonValue.Create(value));
        };
        group.Add(row);
    }

    async Task ChooseBackgroundAsync()
    {
        if(await App.Main!.PickFileAsync(".png",".jpg",".jpeg",".webp") is not { } file)return;
        try
        {
            await using var input=File.OpenRead(file); if(input.Length>24*1024*1024)throw new IOException("Choose an image under 24 MB.");
            var decoder=await BitmapDecoder.CreateAsync(input.AsRandomAccessStream());
            var ratio=Math.Min(1,1920d/Math.Max(decoder.PixelWidth,decoder.PixelHeight));
            var transform=new BitmapTransform { ScaledWidth=Math.Max(1,(uint)(decoder.PixelWidth*ratio)),ScaledHeight=Math.Max(1,(uint)(decoder.PixelHeight*ratio)) };
            var pixels=await decoder.GetPixelDataAsync(BitmapPixelFormat.Bgra8,BitmapAlphaMode.Ignore,transform,ExifOrientationMode.RespectExifOrientation,ColorManagementMode.ColorManageToSRgb);
            using var output=new InMemoryRandomAccessStream();var encoder=await BitmapEncoder.CreateAsync(BitmapEncoder.JpegEncoderId,output);
            encoder.SetPixelData(BitmapPixelFormat.Bgra8,BitmapAlphaMode.Ignore,transform.ScaledWidth,transform.ScaledHeight,96,96,pixels.DetachPixelData());await encoder.FlushAsync();
            output.Seek(0);using var reader=new DataReader(output);await reader.LoadAsync((uint)output.Size);var bytes=new byte[(int)output.Size];reader.ReadBytes(bytes);
            var value="data:image/jpeg;base64,"+Convert.ToBase64String(bytes);if(value.Length>1600000)throw new IOException("Choose a smaller image for the Game Mode background.");
            await ChangeAsync("background",JsonValue.Create(value));
        }
        catch(Exception error){ShowFeedback(error.Message);}
    }

    void Paint()
    {
        sample.Children.Clear();var light=Text("theme")=="light";var ink=new SolidColorBrush(light?global::Windows.UI.Color.FromArgb(255,35,35,33):global::Windows.UI.Color.FromArgb(255,245,243,238));
        var accent=ArtAccent.TryParse(Text("accent"),out var value)?value:ArtAccent.NoArtwork;
        var background=new Border { Width=480,Height=270,CornerRadius=new CornerRadius(12),Background=new SolidColorBrush(light?global::Windows.UI.Color.FromArgb(255,225,225,220):global::Windows.UI.Color.FromArgb(255,27,28,29)) };sample.Children.Add(background);
        var games=App.Main?.Games.Where(game=>game.PosterPath is not null&&File.Exists(game.PosterPath)).Take(6).ToArray()??[];
        if(Text("background").StartsWith("data:image/",StringComparison.Ordinal))_ = PaintBackgroundAsync(background,Text("background"));
        var nav=new Border { Width=448,Height=30,CornerRadius=new CornerRadius(8),Background=new SolidColorBrush(global::Windows.UI.Color.FromArgb(light?(byte)190:(byte)150,light?(byte)245:(byte)35,light?(byte)245:(byte)36,light?(byte)240:(byte)37)) };
        nav.Child=new TextBlock { Text="rtxForge     Library     Presets     Packages     Settings",FontSize=12,Foreground=ink,VerticalAlignment=VerticalAlignment.Center,Margin=new Thickness(12,0,0,0) };Canvas.SetLeft(nav,16);Canvas.SetTop(nav,Text("navigation")=="bottom"?224:16);sample.Children.Add(nav);
        var title=new TextBlock { Text=detailsSample?games.FirstOrDefault()?.Name??"Game Details":"Your library",FontSize=Text("text")=="large"?23:20,FontWeight=Microsoft.UI.Text.FontWeights.SemiBold,Foreground=ink,MaxWidth=440,TextTrimming=TextTrimming.CharacterEllipsis };Canvas.SetLeft(title,20);Canvas.SetTop(title,Text("navigation")=="bottom"?28:62);sample.Children.Add(title);
        for(var index=0;index<games.Length;index++){
            var card=new Border { Width=65,Height=100,CornerRadius=new CornerRadius(5),Background=new SolidColorBrush(accent) };
            card.Child=new Image { Source=new BitmapImage(new Uri(games[index].PosterPath!)),Stretch=Stretch.UniformToFill };
            Canvas.SetLeft(card,20+index*73);Canvas.SetTop(card,Text("navigation")=="bottom"?70:102);sample.Children.Add(card);
        }
        if(detailsSample){var pane=new Border { Width=300,Height=105,CornerRadius=new CornerRadius(8),Background=new SolidColorBrush(Text("accentMode")=="theme"?global::Windows.UI.Color.FromArgb(235,45,45,43):global::Windows.UI.Color.FromArgb((byte)(80+Number("tintStrength",50)*1.4),accent.R,accent.G,accent.B)),Child=new TextBlock { Text=Text("detailsNavigation")=="sidebar"?"Overview\nGraphics\nReShade & add-ons":"Overview   Graphics   ReShade & add-ons",Foreground=ink,FontSize=14,TextWrapping=TextWrapping.Wrap,Margin=new Thickness(16) } };Canvas.SetLeft(pane,150);Canvas.SetTop(pane,102);sample.Children.Add(pane);}
    }

    async Task PaintBackgroundAsync(Border background,string data)
    {
        if(backgroundKey!=data || backgroundImage is null){backgroundKey=data;backgroundImage=DecodeBackgroundAsync(data);}
        var bitmap=await backgroundImage;if(bitmap is not null&&backgroundKey==data)background.Background=new ImageBrush {ImageSource=bitmap,Stretch=Stretch.UniformToFill};
    }
    static async Task<BitmapImage?> DecodeBackgroundAsync(string data)
    {
        try { var bytes=Convert.FromBase64String(data[(data.IndexOf(',')+1)..]);using var stream=new InMemoryRandomAccessStream();using(var writer=new DataWriter(stream)){writer.WriteBytes(bytes);await writer.StoreAsync();writer.DetachStream();}stream.Seek(0);var bitmap=new BitmapImage();await bitmap.SetSourceAsync(stream);return bitmap; }
        catch(Exception) {return null;}
    }
}
