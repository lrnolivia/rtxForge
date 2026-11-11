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
    Border? customAccentRow;
    string backgroundKey = "";
    Task<BitmapImage?>? backgroundImage;
    string? sampledBackground;
    global::Windows.UI.Color? libraryAccent;
    public List<PreferencesGroup> Groups { get; } = [];

    public GameModeAppearanceView(EngineForgeService? service)
    {
        engine=service; store=engine is null?null:new(engine.EngineRoot); Content=body;
        Children.Add(Prefs.Label("Loading Game Mode appearance…"));
        Loaded += async (_, _) =>
        {
            if (App.Main is { } shell)
            {
                shell.GamesChanged += RepaintWhenReady;
                shell.SystemAccentChanged += RepaintSystemAccent;
            }
            if (ready) { Paint(); return; }
            ready=true;
            await LoadAsync();
        };
        Unloaded += (_, _) =>
        {
            if (App.Main is not { } shell) return;
            shell.GamesChanged -= RepaintWhenReady;
            shell.SystemAccentChanged -= RepaintSystemAccent;
        };
    }

    void RepaintWhenReady() { if (ready) Paint(); }
    void RepaintSystemAccent() { if (ready && Text("accentSource") == "system") Paint(); }

    async Task LoadAsync()
    {
        try
        {
            appearance=(store is null?null:await store.ReadAsync()) ?? GameModeAppearance.Defaults;
            await ReadLibraryAccentAsync();
            Build();
        }
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
            appearance=await store.WriteAsync(latest);
            await ReadLibraryAccentAsync();
            Paint();
            if(customAccentRow is not null)customAccentRow.Visibility=Text("accentSource")=="custom"?Visibility.Visible:Visibility.Collapsed;
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
        var material = new StackPanel { Spacing=12 };
        var themes = new OverlayThemePicker(Text("theme"));
        themes.SelectionChanged += async (_, _) =>
        {
            if(themes.SelectedIndex>=0) await ChangeAsync("theme",JsonValue.Create(new[] {"light","clear","dark"}[themes.SelectedIndex]));
        };
        material.Children.Add(themes);
        var previewOptions = new PreferencesGroup(null);
        surface.Add(PreviewPanel(material, sample, "Library preview", "library", previewOptions.Root));
        Groups.Add(surface);

        var main = new PreferencesGroup(null);
        material.Children.Add(main.Root);
        Choice(main,"Accent",null,"accentSource",AccentResources.Captions,AccentResources.Sources);
        var swatch = new Microsoft.UI.Xaml.Shapes.Ellipse { Width=24,Height=24,
            Fill=new SolidColorBrush(ArtAccent.TryParse(Text("accent"),out var color)?color:ArtAccent.NoArtwork) };
        var colorButton = new Button { Content=swatch, Width=40,Height=40,Padding=new Thickness(6),CornerRadius=new CornerRadius(20) };
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(colorButton,"Game Mode accent color");
        colorButton.Click += async (_, _) =>
        {
            if (await AccentResources.PickAsync(App.Main!, "Game Mode accent color", ((SolidColorBrush)swatch.Fill).Color) is not { } picked) return;
            await ChangeAsync("accent", JsonValue.Create(ArtAccent.Hex(picked)));
            swatch.Fill = new SolidColorBrush(AccentResources.Resolve("custom", Text("accent")));
        };
        customAccentRow = Prefs.Row("Custom accent color", null, colorButton,"\uE790");
        customAccentRow.Visibility = Text("accentSource") == "custom" ? Visibility.Visible : Visibility.Collapsed;
        main.Add(customAccentRow);
        var backgroundButtons=new StackPanel { Orientation=Orientation.Horizontal,Spacing=8 };
        backgroundButtons.Children.Add(Prefs.ActionButton("Choose image",async (_, _) => await ChooseBackgroundAsync()));
        backgroundButtons.Children.Add(Prefs.ActionButton("Use default",async (_, _) => await ChangeAsync("background",null)));
        main.Add(Prefs.Row("Background","PNG, JPEG or WebP for the main Game Mode interface.",backgroundButtons,"\uEB9F"));
        Choice(main,"Navigation placement",null,"navigation",["Top","Bottom"],["top","bottom"]);
        Choice(main,"Text size",null,"text",["Standard","Large"],["standard","large"]);
        Choice(previewOptions,"Interface scale","Automatic adapts to the display.","scale",["Automatic","100%","125%","130%","150%","175%","200%"],["auto","100","125","130","150","175","200"]);

        var details = new PreferencesGroup("Game Details", "Use a separate surface and adjust how each game’s accent appears.");
        var detailsOptions = new PreferencesGroup(null);
        Choice(detailsOptions,"Surface",null,"detailsTheme",["Match Game Mode","Light","Clear","Dark"],["same","light","clear","dark"]);
        Choice(detailsOptions,"Accent source",null,"accentMode",["None","Adaptive","Game"],["theme","adaptive","custom"]);
        var tint = new Slider { Minimum=0,Maximum=100,Value=Number("tintStrength",50),StepFrequency=5,Width=200 };
        var strength=Prefs.Row("Surface Tint","Tint strength for Game Details.",tint,"\uE790");tintRow=strength;
        strength.Visibility=Text("accentMode")=="theme"?Visibility.Collapsed:Visibility.Visible;
        tint.ValueChanged += async (_, args) => { if(ready)await ChangeAsync("tintStrength",JsonValue.Create((int)args.NewValue)); };
        detailsOptions.Add(strength);
        Choice(detailsOptions,"Game Details navigation",null,"detailsNavigation",["Sidebar","Tabs"],["sidebar","tabs"]);
        details.Add(PreviewPanel(detailsOptions.Root, detailsSample, "Game Details preview", "details", null));
        Groups.Add(details);
        var reading = new PreferencesGroup("Motion and reset");
        var (row,motion)=Prefs.SwitchRow("Motion","Follows your system's reduced-motion preference.",On("motion"),"\uE768");
        motion.Toggled += async (_, _) => await ChangeAsync("motion",JsonValue.Create(motion.IsOn));reading.Add(row);Groups.Add(reading);
        reading.Add(Prefs.Row("Reset appearance", "Restore the Game Mode appearance defaults.", Prefs.ActionButton("Reset", async (_, _) =>
        { try { if(store is null)return; appearance=await store.WriteAsync(GameModeAppearance.Defaults); Build(); ShowFeedback("Appearance reset"); } catch(Exception error){ShowFeedback(error.Message);} }),"\uE777"));
        reading.Add(feedback);
        foreach(var group in Groups) Children.Add(group.Root);
        IsEnabled=engine is { IsPreview:false }; Paint();
    }

    static Border PreviewPanel(FrameworkElement options, Canvas scene, string caption, string route, FrameworkElement? previewOptions)
    {
        var layout = new Grid { ColumnSpacing=20, RowSpacing=16 };
        layout.ColumnDefinitions.Add(new());
        layout.ColumnDefinitions.Add(new() { Width=new GridLength(0) });
        layout.RowDefinitions.Add(new() { Height=GridLength.Auto });
        layout.RowDefinitions.Add(new() { Height=GridLength.Auto });
        layout.Children.Add(options);
        // Centred beside the options column when the two sit side by side.
        var preview = new StackPanel { Spacing=10, MaxWidth=560, HorizontalAlignment=HorizontalAlignment.Stretch, VerticalAlignment=VerticalAlignment.Center };
        preview.Children.Add(Prefs.Label(caption, "ForgeCaptionDimTextStyle"));
        preview.Children.Add(new Viewbox { Child=scene, Stretch=Stretch.Uniform });
        var open = Prefs.ActionButton("Open full preview", async (_, _) => await App.Main!.OpenGameModePreview(route));
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(open, "Open " + caption);
        preview.Children.Add(open);
        if(previewOptions is not null) preview.Children.Add(previewOptions);
        Grid.SetRow(preview,1);
        layout.Children.Add(preview);
        layout.SizeChanged += (_, args) =>
        {
            var wide=args.NewSize.Width>=780;
            layout.ColumnDefinitions[1].Width=wide ? new GridLength(Math.Min(560,args.NewSize.Width*.46)) : new GridLength(0);
            Grid.SetColumn(preview,wide?1:0); Grid.SetRow(preview,wide?0:1);
        };
        return new Border { Style=Prefs.GetStyle("ForgeSettingsCardStyle"), Padding=new Thickness(16), Child=layout };
    }

    static Uri? Artwork(string? path)
    {
        if (!Uri.TryCreate(path, UriKind.Absolute, out var uri)) return null;
        return uri.IsFile ? File.Exists(uri.LocalPath) ? uri : null
            : uri.Scheme == Uri.UriSchemeHttps ? uri : null;
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
        var accent = AccentResources.Resolve(Text("accentSource"), Text("accent"));
        var surfaceAccent = Text("accentMode") == "adaptive" && libraryAccent is { } sampled ? sampled : accent;
        var ink = new SolidColorBrush(light ? global::Windows.UI.Color.FromArgb(255,35,35,33) : global::Windows.UI.Color.FromArgb(255,245,243,238));
        var shellInk = new SolidColorBrush(global::Windows.UI.Color.FromArgb(255,245,243,238));
        var neutral = light ? global::Windows.UI.Color.FromArgb(222,246,244,239) :
            global::Windows.UI.Color.FromArgb(clear ? (byte)128 : (byte)231,42,42,43);
        var strength = TintStrength();
        var glass = new SolidColorBrush(Mix(neutral, surfaceAccent, .09 * strength));
        var navigationGlass = new SolidColorBrush(Mix(neutral, surfaceAccent, .07 * strength));
        void Place(UIElement element, double x, double y)
        {
            Canvas.SetLeft(element,x); Canvas.SetTop(element,y); sample.Children.Add(element);
        }
        var asset = LibraryBackground(light);
        var backdrop = new Border { Width=480,Height=270,CornerRadius=new CornerRadius(12),Background=new ImageBrush
        {
            ImageSource=new BitmapImage(new Uri(asset)) { DecodePixelWidth=480 },
            Stretch=Stretch.UniformToFill, Opacity=light ? .85 : .58,
        }};
        Place(backdrop,0,0);
        if(Text("background").StartsWith("data:image/",StringComparison.Ordinal)) _=PaintBackgroundAsync(backdrop,Text("background"));
        var bottom = Text("navigation") == "bottom";
        var navTop = bottom ? 231 : 10;
        var libraryTop = bottom ? 10 : 49;
        Place(new TextBlock { Text="rtxForge",FontSize=13,FontWeight=Microsoft.UI.Text.FontWeights.Bold,Foreground=shellInk },18,navTop+8);
        Place(new Border { Width=270,Height=30,CornerRadius=new CornerRadius(15),Background=navigationGlass },107,navTop);
        Place(new Border { Width=53,Height=23,CornerRadius=new CornerRadius(12),Background=new SolidColorBrush(
            global::Windows.UI.Color.FromArgb(82,accent.R,accent.G,accent.B)) },111,navTop+3);
        Place(new TextBlock { Text="Library     Presets     Packages     Extras     Settings",FontSize=10,Foreground=ink },121,navTop+8);
        Place(new Border { Width=456,Height=176,CornerRadius=new CornerRadius(13),Background=glass,BorderBrush=new SolidColorBrush(
            global::Windows.UI.Color.FromArgb(55,255,255,255)),BorderThickness=new Thickness(1) },12,libraryTop);
        Place(new TextBlock { Text="LIBRARY",FontSize=Text("text")=="large"?19:16,FontWeight=Microsoft.UI.Text.FontWeights.Bold,Foreground=ink },24,libraryTop+10);

        var posters=App.Main?.Games.Select(game=>Artwork(game.PosterPath)).OfType<Uri>().Take(6).ToArray()??[];
        for(var index=0;index<6;index++)
        {
            var card=new Border { Width=63,Height=96,CornerRadius=new CornerRadius(6),Background=glass,
                BorderBrush=new SolidColorBrush(accent),BorderThickness=new Thickness(index==0?2:0) };
            if(index<posters.Length)card.Child=new Image { Source=new BitmapImage(posters[index]) { DecodePixelWidth=110 },Stretch=Stretch.UniformToFill };
            Place(card,25+index*72,libraryTop+52);
        }
        PaintDetails();
    }

    Models.Game? accentGame;
    global::Windows.UI.Color? gameAccent;
    async Task LoadGameAccentAsync(Models.Game game)
    {
        var palette = await ArtAccent.ForGameAsync(game);
        if (palette is null) return;
        DispatcherQueue.TryEnqueue(() =>
        {
            if (!ReferenceEquals(accentGame, game) || !IsLoaded) return;
            gameAccent = palette.Color;
            PaintDetails();
        });
    }

    void PaintDetails()
    {
        detailsSample.Children.Clear();
        var theme = Text("detailsTheme") is "light" or "clear" or "dark" ? Text("detailsTheme") : Text("theme");
        var light = theme == "light";
        var game = App.Main?.Games.FirstOrDefault(item => Artwork(item.HeroPath ?? item.PosterPath) is not null);
        var accent = ArtAccent.TryParse(Text("accent"), out var color) ? color : ArtAccent.NoArtwork;
        // Adaptive and Game take the sample game's artwork colour, as Game Mode
        // does; the Game Mode accent is only the fallback while it loads.
        if(Text("accentMode") != "theme" && game is not null)
        {
            var custom = App.Main?.Settings.GameAccents.GetValueOrDefault(game.Id);
            if(ArtAccent.TryParse(custom ?? "", out var saved)) accent = saved;
            else if(ReferenceEquals(accentGame, game)) { if(gameAccent is { } sampled) accent = sampled; }
            else { accentGame = game; gameAccent = null; _ = LoadGameAccentAsync(game); }
        }
        var ink = new SolidColorBrush(light ? global::Windows.UI.Color.FromArgb(255,30,30,29) : global::Windows.UI.Color.FromArgb(255,246,243,238));
        void Place(UIElement element, double x, double y)
        {
            Canvas.SetLeft(element,x); Canvas.SetTop(element,y); detailsSample.Children.Add(element);
        }
        var neutral = light ? global::Windows.UI.Color.FromArgb(255,235,230,225) : global::Windows.UI.Color.FromArgb(255,40,40,42);
        var titleInk = new SolidColorBrush(light ? global::Windows.UI.Color.FromArgb(255,50,39,34) : accent);
        var hero = Artwork(game?.HeroPath) ?? new Uri(Path.Combine(AppContext.BaseDirectory,"Assets","GameMode",light?"app-hero-light.png":"app-hero-dark.png"));
        ImageBrush Image(Uri uri, double opacity=1) => new()
        {
            ImageSource=new BitmapImage(uri) { DecodePixelWidth=480 }, Stretch=Stretch.UniformToFill, Opacity=opacity
        };
        void Panel(double x,double y,double w,double h,double radius,Brush background) =>
            Place(new Border { Width=w, Height=h, CornerRadius=new CornerRadius(radius), Background=background },x,y);
        void Label(string label,double x,double y,double size,Brush foreground,double width=440,bool bold=false) =>
            Place(new TextBlock { Text=label,FontSize=size,Foreground=foreground,MaxWidth=width,TextTrimming=TextTrimming.CharacterEllipsis,
                FontWeight=bold?Microsoft.UI.Text.FontWeights.SemiBold:Microsoft.UI.Text.FontWeights.Normal },x,y);

        var surface = neutral;
        surface.A=theme=="clear"?(byte)170:(byte)238;
        var glassColor = Mix(surface, accent, .25 * TintStrength());
        var glass = new SolidColorBrush(glassColor);
        var raised = new SolidColorBrush(global::Windows.UI.Color.FromArgb(60,accent.R,accent.G,accent.B));
        Panel(0,0,480,270,12,new SolidColorBrush(neutral));
        Panel(0,0,480,270,12,Image(hero,.20));
        var bottom = Text("navigation")=="bottom";
        var navY=bottom?239:8;
        var panelY=bottom?8:39;
        Panel(121,navY,248,24,12,glass);
        Panel(124,navY+3,45,18,9,raised);
        Label("rtxForge",18,navY+4,12,ink,bold:true);
        Label("Library    Presets    Packages    Extras    Settings",132,navY+5,9,ink);
        Panel(12,panelY,456,190,12,glass);
        Panel(12,panelY,456,106,11,Image(hero,light?.64:.86));
        var fade = new LinearGradientBrush { StartPoint=new global::Windows.Foundation.Point(0,0), EndPoint=new global::Windows.Foundation.Point(0,1) };
        fade.GradientStops.Add(new GradientStop { Color=global::Windows.UI.Color.FromArgb(0,neutral.R,neutral.G,neutral.B),Offset=.15 });
        fade.GradientStops.Add(new GradientStop { Color=glassColor,Offset=1 });
        Panel(12,panelY+35,456,78,9,fade);
        if (Artwork(game?.PosterPath) is { } poster)
            Panel(25,panelY+31,43,65,5,Image(poster));
        Label(game?.Name??"Game Details",76,panelY+48,16,titleInk,285,true);
        Panel(74,panelY+72,246,21,5,glass);
        Label("Steam   ·   Overview",82,panelY+76,9,ink);
        Panel(354,panelY+72,96,21,11,raised);
        Label("Update Features",365,panelY+76,9,ink);

        var tabs=Text("detailsNavigation")=="tabs";
        if (tabs)
        {
            Panel(23,panelY+111,54,19,5,raised);
            Label("Overview    Features    DLSS Files    Tools    Appearance",30,panelY+113,9,ink);
        }
        else
        {
            Panel(23,panelY+111,76,19,5,raised);
            Label("Overview",30,panelY+113,9,ink);
            Label("Features",30,panelY+136,9,ink);
            Label("DLSS Files",30,panelY+156,9,ink);
        }
        var cardX=tabs?23:110;
        var cardY=panelY+(tabs?136:111);
        var cardWidth=(452-cardX-12)/3d;
        var labels=new[] { "Features", "Compatibility", "Neural rendering" };
        for(var index=0;index<labels.Length;index++)
        {
            var x=cardX+index*(cardWidth+6);
            Panel(x,cardY,cardWidth,41,6,raised);
            Label(labels[index],x+7,cardY+6,8,ink,cardWidth-14,true);
            Panel(x+7,cardY+23,cardWidth*.53,7,3,glass);
        }
    }

    static string LibraryBackground(bool light) => Path.Combine(AppContext.BaseDirectory,"Assets","GameMode",
        light ? "app-hero-light.png" : "app-hero-dark.png");

    async Task ReadLibraryAccentAsync()
    {
        if (Text("accentMode") != "adaptive") return;
        var source = Text("background");
        var custom = source.StartsWith("data:image/",StringComparison.Ordinal);
        if (!custom) source = LibraryBackground(Text("theme") == "light");
        if (sampledBackground == source) return;
        sampledBackground = source;
        libraryAccent = null;
        try
        {
            var bytes = custom ? Convert.FromBase64String(source[(source.IndexOf(',')+1)..]) : await File.ReadAllBytesAsync(source);
            libraryAccent = await ArtAccent.SignatureColorAsync(bytes);
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or FormatException
            or ArgumentException or System.Runtime.InteropServices.COMException) {}
    }

    double TintStrength() => Text("accentMode")=="theme" ? 0 : Math.Clamp(Number("tintStrength",50),0,100)/50;

    static global::Windows.UI.Color Mix(global::Windows.UI.Color surface, global::Windows.UI.Color accent, double amount)
    {
        byte Blend(byte channel,byte hue)=>(byte)(channel+(hue-channel)*amount);
        return global::Windows.UI.Color.FromArgb(surface.A,Blend(surface.R,accent.R),Blend(surface.G,accent.G),Blend(surface.B,accent.B));
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
