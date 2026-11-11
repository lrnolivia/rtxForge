using System.Diagnostics;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Imaging;
using RtxForge.Windows.Models;
using RtxForge.Windows.Services;
using Windows.UI;

namespace RtxForge.Windows.Controls;

/// <summary>Instant layout illustration; the real renderer opens only on click.</summary>
sealed class OverlayPreviewView : StackPanel
{
    readonly EngineForgeService? engine;
    readonly AutoSuggestBox search = new() { PlaceholderText = "Find a game…", DisplayMemberPath = "Name", HorizontalAlignment=HorizontalAlignment.Stretch, QueryIcon = new SymbolIcon(Symbol.Find) };
    readonly Canvas scene = new() { Width = 960, Height = 540, IsHitTestVisible = false };
    readonly Canvas diagram = new() { Width = 960, Height = 540, IsHitTestVisible = false };
    readonly Image image = new() { Stretch = Stretch.UniformToFill };
    readonly Button frame;
    readonly TextBlock status = new() { Text = "Explore every control in the full preview.", FontSize = 12, Opacity = .75, TextWrapping = TextWrapping.Wrap };
    readonly Microsoft.UI.Dispatching.DispatcherQueueTimer timer;
    IReadOnlyList<Game> games;
    public Game SelectedGame=>selected;
    Game selected = new() { Id = "overlay-preview-control", Name = "Control Resonant", AppId = "3669870" };
    OverlayPreview.Screenshot shot = new(Path.Combine(AppContext.BaseDirectory,"Assets","OverlayScene.webp"), "Control Resonant · gameplay", .27f);
    CancellationTokenSource? loading;
    Process? fullPreview;
    Color accent = Color.FromArgb(255,213,137,117);
    readonly string? preferencesPath;
    Color sampledAccent = Color.FromArgb(255,213,137,117);
    Color sceneAccent = Color.FromArgb(255,213,137,117);
    string stamp = "";
    bool active;

