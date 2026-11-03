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
    readonly EngineForgeService? engine;
    readonly GameModeAppearance? store;
    readonly SemaphoreSlim edits = new(1, 1);
    readonly TextBlock feedback = new() { FontSize=12, TextWrapping=TextWrapping.Wrap, Visibility=Visibility.Collapsed };
    readonly Canvas sample = new() { Width=480, Height=270, IsHitTestVisible=false };
    readonly Canvas detailsSample = new() { Width=480, Height=270, IsHitTestVisible=false };
    JsonObject appearance = GameModeAppearance.Defaults;
    bool ready;
    Border? tintRow;
    string backgroundKey = "";
    Task<BitmapImage?>? backgroundImage;
    public List<PreferencesGroup> Groups { get; } = [];

    public GameModeAppearanceView(EngineForgeService? service)
    {
        engine=service; store=engine is null?null:new(engine.EngineRoot); Content=body;
        Children.Add(Prefs.Label("Loading Game Mode appearance…"));
        Loaded += async (_, _) => { if (ready) return; ready=true; await LoadAsync(); };
    }

    async Task LoadAsync()
    {
        try { appearance=(store is null?null:await store.ReadAsync()) ?? GameModeAppearance.Defaults; Build(); }
        catch (Exception error) { Children.Clear(); Children.Add(Prefs.Label(error.Message));
            Children.Add(Prefs.ActionButton("Try again", async (_, _) => await LoadAsync())); }
    }

    string Text(string key) => appearance[key]?.ToString() ?? "";
    double Number(string key, double fallback) => double.TryParse(Text(key), out var value) ? value : fallback;
    bool On(string key) => appearance[key]?.GetValue<bool>() == true;
    async Task ChangeAsync(string key, JsonNode? value)
    {
        if(store is null)return;
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
        if(detailsSample.Parent is Viewbox previousDetails)previousDetails.Child=null;
        if(feedback.Parent is Panel feedbackParent)feedbackParent.Children.Remove(feedback);
        Children.Clear(); Groups.Clear();
        var surface = new PreferencesGroup("Game Mode appearance", "The same preferences as Game Mode, saved automatically.");
        var layout = new Grid { ColumnSpacing=24, RowSpacing=16 };
        layout.ColumnDefinitions.Add(new()); layout.ColumnDefinitions.Add(new() { Width=new GridLength(440) });
        layout.RowDefinitions.Add(new() { Height=GridLength.Auto }); layout.RowDefinitions.Add(new() { Height=GridLength.Auto });
        var material = new StackPanel { Spacing=12 };
        var themes = new OverlayThemePicker(Text("theme"));
        themes.SelectionChanged += async (_, _) => { if(themes.SelectedIndex>=0) await ChangeAsync("theme",JsonValue.Create(new[] {"light","clear","dark"}[themes.SelectedIndex])); };
        material.Children.Add(themes); layout.Children.Add(material);
        var preview = new StackPanel { Spacing=12 };
        preview.Children.Add(Prefs.Label("Library preview"));
        preview.Children.Add(new Viewbox { Child=sample, Stretch=Stretch.Uniform, MaxHeight=248 });
        Grid.SetColumn(preview,1); layout.Children.Add(preview);
        layout.SizeChanged += (_, eventArgs) => { var wide=eventArgs.NewSize.Width>=820; layout.ColumnDefinitions[1].Width=wide?new GridLength(440):new GridLength(0);Grid.SetColumn(preview,wide?1:0);Grid.SetRow(preview,wide?0:1); };
        surface.Add(new Border { Style=Prefs.GetStyle("ForgeSettingsCardStyle"), Child=layout }); Groups.Add(surface);

        var main = new PreferencesGroup(null);
        material.Children.Add(main.Root);
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
        main.Add(Prefs.Row("Background","PNG, JPEG or WebP for the main Game Mode interface.",backgroundButtons,"\uEB9F"));
        Choice(main,"Text size",null,"text",["Standard","Large"],["standard","large"]);
        Choice(main,"Navigation placement",null,"navigation",["Top","Bottom"],["top","bottom"]);
        Choice(main,"Interface scale","Automatic adapts to the display.","scale",["Automatic","100%","125%","130%","150%","175%","200%"],["auto","100","125","130","150","175","200"]);

        var details = new PreferencesGroup("Game Details", "Surface Tint follows each game's saved color or artwork.");
        details.Add(Prefs.Label("Game Details preview"));
        details.Add(new Viewbox { Child=detailsSample, Stretch=Stretch.Uniform, MaxHeight=220 });
        Choice(details,"Surface",null,"detailsTheme",["Match Game Mode","Light","Clear","Dark"],["same","light","clear","dark"]);
        Choice(details,"Accent",null,"accentMode",["None","Adaptive","Game"],["theme","adaptive","custom"]);
        var tint = new Slider { Minimum=0,Maximum=100,Value=Number("tintStrength",50),StepFrequency=5,Width=200 };
        var strength=Prefs.Row("Surface Tint","Tint strength for Game Details.",tint,"\uE790");tintRow=strength;
        strength.Visibility=Text("accentMode")=="theme"?Visibility.Collapsed:Visibility.Visible;
        tint.ValueChanged += async (_, args) => { if(ready)await ChangeAsync("tintStrength",JsonValue.Create((int)args.NewValue)); };
        details.Add(strength);
        Choice(details,"Game Details navigation",null,"detailsNavigation",["Sidebar","Tabs"],["sidebar","tabs"]); Groups.Add(details);
        var reading = new PreferencesGroup("Motion and reset");
        var (row,motion)=Prefs.SwitchRow("Motion","Follows your system's reduced-motion preference.",On("motion"),"\uE768");
        motion.Toggled += async (_, _) => await ChangeAsync("motion",JsonValue.Create(motion.IsOn));reading.Add(row);Groups.Add(reading);
        reading.Add(Prefs.Row("Reset appearance", "Restore the Game Mode appearance defaults.", Prefs.ActionButton("Reset", async (_, _) =>
        { try { if(store is null)return; appearance=await store.WriteAsync(GameModeAppearance.Defaults); Build(); ShowFeedback("Appearance reset"); } catch(Exception error){ShowFeedback(error.Message);} }),"\uE777"));
        reading.Add(feedback);
        Children.Add(Groups[0].Root);
        var columns=new PresetColumns(480,2) {ColumnSpacing=24,RowSpacing=16};
        foreach(var group in Groups.Skip(1))columns.Children.Add(group.Root);Children.Add(columns);
        IsEnabled=engine is { IsPreview:false }; Paint();
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
        sample.Children.Clear();
        var light = Text("theme") == "light";
        var clear = Text("theme") == "clear";
        var accent = ArtAccent.TryParse(Text("accent"), out var value) ? value : ArtAccent.NoArtwork;
        var ink = new SolidColorBrush(light ? global::Windows.UI.Color.FromArgb(255,35,35,33) : global::Windows.UI.Color.FromArgb(255,245,243,238));
        var shellInk = new SolidColorBrush(global::Windows.UI.Color.FromArgb(255,245,243,238));
        var glass = new SolidColorBrush(light ? global::Windows.UI.Color.FromArgb(222,246,244,239) :
            global::Windows.UI.Color.FromArgb(clear ? (byte)128 : (byte)231,42,42,43));
        void Place(UIElement element, double x, double y)
        {
            Canvas.SetLeft(element,x); Canvas.SetTop(element,y); sample.Children.Add(element);
        }
        var asset = light ? "app-hero-light.png" : "app-hero-dark.png";
        var backdrop = new Border { Width=480,Height=270,CornerRadius=new CornerRadius(12),Background=new ImageBrush
        {
            ImageSource=new BitmapImage(new Uri(Path.Combine(AppContext.BaseDirectory,"Assets","GameMode",asset))) { DecodePixelWidth=480 },
            Stretch=Stretch.UniformToFill, Opacity=light ? .85 : .58,
        }};
        Place(backdrop,0,0);
        if(Text("background").StartsWith("data:image/",StringComparison.Ordinal)) _=PaintBackgroundAsync(backdrop,Text("background"));
        var bottom = Text("navigation") == "bottom";
        var navTop = bottom ? 231 : 10;
        var libraryTop = bottom ? 10 : 49;
        Place(new TextBlock { Text="rtxForge",FontSize=13,FontWeight=Microsoft.UI.Text.FontWeights.Bold,Foreground=shellInk },18,navTop+8);
        Place(new Border { Width=270,Height=30,CornerRadius=new CornerRadius(15),Background=glass },107,navTop);
        Place(new Border { Width=53,Height=23,CornerRadius=new CornerRadius(12),Background=new SolidColorBrush(
            global::Windows.UI.Color.FromArgb(82,accent.R,accent.G,accent.B)) },111,navTop+3);
        Place(new TextBlock { Text="Library     Presets     Packages     Extras     Settings",FontSize=10,Foreground=ink },121,navTop+8);
        Place(new Border { Width=456,Height=176,CornerRadius=new CornerRadius(13),Background=glass,BorderBrush=new SolidColorBrush(
            global::Windows.UI.Color.FromArgb(55,255,255,255)),BorderThickness=new Thickness(1) },12,libraryTop);
        Place(new TextBlock { Text="LIBRARY",FontSize=Text("text")=="large"?19:16,FontWeight=Microsoft.UI.Text.FontWeights.Bold,Foreground=ink },24,libraryTop+10);

        var games=App.Main?.Games.Where(game=>game.PosterPath is not null&&File.Exists(game.PosterPath)).Take(6).ToArray()??[];
        for(var index=0;index<6;index++)
        {
            var card=new Border { Width=63,Height=96,CornerRadius=new CornerRadius(6),Background=glass,
                BorderBrush=new SolidColorBrush(accent),BorderThickness=new Thickness(index==0?2:0) };
            if(index<games.Length)card.Child=new Image { Source=new BitmapImage(new Uri(games[index].PosterPath!)),Stretch=Stretch.UniformToFill };
            Place(card,25+index*72,libraryTop+52);
        }
        PaintDetails();
    }

    void PaintDetails()
    {
        detailsSample.Children.Clear();
        var theme = Text("detailsTheme") is "light" or "clear" or "dark" ? Text("detailsTheme") : Text("theme");
        var light = theme == "light";
        var game = App.Main?.Games.FirstOrDefault(item => item.HeroPath is { } path && File.Exists(path));
        var accent = ArtAccent.TryParse(Text("accent"), out var color) ? color : ArtAccent.NoArtwork;
        var ink = new SolidColorBrush(light ? global::Windows.UI.Color.FromArgb(255,30,30,29) : global::Windows.UI.Color.FromArgb(255,246,243,238));
        void Place(UIElement element, double x, double y)
        {
            Canvas.SetLeft(element,x); Canvas.SetTop(element,y); detailsSample.Children.Add(element);
        }
        var neutral = light ? global::Windows.UI.Color.FromArgb(255,235,230,225) : global::Windows.UI.Color.FromArgb(255,40,40,42);
        Place(new Border { Width=480,Height=270,CornerRadius=new CornerRadius(12),Background=new SolidColorBrush(neutral) },0,0);
        if (game?.HeroPath is { } hero)
            Place(new Border { Width=480,Height=132,Background=new ImageBrush
            {
                ImageSource=new BitmapImage(new Uri(hero)) { DecodePixelWidth=480 },
                Stretch=Stretch.UniformToFill,Opacity=.55,
            } },0,0);
        var tint=(Number("tintStrength",50)/100)*.55;
        if(Text("accentMode")=="theme")tint=0;
        byte Blend(byte channel,byte hue)=>(byte)(channel+(hue-channel)*tint);
        var glass=new SolidColorBrush(global::Windows.UI.Color.FromArgb(theme=="clear"?(byte)170:(byte)238,
            Blend(neutral.R,accent.R),Blend(neutral.G,accent.G),Blend(neutral.B,accent.B)));
        Place(new TextBlock { Text=game?.Name??"Game Details",Foreground=ink,FontSize=20,MaxWidth=420,
            TextTrimming=TextTrimming.CharacterEllipsis,FontWeight=Microsoft.UI.Text.FontWeights.Bold },24,83);
        var tabs=Text("detailsNavigation")=="tabs";
        Place(new Border { Width=442,Height=114,CornerRadius=new CornerRadius(11),Background=glass },19,140);
        Place(new TextBlock { Text=tabs?"Overview     Features     DLSS Files":"Overview\nFeatures\nDLSS Files",Foreground=ink,FontSize=12 },31,153);
        Place(new TextBlock { Text="Features     Compatibility",Foreground=ink,FontSize=12 },tabs?31:143,tabs?194:153);
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