    public OverlayPreviewView(EngineForgeService? engine, IReadOnlyList<Game> library, Game? initialGame = null, string? preferencesPath = null)
    {
        this.preferencesPath=preferencesPath;this.engine=engine; games=library; Spacing=12; MaxWidth=440; HorizontalAlignment=HorizontalAlignment.Stretch;VerticalAlignment=VerticalAlignment.Center;
        // Frame the unobstructed right side of the existing gameplay photograph.
        // This small illustration has no telemetry, live controls or GPU renderer.
        scene.Clip=new RectangleGeometry { Rect=new global::Windows.Foundation.Rect(0,0,960,540) };
        scene.Children.Add(image);scene.Children.Add(diagram);
        frame=new Button { Padding=new Thickness(0),
            HorizontalAlignment=HorizontalAlignment.Stretch,HorizontalContentAlignment=HorizontalAlignment.Stretch,CornerRadius=new CornerRadius(12) };
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(frame,"Open full overlay preview");
        if (engine is null)
            Children.Add(new Viewbox { Child = scene, Stretch = Stretch.Uniform });
        else
        {
            frame.Content = new Viewbox { Child = scene, Stretch = Stretch.Uniform };
            ToolTipService.SetToolTip(frame, "Open full preview");
            Children.Add(frame);
        }
        Children.Add(search);
        var openContent=new StackPanel { Orientation=Orientation.Horizontal,Spacing=8,HorizontalAlignment=HorizontalAlignment.Center };
        openContent.Children.Add(new SymbolIcon(Symbol.FullScreen));openContent.Children.Add(new TextBlock {Text="Open full preview"});
        var open=new Button {Content=openContent,HorizontalAlignment=HorizontalAlignment.Stretch,HorizontalContentAlignment=HorizontalAlignment.Center};
        Children.Add(open);Children.Add(status);
        frame.IsEnabled = engine is not null;
        open.Visibility = status.Visibility = engine is null ? Visibility.Collapsed : Visibility.Visible;
        search.Text=selected.Name;SetPhoto(shot);Draw();
        search.TextChanged+=(_,e)=>{if(e.Reason==AutoSuggestionBoxTextChangeReason.UserInput)search.ItemsSource=Matches().Take(30).ToArray();};
        search.GotFocus+=(_,_)=>search.ItemsSource=Matches().Take(30).ToArray();
        search.SuggestionChosen+=async(_,e)=>{if(e.SelectedItem is Game game)await ChooseAsync(game);};
        search.QuerySubmitted+=async(_,e)=>{if(e.ChosenSuggestion is not Game && Matches().FirstOrDefault() is { } game)await ChooseAsync(game);};
        async Task OpenAsync(){if(engine is null)return;try{OverlayPreview.Close(fullPreview);fullPreview=await OverlayPreview.StartAsync(engine.EngineRoot,selected,shot,games,sceneAccent,preferencesPath);}catch(Exception error)when(error is IOException or InvalidOperationException or System.ComponentModel.Win32Exception){status.Text=error.Message;}}
        frame.Click+=async(_,_)=>await OpenAsync();open.Click+=async(_,_)=>await OpenAsync();
        frame.RegisterPropertyChangedCallback(Control.IsEnabledProperty,(_,_)=>open.IsEnabled=frame.IsEnabled);
        timer=DispatcherQueue.CreateTimer();timer.Interval=TimeSpan.FromMilliseconds(400);
        timer.Tick+=(_,_)=>{var next=PreferenceStamp();if(next!=stamp){stamp=next;Draw();}};
        Loaded+=async(_,_)=>{
            active=true;timer.Start();
            if(App.Main is { } shell){games=shell.Games;shell.GamesChanged+=LibraryChanged;}
            Draw();
            if(initialGame is not null){var game=initialGame;initialGame=null;await ChooseAsync(game);}
            else await SampleSceneAsync(shot, CancellationToken.None);
        };
        Unloaded+=(_,_)=>{active=false;timer.Stop();loading?.Cancel();if(App.Main is { } shell)shell.GamesChanged-=LibraryChanged;OverlayPreview.Close(fullPreview);fullPreview=null;};
    }
    IEnumerable<Game> Matches()=>games.OrderBy(g=>g.Name).Where(g=>g.Name.Contains(search.Text,StringComparison.CurrentCultureIgnoreCase));
    void LibraryChanged(){if(App.Main is { } shell)games=shell.Games;}
    string PreferenceStamp()
    {
        var path=preferencesPath??GlassAppearance.FilePath;
        return File.Exists(path)?File.GetLastWriteTimeUtc(path).Ticks.ToString():"default";
    }
    public void RefreshAppearance(){stamp=PreferenceStamp();Draw();}
    async Task ChooseAsync(Game game)
    {
        loading?.Cancel();loading?.Dispose();loading=new();var request=loading;search.Text=game.Name;status.Text="Loading "+game.Name+"…";
        bool Current()=>ReferenceEquals(loading,request)&&!request.IsCancellationRequested&&active;
        frame.IsEnabled=false;
        // The local palette must not wait behind a store screenshot download.
        // Keep the previous scene until the matching photo is ready.
        async Task<OverlayPreview.Screenshot?> PhotoAsync(CancellationToken cancel)
        {
            try{return (await OverlayPreview.ScreenshotsAsync(game,ForgeSettings.Load().OnlineArt,cancel)).FirstOrDefault();}
            catch(OperationCanceledException){return null;}
            catch(Exception error)when(error is IOException or HttpRequestException or System.Text.Json.JsonException or UnauthorizedAccessException){return null;}
        }
        var photo=PhotoAsync(request.Token);
        try {
            var palette=await OverlayAccent.ForGameAsync(game);
            if(!Current())return;
            accent=palette.Color;Draw();
            var found=await photo;
            if(!Current())return;
            if(found is null){accent=sceneAccent;Draw();status.Text="No 1440p or 4K screenshot available · showing "+selected.Name;return;}
            selected=game;shot=found;sampledAccent=sceneAccent=accent;SetPhoto(shot);Draw();
            await SampleSceneAsync(found,request.Token);
            if(Current())status.Text="Explore every control in the full preview.";
        }
        catch(OperationCanceledException){}
        catch(Exception error)when(error is IOException or HttpRequestException or System.Text.Json.JsonException or UnauthorizedAccessException){if(Current()){accent=sceneAccent;Draw();status.Text="Screenshot unavailable · showing the previous scene";}}
        finally{if(Current())frame.IsEnabled=true;}
    }
    async Task SampleSceneAsync(OverlayPreview.Screenshot photo, CancellationToken cancel)
    {
        try
        {
            var color=await ArtAccent.SignatureColorAsync(await File.ReadAllBytesAsync(photo.Path,cancel));
            if(!active||cancel.IsCancellationRequested||shot!=photo||color is not { } sampled)return;
            sampledAccent=sampled;Draw();
        }
        catch(Exception error) when(error is IOException or UnauthorizedAccessException or OperationCanceledException
            or ArgumentException or System.Runtime.InteropServices.COMException) {}
    }
    void SetPhoto(OverlayPreview.Screenshot photo)
    {
        image.Source=new BitmapImage(new Uri(photo.Path)){DecodePixelWidth=960};
        var zoom=photo.Crop>0?1/(1-photo.Crop):1;
        image.Width=960*zoom;image.Height=540*zoom;
        Canvas.SetLeft(image,960-image.Width);Canvas.SetTop(image,(540-image.Height)/2);
    }
    void Draw()
    {
        var appearance=GlassAppearance.Load(preferencesPath);var light=appearance.BaseTheme=="light";
        var clear=appearance.BaseTheme=="clear";diagram.Children.Clear();
        var accent = appearance.AccentMode == "theme" ? (light ? Color.FromArgb(255,82,82,82) : Color.FromArgb(255,180,180,180)) : appearance.AccentMode == "adaptive" ? sampledAccent : this.accent;
        if(appearance.AccentMode=="custom" && appearance.AccentColor.Length==7){var rgb=Convert.ToUInt32(appearance.AccentColor[1..],16);accent=Color.FromArgb(255,(byte)(rgb>>16),(byte)(rgb>>8),(byte)rgb);}
        var neutral=light?Color.FromArgb(238,235,235,235):clear?Color.FromArgb(112,225,225,225):Color.FromArgb(225,40,40,40);
        if(appearance.AccentEnabled && appearance.AccentMode!="theme")neutral=Mix(neutral,accent,appearance.Tint/100.0);
        var ink=light?Color.FromArgb(255,59,59,59):Color.FromArgb(255,246,246,246);
        void Shape(double x,double y,double w,double h,Color color,double radius=8){var shape=new Border {Width=w,Height=h,Background=new SolidColorBrush(color),CornerRadius=new CornerRadius(radius)};Canvas.SetLeft(shape,x);Canvas.SetTop(shape,y);diagram.Children.Add(shape);}
        void Panel(double x,double y,double w,double h){Shape(x,y+5,w,h,Color.FromArgb(35,0,0,0),14);Shape(x,y,w,h,neutral,14);}
        var card=Color.FromArgb(light?(byte)110:(byte)40,255,255,255);
        var line=Color.FromArgb(light?(byte)100:(byte)180,ink.R,ink.G,ink.B);
        if(appearance.Layout=="floating") {
            var x=appearance.SidePanelSide=="right"?675:40;
            Panel(x,40,245,460);Shape(x+20,62,88,6,accent,3);
            for(var row=0;row<3;row++){Shape(x+18,94+row*120,209,100,card);Shape(x+32,109+row*120,65,5,line,3);Shape(x+32,134+row*120,180,15,card,5);Shape(x+32,163+row*120,110,3,accent,2);}
        } else if(appearance.Layout=="centered") {
            Panel(190,85,580,370);Shape(214,110,90,6,accent,3);
            for(var row=0;row<5;row++)Shape(214,160+row*43,105,7,row==0?accent:line,3);
            Shape(342,144,402,112,card);Shape(359,161,82,5,line,3);Shape(359,186,182,35,card);
            for(var col=0;col<2;col++){Shape(342+col*210,274,192,150,card);Shape(359+col*210,293,74,5,line,3);Shape(359+col*210,330,155,4,accent,2);Shape(359+col*210,365,155,4,line,2);}
        } else {
            var y=appearance.BarPosition=="top"?20:366;
            Panel(20,y,920,154);Shape(42,y+19,88,6,accent,3);
            for(var col=0;col<2;col++){Shape(40+col*453,y+44,433,90,card);Shape(56+col*453,y+61,80,5,line,3);Shape(56+col*453,y+86,398,22,card,5);Shape(56+col*453,y+86,128,22,Color.FromArgb(100,accent.R,accent.G,accent.B),5);}
        }
    }
    static Color Mix(Color a,Color b,double amount)=>Color.FromArgb(a.A,(byte)(a.R+(b.R-a.R)*amount),(byte)(a.G+(b.G-a.G)*amount),(byte)(a.B+(b.B-a.B)*amount));
}

/// <summary>Native swatches with the overlay's Theme / Surface Tint hierarchy.</summary>
sealed class OverlayThemePicker : UserControl
{
    public int SelectedIndex {get;private set;}
    public event EventHandler? SelectionChanged;
    public OverlayThemePicker(string theme, string title = "Surface", string[]? keys = null, string[]? labels = null)
    {
        var root=new StackPanel {Spacing=8};root.Children.Add(new TextBlock {Text=title});
        var choices=new Grid {ColumnSpacing=8};var group="overlay-theme-"+Guid.NewGuid();
        keys ??= ["light","clear","dark"]; labels ??= ["Light","Clear","Dark"];

        SelectedIndex=Math.Max(0,Array.IndexOf(keys,theme));
        for(var i=0;i<keys.Length;i++){
            choices.ColumnDefinitions.Add(new());var body=new StackPanel {Spacing=8,HorizontalAlignment=HorizontalAlignment.Center};
            var color = keys[i] switch
            {
                "light" => Color.FromArgb(255,234,234,234),
                "dark" => Color.FromArgb(255,48,48,48),
                "night" => Color.FromArgb(255,12,12,12),
                _ => Color.FromArgb(72,225,225,225),
            };
            var ink = new SolidColorBrush(keys[i] == "light" ? Color.FromArgb(90,25,26,25) : Color.FromArgb(110,255,255,255));
            var lines = new StackPanel { Spacing=4, Width=28, VerticalAlignment=VerticalAlignment.Center };
            lines.Children.Add(new Border { Height=4, CornerRadius=new CornerRadius(2), Background=ink });
            lines.Children.Add(new Border { Width=17, Height=4, CornerRadius=new CornerRadius(2), Background=ink, HorizontalAlignment=HorizontalAlignment.Left });
            body.Children.Add(new Border { Width=48, Height=32, CornerRadius=new CornerRadius(7), Background=new SolidColorBrush(color),
                BorderBrush=new SolidColorBrush(Color.FromArgb(70,128,128,128)), BorderThickness=new Thickness(1), Child=lines });
            body.Children.Add(new TextBlock {Text=keys[i]=="system"?"System":labels[i],FontSize=14,HorizontalAlignment=HorizontalAlignment.Center});
            var button=new RadioButton {Content=body,GroupName=group,IsChecked=i==SelectedIndex,Style=Prefs.GetStyle("ForgeSegmentStyle"),Padding=new Thickness(12),HorizontalAlignment=HorizontalAlignment.Stretch};
            Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(button,labels[i]);var index=i;
            button.Checked+=(_,_)=>{SelectedIndex=index;SelectionChanged?.Invoke(this,EventArgs.Empty);};Grid.SetColumn(button,i);choices.Children.Add(button);
        }
        root.Children.Add(choices);Content=root;
    }
}
